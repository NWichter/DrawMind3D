"""Low-level PDF access via PDFium.

Everything that touches a PDF engine lives here, so swapping engines means
changing one module. Coordinates are returned top-down in unrotated page
space, which is what the annotation and leader-line code expects.
"""

from __future__ import annotations

import ctypes
import io
import threading
from contextlib import contextmanager
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

# Stroke widths above this are frame lines and hatching, not leader lines.
MAX_STROKE_WIDTH = 3.0


# PDFium is not thread-safe, not even across different documents, and its
# ctypes calls release the GIL. The web app runs analyses in worker threads,
# so every document is used under this lock from open to close.
_PDFIUM_LOCK = threading.RLock()


@contextmanager
def open_document(pdf_path: str | Path):
    """Open a PDF, yielding the document and closing it afterwards.

    Pages and text pages taken from the document must not outlive the block.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    with _PDFIUM_LOCK:
        doc = pdfium.PdfDocument(str(pdf_path))
        try:
            yield doc
        finally:
            doc.close()


def page_height(page) -> float:
    """Unrotated page height, the reference for the top-down y axis."""
    return page.get_mediabox()[3]


def page_size(page) -> tuple[float, float]:
    """Displayed page size in points, with rotation applied."""
    return page.get_size()


def to_display(page, x: float, y: float) -> tuple[float, float]:
    """Map an unrotated top-down point into displayed page space.

    Text and path coordinates are stored unrotated, while rasterised output
    and therefore anything derived from it — OCR boxes, vision LLM regions —
    is in displayed space. Landscape CAD drawings are usually stored rotated,
    so the two disagree unless points are mapped across.
    """
    # The rendered page shows the crop box, which may be smaller than the media
    # box or not start at the origin; shift into it before rotating. PDFium
    # clips a crop box that overhangs the media box, so do the same.
    c_left, c_bottom, c_right, c_top = page.get_cropbox()
    m_left, m_bottom, m_right, m_top = page.get_mediabox()
    left, bottom = max(c_left, m_left), max(c_bottom, m_bottom)
    right, top = min(c_right, m_right), min(c_top, m_top)
    x -= left
    y -= page_height(page) - top

    rotation = page.get_rotation() % 360
    if rotation == 0:
        return x, y

    width, height = right - left, top - bottom

    if rotation == 90:
        return height - y, x
    if rotation == 180:
        return width - x, height - y
    return y, width - x


def to_display_box(page, box: dict) -> dict:
    """Map a top-down bounding box into displayed page space."""
    corners = [
        to_display(page, box["x0"], box["y0"]),
        to_display(page, box["x1"], box["y1"]),
    ]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)}


def page_text(page) -> str:
    """Full page text in reading order."""
    textpage = page.get_textpage()
    try:
        return textpage.get_text_range()
    finally:
        textpage.close()


# Safety net for runs PDFium reports without any break: a jump wider than
# this multiple of the character size is a move to a different callout, not
# word spacing. Kept generous so normal spacing never splits a line.
LINE_BREAK_GAP_RATIO = 2.5


def text_lines(page) -> list[dict]:
    """Extract text lines with bounding boxes.

    PDFium marks line breaks with CRLF, but some drawings position their
    whole text with explicit offsets inside a single text object, and then no
    break is reported at all. Runs are therefore also split wherever
    consecutive characters are too far apart to belong to the same callout.

    Coordinates are returned in displayed page space so that they line up
    with OCR boxes and anything else derived from the rendered page.

    Returns:
        List of dicts with keys: text, x0, y0, x1, y1
    """
    height = page_height(page)
    textpage = page.get_textpage()
    try:
        count = textpage.count_chars()
        if count == 0:
            return []

        lines = []
        chars = []

        for i in range(count):
            # Read by character index: get_text_range() may insert or drop
            # characters, which would pair text with the wrong boxes.
            char = _char_at(textpage, i)
            if char in ("\r", "\n"):
                _flush_line(chars, lines, height)
                continue

            box = _charbox(textpage, i)
            if box is None:
                # Spaces collapse to a point; keep the glyph, skip the box.
                chars.append((char, None))
                continue

            if chars and _is_detached(chars, box):
                _flush_line(chars, lines, height)

            chars.append((char, box))

        _flush_line(chars, lines, height)
        return [{**line, **to_display_box(page, line)} for line in lines]
    finally:
        textpage.close()


def _char_at(textpage, index: int) -> str:
    code = pdfium_c.FPDFText_GetUnicode(textpage.raw, index)
    return chr(code) if code else ""


def _charbox(textpage, index: int) -> tuple[float, float, float, float] | None:
    try:
        left, bottom, right, top = textpage.get_charbox(index)
    except Exception:
        return None
    if left == right or bottom == top:
        return None
    return left, bottom, right, top


def _is_detached(chars: list, box: tuple[float, float, float, float]) -> bool:
    """Is this character too far from the previous one to continue the line?"""
    previous = next((b for _, b in reversed(chars) if b is not None), None)
    if previous is None:
        return False

    gap_x = max(previous[0] - box[2], box[0] - previous[2], 0.0)
    gap_y = max(previous[1] - box[3], box[1] - previous[3], 0.0)
    gap = (gap_x**2 + gap_y**2) ** 0.5

    size = max(
        box[2] - box[0],
        box[3] - box[1],
        previous[2] - previous[0],
        previous[3] - previous[1],
    )
    return gap > size * LINE_BREAK_GAP_RATIO


def _flush_line(chars: list, lines: list, height: float) -> None:
    """Turn the collected characters into a line and reset the buffer."""
    if not chars:
        return

    content = "".join(c for c, _ in chars)
    # PDFium hands out UTF-16 code units: rejoin surrogate pairs, and turn a
    # stray half into U+FFFD rather than text that cannot be written as UTF-8.
    content = content.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace").strip()
    boxes = [b for _, b in chars if b is not None]
    chars.clear()

    if not content or not boxes:
        return

    lines.append(
        {
            "text": content,
            "x0": min(b[0] for b in boxes),
            "y0": height - max(b[3] for b in boxes),
            "x1": max(b[2] for b in boxes),
            "y1": height - min(b[1] for b in boxes),
        }
    )


def render_png(page, dpi: int = 300) -> bytes:
    """Render a page to PNG bytes at the given resolution."""
    bitmap = page.render(scale=dpi / 72.0)
    image = bitmap.to_pil()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def line_segments(page) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Extract straight stroked segments from the page's vector artwork.

    Path points are stored in the coordinate space of the object that holds
    them, so the transform of each enclosing form has to be applied before
    the points mean anything on the page.

    Returns:
        List of ((x0, y0), (x1, y1)) in displayed page coordinates
    """
    height = page_height(page)
    segments = []

    for obj in page.get_objects(max_depth=4):
        if obj.type != pdfium_c.FPDF_PAGEOBJ_PATH:
            continue
        if _stroke_width(obj) > MAX_STROKE_WIDTH:
            continue

        points = _path_points(obj, height)
        subpath_start = None

        for i, (kind, x, y, closes) in enumerate(points):
            if kind == pdfium_c.FPDF_SEGMENT_MOVETO:
                subpath_start = (x, y)
            elif kind == pdfium_c.FPDF_SEGMENT_LINETO and i > 0:
                _, px, py, _ = points[i - 1]
                segments.append(((px, py), (x, y)))

            # PDFium reports path closure as a flag, not as a segment.
            if closes and subpath_start is not None and (x, y) != subpath_start:
                segments.append(((x, y), subpath_start))

    return [(to_display(page, *start), to_display(page, *end)) for start, end in segments]


def _stroke_width(obj) -> float:
    width = ctypes.c_float()
    if not pdfium_c.FPDFPageObj_GetStrokeWidth(obj.raw, ctypes.byref(width)):
        return 0.0
    return width.value


def _object_matrices(obj) -> list:
    """Transforms from the object outwards, innermost first."""
    matrices = []
    current = obj
    while current is not None and hasattr(current, "get_matrix"):
        try:
            matrices.append(current.get_matrix())
        except Exception:
            break
        current = getattr(current, "parent", None)
    return matrices


def _path_points(obj, height: float) -> list[tuple[int, float, float, bool]]:
    """Path points as (type, x, y, closes_subpath) in top-down coordinates."""
    matrices = _object_matrices(obj)
    points = []

    for i in range(pdfium_c.FPDFPath_CountSegments(obj.raw)):
        segment = pdfium_c.FPDFPath_GetPathSegment(obj.raw, i)
        x = ctypes.c_float()
        y = ctypes.c_float()
        if not pdfium_c.FPDFPathSegment_GetPoint(segment, ctypes.byref(x), ctypes.byref(y)):
            continue

        px, py = x.value, y.value
        for m in matrices:
            px, py = m.a * px + m.c * py + m.e, m.b * px + m.d * py + m.f

        points.append(
            (
                pdfium_c.FPDFPathSegment_GetType(segment),
                px,
                height - py,
                bool(pdfium_c.FPDFPathSegment_GetClose(segment)),
            )
        )

    return points
