"""JSON output schema documentation and validation."""

# The output JSON follows this schema (for documentation purposes).
# The actual validation is done by Pydantic models in models.py.

OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["metadata", "features", "unmatched_annotations", "unmatched_features", "summary"],
    "properties": {
        "metadata": {
            "type": "object",
            "required": ["pdf_file", "step_file", "timestamp", "pipeline_version", "llm_enhanced"],
            "properties": {
                "pdf_file": {"type": "string", "description": "Input PDF filename"},
                "step_file": {"type": "string", "description": "Input STEP filename"},
                "timestamp": {
                    "type": "string",
                    "format": "date-time",
                    "description": "ISO 8601 UTC timestamp",
                },
                "pipeline_version": {"type": "string", "description": "DrawMind3D version"},
                "llm_enhanced": {"type": "boolean", "description": "Whether Vision LLM was used"},
            },
        },
        "features": {
            "type": "array",
            "description": "Matched annotation-to-feature pairs",
            "items": {
                "type": "object",
                "required": ["id", "annotation_id", "feature_id", "annotation_text", "confidence"],
                "properties": {
                    "id": {"type": "string", "description": "Unique match ID (e.g. match_001)"},
                    "annotation_id": {
                        "type": "string",
                        "description": "Reference to source annotation",
                    },
                    "feature_id": {"type": "string", "description": "Reference to 3D hole group"},
                    "annotation_text": {
                        "type": "string",
                        "description": "Raw annotation text from drawing (e.g. M10x1.5-6H)",
                    },
                    "parsed_interpretation": {
                        "type": "object",
                        "description": "Structured parsing: thread type, size, pitch, tolerance class, depth",
                    },
                    "feature_3d_ref": {
                        "type": "object",
                        "description": "3D feature reference sufficient to re-locate the hole",
                        "properties": {
                            "hole_group_id": {
                                "type": "string",
                                "description": "Coaxial hole group ID",
                            },
                            "face_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "B-Rep face indices",
                            },
                            "primary_diameter_mm": {
                                "type": "number",
                                "description": "Main hole diameter in mm",
                            },
                            "secondary_diameter_mm": {
                                "type": ["number", "null"],
                                "description": "Outer diameter for counterbore/countersink",
                            },
                            "center": {
                                "type": "array",
                                "items": {"type": "number"},
                                "minItems": 3,
                                "maxItems": 3,
                                "description": "3D center point [x, y, z] in mm",
                            },
                            "axis_direction": {
                                "type": "array",
                                "items": {"type": "number"},
                                "minItems": 3,
                                "maxItems": 3,
                                "description": "Normalized hole axis direction [dx, dy, dz]",
                            },
                            "total_depth_mm": {
                                "type": "number",
                                "description": "Total hole depth in mm",
                            },
                            "is_through_hole": {
                                "type": "boolean",
                                "description": "Whether hole passes through entire body",
                            },
                            "hole_type": {
                                "type": "string",
                                "enum": ["simple", "counterbore", "countersink", "stepped"],
                                "description": "Hole geometry classification",
                            },
                        },
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "Match confidence score (0-1)",
                    },
                    "confidence_level": {
                        "type": "string",
                        "enum": ["high", "review"],
                        "description": "high (>=0.8) or review (0.6-0.8)",
                    },
                    "scoring_breakdown": {
                        "type": "object",
                        "description": "Per-factor scoring details",
                        "properties": {
                            "diameter": {
                                "type": "number",
                                "description": "Diameter match score (weight: 45%)",
                            },
                            "depth": {
                                "type": "number",
                                "description": "Depth match score (weight: 18%)",
                            },
                            "type_compatibility": {
                                "type": "number",
                                "description": "Type compatibility score (weight: 22%)",
                            },
                            "count_agreement": {
                                "type": "number",
                                "description": "Count agreement score (weight: 8%)",
                            },
                            "uniqueness": {
                                "type": "number",
                                "description": "Uniqueness bonus (weight: 4%)",
                            },
                            "spatial": {
                                "type": "number",
                                "description": "Spatial correlation score (weight: 3%)",
                            },
                            "source_confidence": {
                                "type": "number",
                                "description": "Annotation source confidence (1.0 for native, <1 for vision)",
                            },
                        },
                    },
                    "evidence": {
                        "type": "object",
                        "description": "Evidence trace linking to drawing region",
                        "properties": {
                            "bbox": {
                                "type": "object",
                                "description": "Bounding box in PDF coordinates",
                                "properties": {
                                    "x0": {"type": "number"},
                                    "y0": {"type": "number"},
                                    "x1": {"type": "number"},
                                    "y1": {"type": "number"},
                                    "page": {
                                        "type": "integer",
                                        "description": "0-indexed page number",
                                    },
                                },
                            },
                            "source": {
                                "type": "string",
                                "enum": ["native", "ocr", "vision_llm"],
                                "description": "How annotation was detected",
                            },
                            "multiplier": {
                                "type": "integer",
                                "description": "Annotation multiplier (e.g. 4 for '4x M8')",
                            },
                        },
                    },
                },
            },
        },
        "unmatched_annotations": {
            "type": "array",
            "description": "Annotations with no matching 3D feature",
            "items": {
                "type": "object",
                "properties": {
                    "annotation_id": {"type": "string"},
                    "text": {"type": "string"},
                    "type": {"type": "string"},
                    "parsed": {"type": "object"},
                    "bbox": {"type": "object"},
                    "reason": {"type": "string"},
                },
            },
        },
        "unmatched_features": {
            "type": "array",
            "description": "3D hole features with no matching annotation",
            "items": {
                "type": "object",
                "properties": {
                    "hole_group_id": {"type": "string"},
                    "face_ids": {"type": "array", "items": {"type": "integer"}},
                    "primary_diameter_mm": {"type": "number"},
                    "secondary_diameter_mm": {"type": ["number", "null"]},
                    "total_depth_mm": {"type": "number"},
                    "center": {"type": "array", "items": {"type": "number"}, "minItems": 3},
                    "axis_direction": {"type": "array", "items": {"type": "number"}, "minItems": 3},
                    "hole_type": {"type": "string"},
                    "is_through_hole": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
            },
        },
        "summary": {
            "type": "object",
            "properties": {
                "total_annotations_found": {"type": "integer"},
                "total_3d_holes": {"type": "integer"},
                "matched": {"type": "integer"},
                "high_confidence": {
                    "type": "integer",
                    "description": "Matches with confidence >= 0.8",
                },
                "needs_review": {
                    "type": "integer",
                    "description": "Matches with confidence 0.6-0.8",
                },
                "unmatched_annotations": {"type": "integer"},
                "unmatched_holes": {"type": "integer"},
                "avg_confidence": {"type": "number"},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}
