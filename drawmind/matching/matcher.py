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
from drawmind.config import MATCH_CONFIDENCE_THRESHOLD, LLM_REVIEW_THRESHOLD

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

    # Expand multiplier annotations into virtual copies for unified Hungarian
    # e.g., "4X Ø8" becomes 4 entries so Hungarian can optimally assign each
    expanded_annotations = []
    for ann in hole_annotations:
        count = max(ann.multiplier, 1)
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
