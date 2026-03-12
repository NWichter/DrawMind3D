"""Generate synthetic STEP + PDF test pairs with known ground truth.

Creates parametric parts with known holes/threads, generates matching
PDF drawings with text-based annotations, and ground truth JSON.

Usage:
    uv run python scripts/generate_synthetic.py [--count 5]
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# OCP imports for STEP generation
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Ax1, gp_Vec
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.TopoDS import TopoDS_Shape

# PDF generation
import fitz  # PyMuPDF


def _text_as_image(text: str, fontsize: int = 9) -> tuple[bytes, float, float]:
    """Render text as a rasterized PNG image (not extractable as text).

    Used to simulate vector-drawn annotations that only Vision LLM can read.
    Returns (png_bytes, width_pt, height_pt).
    """
    char_width = fontsize * 0.52
    img_w = len(text) * char_width + 8
    img_h = fontsize + 8

    tmp_doc = fitz.open()
    tmp_page = tmp_doc.new_page(width=img_w, height=img_h)
    tmp_page.insert_text(
        fitz.Point(4, fontsize + 2),
        text,
        fontsize=fontsize,
        color=(0, 0, 0),
    )

    # Render at 3x zoom for crisp text
    mat = fitz.Matrix(3, 3)
    pix = tmp_page.get_pixmap(matrix=mat, alpha=False)
    img_bytes = pix.tobytes("png")
    tmp_doc.close()

    return img_bytes, img_w, img_h


# Standard metric thread table (subset)
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
    """Generate a 3D part with holes based on part definition.

    Returns:
        (shape, holes_info) where holes_info is the ground truth
    """
    # Create base block
    w = part_def["width"]
    h = part_def["height"]
    d = part_def["depth"]
    box = BRepPrimAPI_MakeBox(w, h, d).Shape()

    shape = box
    holes_info = []

    for hole in part_def["holes"]:
        hx, hy = hole["x"], hole["y"]
        diameter = hole["diameter"]
        depth = hole.get("depth", d)  # default: through
        is_through = hole.get("through", depth >= d)

        # Create cylinder for the hole
        actual_depth = d + 2 if is_through else depth  # extend through for clean cut
        center = gp_Pnt(hx, hy, d if is_through else d - depth + depth)
        axis = gp_Ax2(gp_Pnt(hx, hy, d + 1 if is_through else d), gp_Dir(0, 0, -1))
        cyl = BRepPrimAPI_MakeCylinder(axis, diameter / 2, actual_depth + 1).Shape()

        # Subtract cylinder from block
        shape = BRepAlgoAPI_Cut(shape, cyl).Shape()

        holes_info.append({
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
        })

    return shape, holes_info


def export_step(shape: TopoDS_Shape, path: Path):
    """Export shape to STEP file."""
    writer = STEPControl_Writer()
    writer.Transfer(shape, STEPControl_AsIs)
    writer.Write(str(path))


def generate_pdf_drawing(
    part_def: dict,
    holes_info: list[dict],
    pdf_path: Path,
    unit_system: str = "metric",
):
    """Generate a simplified 2D technical drawing PDF with annotations.

    Creates a schematic top-view with hole positions and dimension callouts.
    """
    # Page setup (A4 landscape)
    page_w, page_h = 842, 595  # A4 landscape in points
    doc = fitz.open()
    page = doc.new_page(width=page_w, height=page_h)

    # Scale factor: fit part into drawing area
    margin = 80
    draw_area_w = page_w - 2 * margin - 200  # Reserve right side for notes
    draw_area_h = page_h - 2 * margin - 60  # Reserve bottom for title

    part_w = part_def["width"]
    part_h = part_def["height"]
    scale = min(draw_area_w / part_w, draw_area_h / part_h) * 0.7

    # Origin offset (center the drawing)
    ox = margin + (draw_area_w - part_w * scale) / 2
    oy = margin + 30 + (draw_area_h - part_h * scale) / 2

    # Draw part outline (top view)
    rect = fitz.Rect(ox, oy, ox + part_w * scale, oy + part_h * scale)
    page.draw_rect(rect, color=(0, 0, 0), width=1.5)

    # Draw holes and annotations
    annotations = []
    ann_y = margin + 20
    font_size = 9

    for i, hole in enumerate(holes_info):
        hx = ox + hole["x"] * scale
        hy = oy + hole["y"] * scale
        r = (hole["diameter_mm"] / 2) * scale

        # Draw hole circle
        page.draw_circle(fitz.Point(hx, hy), r, color=(0, 0, 0), width=0.8)

        # Center mark
        page.draw_line(fitz.Point(hx - 3, hy), fitz.Point(hx + 3, hy), color=(0, 0, 0), width=0.3)
        page.draw_line(fitz.Point(hx, hy - 3), fitz.Point(hx, hy + 3), color=(0, 0, 0), width=0.3)

        # Build annotation text
        ann_text = hole.get("annotation_text", "")
        if not ann_text:
            if hole.get("thread"):
                thread = hole["thread"]
                t_info = METRIC_THREADS.get(thread, {})
                pitch = t_info.get("pitch", "")
                ann_text = f"{thread}"
                if pitch:
                    ann_text += f"x{pitch}"
            else:
                d = hole["diameter_mm"]
                if unit_system == "inch":
                    d_inch = d / 25.4
                    ann_text = f"\u00d8{d_inch:.3f}"
                else:
                    ann_text = f"\u00d8{d:.1f}"

            # Add count prefix
            count = hole.get("count", 1)
            if count > 1:
                ann_text = f"{count}X {ann_text}"

            # Add depth/through
            if hole["is_through"]:
                ann_text += " THRU"
            else:
                depth = hole.get("depth_mm", 0)
                if depth > 0:
                    if unit_system == "inch":
                        ann_text += f" depth {depth/25.4:.3f}"
                    else:
                        ann_text += f" depth {depth:.1f}"

        # Place annotation text
        # Draw leader line from hole to annotation
        ann_x = ox + part_w * scale + 20
        ann_text_y = ann_y + i * 22

        # Leader line
        page.draw_line(
            fitz.Point(hx, hy),
            fitz.Point(ann_x - 5, ann_text_y + font_size / 2),
            color=(0, 0, 0),
            width=0.5,
        )

        # Annotation text (image-based for some to require Vision LLM)
        if hole.get("image_annotation"):
            img_bytes, img_w, img_h = _text_as_image(ann_text, fontsize=font_size)
            img_rect = fitz.Rect(ann_x, ann_text_y, ann_x + img_w, ann_text_y + img_h)
            page.insert_image(img_rect, stream=img_bytes)
        else:
            page.insert_text(
                fitz.Point(ann_x, ann_text_y + font_size),
                ann_text,
                fontsize=font_size,
                color=(0, 0, 0),
            )

        annotations.append({
            "text": ann_text,
            "bbox": {
                "x0": ann_x,
                "y0": ann_text_y,
                "x1": ann_x + len(ann_text) * font_size * 0.5,
                "y1": ann_text_y + font_size + 2,
            },
            "page": 0,
            "hole_index": i,
        })

    # Title block
    title_y = page_h - 50
    page.draw_line(fitz.Point(margin, title_y - 5), fitz.Point(page_w - margin, title_y - 5), color=(0, 0, 0), width=0.8)
    page.insert_text(fitz.Point(margin, title_y + 12), part_def["name"], fontsize=11, fontname="helv", color=(0, 0, 0))

    # Unit note
    unit_text = f"UNITS: {'INCHES' if unit_system == 'inch' else 'MILLIMETERS'}"
    page.insert_text(fitz.Point(page_w - margin - 140, title_y + 12), unit_text, fontsize=8, color=(0, 0, 0))

    # Notes
    notes_y = page_h - 30
    page.insert_text(fitz.Point(margin, notes_y + 10), "DrawMind3D Synthetic Test Part", fontsize=7, color=(0.5, 0.5, 0.5))

    doc.save(str(pdf_path))
    doc.close()

    return annotations


def generate_ground_truth(part_def: dict, holes_info: list[dict], unit_system: str) -> dict:
    """Generate ground truth JSON for evaluation."""
    gt_annotations = []
    for i, hole in enumerate(holes_info):
        ann = {
            "id": f"gt_{i+1:02d}",
            "type": "thread" if hole.get("thread") else "diameter",
            "diameter_mm": hole["diameter_mm"],
            "count": hole.get("count", 1),
            "is_through": hole["is_through"],
            "description": f"Hole {i+1}",
        }
        if hole.get("thread"):
            ann["thread"] = hole["thread"]
            t_info = METRIC_THREADS.get(hole["thread"], {})
            ann["drill_diameter_mm"] = t_info.get("drill", hole["diameter_mm"])
        if not hole["is_through"]:
            ann["depth_mm"] = hole.get("depth_mm", 0)

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
        "width": 100, "height": 60, "depth": 20,
        "unit_system": "metric",
        "holes": [
            {"x": 15, "y": 15, "diameter": 8.0, "through": True, "count": 4,
             "annotation_text": "4X \u00d88.0 THRU"},
            {"x": 45, "y": 15, "diameter": 8.0, "through": True},
            {"x": 15, "y": 45, "diameter": 8.0, "through": True},
            {"x": 45, "y": 45, "diameter": 8.0, "through": True},
            {"x": 75, "y": 20, "diameter": 12.0, "depth": 15, "through": False,
             "annotation_text": "\u00d812.0 depth 15"},
            {"x": 75, "y": 40, "diameter": 10.0, "depth": 10, "through": False,
             "annotation_text": "\u00d810.0 depth 10", "image_annotation": True},
        ],
    },
    {
        "name": "SYN-02-ThreadedPlate",
        "description": "Plate with metric threaded holes M6, M8, M10",
        "width": 120, "height": 80, "depth": 15,
        "unit_system": "metric",
        "holes": [
            {"x": 20, "y": 20, "diameter": 5.0, "through": True, "thread": "M6", "count": 4,
             "annotation_text": "4X M6x1.0 THRU"},
            {"x": 50, "y": 20, "diameter": 5.0, "through": True, "thread": "M6"},
            {"x": 20, "y": 60, "diameter": 5.0, "through": True, "thread": "M6"},
            {"x": 50, "y": 60, "diameter": 5.0, "through": True, "thread": "M6"},
            {"x": 80, "y": 30, "diameter": 6.8, "depth": 12, "thread": "M8",
             "annotation_text": "M8x1.25 depth 12", "image_annotation": True},
            {"x": 100, "y": 30, "diameter": 6.8, "depth": 12, "thread": "M8",
             "annotation_text": "2X M8x1.25 depth 12"},
            {"x": 80, "y": 50, "diameter": 8.5, "through": True, "thread": "M10",
             "annotation_text": "M10x1.5 THRU", "image_annotation": True},
        ],
    },
    {
        "name": "SYN-03-InchPart",
        "description": "Inch-dimensioned part with clearance and tapped holes",
        "width": 100, "height": 70, "depth": 25,
        "unit_system": "inch",
        "holes": [
            {"x": 20, "y": 15, "diameter": 6.35, "through": True, "count": 2,
             "annotation_text": "2X \u00d8.250 THRU"},
            {"x": 50, "y": 15, "diameter": 6.35, "through": True},
            {"x": 20, "y": 50, "diameter": 8.731, "through": True,
             "annotation_text": "\u00d8.3438 THRU"},
            {"x": 50, "y": 50, "diameter": 11.1125, "depth": 12.7,
             "annotation_text": "\u00d8.4375 depth .500", "image_annotation": True},
            {"x": 80, "y": 35, "diameter": 4.2, "depth": 10, "thread": "M5",
             "annotation_text": "M5x0.8 depth 10"},
        ],
    },
    {
        "name": "SYN-04-MixedFeatures",
        "description": "Complex part with counterbores, countersinks, and threads",
        "width": 150, "height": 100, "depth": 30,
        "unit_system": "metric",
        "holes": [
            {"x": 25, "y": 25, "diameter": 6.0, "through": True, "count": 4,
             "annotation_text": "4X \u00d86.0 THRU"},
            {"x": 55, "y": 25, "diameter": 6.0, "through": True},
            {"x": 25, "y": 75, "diameter": 6.0, "through": True},
            {"x": 55, "y": 75, "diameter": 6.0, "through": True},
            {"x": 90, "y": 35, "diameter": 10.0, "depth": 20,
             "annotation_text": "\u00d810.0 depth 20"},
            {"x": 90, "y": 65, "diameter": 10.0, "depth": 20,
             "annotation_text": "2X \u00d810.0 depth 20"},
            {"x": 120, "y": 30, "diameter": 5.0, "through": True, "thread": "M6",
             "annotation_text": "M6x1.0 THRU"},
            {"x": 120, "y": 50, "diameter": 6.8, "depth": 15, "thread": "M8",
             "annotation_text": "M8x1.25 depth 15", "image_annotation": True},
            {"x": 120, "y": 70, "diameter": 8.5, "depth": 20, "thread": "M10",
             "annotation_text": "M10x1.5 depth 20", "image_annotation": True},
        ],
    },
    {
        "name": "SYN-05-ManyHoles",
        "description": "Plate with many holes of different sizes for stress-testing",
        "width": 200, "height": 120, "depth": 10,
        "unit_system": "metric",
        "holes": [
            {"x": 20, "y": 20, "diameter": 4.0, "through": True, "count": 6,
             "annotation_text": "6X \u00d84.0 THRU"},
            {"x": 50, "y": 20, "diameter": 4.0, "through": True},
            {"x": 80, "y": 20, "diameter": 4.0, "through": True},
            {"x": 20, "y": 100, "diameter": 4.0, "through": True},
            {"x": 50, "y": 100, "diameter": 4.0, "through": True},
            {"x": 80, "y": 100, "diameter": 4.0, "through": True},
            {"x": 120, "y": 40, "diameter": 8.0, "through": True, "count": 3,
             "annotation_text": "3X \u00d88.0 THRU"},
            {"x": 150, "y": 40, "diameter": 8.0, "through": True},
            {"x": 120, "y": 80, "diameter": 8.0, "through": True},
            {"x": 170, "y": 60, "diameter": 16.0, "through": True,
             "annotation_text": "\u00d816.0 THRU"},
            {"x": 35, "y": 60, "diameter": 3.3, "through": True, "thread": "M4",
             "annotation_text": "M4x0.7 THRU", "image_annotation": True},
            {"x": 65, "y": 60, "diameter": 5.0, "through": True, "thread": "M6",
             "annotation_text": "M6x1.0 THRU"},
        ],
    },
]


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate synthetic test data")
    parser.add_argument("--count", type=int, default=len(PART_DEFINITIONS), help="Number of parts to generate")
    args = parser.parse_args()

    output_dir = Path(__file__).parent.parent / "data" / "synthetic"
    output_dir.mkdir(parents=True, exist_ok=True)

    count = min(args.count, len(PART_DEFINITIONS))

    for i in range(count):
        part_def = PART_DEFINITIONS[i]
        name = part_def["name"]
        unit_system = part_def.get("unit_system", "metric")

        print(f"\nGenerating {name}...")

        # Generate 3D part
        shape, holes_info = generate_part(part_def)

        # Export STEP
        step_path = output_dir / f"{name}.stp"
        export_step(shape, step_path)
        print(f"  STEP: {step_path}")

        # Generate PDF drawing
        pdf_path = output_dir / f"{name}.pdf"
        annotations = generate_pdf_drawing(part_def, holes_info, pdf_path, unit_system)
        print(f"  PDF:  {pdf_path} ({len(annotations)} annotations)")

        # Generate ground truth
        gt = generate_ground_truth(part_def, holes_info, unit_system)
        gt_path = output_dir / f"{name}_ground_truth.json"
        with open(gt_path, "w") as f:
            json.dump(gt, f, indent=2)
        print(f"  GT:   {gt_path}")

        # Print summary
        print(f"  Holes: {len(holes_info)}, Unit: {unit_system}")
        for h in holes_info:
            t = h.get("thread", "")
            d = h["diameter_mm"]
            thr = "THRU" if h["is_through"] else f"depth {h.get('depth_mm', '?')}"
            print(f"    {t or f'D{d:.1f}'} ({thr})")

    print(f"\n{'='*50}")
    print(f"Generated {count} synthetic test parts in: {output_dir}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
