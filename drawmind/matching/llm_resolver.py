"""LLM-based disambiguation for ambiguous annotation-to-feature matches."""

from __future__ import annotations

import json
import logging

from drawmind.models import PDFAnnotation, HoleGroup, MatchResult
from drawmind.llm.client import get_llm_client
from drawmind.llm.prompts import DISAMBIGUATE_BATCH_PROMPT, SYSTEM_ENGINEERING
from drawmind.config import DISAMBIGUATE_MODEL

logger = logging.getLogger(__name__)

# Max annotations per batch call to avoid token limits
_BATCH_SIZE = 10


def _clamp_confidence(value) -> float:
    """Coerce an LLM-supplied confidence into [0, 1]."""
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.5
    if confidence != confidence:  # NaN
        return 0.5
    if 10.0 <= confidence <= 100.0:
        confidence /= 100.0  # some models answer in percent
    return min(max(confidence, 0.0), 1.0)


def resolve_ambiguous_matches(
    ambiguous_annotations: list[PDFAnnotation],
    candidate_holes: list[HoleGroup],
    report: dict | None = None,
) -> list[MatchResult]:
    """Use LLM to resolve ambiguous matches in batches.

    Sends all unmatched annotations in a single (or few) LLM call(s)
    instead of one call per annotation, reducing cost by ~70%.

    Args:
        ambiguous_annotations: Annotations that couldn't be uniquely matched
        candidate_holes: All available hole groups
        report: Optional dict filled with ``batches`` and ``failed_batches``
            so the caller can tell "nothing to resolve" from "resolution failed"

    Returns:
        List of resolved MatchResult objects
    """
    if report is None:
        report = {}
    report.update(batches=0, failed_batches=0, error=None)

    client = get_llm_client()
    if not client.available:
        logger.warning("No LLM available for disambiguation")
        report["unavailable"] = "no model provider configured"
        return []

    if not ambiguous_annotations or not candidate_holes:
        return []

    # Build candidates JSON (shared across all annotations)
    candidates = []
    for hole in candidate_holes:
        cand = {
            "feature_id": hole.id,
            "primary_diameter_mm": round(hole.primary_diameter, 3),
            "total_depth_mm": round(hole.total_depth, 2) if hole.total_depth else None,
            "is_through_hole": hole.is_through_hole,
            "hole_type": hole.hole_type,
        }
        if hole.secondary_diameter:
            cand["secondary_diameter_mm"] = round(hole.secondary_diameter, 3)
        candidates.append(cand)

    candidates_json = json.dumps(candidates, indent=1)

    results = []

    # Process in batches
    for batch_start in range(0, len(ambiguous_annotations), _BATCH_SIZE):
        batch = ambiguous_annotations[batch_start : batch_start + _BATCH_SIZE]

        # Build annotations array for the batch
        ann_items = []
        for ann in batch:
            ann_items.append(
                {
                    "id": ann.id,
                    "text": ann.raw_text,
                    "type": ann.annotation_type.value,
                    "parsed": ann.parsed,
                }
            )

        annotations_json = json.dumps(ann_items, indent=1)

        prompt = DISAMBIGUATE_BATCH_PROMPT.format(
            annotations_json=annotations_json,
            candidates_json=candidates_json,
        )

        report["batches"] += 1
        try:
            result = client.complete_json(
                prompt,
                model=DISAMBIGUATE_MODEL,
                system=SYSTEM_ENGINEERING,
            )

            # Result should be a list of {annotation_id, feature_id, confidence, reasoning}
            if not isinstance(result, list):
                result = [result]

            for item in result:
                if not isinstance(item, dict):
                    continue
                ann_id = item.get("annotation_id")
                feature_id = item.get("feature_id")
                confidence = _clamp_confidence(item.get("confidence", 0.5))

                if not ann_id or not feature_id:
                    continue

                # Find matching annotation and hole
                ann = next((a for a in batch if a.id == ann_id), None)
                hole = next((h for h in candidate_holes if h.id == feature_id), None)

                if ann and hole:
                    match_counter = len(results) + 1
                    results.append(
                        MatchResult(
                            id=f"llm_match_{match_counter:03d}",
                            annotation_id=ann.id,
                            feature_id=hole.id,
                            annotation_text=ann.raw_text,
                            parsed_interpretation=ann.parsed,
                            feature_3d_ref={
                                "hole_group_id": hole.id,
                                "face_ids": [fid for f in hole.features for fid in f.face_ids],
                                "primary_diameter_mm": hole.primary_diameter,
                                "secondary_diameter_mm": hole.secondary_diameter,
                                "center": list(hole.center),
                                "axis_direction": list(hole.axis_direction),
                                "total_depth_mm": hole.total_depth,
                                "is_through_hole": hole.is_through_hole,
                                "hole_type": hole.hole_type,
                            },
                            confidence=confidence,
                            scoring_breakdown={"llm_resolved": True},
                            evidence={
                                "bbox": ann.bbox.model_dump(),
                                "source": "llm_disambiguation",
                                "reasoning": item.get("reasoning", ""),
                            },
                        )
                    )

        except Exception as e:
            logger.error(f"LLM batch disambiguation failed: {e}")
            report["failed_batches"] += 1
            report["error"] = str(e)

    return results
