"""JSON output schema documentation and validation."""

# The output JSON follows this schema (for documentation purposes).
# The actual validation is done by Pydantic models in models.py.

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "metadata": {
            "type": "object",
            "properties": {
                "pdf_file": {"type": "string"},
                "step_file": {"type": "string"},
                "timestamp": {"type": "string", "format": "date-time"},
                "pipeline_version": {"type": "string"},
                "llm_enhanced": {"type": "boolean"},
            },
        },
        "features": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "annotation_id", "feature_id", "confidence"],
                "properties": {
                    "id": {"type": "string", "description": "Unique match ID"},
                    "annotation_id": {"type": "string"},
                    "feature_id": {"type": "string"},
                    "annotation_text": {"type": "string", "description": "Raw text from drawing"},
                    "parsed_interpretation": {
                        "type": "object",
                        "description": "Structured parsing of the annotation",
                    },
                    "feature_3d_ref": {
                        "type": "object",
                        "properties": {
                            "hole_group_id": {"type": "string"},
                            "face_ids": {"type": "array", "items": {"type": "integer"}},
                            "primary_diameter_mm": {"type": "number"},
                            "center": {"type": "array", "items": {"type": "number"}, "minItems": 3},
                            "axis_direction": {"type": "array", "items": {"type": "number"}},
                            "total_depth_mm": {"type": "number"},
                            "is_through_hole": {"type": "boolean"},
                            "hole_type": {"type": "string"},
                        },
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "scoring_breakdown": {"type": "object"},
                    "evidence": {
                        "type": "object",
                        "properties": {
                            "bbox": {"type": "object"},
                            "source": {"type": "string"},
                            "reasoning": {"type": "string"},
                        },
                    },
                },
            },
        },
        "unmatched_annotations": {"type": "array"},
        "unmatched_features": {"type": "array"},
        "summary": {
            "type": "object",
            "properties": {
                "total_annotations_found": {"type": "integer"},
                "total_3d_holes": {"type": "integer"},
                "matched": {"type": "integer"},
                "unmatched_annotations": {"type": "integer"},
                "unmatched_holes": {"type": "integer"},
                "avg_confidence": {"type": "number"},
            },
        },
    },
}
