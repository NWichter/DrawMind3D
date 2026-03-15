"""Tests for JSON output generation."""

import json

import pytest

from drawmind.models import (
    PDFAnnotation,
    AnnotationType,
    BoundingBox,
    CylindricalFeature,
    HoleGroup,
    MatchResult,
)
from drawmind.output.writer import write_output


@pytest.fixture
def sample_match():
    return MatchResult(
        id="match_001",
        annotation_id="ann_001",
        feature_id="hole_001",
        annotation_text="M10x1.5-6H",
        parsed_interpretation={"nominal_diameter": 10.0, "pitch": 1.5},
        feature_3d_ref={
            "hole_group_id": "hole_001",
            "face_ids": [10],
            "primary_diameter_mm": 9.026,
            "center": [25.0, 0.0, 15.0],
            "axis_direction": [0.0, 0.0, 1.0],
            "total_depth_mm": 20.0,
            "is_through_hole": False,
            "hole_type": "simple",
        },
        confidence=0.92,
        scoring_breakdown={"diameter": 0.95, "depth": 0.8, "type_compatibility": 1.0},
        evidence={
            "bbox": {"x0": 100, "y0": 50, "x1": 180, "y1": 65, "page": 0},
            "source": "native",
        },
    )


@pytest.fixture
def sample_unmatched_ann():
    return PDFAnnotation(
        id="ann_099",
        raw_text="Ø50",
        annotation_type=AnnotationType.DIAMETER,
        parsed={"value": 50.0},
        bbox=BoundingBox(x0=0, y0=0, x1=50, y1=15, page=0),
    )


@pytest.fixture
def sample_unmatched_hole():
    feat = CylindricalFeature(
        id="feat_099",
        face_ids=[99],
        radius=3.0,
        diameter=6.0,
        center=(0, 0, 0),
        axis_direction=(0, 0, 1),
        estimated_depth=10.0,
        surface_area=100.0,
    )
    return HoleGroup(
        id="hole_099",
        features=[feat],
        primary_diameter=6.0,
        total_depth=10.0,
        center=(0, 0, 0),
        axis_direction=(0, 0, 1),
    )


class TestOutputWriter:
    def test_writes_valid_json(self, sample_match, tmp_path):
        out = tmp_path / "result.json"
        write_output([sample_match], [], [], out, "test.pdf", "test.stp")
        data = json.loads(out.read_text())
        assert "metadata" in data
        assert "features" in data
        assert "summary" in data
        assert data["metadata"]["pipeline_version"] == "1.0.0"

    def test_confidence_level_high(self, sample_match, tmp_path):
        out = tmp_path / "result.json"
        write_output([sample_match], [], [], out)
        data = json.loads(out.read_text())
        assert data["features"][0]["confidence_level"] == "high"

    def test_confidence_level_review(self, sample_match, tmp_path):
        sample_match.confidence = 0.65
        out = tmp_path / "result.json"
        write_output([sample_match], [], [], out)
        data = json.loads(out.read_text())
        assert data["features"][0]["confidence_level"] == "review"

    def test_summary_counts(
        self, sample_match, sample_unmatched_ann, sample_unmatched_hole, tmp_path
    ):
        out = tmp_path / "result.json"
        write_output([sample_match], [sample_unmatched_ann], [sample_unmatched_hole], out)
        data = json.loads(out.read_text())
        s = data["summary"]
        assert s["matched"] == 1
        assert s["unmatched_annotations"] == 1
        assert s["unmatched_holes"] == 1
        assert s["high_confidence"] == 1

    def test_warnings_generated(self, sample_match, sample_unmatched_ann, tmp_path):
        sample_match.confidence = 0.65
        out = tmp_path / "result.json"
        write_output([sample_match], [sample_unmatched_ann], [], out)
        data = json.loads(out.read_text())
        warnings = data["summary"]["warnings"]
        assert any("could not be matched" in w for w in warnings)
        assert any("review" in w for w in warnings)

    def test_unmatched_has_reason(
        self, sample_match, sample_unmatched_ann, sample_unmatched_hole, tmp_path
    ):
        out = tmp_path / "result.json"
        write_output([sample_match], [sample_unmatched_ann], [sample_unmatched_hole], out)
        data = json.loads(out.read_text())
        assert data["unmatched_annotations"][0]["reason"] == "no_matching_3d_feature"
        assert data["unmatched_features"][0]["reason"] == "no_matching_annotation"

    def test_empty_matches(self, tmp_path):
        out = tmp_path / "result.json"
        write_output([], [], [], out)
        data = json.loads(out.read_text())
        assert data["summary"]["matched"] == 0
        assert data["summary"]["avg_confidence"] == 0.0
        assert data["summary"]["warnings"] == []

    def test_llm_enhanced_flag(self, sample_match, tmp_path):
        out = tmp_path / "result.json"
        write_output([sample_match], [], [], out, llm_enhanced=True)
        data = json.loads(out.read_text())
        assert data["metadata"]["llm_enhanced"] is True
