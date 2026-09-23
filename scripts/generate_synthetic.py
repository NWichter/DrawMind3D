"""Generate synthetic STEP + PDF test pairs with known ground truth.

Creates parametric parts with known holes/threads, generates matching
PDF drawings with dimension lines, leader lines, and title blocks.

The pairs it produces are committed under data/synthetic/; neither the
package nor the test suite imports this script. The drawings are written as
plain PDF by the small writer below, so no PDF library is needed:

    uv run python scripts/generate_synthetic.py [--count 5] [--out DIR]
"""

from __future__ import annotations

import io
import json
import math
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# OCP imports for STEP generation
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeCone
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.TopoDS import TopoDS_Shape

from PIL import Image, ImageDraw, ImageFont


def Point(x: float, y: float) -> tuple[float, float]:
    return (x, y)


def Rect(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
    return (x0, y0, x1, y1)


# Control-point factor for approximating a quarter circle with one Bezier curve.
_KAPPA = 0.5523


def _win_ansi(ch: str) -> bytes:
    try:
        return ch.encode("cp1252")
    except UnicodeEncodeError:
        return b"\xb7"


class _Page:
    """A single-page PDF in top-down page coordinates.

    Text uses the standard Helvetica font with WinAnsi encoding, which covers
    the diameter and degree signs. Symbols outside it, such as the counterbore
    and countersink signs, are written as a middle dot, as in the committed
    fixtures.
    """

    def __init__(self, width: float, height: float):
        self.width = width
        self.height = height
        self._ops: list[str] = []
        self._images: list[tuple[int, int, bytes]] = []

    def _y(self, y: float) -> float:
        return self.height - y

    def _stroke(self, color, width) -> str:
        r, g, b = color
        return f"{r:.3f} {g:.3f} {b:.3f} RG {width:.2f} w"

    def draw_line(self, p1, p2, color=(0, 0, 0), width=1.0):
        self._ops.append(
            f"{self._stroke(color, width)} {p1[0]:.2f} {self._y(p1[1]):.2f} m "
            f"{p2[0]:.2f} {self._y(p2[1]):.2f} l S"
        )

    def draw_rect(self, rect, color=(0, 0, 0), width=1.0):
        x0, y0, x1, y1 = rect
        self._ops.append(
            f"{self._stroke(color, width)} {x0:.2f} {self._y(y1):.2f} "
            f"{x1 - x0:.2f} {y1 - y0:.2f} re S"
        )

    def draw_circle(self, center, radius, color=(0, 0, 0), width=1.0):
        cx, cy = center[0], self._y(center[1])
        r, k = radius, radius * _KAPPA
        self._ops.append(
            f"{self._stroke(color, width)} {cx + r:.2f} {cy:.2f} m "
            f"{cx + r:.2f} {cy + k:.2f} {cx + k:.2f} {cy + r:.2f} {cx:.2f} {cy + r:.2f} c "
            f"{cx - k:.2f} {cy + r:.2f} {cx - r:.2f} {cy + k:.2f} {cx - r:.2f} {cy:.2f} c "
            f"{cx - r:.2f} {cy - k:.2f} {cx - k:.2f} {cy - r:.2f} {cx:.2f} {cy - r:.2f} c "
            f"{cx + k:.2f} {cy - r:.2f} {cx + r:.2f} {cy - k:.2f} {cx + r:.2f} {cy:.2f} c S"
        )

    def insert_text(self, point, text, fontsize=11, color=(0, 0, 0), fontname=None):
        """Place text with its baseline starting at ``point``."""
        encoded = b"".join(_win_ansi(ch) for ch in text)
        escaped = encoded.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
        r, g, b = color
        self._ops.append(
            f"BT /F1 {fontsize:.2f} Tf {r:.3f} {g:.3f} {b:.3f} rg "
            f"{point[0]:.2f} {self._y(point[1]):.2f} Td (" + escaped.decode("latin-1") + ") Tj ET"
        )

    def insert_image(self, rect, stream: bytes):
        """Place a PNG so that it fills ``rect``."""
        image = Image.open(io.BytesIO(stream)).convert("RGB")
        self._images.append((image.width, image.height, zlib.compress(image.tobytes())))
        x0, y0, x1, y1 = rect
        self._ops.append(
            f"q {x1 - x0:.2f} 0 0 {y1 - y0:.2f} {x0:.2f} {self._y(y1):.2f} cm "
            f"/Im{len(self._images)} Do Q"
        )

    def save(self, path) -> None:
        content = "\n".join(self._ops).encode("latin-1")
        image_refs = " ".join(f"/Im{i + 1} {6 + i} 0 R" for i in range(len(self._images)))
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.width} {self.height}] "
                f"/Resources << /Font << /F1 5 0 R >> /XObject << {image_refs} >> >> "
                f"/Contents 4 0 R >>"
            ).encode("ascii"),
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        ]
        for width, height, data in self._images:
            objects.append(
                b"<< /Type /XObject /Subtype /Image /Width %d /Height %d "
                b"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
                b"/Length %d >>\nstream\n%s\nendstream" % (width, height, len(data), data)
            )

        out = bytearray(b"%PDF-1.4\n")
        offsets = []
        for number, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
        xref_at = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
        for offset in offsets:
            out += b"%010d 00000 n \n" % offset
        out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
            len(objects) + 1,
            xref_at,
        )
        Path(path).write_bytes(bytes(out))


def _text_as_image(text: str, fontsize: int = 9) -> tuple[bytes, float, float]:
    """Render text as a rasterized PNG image (not extractable as text)."""
    # Pillow's built-in font has no diameter sign; matplotlib ships DejaVu Sans.
    from matplotlib import font_manager

    scale = 3
    font = ImageFont.truetype(font_manager.findfont("DejaVu Sans"), fontsize * scale)
    # Size the image to the rendered text so nothing is clipped at the edge.
    img_w = font.getlength(text) / scale + 8
    img_h = fontsize + 8

    image = Image.new("RGB", (round(img_w * scale), round(img_h * scale)), "white")
    ImageDraw.Draw(image).text((4 * scale, 2 * scale), text, fill="black", font=font)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue(), img_w, img_h


METRIC_THREADS = {
    "M3": {"major": 3.0, "pitch": 0.5, "drill": 2.5},
    "M4": {"major": 4.0, "pitch": 0.7, "drill": 3.3},
    "M5": {"major": 5.0, "pitch": 0.8, "drill": 4.2},
    "M6": {"major": 6.0, "pitch": 1.0, "drill": 5.0},
    "M8": {"major": 8.0, "pitch": 1.25, "drill": 6.8},
    "M10": {"major": 10.0, "pitch": 1.5, "drill": 8.5},
    "M12": {"major": 12.0, "pitch": 1.75, "drill": 10.2},
    "M16": {"major": 16.0, "pitch": 2.0, "drill": 14.0},
    "M20": {"major": 20.0, "pitch": 2.5, "drill": 17.5},
}


def generate_part(part_def: dict) -> tuple[TopoDS_Shape, list[dict]]:
    """Generate a 3D part with holes based on part definition."""
    w = part_def["width"]
    h = part_def["height"]
    d = part_def["depth"]

    # Build base shape from sub-shapes if defined, otherwise simple box
    if "sub_shapes" in part_def:
        shape = _build_compound_shape(part_def["sub_shapes"])
    else:
        shape = BRepPrimAPI_MakeBox(w, h, d).Shape()

    holes_info = []

    for hole in part_def["holes"]:
        hx, hy = hole["x"], hole["y"]
        diameter = hole["diameter"]
        depth = hole.get("depth", d)
        is_through = hole.get("through", depth >= d)

        actual_depth = d + 2 if is_through else depth
        axis = gp_Ax2(gp_Pnt(hx, hy, d + 1 if is_through else d), gp_Dir(0, 0, -1))
        cyl = BRepPrimAPI_MakeCylinder(axis, diameter / 2, actual_depth + 1).Shape()
        shape = BRepAlgoAPI_Cut(shape, cyl).Shape()

        # Counterbore: cut a larger cylinder on top
        if hole.get("counterbore"):
            cb = hole["counterbore"]
            cb_axis = gp_Ax2(gp_Pnt(hx, hy, d + 1), gp_Dir(0, 0, -1))
            cb_cyl = BRepPrimAPI_MakeCylinder(cb_axis, cb["diameter"] / 2, cb["depth"] + 1).Shape()
            shape = BRepAlgoAPI_Cut(shape, cb_cyl).Shape()

        # Countersink: cut a cone on top
        if hole.get("countersink"):
            cs = hole["countersink"]
            cs_d = cs.get("diameter", diameter * 2)
            cs_angle = cs.get("angle", 90)
            cs_depth = (cs_d - diameter) / 2 / math.tan(math.radians(cs_angle / 2))
            cs_axis = gp_Ax2(gp_Pnt(hx, hy, d + 0.01), gp_Dir(0, 0, -1))
            cone = BRepPrimAPI_MakeCone(cs_axis, cs_d / 2, diameter / 2, cs_depth).Shape()
            shape = BRepAlgoAPI_Cut(shape, cone).Shape()

        holes_info.append(
            {
                "x": hx,
                "y": hy,
                "diameter_mm": diameter,
                "depth_mm": d if is_through else depth,
                "is_through": is_through,
                "type": hole.get("type", "simple"),
                "thread": hole.get("thread"),
                "count": hole.get("count", 1),
                "annotation_text": hole.get("annotation_text", ""),
                "image_annotation": hole.get("image_annotation", False),
                "counterbore": hole.get("counterbore"),
                "countersink": hole.get("countersink"),
            }
        )

    return shape, holes_info


def _build_compound_shape(sub_shapes: list[dict]) -> TopoDS_Shape:
    """Build a compound shape from a list of box definitions (fused together)."""
    result = None
    for ss in sub_shapes:
        ox, oy, oz = ss.get("ox", 0), ss.get("oy", 0), ss.get("oz", 0)
        _ = gp_Ax2(gp_Pnt(ox, oy, oz), gp_Dir(0, 0, 1))  # noqa: F841
        box = BRepPrimAPI_MakeBox(
            gp_Pnt(ox, oy, oz), gp_Pnt(ox + ss["w"], oy + ss["h"], oz + ss["d"])
        ).Shape()
        if result is None:
            result = box
        else:
            result = BRepAlgoAPI_Fuse(result, box).Shape()
    return result


def export_step(shape: TopoDS_Shape, path: Path):
    """Export shape to STEP file."""
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    writer.Write(str(path))


def _draw_arrow(page, start, end, color=(0, 0, 0), width=0.5, head_size=4):
    """Draw a line with an arrowhead at the end."""
    page.draw_line(Point(*start), Point(*end), color=color, width=width)
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length < 0.1:
        return
    ux, uy = dx / length, dy / length
    # Perpendicular
    px, py = -uy, ux
    # Arrowhead
    ax = end[0] - ux * head_size
    ay = end[1] - uy * head_size
    page.draw_line(
        Point(end[0], end[1]),
        Point(ax + px * head_size * 0.4, ay + py * head_size * 0.4),
        color=color,
        width=width,
    )
    page.draw_line(
        Point(end[0], end[1]),
        Point(ax - px * head_size * 0.4, ay - py * head_size * 0.4),
        color=color,
        width=width,
    )


def _draw_dimension_line(page, p1, p2, offset, text, fontsize=8, color=(0, 0, 0)):
    """Draw a dimension line with extension lines and centered text."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1:
        return

    # Normal direction for offset
    nx, ny = -dy / length, dx / length
    # Offset points
    o1 = (p1[0] + nx * offset, p1[1] + ny * offset)
    o2 = (p2[0] + nx * offset, p2[1] + ny * offset)

    # Extension lines
    ext_extra = 3
    page.draw_line(
        Point(p1[0] + nx * (offset * 0.3), p1[1] + ny * (offset * 0.3)),
        Point(o1[0] + nx * ext_extra, o1[1] + ny * ext_extra),
        color=color,
        width=0.3,
    )
    page.draw_line(
        Point(p2[0] + nx * (offset * 0.3), p2[1] + ny * (offset * 0.3)),
        Point(o2[0] + nx * ext_extra, o2[1] + ny * ext_extra),
        color=color,
        width=0.3,
    )

    # Dimension line with arrows
    mid = ((o1[0] + o2[0]) / 2, (o1[1] + o2[1]) / 2)
    _draw_arrow(page, mid, o1, color=color, width=0.4)
    _draw_arrow(page, mid, o2, color=color, width=0.4)

    # Text
    text_x = mid[0] - len(text) * fontsize * 0.15
    text_y = mid[1] - 3
    page.insert_text(Point(text_x, text_y), text, fontsize=fontsize, color=color)


def generate_pdf_drawing(
    part_def: dict,
    holes_info: list[dict],
    pdf_path: Path,
    unit_system: str = "metric",
):
    """Generate a technical drawing PDF with top view, annotations, and title block."""
    page_w, page_h = 842, 595  # A4 landscape
    page = _Page(page_w, page_h)

    margin = 60
    title_block_h = 50

    # Drawing area
    draw_w = page_w - 2 * margin
    draw_h = page_h - 2 * margin - title_block_h

    # Draw border
    page.draw_rect(
        Rect(margin - 5, margin - 5, page_w - margin + 5, page_h - margin + 5),
        color=(0, 0, 0),
        width=1.5,
    )

    part_w = part_def["width"]
    part_h = part_def["height"]
    part_d = part_def["depth"]

    # Top view occupies left 60% of drawing area
    top_area_w = draw_w * 0.55
    top_area_h = draw_h * 0.7
    scale = min(top_area_w / part_w, top_area_h / part_h) * 0.75

    ox = margin + 30 + (top_area_w - part_w * scale) / 2
    oy = margin + 40 + (top_area_h - part_h * scale) / 2

    # Section label
    page.insert_text(Point(ox, oy - 12), "TOP VIEW", fontsize=7, color=(0.4, 0.4, 0.4))

    # Draw part outline
    rect = Rect(ox, oy, ox + part_w * scale, oy + part_h * scale)
    page.draw_rect(rect, color=(0, 0, 0), width=1.2)

    # Front view (below or to the right) — simple rectangle showing depth
    front_ox = ox
    front_oy = oy + part_h * scale + 40
    front_w = part_w * scale
    front_h = part_d * scale
    if front_oy + front_h < page_h - margin - title_block_h - 10:
        page.insert_text(
            Point(front_ox, front_oy - 8), "FRONT VIEW", fontsize=7, color=(0.4, 0.4, 0.4)
        )
        page.draw_rect(
            Rect(front_ox, front_oy, front_ox + front_w, front_oy + front_h),
            color=(0, 0, 0),
            width=1.0,
        )
        # Draw through-hole projections as dashed lines in front view
        for hole in holes_info:
            if hole["is_through"]:
                hfx = front_ox + hole["x"] * scale
                r = (hole["diameter_mm"] / 2) * scale
                # Hidden lines for hole
                _draw_dashed_line(page, (hfx - r, front_oy), (hfx - r, front_oy + front_h))
                _draw_dashed_line(page, (hfx + r, front_oy), (hfx + r, front_oy + front_h))

    # Side view (right of top view) — rectangle showing height x depth
    side_ox = ox + part_w * scale + 40
    side_oy = oy
    side_w = part_d * scale
    side_h = part_h * scale
    if side_ox + side_w < page_w - margin - 10:
        page.insert_text(
            Point(side_ox, side_oy - 8), "SIDE VIEW", fontsize=7, color=(0.4, 0.4, 0.4)
        )
        page.draw_rect(
            Rect(side_ox, side_oy, side_ox + side_w, side_oy + side_h),
            color=(0, 0, 0),
            width=1.0,
        )

    # Draw width dimension below top view
    _draw_dimension_line(
        page,
        (ox, oy + part_h * scale + 15),
        (ox + part_w * scale, oy + part_h * scale + 15),
        offset=0,
        text=f"{part_w:.0f}" if unit_system == "metric" else f"{part_w / 25.4:.3f}",
        fontsize=7,
    )

    # Draw holes in top view and annotations
    annotations = []
    ann_x_base = (
        ox + part_w * scale + (40 + side_w + 15 if side_ox + side_w < page_w - margin - 10 else 25)
    )
    ann_y = margin + 40
    font_size = 9

    for i, hole in enumerate(holes_info):
        hx = ox + hole["x"] * scale
        hy = oy + hole["y"] * scale
        r = (hole["diameter_mm"] / 2) * scale

        # Draw hole circle
        page.draw_circle(Point(hx, hy), max(r, 2), color=(0, 0, 0), width=0.8)

        # Center mark (crosshair)
        cm = max(r * 0.5, 3)
        page.draw_line(Point(hx - cm, hy), Point(hx + cm, hy), color=(0, 0, 0), width=0.3)
        page.draw_line(Point(hx, hy - cm), Point(hx, hy + cm), color=(0, 0, 0), width=0.3)

        # Build annotation text
        ann_text = hole.get("annotation_text", "")
        if not ann_text:
            ann_text = _build_annotation_text(hole, unit_system)

        # Place annotation with leader line
        ann_text_y = ann_y + i * 24
        ann_x = min(ann_x_base, page_w - margin - len(ann_text) * font_size * 0.5 - 5)

        # Leader line with a small horizontal segment at the end
        leader_end_x = ann_x - 5
        page.draw_line(
            Point(hx, hy),
            Point(leader_end_x, ann_text_y + font_size / 2),
            color=(0, 0, 0),
            width=0.5,
        )

        # Place text (image-based for some, text for others)
        if hole.get("image_annotation"):
            img_bytes, img_w, img_h = _text_as_image(ann_text, fontsize=font_size)
            img_rect = Rect(ann_x, ann_text_y, ann_x + img_w, ann_text_y + img_h)
            page.insert_image(img_rect, stream=img_bytes)
        else:
            page.insert_text(
                Point(ann_x, ann_text_y + font_size),
                ann_text,
                fontsize=font_size,
                color=(0, 0, 0),
            )

        annotations.append(
            {
                "text": ann_text,
                "bbox": {
                    "x0": ann_x,
                    "y0": ann_text_y,
                    "x1": ann_x + len(ann_text) * font_size * 0.5,
                    "y1": ann_text_y + font_size + 2,
                },
                "page": 0,
                "hole_index": i,
            }
        )

    # Title block
    tb_y = page_h - margin - title_block_h
    page.draw_rect(
        Rect(margin - 5, tb_y, page_w - margin + 5, page_h - margin + 5),
        color=(0, 0, 0),
        width=1.0,
    )

    # Title block content
    page.insert_text(
        Point(margin + 10, tb_y + 18),
        part_def["name"],
        fontsize=12,
        fontname="helv",
        color=(0, 0, 0),
    )
    page.insert_text(
        Point(margin + 10, tb_y + 32),
        part_def.get("description", ""),
        fontsize=7,
        color=(0.3, 0.3, 0.3),
    )

    unit_label = "INCHES" if unit_system == "inch" else "MILLIMETERS"
    page.insert_text(
        Point(page_w - margin - 150, tb_y + 18),
        f"UNITS: {unit_label}",
        fontsize=8,
        color=(0, 0, 0),
    )
    page.insert_text(
        Point(page_w - margin - 150, tb_y + 32),
        f"SCALE: ~{scale:.2f}:1",
        fontsize=7,
        color=(0.3, 0.3, 0.3),
    )
    page.insert_text(
        Point(page_w - margin - 150, tb_y + 44),
        "DrawMind3D Synthetic",
        fontsize=6,
        color=(0.5, 0.5, 0.5),
    )

    # Vertical divider in title block
    page.draw_line(
        Point(page_w - margin - 160, tb_y),
        Point(page_w - margin - 160, page_h - margin + 5),
        color=(0, 0, 0),
        width=0.5,
    )

    page.save(pdf_path)

    return annotations


def _draw_dashed_line(page, p1, p2, dash_len=4, gap_len=3, color=(0, 0, 0), width=0.3):
    """Draw a dashed line between two points."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length = math.sqrt(dx * dx + dy * dy)
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    pos = 0
    while pos < length:
        end = min(pos + dash_len, length)
        page.draw_line(
            Point(p1[0] + ux * pos, p1[1] + uy * pos),
            Point(p1[0] + ux * end, p1[1] + uy * end),
            color=color,
            width=width,
        )
        pos = end + gap_len


def _build_annotation_text(hole: dict, unit_system: str) -> str:
    """Build annotation text from hole definition."""
    if hole.get("thread"):
        thread = hole["thread"]
        t_info = METRIC_THREADS.get(thread, {})
        pitch = t_info.get("pitch", "")
        ann_text = thread
        if pitch:
            ann_text += f"x{pitch}"
        # Add tolerance class for some threads
        if hole.get("tolerance_class"):
            ann_text += f" {hole['tolerance_class']}"
    else:
        d = hole["diameter_mm"]
        if unit_system == "inch":
            ann_text = f"\u00d8{d / 25.4:.3f}"
        else:
            ann_text = f"\u00d8{d:.1f}"

        # Add bilateral tolerance if specified
        if hole.get("tolerance"):
            tol = hole["tolerance"]
            if isinstance(tol, dict):
                ann_text += f" +{tol['plus']:.3f}/-{tol['minus']:.3f}"
            elif isinstance(tol, str):
                ann_text += f" {tol}"  # e.g., "H7"

    count = hole.get("count", 1)
    if count > 1:
        ann_text = f"{count}X {ann_text}"

    if hole["is_through"]:
        ann_text += " THRU"
    else:
        depth = hole.get("depth_mm", 0)
        if depth > 0:
            if unit_system == "inch":
                ann_text += f" depth {depth / 25.4:.3f}"
            else:
                ann_text += f" depth {depth:.1f}"

    # Add counterbore/countersink notation
    if hole.get("counterbore"):
        cb = hole["counterbore"]
        if unit_system == "inch":
            ann_text += f" \u2334\u00d8{cb['diameter'] / 25.4:.3f} depth {cb['depth'] / 25.4:.3f}"
        else:
            ann_text += f" \u2334\u00d8{cb['diameter']:.1f} depth {cb['depth']:.1f}"

    if hole.get("countersink"):
        cs = hole["countersink"]
        _ = cs.get("diameter", hole["diameter_mm"] * 2)  # noqa: F841
        cs_a = cs.get("angle", 90)
        ann_text += f" \u2335{cs_a}\u00b0"

    return ann_text


def generate_ground_truth(part_def: dict, holes_info: list[dict], unit_system: str) -> dict:
    """Generate ground truth JSON for evaluation."""
    gt_annotations = []
    for i, hole in enumerate(holes_info):
        ann = {
            "id": f"gt_{i + 1:02d}",
            "type": "thread" if hole.get("thread") else "diameter",
            "diameter_mm": hole["diameter_mm"],
            "count": hole.get("count", 1),
            "is_through": hole["is_through"],
            "description": f"Hole {i + 1}",
        }
        if hole.get("thread"):
            ann["thread"] = hole["thread"]
            t_info = METRIC_THREADS.get(hole["thread"], {})
            ann["drill_diameter_mm"] = t_info.get("drill", hole["diameter_mm"])
        if not hole["is_through"]:
            ann["depth_mm"] = hole.get("depth_mm", 0)
        if hole.get("counterbore"):
            ann["type"] = "counterbore"
            ann["counterbore_diameter_mm"] = hole["counterbore"]["diameter"]
            ann["counterbore_depth_mm"] = hole["counterbore"]["depth"]
        if hole.get("countersink"):
            ann["type"] = "countersink"
            ann["countersink_angle"] = hole["countersink"].get("angle", 90)

        gt_annotations.append(ann)

    return {
        "test_case": part_def["name"],
        "source": "synthetic",
        "unit_system": unit_system,
        "description": part_def.get("description", "Synthetic test part"),
        "expected_annotations": gt_annotations,
        "total_unique_annotations": len(gt_annotations),
        "total_individual_holes": sum(h.get("count", 1) for h in holes_info),
    }


# ---- Part Definitions ----

PART_DEFINITIONS = [
    {
        "name": "SYN-01-SimpleBlock",
        "description": "Simple block with 4 through-holes and 2 blind holes",
        "width": 100,
        "height": 60,
        "depth": 20,
        "unit_system": "metric",
        "holes": [
            {
                "x": 15,
                "y": 15,
                "diameter": 8.0,
                "through": True,
                "count": 4,
                "annotation_text": "4X \u00d88.0 THRU",
            },
            {"x": 45, "y": 15, "diameter": 8.0, "through": True},
            {"x": 15, "y": 45, "diameter": 8.0, "through": True},
            {"x": 45, "y": 45, "diameter": 8.0, "through": True},
            {
                "x": 75,
                "y": 20,
                "diameter": 12.0,
                "depth": 15,
                "through": False,
                "annotation_text": "\u00d812.0 depth 15",
            },
            {
                "x": 75,
                "y": 40,
                "diameter": 10.0,
                "depth": 10,
                "through": False,
                "annotation_text": "\u00d810.0 depth 10",
                "image_annotation": True,
            },
        ],
    },
    {
        "name": "SYN-02-ThreadedPlate",
        "description": "Plate with metric threaded holes M6, M8, M10 with tolerance classes",
        "width": 120,
        "height": 80,
        "depth": 15,
        "unit_system": "metric",
        "holes": [
            {
                "x": 20,
                "y": 20,
                "diameter": 5.0,
                "through": True,
                "thread": "M6",
                "count": 4,
                "tolerance_class": "6H",
                "annotation_text": "4X M6x1.0 6H THRU",
            },
            {"x": 50, "y": 20, "diameter": 5.0, "through": True, "thread": "M6"},
            {"x": 20, "y": 60, "diameter": 5.0, "through": True, "thread": "M6"},
            {"x": 50, "y": 60, "diameter": 5.0, "through": True, "thread": "M6"},
            {
                "x": 80,
                "y": 30,
                "diameter": 6.8,
                "depth": 12,
                "thread": "M8",
                "annotation_text": "M8x1.25 depth 12",
                "image_annotation": True,
            },
            {
                "x": 100,
                "y": 30,
                "diameter": 6.8,
                "depth": 12,
                "thread": "M8",
                "annotation_text": "2X M8x1.25 depth 12",
            },
            {
                "x": 80,
                "y": 50,
                "diameter": 8.5,
                "through": True,
                "thread": "M10",
                "annotation_text": "M10x1.5 THRU",
                "image_annotation": True,
            },
        ],
    },
    {
        "name": "SYN-03-InchPart",
        "description": "Inch-dimensioned part with bilateral tolerances",
        "width": 100,
        "height": 70,
        "depth": 25,
        "unit_system": "inch",
        "holes": [
            {
                "x": 20,
                "y": 15,
                "diameter": 6.35,
                "through": True,
                "count": 2,
                "annotation_text": "2X \u00d8.250 +.005/-.002 THRU",
            },
            {"x": 50, "y": 15, "diameter": 6.35, "through": True},
            {
                "x": 20,
                "y": 50,
                "diameter": 8.731,
                "through": True,
                "annotation_text": "\u00d8.3438 +.003/-.001 THRU",
            },
            {
                "x": 50,
                "y": 50,
                "diameter": 11.1125,
                "depth": 12.7,
                "annotation_text": "\u00d8.4375 depth .500",
                "image_annotation": True,
            },
            {
                "x": 80,
                "y": 35,
                "diameter": 4.2,
                "depth": 10,
                "thread": "M5",
                "annotation_text": "M5x0.8 depth 10",
            },
        ],
    },
    {
        "name": "SYN-04-MixedFeatures",
        "description": "Complex part with counterbores, countersinks, threads, and tolerance classes",
        "width": 150,
        "height": 100,
        "depth": 30,
        "unit_system": "metric",
        "holes": [
            {
                "x": 25,
                "y": 25,
                "diameter": 6.0,
                "through": True,
                "count": 4,
                "annotation_text": "4X \u00d86.0 THRU \u2334\u00d812.0 depth 5.0",
                "counterbore": {"diameter": 12.0, "depth": 5.0},
            },
            {
                "x": 55,
                "y": 25,
                "diameter": 6.0,
                "through": True,
                "counterbore": {"diameter": 12.0, "depth": 5.0},
            },
            {
                "x": 25,
                "y": 75,
                "diameter": 6.0,
                "through": True,
                "counterbore": {"diameter": 12.0, "depth": 5.0},
            },
            {
                "x": 55,
                "y": 75,
                "diameter": 6.0,
                "through": True,
                "counterbore": {"diameter": 12.0, "depth": 5.0},
            },
            {
                "x": 90,
                "y": 35,
                "diameter": 10.0,
                "depth": 20,
                "tolerance": "H7",
                "annotation_text": "\u00d810.0 H7 depth 20",
            },
            {
                "x": 90,
                "y": 65,
                "diameter": 10.0,
                "depth": 20,
                "annotation_text": "2X \u00d810.0 depth 20",
            },
            {
                "x": 120,
                "y": 30,
                "diameter": 5.0,
                "through": True,
                "thread": "M6",
                "tolerance_class": "6H",
                "annotation_text": "M6x1.0 6H THRU",
            },
            {
                "x": 120,
                "y": 50,
                "diameter": 6.8,
                "depth": 15,
                "thread": "M8",
                "annotation_text": "M8x1.25 depth 15",
                "image_annotation": True,
            },
            {
                "x": 120,
                "y": 70,
                "diameter": 5.0,
                "through": True,
                "countersink": {"diameter": 10.0, "angle": 90},
                "annotation_text": "\u00d85.0 THRU \u233590\u00b0",
            },
        ],
    },
    {
        "name": "SYN-05-ManyHoles",
        "description": "Plate with many holes of different sizes for stress-testing",
        "width": 200,
        "height": 120,
        "depth": 10,
        "unit_system": "metric",
        "holes": [
            {
                "x": 20,
                "y": 20,
                "diameter": 4.0,
                "through": True,
                "count": 6,
                "annotation_text": "6X \u00d84.0 THRU",
            },
            {"x": 50, "y": 20, "diameter": 4.0, "through": True},
            {"x": 80, "y": 20, "diameter": 4.0, "through": True},
            {"x": 20, "y": 100, "diameter": 4.0, "through": True},
            {"x": 50, "y": 100, "diameter": 4.0, "through": True},
            {"x": 80, "y": 100, "diameter": 4.0, "through": True},
            {
                "x": 120,
                "y": 40,
                "diameter": 8.0,
                "through": True,
                "count": 3,
                "tolerance": "H8",
                "annotation_text": "3X \u00d88.0 H8 THRU",
            },
            {"x": 150, "y": 40, "diameter": 8.0, "through": True},
            {"x": 120, "y": 80, "diameter": 8.0, "through": True},
            {
                "x": 170,
                "y": 60,
                "diameter": 16.0,
                "through": True,
                "annotation_text": "\u00d816.0 +0.025/-0.010 THRU",
            },
            {
                "x": 35,
                "y": 60,
                "diameter": 3.3,
                "through": True,
                "thread": "M4",
                "annotation_text": "M4x0.7 THRU",
                "image_annotation": True,
            },
            {
                "x": 65,
                "y": 60,
                "diameter": 5.0,
                "through": True,
                "thread": "M6",
                "tolerance_class": "6H",
                "annotation_text": "M6x1.0 6H THRU",
            },
        ],
    },
]


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate synthetic test data")
    parser.add_argument("--count", type=int, default=len(PART_DEFINITIONS))
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent.parent / "data" / "synthetic",
        help="output directory (default: data/synthetic)",
    )
    args = parser.parse_args()

    output_dir = args.out
    output_dir.mkdir(parents=True, exist_ok=True)

    count = min(args.count, len(PART_DEFINITIONS))

    for i in range(count):
        part_def = PART_DEFINITIONS[i]
        name = part_def["name"]
        unit_system = part_def.get("unit_system", "metric")

        print(f"\nGenerating {name}...")

        shape, holes_info = generate_part(part_def)

        step_path = output_dir / f"{name}.stp"
        export_step(shape, step_path)
        print(f"  STEP: {step_path}")

        pdf_path = output_dir / f"{name}.pdf"
        annotations = generate_pdf_drawing(part_def, holes_info, pdf_path, unit_system)
        print(f"  PDF:  {pdf_path} ({len(annotations)} annotations)")

        gt = generate_ground_truth(part_def, holes_info, unit_system)
        gt_path = output_dir / f"{name}_ground_truth.json"
        with open(gt_path, "w") as f:
            json.dump(gt, f, indent=2)
        print(f"  GT:   {gt_path}")

        print(f"  Holes: {len(holes_info)}, Unit: {unit_system}")
        for h in holes_info:
            t = h.get("thread", "")
            d = h["diameter_mm"]
            thr = "THRU" if h["is_through"] else f"depth {h.get('depth_mm', '?')}"
            extras = []
            if h.get("counterbore"):
                extras.append(f"CBORE \u00d8{h['counterbore']['diameter']}")
            if h.get("countersink"):
                extras.append(f"CSINK {h['countersink'].get('angle', 90)}\u00b0")
            extra_str = f" [{', '.join(extras)}]" if extras else ""
            print(f"    {t or f'D{d:.1f}'} ({thr}){extra_str}")

    print(f"\n{'=' * 50}")
    print(f"Generated {count} synthetic test parts in: {output_dir}")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
