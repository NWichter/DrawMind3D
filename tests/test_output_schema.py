"""The documented output schema has to accept what the product emits."""

import json
import tempfile
import unittest
from pathlib import Path

from drawmind.models import (
    AnnotationType,
    BoundingBox,
    CylindricalFeature,
    HoleGroup,
    MatchResult,
    PDFAnnotation,
)
from drawmind.output.schema import OUTPUT_SCHEMA
from drawmind.output.writer import write_output

jsonschema = None
try:
    import jsonschema
except ImportError:
    pass


def _annotation(ann_id: str, ann_type: AnnotationType, source: str) -> PDFAnnotation:
    return PDFAnnotation(
        id=ann_id,
        raw_text="M8x1.25",
        annotation_type=ann_type,
        parsed={"nominal_diameter": 8.0, "pitch": 1.25},
        bbox=BoundingBox(x0=10, y0=20, x1=60, y1=32, page=0),
        source=source,
    )


def _hole(hole_id: str) -> HoleGroup:
    feature = CylindricalFeature(
        id=f"{hole_id}_f0",
        face_ids=[3],
        radius=4.0,
        diameter=8.0,
        center=(0.0, 0.0, 0.0),
        axis_direction=(0.0, 0.0, 1.0),
        estimated_depth=12.0,
        surface_area=301.6,
    )
    return HoleGroup(
        id=hole_id,
        features=[feature],
        primary_diameter=8.0,
        total_depth=12.0,
        center=(0.0, 0.0, 0.0),
        axis_direction=(0.0, 0.0, 1.0),
        hole_type="simple",
    )


def _match(annotation: PDFAnnotation, hole: HoleGroup) -> MatchResult:
    return MatchResult(
        id="match_001",
        annotation_id=annotation.id,
        feature_id=hole.id,
        annotation_text=annotation.raw_text,
        parsed_interpretation=annotation.parsed,
        feature_3d_ref={
            "hole_group_id": hole.id,
            "face_ids": [3],
            "primary_diameter_mm": hole.primary_diameter,
            "secondary_diameter_mm": None,
            "center": list(hole.center),
            "axis_direction": list(hole.axis_direction),
            "total_depth_mm": hole.total_depth,
            "is_through_hole": False,
            "hole_type": hole.hole_type,
        },
        confidence=0.91,
        scoring_breakdown={"diameter": 1.0, "depth": 0.8},
        evidence={
            "bbox": annotation.bbox.model_dump(),
            "source": annotation.source,
            "multiplier": 1,
        },
    )


@unittest.skipIf(jsonschema is None, "jsonschema not installed")
class TestOutputSchema(unittest.TestCase):
    def _write_and_validate(self, **kwargs) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_output(output_path=Path(tmp) / "result.json", **kwargs)
            payload = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.validate(payload, OUTPUT_SCHEMA)
        return payload

    def test_every_real_source_value_validates(self):
        """The enum must cover the sources the pipeline actually sets."""
        hole = _hole("hole_001")
        for source in ("native", "ocr_tesseract", "vision_llm", "llm_disambiguation"):
            with self.subTest(source=source):
                annotation = _annotation("ann_001", AnnotationType.THREAD, source)
                self._write_and_validate(
                    matches=[_match(annotation, hole)],
                    unmatched_annotations=[],
                    unmatched_holes=[],
                    pdf_file="drawing.pdf",
                    step_file="model.stp",
                )

    def test_stages_and_other_annotations_validate(self):
        hole = _hole("hole_001")
        annotation = _annotation("ann_001", AnnotationType.THREAD, "native")
        depth = _annotation("ann_002", AnnotationType.DEPTH, "native")

        payload = self._write_and_validate(
            matches=[_match(annotation, hole)],
            unmatched_annotations=[],
            unmatched_holes=[_hole("hole_002")],
            pdf_file="drawing.pdf",
            step_file="model.stp",
            llm_enhanced=False,
            stages=[
                {"name": "text_extraction", "status": "ok", "detail": "12 native"},
                {"name": "vision_llm", "status": "skipped", "detail": "disabled by caller"},
                {"name": "ocr", "status": "failed", "detail": "tesseract missing"},
            ],
            other_annotations=[depth],
        )

        self.assertEqual(len(payload["other_annotations"]), 1)
        self.assertEqual(payload["summary"]["other_annotations"], 1)
        self.assertEqual(payload["summary"]["total_annotations_found"], 2)
        self.assertTrue(
            any("ocr" in w for w in payload["summary"]["warnings"]),
            "a failed stage must surface as a warning",
        )

    def test_empty_run_validates(self):
        self._write_and_validate(
            matches=[],
            unmatched_annotations=[],
            unmatched_holes=[],
            pdf_file="drawing.pdf",
            step_file="model.stp",
        )


if __name__ == "__main__":
    unittest.main()
