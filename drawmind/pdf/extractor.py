"""PDF text extraction with bounding boxes."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from drawmind.config import MIN_TEXT_COUNT_FOR_NATIVE
from drawmind.pdf import backend

logger = logging.getLogger(__name__)


def _has_engineering_content(texts: list[dict]) -> bool:
    """Check if extracted text contains recognizable engineering annotations.

    Vector PDFs with custom fonts may extract text but yield mostly garbage
    (replacement chars \ufffd) rather than usable engineering annotations.
    """
    if not texts:
        return False

    engineering_patterns = [
        r"M\d+",  # Thread: M10, M8
        r"[\u2300\u00d8]\s*\d",  # Diameter: Ø10, ⌀8
        r"\b(?:THRU|DEPTH|DEEP|CBORE|CSINK)\b",
        r"\d+\s*[xX\u00d7]\s",  # Multiplier: 4x, 6X
        r"[A-Z]\d{1,2}\s*/\s*[a-z]\d",  # Fit: H7/g6
    ]

    total_chars = sum(len(t["text"]) for t in texts)
    replacement_chars = sum(t["text"].count("\ufffd") for t in texts)

    # If >30% of characters are replacement chars, text is corrupted
    if total_chars > 0 and replacement_chars / total_chars > 0.3:
        return False

    combined = " ".join(t["text"] for t in texts)
    for pat in engineering_patterns:
        if re.search(pat, combined, re.IGNORECASE):
            return True

    return False


def extract_all_text(pdf_path: str | Path, report: dict | None = None) -> list[dict]:
    """Extract all text elements with bounding boxes from a PDF.

    Tries native text extraction first. Falls back to OCR when:
    - Native extraction yields too few text elements (scanned PDF)
    - Native text is corrupted (custom fonts → replacement characters)
    - Native text has no recognizable engineering annotations

    Args:
        pdf_path: Path to the PDF file
        report: Optional dict filled with ``ocr_pages`` (pages OCR was tried
            on) and ``ocr_errors`` (one message per page where it crashed)

    Returns:
        List of dicts with keys: text, bbox, font, size, page, source
    """
    if report is None:
        report = {}
    report.update(ocr_pages=0, ocr_errors=[])
    all_texts = []

    with backend.open_document(pdf_path) as doc:
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_texts = _extract_page_native(page, page_num)

            needs_ocr = False
            if len(page_texts) < MIN_TEXT_COUNT_FOR_NATIVE:
                needs_ocr = True
            elif not _has_engineering_content(page_texts):
                # Native text exists but is corrupted or has no engineering content
                needs_ocr = True

            if needs_ocr and _tesseract_available():
                report["ocr_pages"] += 1
                try:
                    ocr_texts = _extract_page_ocr(page, page_num)
                except Exception as e:
                    logger.warning(f"OCR failed on page {page_num + 1}: {e}")
                    report["ocr_errors"].append(f"page {page_num + 1}: {e}")
                    ocr_texts = []
                if _has_engineering_content(ocr_texts):
                    # OCR found engineering content — merge with native
                    page_texts = _merge_text_sources(page_texts, ocr_texts)
                elif len(ocr_texts) > len(page_texts):
                    page_texts = ocr_texts

            all_texts.extend(page_texts)

    return all_texts


def _merge_text_sources(native: list[dict], ocr: list[dict]) -> list[dict]:
    """Merge native and OCR text, preferring OCR for engineering annotations.

    Keeps native text that doesn't overlap with OCR, and adds all OCR text.
    This handles the case where native text has some valid content (title block)
    but engineering annotations are only readable via OCR.
    """
    # Simple strategy: use OCR as primary, add non-overlapping native text
    merged = list(ocr)

    for n_item in native:
        n_cx = (n_item["bbox"]["x0"] + n_item["bbox"]["x1"]) / 2
        n_cy = (n_item["bbox"]["y0"] + n_item["bbox"]["y1"]) / 2
        has_overlap = False

        for o_item in ocr:
            if n_item["page"] != o_item["page"]:
                continue
            o_cx = (o_item["bbox"]["x0"] + o_item["bbox"]["x1"]) / 2
            o_cy = (o_item["bbox"]["y0"] + o_item["bbox"]["y1"]) / 2
            dist = ((n_cx - o_cx) ** 2 + (n_cy - o_cy) ** 2) ** 0.5
            if dist < 20:  # Close enough to be the same text
                has_overlap = True
                break

        if not has_overlap and "\ufffd" not in n_item["text"]:
            merged.append(n_item)

    return merged


def _extract_page_native(page, page_num: int) -> list[dict]:
    """Extract text natively from a PDF page."""
    return [
        {
            "text": line["text"],
            "bbox": {
                "x0": line["x0"],
                "y0": line["y0"],
                "x1": line["x1"],
                "y1": line["y1"],
            },
            "font": "",
            "size": 0,
            "page": page_num,
            "source": "native",
        }
        for line in backend.text_lines(page)
    ]


def _extract_page_ocr(page, page_num: int) -> list[dict]:
    """Extract text from a page using Tesseract OCR."""
    return _extract_page_tesseract(page, page_num)


_TESSERACT_OK: bool | None = None


def _tesseract_available() -> bool:
    """Check once whether the Tesseract binary can be reached."""
    global _TESSERACT_OK

    if _TESSERACT_OK is None:
        try:
            import pytesseract

            pytesseract.get_tesseract_version()
            _TESSERACT_OK = True
        except Exception:
            _TESSERACT_OK = False
            logger.warning(
                "Tesseract is not available — scanned or vector-only drawings "
                "will yield no text. Install tesseract-ocr to enable OCR."
            )

    return _TESSERACT_OK


OCR_WORD_GAP_RATIO = 1.2


def _group_ocr_words(words: list[dict]) -> list[dict]:
    """Join OCR words that belong to the same callout."""
    groups = []

    for key in dict.fromkeys(w["line"] for w in words):
        line = sorted((w for w in words if w["line"] == key), key=lambda w: w["x0"])
        current = [line[0]]

        for word in line[1:]:
            previous = current[-1]
            height = max(previous["y1"] - previous["y0"], word["y1"] - word["y0"], 1.0)
            if word["x0"] - previous["x1"] > height * OCR_WORD_GAP_RATIO:
                groups.append(_merge_ocr_words(current))
                current = []
            current.append(word)

        groups.append(_merge_ocr_words(current))

    return groups


def _merge_ocr_words(words: list[dict]) -> dict:
    return {
        "text": " ".join(w["text"] for w in words),
        "bbox": {
            "x0": min(w["x0"] for w in words),
            "y0": min(w["y0"] for w in words),
            "x1": max(w["x1"] for w in words),
            "y1": max(w["y1"] for w in words),
        },
        "font": "",
        "size": 0,
        "source": "ocr_tesseract",
        "confidence": min(w["confidence"] for w in words),
    }


def _extract_page_tesseract(page, page_num: int) -> list[dict]:
    """Extract text from a page using Tesseract OCR (sparse text mode).

    Returns empty list if Tesseract is not available; raises if OCR itself
    fails, so the caller can report it instead of mistaking it for a blank page.
    """
    if not _tesseract_available():
        return []

    import io

    import pytesseract
    from PIL import Image

    from drawmind.config import OCR_DPI, OCR_CONFIDENCE_THRESHOLD

    img = Image.open(io.BytesIO(backend.render_png(page, dpi=OCR_DPI)))

    data = pytesseract.image_to_data(
        img,
        output_type=pytesseract.Output.DICT,
        config="--psm 11 --oem 3",
    )

    # Derive the scale from the raster actually produced rather than from
    # the requested DPI — renderers round the pixel count.
    page_width, _ = backend.page_size(page)
    scale = page_width / img.width

    words = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        conf = int(data["conf"][i])
        if not text or conf <= OCR_CONFIDENCE_THRESHOLD:
            continue
        words.append(
            {
                "text": text,
                "line": (data["block_num"][i], data["par_num"][i], data["line_num"][i]),
                "x0": data["left"][i] * scale,
                "y0": data["top"][i] * scale,
                "x1": (data["left"][i] + data["width"][i]) * scale,
                "y1": (data["top"][i] + data["height"][i]) * scale,
                "confidence": conf / 100.0,
            }
        )

    return [dict(group, page=page_num) for group in _group_ocr_words(words)]


def get_page_as_image(pdf_path: str | Path, page_num: int = 0, dpi: int = 300) -> bytes:
    """Render a PDF page as a PNG image (for vision LLM).

    Returns:
        PNG image bytes
    """
    with backend.open_document(pdf_path) as doc:
        return backend.render_png(doc[page_num], dpi=dpi)


def detect_unit_system(
    pdf_path: str | Path, use_llm: bool = False, report: dict | None = None
) -> str:
    """Detect the unit system used in a technical drawing PDF.

    Checks explicit unit declarations first, then uses heuristics on
    dimension values (e.g., Ø.438 patterns indicate inches).

    Args:
        pdf_path: Path to the drawing.
        use_llm: Allow a vision model as the last resort. This renders the
            page and sends it to the configured provider.
        report: Optional dict that receives ``source`` (``declaration``,
            ``thread_spec``, ``dimension_format``, ``value_heuristic``,
            ``vision`` or ``default``) and ``error`` when the vision check
            was attempted and failed, so a metric default is not mistaken for
            a detected one.

    Returns:
        "inch" or "metric"
    """
    if report is None:
        report = {}

    with backend.open_document(pdf_path) as doc:
        full_text = "".join(backend.page_text(page) for page in doc)

    # 1. Explicit metric declarations (strongest signal)
    metric_patterns = [
        r"UNITS?\s*:\s*(?:MM|MILLIMETERS?)",
        r"ALL\s+DIMENSIONS\s+(?:IN\s+)?(?:MM|MILLIMETERS?)",
        r"DIMENSIONS\s+(?:ARE\s+)?IN\s+(?:MM|MILLIMETERS?)",
        r"MILLIMETERS?\s+UNLESS",
    ]
    for pat_str in metric_patterns:
        if re.search(pat_str, full_text, re.IGNORECASE):
            report["source"] = "declaration"
            return "metric"

    # 2. Explicit inch declarations
    inch_patterns = [
        r"UNITS?\s*:\s*INCH",
        r"DIMENSIONING\s+IN\s+INCH",
        r"ALL\s+DIMENSIONS\s+IN\s+INCH",
        r"DIMENSIONS\s+ARE\s+IN\s+INCH",
        r"INCH(?:ES)?\s+UNLESS",
    ]
    for pat_str in inch_patterns:
        if re.search(pat_str, full_text, re.IGNORECASE):
            report["source"] = "declaration"
            return "inch"

    # UNC/UNEF thread specs are exclusively imperial
    unc_pattern = re.compile(r"\d+/\d+-\d+\s*(?:UNC|UNF|UNEF)", re.IGNORECASE)
    if unc_pattern.search(full_text):
        report["source"] = "thread_spec"
        return "inch"

    # 3. Implicit inch detection via dimension value patterns
    # Inch drawings commonly use .XXX format (e.g., Ø.438, .250 THRU)
    # Only count values preceded by a diameter symbol or at start of dimension —
    # NOT values inside tolerances (+.025/-.010)
    inch_dim_pattern = re.compile(
        r"(?:^|[\u00d8\u2300\u2205\s])\.(\d{2,4})\b"  # .438, .250 (preceded by Ø or whitespace)
    )
    inch_vals = []
    for m in inch_dim_pattern.finditer(full_text):
        # Check if preceded by + or - (tolerance, not dimension)
        prefix_start = max(0, m.start() - 3)
        prefix = full_text[prefix_start : m.start()]
        if not re.search(r"[+\-]", prefix):
            inch_vals.append(m.group(1))

    # If we find >=2 decimal-inch style dimensions, classify as inch
    if len(inch_vals) >= 2:
        report["source"] = "dimension_format"
        return "inch"

    # 4. Heuristic: if most dimension values are small (< 2.0) and none > 25,
    # it's likely an inch drawing where the text was poorly extracted
    dim_pattern = re.compile(r"(\d{1,3}\.?\d{0,4})")
    all_dims = []
    for m in dim_pattern.finditer(full_text):
        try:
            v = float(m.group(1))
            if 0.05 < v < 200:  # Filter out noise
                all_dims.append(v)
        except ValueError:
            pass
    if len(all_dims) >= 3:
        small_count = sum(1 for d in all_dims if d < 2.0)
        large_count = sum(1 for d in all_dims if d > 25.0)
        if small_count > len(all_dims) * 0.6 and large_count == 0:
            report["source"] = "value_heuristic"
            return "inch"

    # 5. Fallback: use Vision LLM to detect unit system from drawing image
    if use_llm:
        try:
            unit = _detect_unit_system_vision(pdf_path)
            if unit:
                report["source"] = "vision"
                return unit
        except Exception as e:
            logger.warning(f"Vision unit detection failed: {e}")
            report["error"] = str(e)

    report["source"] = "default"
    return "metric"


def _detect_unit_system_vision(pdf_path: str | Path) -> str | None:
    """Use Vision LLM to detect unit system from drawing title block."""
    from drawmind.llm.client import get_llm_client

    client = get_llm_client()
    if not client.available:
        return None

    img_bytes = get_page_as_image(pdf_path, page_num=0, dpi=100)
    result = client.complete_json(
        "Look at this technical drawing. What unit system is used? "
        "Check the title block, notes, or dimension format. "
        "Inch drawings use values like .250, .438, 1/4-20 UNC. "
        "Metric drawings use values like 10.0, M8, Ø20. "
        'Return JSON: {"unit_system": "inch" or "metric", "evidence": "brief reason"}',
        images=[img_bytes],
    )

    if isinstance(result, dict):
        unit = str(result.get("unit_system") or "").lower()
        if unit in ("inch", "metric"):
            logger.info(f"Vision LLM detected unit system: {unit} ({result.get('evidence', '')})")
            return unit
    logger.warning(f"Vision unit detection returned no usable answer: {result!r:.120}")
    return None


def get_page_dimensions(pdf_path: str | Path, page_num: int = 0) -> tuple[float, float]:
    """Get page dimensions in points.

    Returns:
        (width, height) in points
    """
    with backend.open_document(pdf_path) as doc:
        return backend.page_size(doc[page_num])
