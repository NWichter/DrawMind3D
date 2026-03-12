"""Multi-factor scoring for annotation-to-feature matching."""

from __future__ import annotations

from drawmind.models import PDFAnnotation, AnnotationType, CylindricalFeature, HoleGroup
from drawmind.cad.thread_table import match_thread_to_diameter, get_thread_diameters, get_clearance_hole_diameter
from drawmind.config import DIAMETER_TOLERANCE_MM, DEPTH_TOLERANCE_MM

# Diameter ratio beyond which a match is implausible (e.g., ann=100mm vs feat=9mm)
MAX_DIAMETER_RATIO = 3.0


# Scoring weights (diameter is the strongest signal, count rarely informative)
WEIGHT_DIAMETER = 0.43
WEIGHT_DEPTH = 0.20
WEIGHT_TYPE_COMPAT = 0.18
WEIGHT_COUNT = 0.05
WEIGHT_UNIQUENESS = 0.09
WEIGHT_SPATIAL = 0.05  # Spatial position correlation (kept low — projection heuristic is noisy)

# Neutral score for missing data: "no evidence for or against"
# Must be high enough that matches with partial data can still pass confidence threshold
NEUTRAL_SCORE = 0.50


def compute_match_score(
    annotation: PDFAnnotation,
    hole: HoleGroup,
    all_holes: list[HoleGroup],
    all_annotations: list[PDFAnnotation],
) -> dict:
    """Compute a multi-factor match score between an annotation and a hole group.

    Returns:
        Dict with total_score and per-factor breakdown
    """
    scores = {}

    # 1. Diameter match
    scores["diameter"] = _score_diameter(annotation, hole)

    # 2. Depth match (includes through-hole agreement signal)
    scores["depth"] = _score_depth(annotation, hole)

    # 3. Type compatibility
    scores["type_compatibility"] = _score_type_compatibility(annotation, hole)

    # Through-hole agreement bonus/penalty applied to depth score
    if annotation.is_through and hole.is_through_hole:
        scores["depth"] = max(scores["depth"], 0.95)  # Strong agreement
    elif annotation.is_through and not hole.is_through_hole:
        scores["depth"] = min(scores["depth"], 0.15)  # Contradiction

    # 4. Count agreement
    scores["count_agreement"] = _score_count(annotation, hole, all_holes)

    # 5. Uniqueness bonus
    scores["uniqueness"] = _score_uniqueness(annotation, hole, all_holes)

    # 6. Spatial position correlation
    scores["spatial"] = _score_spatial(annotation, hole, all_holes, all_annotations)

    # 7. Diameter ratio sanity check — reject wildly mismatched sizes
    ann_d = _get_annotation_diameter(annotation)
    if ann_d is not None and ann_d > 0:
        compare_d = hole.primary_diameter
        # For counterbore annotations, also check secondary diameter
        if hole.secondary_diameter and hole.secondary_diameter > compare_d:
            compare_d = max(compare_d, hole.secondary_diameter)
        ratio = max(ann_d, compare_d) / max(min(ann_d, compare_d), 0.01)
        if ratio > MAX_DIAMETER_RATIO:
            # Implausible match (e.g., 100mm annotation vs 9mm hole)
            return {"total_score": 0.0, "breakdown": {**scores, "rejected": "diameter_ratio"}}

    # Weighted total
    total = (
        scores["diameter"] * WEIGHT_DIAMETER
        + scores["depth"] * WEIGHT_DEPTH
        + scores["type_compatibility"] * WEIGHT_TYPE_COMPAT
        + scores["count_agreement"] * WEIGHT_COUNT
        + scores["uniqueness"] * WEIGHT_UNIQUENESS
        + scores["spatial"] * WEIGHT_SPATIAL
    )

    # Source confidence factor: scale by annotation's own confidence
    # (Vision LLM annotations carry their detection confidence)
    source_conf = annotation.confidence
    if source_conf < 1.0:
        # Gentle blend: 85% matching score + 15% source confidence
        # (previous 70/30 was too aggressive, pushing correct matches below threshold)
        total = total * 0.85 + source_conf * 0.15
    scores["source_confidence"] = source_conf

    return {"total_score": round(total, 4), "breakdown": scores}


def _score_diameter(annotation: PDFAnnotation, hole: HoleGroup) -> float:
    """Score based on diameter match."""
    ann_diameter = _get_annotation_diameter(annotation)
    if ann_diameter is None:
        return NEUTRAL_SCORE  # No evidence against

    if annotation.annotation_type == AnnotationType.THREAD:
        # For threads, compare against known thread diameters
        thread_spec = _format_thread_spec(annotation)
        pitch = _safe_float(annotation.parsed.get("pitch"))

        score, matched_type = match_thread_to_diameter(
            thread_spec, hole.primary_diameter, DIAMETER_TOLERANCE_MM, pitch=pitch
        )

        # Also check clearance hole diameter (bolt-through patterns)
        # An M10 thread annotation may match an 11mm clearance hole
        if score < 0.8:
            clearance_d = get_clearance_hole_diameter(thread_spec)
            if clearance_d is not None:
                for fit_d in [clearance_d]:  # medium fit
                    diff = abs(hole.primary_diameter - fit_d)
                    if diff < DIAMETER_TOLERANCE_MM:
                        clearance_score = 0.85 * (1.0 - diff / DIAMETER_TOLERANCE_MM)
                        score = max(score, clearance_score)

        return score

    elif annotation.annotation_type in (AnnotationType.COUNTERBORE, AnnotationType.COUNTERSINK):
        # Counterbore/countersink diameter refers to the LARGER (outer) diameter
        compare_d = hole.secondary_diameter if hole.secondary_diameter else hole.primary_diameter
        diff = abs(ann_diameter - compare_d)
        if diff <= 0.1:
            return 1.0
        elif diff <= DIAMETER_TOLERANCE_MM:
            return 1.0 - (diff / DIAMETER_TOLERANCE_MM)
        # Also check primary diameter as fallback
        diff_primary = abs(ann_diameter - hole.primary_diameter)
        if diff_primary <= DIAMETER_TOLERANCE_MM:
            return 0.7 * (1.0 - diff_primary / DIAMETER_TOLERANCE_MM)
        return 0.0

    else:
        # Direct diameter comparison against primary
        diff = abs(ann_diameter - hole.primary_diameter)
        if diff <= 0.1:
            return 1.0
        elif diff <= DIAMETER_TOLERANCE_MM:
            return 1.0 - (diff / DIAMETER_TOLERANCE_MM)
        # Also check secondary diameter (annotation may reference outer bore)
        # Give full score (not capped at 0.7) since the annotation likely describes
        # the counterbore outer diameter — this is a valid match, not a fallback
        if hole.secondary_diameter:
            diff_sec = abs(ann_diameter - hole.secondary_diameter)
            if diff_sec <= 0.1:
                return 0.95  # Strong match to secondary diameter
            elif diff_sec <= DIAMETER_TOLERANCE_MM:
                return 0.90 * (1.0 - diff_sec / DIAMETER_TOLERANCE_MM)
        return 0.0


def _score_depth(annotation: PDFAnnotation, hole: HoleGroup) -> float:
    """Score based on depth match."""
    # Check if annotation is through-hole
    if annotation.is_through:
        return 1.0 if hole.is_through_hole else 0.15

    # Check associated depth annotations
    ann_depth = _get_annotation_depth(annotation)
    if ann_depth is None:
        # Missing depth is less informative for through-holes (common to omit depth)
        if hole.is_through_hole:
            return 0.6  # Likely through, just no annotation for it
        return NEUTRAL_SCORE

    if hole.is_through_hole and not annotation.is_through:
        return 0.2  # Mismatch: hole is through but annotation specifies depth

    # Adaptive tolerance: tighter for simple holes, looser for stepped holes
    tolerance = DEPTH_TOLERANCE_MM
    if hole.hole_type in ("counterbore", "countersink", "stepped"):
        tolerance = DEPTH_TOLERANCE_MM * 1.5

    # Check against total depth first
    diff = abs(ann_depth - hole.total_depth)
    if diff <= 0.5:
        return 1.0
    elif diff <= tolerance:
        return 1.0 - (diff / tolerance) * 0.5

    # Also check against individual feature depths (for stepped/counterbore holes
    # the annotation depth may refer to one segment, not the total)
    for feat in hole.features:
        feat_diff = abs(ann_depth - feat.estimated_depth)
        if feat_diff <= 0.5:
            return 0.9
        elif feat_diff <= tolerance:
            return 0.85 * (1.0 - feat_diff / tolerance)

    return 0.0


def _score_type_compatibility(annotation: PDFAnnotation, hole: HoleGroup) -> float:
    """Score based on type compatibility."""
    ann_type = annotation.annotation_type
    tol_class = annotation.parsed.get("tolerance_class", "")

    # Check tolerance class for internal vs external indication
    # Internal (uppercase letter: H, G, F...) = hole/bore → compatible
    # External (lowercase letter: h, g, f...) = shaft → NOT a hole feature
    if tol_class:
        position_letter = None
        if ann_type == AnnotationType.THREAD:
            # Thread format: grade + position (e.g., "6H", "6g")
            for ch in tol_class:
                if ch.isalpha():
                    position_letter = ch
                    break
        else:
            # Diameter format: position + grade (e.g., "H7", "g6")
            if tol_class[0].isalpha():
                position_letter = tol_class[0]

        if position_letter and position_letter.islower():
            return 0.1  # External tolerance (shaft) → very unlikely to be a hole

    if ann_type == AnnotationType.THREAD:
        # Thread annotations should match holes whose diameter aligns with thread sizes
        thread_spec = _format_thread_spec(annotation)
        diameters = get_thread_diameters(thread_spec)
        if diameters:
            for d_type in ["major", "pitch", "minor", "drill"]:
                diff = abs(diameters[f"{d_type}_d" if d_type != "drill" else "drill_d"] - hole.primary_diameter)
                if diff < DIAMETER_TOLERANCE_MM:
                    return 1.0
        return 0.3

    elif ann_type == AnnotationType.COUNTERBORE:
        return 1.0 if hole.hole_type == "counterbore" else 0.2

    elif ann_type == AnnotationType.COUNTERSINK:
        return 1.0 if hole.hole_type == "countersink" else 0.2

    elif ann_type in (AnnotationType.DIAMETER, AnnotationType.HOLE_CALLOUT):
        return 1.0  # Diameter callout is fully type-compatible with any hole

    elif ann_type == AnnotationType.FIT:
        # Fit specs (H7) typically apply to precision holes
        return 0.7

    return NEUTRAL_SCORE


def _score_count(
    annotation: PDFAnnotation, hole: HoleGroup, all_holes: list[HoleGroup]
) -> float:
    """Score based on count agreement (e.g., '4x M8' needs 4 matching holes)."""
    if annotation.multiplier <= 1:
        return NEUTRAL_SCORE  # No count specified, no evidence against

    # Count holes with similar diameter
    tolerance = DIAMETER_TOLERANCE_MM
    matching_count = sum(
        1 for h in all_holes
        if abs(h.primary_diameter - hole.primary_diameter) < tolerance
    )

    if matching_count == annotation.multiplier:
        return 1.0
    elif matching_count > annotation.multiplier:
        return 0.7  # More holes than expected, still reasonable
    else:
        return 0.3  # Fewer holes than expected


def _score_uniqueness(
    annotation: PDFAnnotation, hole: HoleGroup, all_holes: list[HoleGroup]
) -> float:
    """Bonus if this is the only candidate match (unambiguous)."""
    ann_diameter = _get_annotation_diameter(annotation)
    if ann_diameter is None:
        return NEUTRAL_SCORE

    candidates = 0
    for h in all_holes:
        diff = abs(ann_diameter - h.primary_diameter)
        if diff < DIAMETER_TOLERANCE_MM * 2:  # Wider tolerance for candidate count
            candidates += 1

    if candidates == 1:
        return 1.0
    elif candidates <= 3:
        return 0.7
    else:
        return 0.3


def _score_spatial(
    annotation: PDFAnnotation, hole: HoleGroup, all_holes: list[HoleGroup],
    all_annotations: list[PDFAnnotation] | None = None,
) -> float:
    """Score based on spatial position correlation between PDF and 3D model.

    Compares the annotation's normalized position on the PDF page with the
    hole's normalized position in the 3D model. Tries all three 2D projections
    (XY, XZ, YZ) and returns the best match.
    """
    if len(all_holes) < 2:
        return NEUTRAL_SCORE  # Can't compute spatial with single hole

    # Annotation center normalized to page dimensions
    # Infer page size from all annotations on the same page (max bbox extent)
    # Falls back to US Letter (612 x 792 pts) if no other annotations
    if all_annotations:
        page_anns = [a for a in all_annotations if a.bbox.page == annotation.bbox.page]
        page_w = max((a.bbox.x1 for a in page_anns), default=612.0)
        page_h = max((a.bbox.y1 for a in page_anns), default=792.0)
    else:
        page_w, page_h = 612.0, 792.0
    # Ensure minimum page dimensions (at least A4/Letter)
    page_w = max(page_w, 500.0)
    page_h = max(page_h, 700.0)

    ann_x = (annotation.bbox.x0 + annotation.bbox.x1) / 2
    ann_y = (annotation.bbox.y0 + annotation.bbox.y1) / 2
    ann_nx = min(ann_x / page_w, 1.0)
    ann_ny = min(ann_y / page_h, 1.0)

    # If leader line target is available, use it instead of bbox center
    leader = annotation.parsed.get("leader_target")
    if leader:
        ann_nx = min(leader["x"] / 612.0, 1.0)
        ann_ny = min(leader["y"] / 792.0, 1.0)

    # Try each 2D projection of the 3D model
    centers = [h.center for h in all_holes]
    best_score = NEUTRAL_SCORE

    for ax1, ax2, flip_y in [(0, 1, False), (0, 2, True), (1, 2, True)]:
        vals1 = [c[ax1] for c in centers]
        vals2 = [c[ax2] for c in centers]
        r1 = max(vals1) - min(vals1)
        r2 = max(vals2) - min(vals2)
        if r1 < 0.1 or r2 < 0.1:
            continue

        hole_nx = (hole.center[ax1] - min(vals1)) / r1
        hole_ny = (hole.center[ax2] - min(vals2)) / r2
        if flip_y:
            hole_ny = 1.0 - hole_ny  # PDF Y increases downward

        dist = ((ann_nx - hole_nx) ** 2 + (ann_ny - hole_ny) ** 2) ** 0.5
        score = max(1.0 - dist * 1.5, 0.0)
        best_score = max(best_score, score)

    return best_score


def _format_thread_spec(annotation: PDFAnnotation) -> str:
    """Format a thread specification string for table lookup.

    Supports both ISO metric (M10) and UTS (1/4-20 UNC) threads.
    """
    standard = annotation.parsed.get("standard", "ISO_metric")

    if standard == "UTS":
        # For UTS threads, return the full spec for table lookup
        return annotation.parsed.get("thread_spec", "")

    nom_d = annotation.parsed.get("nominal_diameter", 0)
    # Use integer format if it's a whole number (M10 not M10.0)
    if nom_d == int(nom_d):
        spec = f"M{int(nom_d)}"
    else:
        spec = f"M{nom_d}"
    return spec


def _safe_float(val) -> float | None:
    """Convert a value to float safely (handles strings from LLM responses)."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _get_annotation_diameter(annotation: PDFAnnotation) -> float | None:
    """Extract the nominal diameter from an annotation."""
    parsed = annotation.parsed

    if annotation.annotation_type == AnnotationType.THREAD:
        return _safe_float(parsed.get("nominal_diameter"))
    elif annotation.annotation_type in (AnnotationType.DIAMETER, AnnotationType.HOLE_CALLOUT):
        return _safe_float(parsed.get("value"))
    elif annotation.annotation_type == AnnotationType.COUNTERBORE:
        return _safe_float(parsed.get("diameter"))
    elif annotation.annotation_type == AnnotationType.COUNTERSINK:
        return _safe_float(parsed.get("diameter"))

    return None


def _get_annotation_depth(annotation: PDFAnnotation) -> float | None:
    """Extract depth from an annotation (if available).

    Checks both DEPTH-type annotations and depth transferred
    from associated annotations via _associate_depths().
    """
    if annotation.annotation_type == AnnotationType.DEPTH:
        return _safe_float(annotation.parsed.get("value"))
    # Check for depth transferred from a nearby depth annotation
    depth = annotation.parsed.get("depth")
    if depth is not None:
        return _safe_float(depth)
    return None
