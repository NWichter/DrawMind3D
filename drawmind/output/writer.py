"""Write pipeline results to JSON output file."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from drawmind.models import MatchResult, PDFAnnotation, HoleGroup, PipelineOutput
from drawmind import __version__


def write_output(
    matches: list[MatchResult],
    unmatched_annotations: list[PDFAnnotation],
    unmatched_holes: list[HoleGroup],
    output_path: str | Path,
    pdf_file: str = "",
    step_file: str = "",
    llm_enhanced: bool = False,
) -> Path:
    """Write the complete pipeline output to a JSON file.

    Args:
        matches: List of matched annotation-feature pairs
        unmatched_annotations: Annotations that couldn't be matched
        unmatched_holes: Holes that have no matching annotation
        output_path: Path for the output JSON file
        pdf_file: Name of the input PDF file
        step_file: Name of the input STEP file
        llm_enhanced: Whether LLM was used in the pipeline

    Returns:
        Path to the written file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output = PipelineOutput(
        metadata={
            "pdf_file": pdf_file,
            "step_file": step_file,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pipeline_version": __version__,
            "llm_enhanced": llm_enhanced,
        },
        features=[m.model_dump() for m in matches],
        unmatched_annotations=[
            {
                "annotation_id": a.id,
                "text": a.raw_text,
                "type": a.annotation_type.value,
                "parsed": a.parsed,
                "bbox": a.bbox.model_dump(),
            }
            for a in unmatched_annotations
        ],
        unmatched_features=[
            {
                "hole_group_id": h.id,
                "primary_diameter_mm": h.primary_diameter,
                "total_depth_mm": h.total_depth,
                "center": list(h.center),
                "hole_type": h.hole_type,
                "is_through_hole": h.is_through_hole,
            }
            for h in unmatched_holes
        ],
        summary={
            "total_annotations_found": len(matches) + len(unmatched_annotations),
            "total_3d_holes": len(matches) + len(unmatched_holes),
            "matched": len(matches),
            "unmatched_annotations": len(unmatched_annotations),
            "unmatched_holes": len(unmatched_holes),
            "avg_confidence": (
                round(sum(m.confidence for m in matches) / len(matches), 3)
                if matches else 0.0
            ),
        },
    )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output.model_dump(), f, indent=2, ensure_ascii=False)

    return output_path


def generate_summary_text(output: PipelineOutput) -> str:
    """Generate a human-readable summary of the pipeline results."""
    s = output.summary
    lines = [
        "=== DrawMind3D Pipeline Summary ===",
        f"PDF: {output.metadata.get('pdf_file', 'N/A')}",
        f"STEP: {output.metadata.get('step_file', 'N/A')}",
        f"LLM Enhanced: {output.metadata.get('llm_enhanced', False)}",
        "",
        f"Annotations found: {s.get('total_annotations_found', 0)}",
        f"3D holes found: {s.get('total_3d_holes', 0)}",
        f"Matched pairs: {s.get('matched', 0)}",
        f"Unmatched annotations: {s.get('unmatched_annotations', 0)}",
        f"Unmatched holes: {s.get('unmatched_holes', 0)}",
        f"Average confidence: {s.get('avg_confidence', 0):.1%}",
        "",
    ]

    if output.features:
        lines.append("--- Matches ---")
        for feat in output.features:
            conf = feat.get("confidence", 0) if isinstance(feat, dict) else feat.confidence
            text = feat.get("annotation_text", "") if isinstance(feat, dict) else feat.annotation_text
            fid = feat.get("feature_id", "") if isinstance(feat, dict) else feat.feature_id
            lines.append(f"  [{conf:.0%}] '{text}' -> {fid}")

    return "\n".join(lines)
