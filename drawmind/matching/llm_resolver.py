"""LLM-based disambiguation for ambiguous annotation-to-feature matches."""

from __future__ import annotations

import json
import logging

from drawmind.models import PDFAnnotation, HoleGroup, MatchResult
from drawmind.llm.client import get_llm_client
from drawmind.llm.prompts import DISAMBIGUATE_PROMPT, SYSTEM_ENGINEERING
from drawmind.config import DISAMBIGUATE_MODEL

logger = logging.getLogger(__name__)


def resolve_ambiguous_matches(
    ambiguous_annotations: list[PDFAnnotation],
    candidate_holes: list[HoleGroup],
    pdf_path: str | None = None,
) -> list[MatchResult]:
    """Use LLM to resolve ambiguous matches.

    Args:
        ambiguous_annotations: Annotations that couldn't be uniquely matched
        candidate_holes: All available hole groups
        pdf_path: Path to PDF for image context (optional)

    Returns:
        List of resolved MatchResult objects
    """
    client = get_llm_client()
    if not client.available:
        logger.warning("No LLM available for disambiguation")
        return []

    results = []

    for ann in ambiguous_annotations:
        # Build candidates JSON
        candidates = []
        for hole in candidate_holes:
            candidates.append({
                "feature_id": hole.id,
                "primary_diameter_mm": hole.primary_diameter,
                "total_depth_mm": hole.total_depth,
                "center": list(hole.center),
                "axis_direction": list(hole.axis_direction),
                "is_through_hole": hole.is_through_hole,
                "hole_type": hole.hole_type,
                "num_features": len(hole.features),
            })

        prompt = DISAMBIGUATE_PROMPT.format(
            annotation_text=ann.raw_text,
            annotation_type=ann.annotation_type.value,
            parsed_data=json.dumps(ann.parsed),
            bbox=ann.bbox.model_dump(),
            candidates_json=json.dumps(candidates, indent=2),
        )

        try:
            # Include PDF image if available
            images = None
            if pdf_path:
                from drawmind.pdf.extractor import get_page_as_image
                images = [get_page_as_image(pdf_path, ann.bbox.page, dpi=150)]

            result = client.complete_json(
                prompt,
                model=DISAMBIGUATE_MODEL,
                images=images,
                system=SYSTEM_ENGINEERING,
            )

            feature_id = result.get("feature_id")
            confidence = result.get("confidence", 0.5)
            reasoning = result.get("reasoning", "")

            # Find the matching hole
            matched_hole = next((h for h in candidate_holes if h.id == feature_id), None)
            if matched_hole:
                match_counter = len(results) + 1
                results.append(MatchResult(
                    id=f"llm_match_{match_counter:03d}",
                    annotation_id=ann.id,
                    feature_id=matched_hole.id,
                    annotation_text=ann.raw_text,
                    parsed_interpretation=ann.parsed,
                    feature_3d_ref={
                        "hole_group_id": matched_hole.id,
                        "face_ids": [fid for f in matched_hole.features for fid in f.face_ids],
                        "primary_diameter_mm": matched_hole.primary_diameter,
                        "center": list(matched_hole.center),
                        "axis_direction": list(matched_hole.axis_direction),
                        "total_depth_mm": matched_hole.total_depth,
                        "is_through_hole": matched_hole.is_through_hole,
                        "hole_type": matched_hole.hole_type,
                    },
                    confidence=confidence,
                    scoring_breakdown={"llm_resolved": True},
                    evidence={
                        "bbox": ann.bbox.model_dump(),
                        "source": "llm_disambiguation",
                        "reasoning": reasoning,
                    },
                ))

        except Exception as e:
            logger.error(f"LLM disambiguation failed for {ann.id}: {e}")

    return results
