"""Write pipeline results to JSON output file."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from drawmind.models import MatchResult, PDFAnnotation, HoleGroup, PipelineOutput
from drawmind.config import MATCH_CONFIDENCE_THRESHOLD, LLM_REVIEW_THRESHOLD
from drawmind import __version__


def write_output(
    matches: list[MatchResult],
    unmatched_annotations: list[PDFAnnotation],
    unmatched_holes: list[HoleGroup],
    output_path: str | Path,
    pdf_file: str = "",
    step_file: str = "",
    llm_enhanced: bool = False,
    stages: list[dict] | None = None,
    other_annotations: list[PDFAnnotation] | None = None,
) -> Path:
    """Write the complete pipeline output to a JSON file.

    Args:
        matches: List of matched annotation-feature pairs
        unmatched_annotations: Annotations that couldn't be matched
        unmatched_holes: Holes that have no matching annotation
        output_path: Path for the output JSON file
        pdf_file: Name of the input PDF file
        step_file: Name of the input STEP file
        llm_enhanced: Whether a model actually contributed to this result
        stages: Per-step outcome records from the pipeline

    Returns:
        Path to the written file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Classify matches by confidence level
    high_conf = [m for m in matches if m.confidence >= LLM_REVIEW_THRESHOLD]
    medium_conf = [
        m for m in matches if MATCH_CONFIDENCE_THRESHOLD <= m.confidence < LLM_REVIEW_THRESHOLD
    ]

    # Add confidence_level flag to each match
    features = []
    for m in matches:
        feat = m.model_dump()
        if m.confidence >= LLM_REVIEW_THRESHOLD:
            feat["confidence_level"] = "high"
        elif m.confidence >= MATCH_CONFIDENCE_THRESHOLD:
            feat["confidence_level"] = "review"
        features.append(feat)

    # Build quality warnings
    stages = stages or []
    warnings = []
    for stage in stages:
        if stage.get("status") == "failed":
            warnings.append(f"Step '{stage.get('name')}' failed: {stage.get('detail')}")
        elif stage.get("status") == "partial":
            warnings.append(
                f"Step '{stage.get('name')}' only partly succeeded: {stage.get('detail')}"
            )
        elif stage.get("status") == "skipped" and stage.get("name") == "ocr":
            warnings.append(f"OCR was not used: {stage.get('detail')}")
    if unmatched_annotations:
        warnings.append(
            f"{len(unmatched_annotations)} annotation(s) could not be matched to any 3D feature"
        )
    if unmatched_holes:
        warnings.append(f"{len(unmatched_holes)} 3D hole(s) have no matching annotation")
    if medium_conf:
        warnings.append(
            f"{len(medium_conf)} match(es) have medium confidence ({MATCH_CONFIDENCE_THRESHOLD:.0%}-{LLM_REVIEW_THRESHOLD:.0%}) and should be reviewed"
        )

    avg_conf = round(sum(m.confidence for m in matches) / len(matches), 3) if matches else 0.0

    output = PipelineOutput(
        metadata={
            "pdf_file": pdf_file,
            "step_file": step_file,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pipeline_version": __version__,
            "llm_enhanced": llm_enhanced,
            "stages": stages,
        },
        features=features,
        unmatched_annotations=[
            {
                "annotation_id": a.id,
                "text": a.raw_text,
                "type": a.annotation_type.value,
                "parsed": a.parsed,
                "bbox": a.bbox.model_dump(),
                "reason": "no_matching_3d_feature",
            }
            for a in unmatched_annotations
        ],
        unmatched_features=[
            {
                "hole_group_id": h.id,
                "face_ids": [fid for feat in h.features for fid in feat.face_ids],
                "primary_diameter_mm": h.primary_diameter,
                "secondary_diameter_mm": h.secondary_diameter,
                "total_depth_mm": h.total_depth,
                "center": list(h.center),
                "axis_direction": list(h.axis_direction),
                "hole_type": h.hole_type,
                "is_through_hole": h.is_through_hole,
                "reason": "no_matching_annotation",
            }
            for h in unmatched_holes
        ],
        other_annotations=[
            {
                "annotation_id": a.id,
                "text": a.raw_text,
                "type": a.annotation_type.value,
                "parsed": a.parsed,
                "bbox": a.bbox.model_dump(),
                "source": a.source,
            }
            for a in (other_annotations or [])
        ],
        summary={
            "total_annotations_found": len(
                {m.annotation_id for m in matches}
                | {a.id for a in unmatched_annotations}
                | {a.id for a in (other_annotations or [])}
            ),
            "other_annotations": len(other_annotations or []),
            "total_3d_holes": len(matches) + len(unmatched_holes),
            "matched": len(matches),
            "high_confidence": len(high_conf),
            "needs_review": len(medium_conf),
            "unmatched_annotations": len(unmatched_annotations),
            "unmatched_holes": len(unmatched_holes),
            "avg_confidence": avg_conf,
            "warnings": warnings,
        },
    )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output.model_dump(), f, indent=2, ensure_ascii=False)

    return output_path
