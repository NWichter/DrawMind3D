"""Main matching orchestrator: links PDF annotations to 3D hole features.

Uses the Hungarian Algorithm (scipy) for optimal assignment instead of greedy.
"""

from __future__ import annotations

import logging

import numpy as np
from scipy.optimize import linear_sum_assignment

from drawmind.models import (
    PDFAnnotation, AnnotationType, CylindricalFeature, HoleGroup, MatchResult,
)
from drawmind.matching.scoring import compute_match_score
from drawmind.matching.llm_resolver import resolve_ambiguous_matches
from drawmind.config import MATCH_CONFIDENCE_THRESHOLD, LLM_REVIEW_THRESHOLD, DIAMETER_TOLERANCE_MM
from drawmind.cad.thread_table import match_thread_to_diameter

logger = logging.getLogger(__name__)

# Annotation types that are relevant for hole matching
HOLE_ANNOTATION_TYPES = {
    AnnotationType.THREAD,
    AnnotationType.DIAMETER,
    AnnotationType.HOLE_CALLOUT,
    AnnotationType.COUNTERBORE,
    AnnotationType.COUNTERSINK,
    AnnotationType.FIT,
}


def match_annotations_to_features(
    annotations: list[PDFAnnotation],
    holes: list[HoleGroup],
    pdf_path: str | None = None,
    use_llm_resolver: bool = False,
) -> tuple[list[MatchResult], list[PDFAnnotation], list[HoleGroup]]:
    """Match PDF annotations to 3D hole features using optimal assignment.

    Uses the Hungarian Algorithm for globally optimal annotation-to-hole
    assignment, then handles multiplier annotations (e.g. '4x M8') separately.

    Args:
        annotations: Parsed PDF annotations
        holes: Grouped hole features from 3D model

    Returns:
        Tuple of (matches, unmatched_annotations, unmatched_holes)
    """
    # Filter to hole-related annotations only
    hole_annotations = [a for a in annotations if a.annotation_type in HOLE_ANNOTATION_TYPES]
    depth_annotations = [a for a in annotations if a.annotation_type == AnnotationType.DEPTH]

    # Associate depth annotations with nearby hole annotations
    _associate_depths(hole_annotations, depth_annotations)

    if not hole_annotations or not holes:
        return [], hole_annotations, holes

    # Post-filter: remove Vision LLM annotations that are likely false positives
    # (part dimensions extracted as diameters). Filter only low-confidence vision
    # annotations that have no matching 3D feature within tolerance.
    if holes:
        hole_annotations = _filter_vision_false_positives(hole_annotations, holes)

    # Expand multiplier annotations into virtual copies for unified Hungarian
    # e.g., "4X Ø8" becomes 4 entries so Hungarian can optimally assign each
    # CAP: don't create more copies than matching features exist in the 3D model
    # to prevent the Hungarian algorithm from force-assigning extras to wrong holes
    expanded_annotations = []
    for ann in hole_annotations:
        count = max(ann.multiplier, 1)
        if count > 1:
            # Count how many 3D features could plausibly match this annotation
            ann_d = _get_annotation_diameter_for_cap(ann)
            if ann_d is not None and ann_d > 0:
                matching_features = sum(
                    1 for h in holes
                    if abs(h.primary_diameter - ann_d) < DIAMETER_TOLERANCE_MM * 2
                    or (h.secondary_diameter and abs(h.secondary_diameter - ann_d) < DIAMETER_TOLERANCE_MM * 2)
                )
                if matching_features > 0:
                    count = min(count, matching_features)
        for _ in range(count):
            expanded_annotations.append(ann)

    # --- Unified Hungarian assignment ---
    score_details = {}  # (exp_idx, hole_idx) -> score_result
    n_exp = len(expanded_annotations)
    n_holes = len(holes)

    if n_exp > 0 and n_holes > 0:
        # Build cost matrix (Hungarian minimizes, so we use 1 - score)
        cost_matrix = np.ones((n_exp, n_holes))
        for i, ann in enumerate(expanded_annotations):
            for j, hole in enumerate(holes):
                score_result = compute_match_score(ann, hole, holes, hole_annotations)
                score_details[(i, j)] = score_result
                cost_matrix[i, j] = 1.0 - score_result["total_score"]

        # Run Hungarian Algorithm
        row_ind, col_ind = linear_sum_assignment(cost_matrix)
    else:
        row_ind, col_ind = np.array([], dtype=int), np.array([], dtype=int)

    matched_annotations = set()
    matched_holes = set()
    results = []
    ambiguous = []
    match_counter = 0

    for r, c in zip(row_ind, col_ind):
        score_result = score_details[(r, c)]
        total_score = score_result["total_score"]

        if total_score < MATCH_CONFIDENCE_THRESHOLD:
            continue

        ann = expanded_annotations[r]
        hole = holes[c]

        # Prevent duplicate hole assignments (safety check)
        if hole.id in matched_holes:
            continue

        match_counter += 1
        results.append(_create_match_result(match_counter, ann, hole, score_result))
        matched_annotations.add(ann.id)
        matched_holes.add(hole.id)

        if total_score < LLM_REVIEW_THRESHOLD:
            ambiguous.append(results[-1])

    # Collect unmatched items
    unmatched_ann = [a for a in hole_annotations if a.id not in matched_annotations]
    unmatched_holes = [h for h in holes if h.id not in matched_holes]

    if ambiguous:
        logger.info(
            f"{len(ambiguous)} matches below confidence threshold "
            f"({LLM_REVIEW_THRESHOLD}) flagged for review"
        )

    # LLM disambiguation for unmatched annotations (if enabled)
    if use_llm_resolver and unmatched_ann and unmatched_holes:
        try:
            llm_results = resolve_ambiguous_matches(
                unmatched_ann, unmatched_holes, pdf_path
            )
            for llm_match in llm_results:
                if llm_match.confidence >= MATCH_CONFIDENCE_THRESHOLD:
                    results.append(llm_match)
                    matched_annotations.add(llm_match.annotation_id)
                    matched_holes.add(llm_match.feature_id)
            # Re-collect unmatched after LLM resolution
            unmatched_ann = [a for a in hole_annotations if a.id not in matched_annotations]
            unmatched_holes = [h for h in holes if h.id not in matched_holes]
            if llm_results:
                logger.info(f"LLM resolver resolved {len(llm_results)} additional matches")
        except Exception as e:
            logger.warning(f"LLM resolver failed: {e}")

    return results, unmatched_ann, unmatched_holes


def _associate_depths(
    hole_annotations: list[PDFAnnotation],
    depth_annotations: list[PDFAnnotation],
) -> None:
    """Associate standalone depth annotations with nearest hole annotation.

    Uses both vertical and horizontal proximity to handle different drawing
    layouts (vertical stacking, horizontal leader lines, or mixed).
    """
    for depth_ann in depth_annotations:
        best_dist = float("inf")
        best_hole_ann = None

        # Depth annotation center
        dc_x = (depth_ann.bbox.x0 + depth_ann.bbox.x1) / 2
        dc_y = (depth_ann.bbox.y0 + depth_ann.bbox.y1) / 2

        for hole_ann in hole_annotations:
            if depth_ann.bbox.page != hole_ann.bbox.page:
                continue

            # Hole annotation center
            hc_x = (hole_ann.bbox.x0 + hole_ann.bbox.x1) / 2
            hc_y = (hole_ann.bbox.y0 + hole_ann.bbox.y1) / 2

            # Euclidean distance between annotation centers
            dist = ((dc_x - hc_x) ** 2 + (dc_y - hc_y) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_hole_ann = hole_ann

        if best_hole_ann and best_dist < 150:  # Within 150 points (covers horizontal layouts)
            if depth_ann.id not in best_hole_ann.associated_annotations:
                best_hole_ann.associated_annotations.append(depth_ann.id)
            # Transfer depth info
            if depth_ann.parsed.get("value"):
                best_hole_ann.parsed["depth"] = depth_ann.parsed["value"]
            if depth_ann.is_through:
                best_hole_ann.is_through = True


def _create_match_result(
    counter: int,
    annotation: PDFAnnotation,
    hole: HoleGroup,
    score_result: dict,
) -> MatchResult:
    """Create a MatchResult from an annotation-hole pair."""
    return MatchResult(
        id=f"match_{counter:03d}",
        annotation_id=annotation.id,
        feature_id=hole.id,
        annotation_text=annotation.raw_text,
        parsed_interpretation=annotation.parsed,
        feature_3d_ref={
            "hole_group_id": hole.id,
            "face_ids": [fid for feat in hole.features for fid in feat.face_ids],
            "primary_diameter_mm": hole.primary_diameter,
            "secondary_diameter_mm": hole.secondary_diameter,
            "center": list(hole.center),
            "axis_direction": list(hole.axis_direction),
            "total_depth_mm": hole.total_depth,
            "is_through_hole": hole.is_through_hole,
            "hole_type": hole.hole_type,
        },
        confidence=score_result["total_score"],
        scoring_breakdown=score_result["breakdown"],
        evidence={
            "bbox": annotation.bbox.model_dump(),
            "source": annotation.source,
            "multiplier": annotation.multiplier,
        },
    )


def _filter_vision_false_positives(
    annotations: list[PDFAnnotation],
    holes: list[HoleGroup],
) -> list[PDFAnnotation]:
    """Remove likely false-positive Vision LLM annotations.

    Vision LLM sometimes extracts overall part dimensions as diameter annotations.
    Filter out annotations from vision source that:
    - Have low confidence (< 0.9)
    - Have type DIAMETER (not thread, counterbore, etc.)
    - Have no matching 3D feature within wide tolerance
    """
    if not holes:
        return annotations

    # Collect all hole diameters (primary and secondary)
    hole_diameters = set()
    for h in holes:
        hole_diameters.add(round(h.primary_diameter, 1))
        if h.secondary_diameter:
            hole_diameters.add(round(h.secondary_diameter, 1))

    wide_tolerance = DIAMETER_TOLERANCE_MM * 3  # 1.5mm wide tolerance

    filtered = []
    for ann in annotations:
        # Only filter vision-sourced DIAMETER annotations with lower confidence
        if (ann.source == "vision"
            and ann.confidence < 0.9
            and ann.annotation_type == AnnotationType.DIAMETER
            and ann.multiplier <= 1):

            ann_d = ann.parsed.get("value")
            if ann_d is not None:
                try:
                    ann_d = float(ann_d)
                except (ValueError, TypeError):
                    filtered.append(ann)
                    continue

                # Check if any hole diameter is close
                has_match = any(
                    abs(ann_d - hd) < wide_tolerance
                    for hd in hole_diameters
                )
                if not has_match:
                    logger.debug(
                        f"Filtered vision FP: {ann.raw_text} "
                        f"(d={ann_d:.1f}mm, no matching 3D feature)"
                    )
                    continue  # Skip this annotation

        filtered.append(ann)

    if len(filtered) < len(annotations):
        logger.info(
            f"Filtered {len(annotations) - len(filtered)} vision false positives"
        )
    return filtered


def _get_annotation_diameter_for_cap(annotation: PDFAnnotation) -> float | None:
    """Get the expected physical diameter for multiplier capping.

    For threads, returns the drill diameter (physical hole size).
    For regular diameters, returns the value directly.
    """
    parsed = annotation.parsed
    if annotation.annotation_type == AnnotationType.THREAD:
        thread_spec = parsed.get("thread_spec", "")
        # Try to get drill diameter from thread table
        if thread_spec:
            from drawmind.cad.thread_table import get_thread_diameters
            diameters = get_thread_diameters(thread_spec.split("x")[0].split("X")[0].strip())
            if diameters:
                return diameters.get("drill_d", diameters.get("minor_d"))
        return parsed.get("nominal_diameter")
    elif annotation.annotation_type in (AnnotationType.DIAMETER, AnnotationType.HOLE_CALLOUT):
        v = parsed.get("value")
        return float(v) if v is not None else None
    elif annotation.annotation_type in (AnnotationType.COUNTERBORE, AnnotationType.COUNTERSINK):
        v = parsed.get("diameter")
        return float(v) if v is not None else None
    return None
