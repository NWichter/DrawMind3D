"""Leader-line extraction from vector PDF drawings.

Leader lines connect annotation callouts to the features they describe.
By extracting these lines, we can determine WHERE on the drawing each
annotation points to, improving spatial matching accuracy.
"""

from __future__ import annotations

import logging
from pathlib import Path

import fitz

from drawmind.models import PDFAnnotation

logger = logging.getLogger(__name__)

# Maximum distance (in PDF points) between a line endpoint and annotation bbox
# center for the line to be considered a leader line for that annotation.
MAX_LEADER_DISTANCE = 50.0

# Minimum leader line length (skip very short segments like tick marks)
MIN_LEADER_LENGTH = 15.0


def extract_leader_targets(
    pdf_path: str | Path,
    annotations: list[PDFAnnotation],
) -> list[PDFAnnotation]:
    """Extract leader line target points for annotations.

    For each annotation, finds line segments in the PDF drawing that
    originate near the annotation's bounding box. The other endpoint
    of such a line indicates where the annotation points to on the drawing.

    The target point is stored in ``annotation.parsed["leader_target"]``
    as ``{"x": float, "y": float}`` in PDF page coordinates.

    Args:
        pdf_path: Path to the PDF file
        annotations: Parsed annotations with bounding boxes

    Returns:
        The same annotations list, enriched with leader_target where found
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return annotations

    doc = fitz.open(str(pdf_path))
    pages_needed = set(a.bbox.page for a in annotations)

    for page_num in pages_needed:
        if page_num >= len(doc):
            continue

        page = doc[page_num]
        try:
            drawings = page.get_drawings()
        except Exception:
            continue

        # Collect all line segments on this page
        lines = _extract_line_segments(drawings)

        # For each annotation on this page, find the best leader line
        page_anns = [a for a in annotations if a.bbox.page == page_num]
        for ann in page_anns:
            target = _find_leader_target(ann, lines)
            if target:
                ann.parsed["leader_target"] = {"x": target[0], "y": target[1]}

    doc.close()

    found = sum(1 for a in annotations if "leader_target" in a.parsed)
    if found:
        logger.info(f"Leader lines: found targets for {found}/{len(annotations)} annotations")

    return annotations


def _extract_line_segments(drawings: list[dict]) -> list[tuple]:
    """Extract line segments from PyMuPDF drawing objects.

    Returns:
        List of ((x1, y1), (x2, y2)) tuples for each line segment
    """
    lines = []
    for d in drawings:
        width = d.get("width", 0)
        # Leader lines are typically thin (0.2-2.0 points)
        if width > 3.0:
            continue

        for item in d.get("items", []):
            if item[0] != "l":  # Only line segments
                continue

            p1, p2 = item[1], item[2]
            length = ((p1.x - p2.x) ** 2 + (p1.y - p2.y) ** 2) ** 0.5
            if length >= MIN_LEADER_LENGTH:
                lines.append(((p1.x, p1.y), (p2.x, p2.y)))

    return lines


def _find_leader_target(
    annotation: PDFAnnotation, lines: list[tuple]
) -> tuple[float, float] | None:
    """Find the leader line target point for an annotation.

    Looks for line segments with one endpoint near the annotation bbox.
    The opposite endpoint is the target (where the annotation points to).

    Returns:
        (x, y) target point in PDF coordinates, or None
    """
    ann_cx = (annotation.bbox.x0 + annotation.bbox.x1) / 2
    ann_cy = (annotation.bbox.y0 + annotation.bbox.y1) / 2

    # Expanded bbox for hit testing (annotation text may not perfectly
    # align with the leader line start)
    margin = 10
    ax0 = annotation.bbox.x0 - margin
    ay0 = annotation.bbox.y0 - margin
    ax1 = annotation.bbox.x1 + margin
    ay1 = annotation.bbox.y1 + margin

    best_target = None
    best_dist = MAX_LEADER_DISTANCE

    for (x1, y1), (x2, y2) in lines:
        # Check if either endpoint is near the annotation bbox
        for (sx, sy), (ex, ey) in [((x1, y1), (x2, y2)), ((x2, y2), (x1, y1))]:
            # Is the start point near or inside the annotation bbox?
            if ax0 <= sx <= ax1 and ay0 <= sy <= ay1:
                # Distance from bbox center to line start
                dist = ((sx - ann_cx) ** 2 + (sy - ann_cy) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_target = (ex, ey)
            else:
                # Also check simple distance to bbox center
                dist = ((sx - ann_cx) ** 2 + (sy - ann_cy) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_target = (ex, ey)

    return best_target
