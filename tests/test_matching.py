"""Tests for annotation-to-feature matching."""

import pytest
from drawmind.matching.scoring import compute_match_score
from drawmind.matching.matcher import match_annotations_to_features
from drawmind.models import PDFAnnotation, AnnotationType, BoundingBox, HoleGroup, CylindricalFeature


class TestScoring:
    """Test match scoring functions."""

    def test_perfect_thread_match(self, sample_thread_annotation, sample_hole_group):
        """M10x1.5 should match a hole with pitch diameter 9.026mm."""
        score = compute_match_score(
            sample_thread_annotation,
            sample_hole_group,
            [sample_hole_group],
            [sample_thread_annotation],
        )
        assert score["total_score"] > 0.7
        assert score["breakdown"]["diameter"] > 0.8

    def test_diameter_mismatch(self, sample_thread_annotation):
        """M10 should NOT match a 20mm diameter hole."""
        feat = CylindricalFeature(
            id="feat_x", face_ids=[1], radius=10.0, diameter=20.0,
            center=(0, 0, 0), axis_direction=(0, 0, 1),
            estimated_depth=10.0, surface_area=100.0,
        )
        hole = HoleGroup(
            id="hole_x", features=[feat], primary_diameter=20.0,
            total_depth=10.0, center=(0, 0, 0), axis_direction=(0, 0, 1),
        )
        score = compute_match_score(
            sample_thread_annotation, hole, [hole], [sample_thread_annotation]
        )
        assert score["breakdown"]["diameter"] < 0.2

    def test_through_hole_score(self, sample_multiplier_annotation, sample_through_holes):
        """Through-hole annotation should score well against through-hole features."""
        score = compute_match_score(
            sample_multiplier_annotation,
            sample_through_holes[0],
            sample_through_holes,
            [sample_multiplier_annotation],
        )
        assert score["breakdown"]["depth"] > 0.8  # Through matches through
        assert score["breakdown"]["count_agreement"] > 0.8  # 4x matches 4 holes


class TestMatcher:
    """Test the full matching pipeline."""

    def test_basic_matching(self, sample_thread_annotation, sample_hole_group):
        matches, unmatched_ann, unmatched_holes = match_annotations_to_features(
            [sample_thread_annotation], [sample_hole_group]
        )
        assert len(matches) == 1
        assert matches[0].annotation_id == "ann_001"
        assert matches[0].feature_id == "hole_001"

    def test_multiplier_matching(self, sample_multiplier_annotation, sample_through_holes):
        """4x M8 should match all 4 through-holes."""
        matches, unmatched_ann, unmatched_holes = match_annotations_to_features(
            [sample_multiplier_annotation], sample_through_holes
        )
        assert len(matches) == 4
        matched_hole_ids = {m.feature_id for m in matches}
        assert len(matched_hole_ids) == 4

    def test_no_annotations(self, sample_hole_group):
        matches, unmatched_ann, unmatched_holes = match_annotations_to_features(
            [], [sample_hole_group]
        )
        assert len(matches) == 0
        assert len(unmatched_holes) == 1

    def test_no_holes(self, sample_thread_annotation):
        matches, unmatched_ann, unmatched_holes = match_annotations_to_features(
            [sample_thread_annotation], []
        )
        assert len(matches) == 0
        assert len(unmatched_ann) == 1

    def test_diameter_ratio_rejection(self, sample_thread_annotation):
        """M10 (10mm) should NOT match a 50mm hole (ratio > 2.5x)."""
        feat = CylindricalFeature(
            id="feat_big", face_ids=[1], radius=25.0, diameter=50.0,
            center=(0, 0, 0), axis_direction=(0, 0, 1),
            estimated_depth=10.0, surface_area=100.0,
        )
        hole = HoleGroup(
            id="hole_big", features=[feat], primary_diameter=50.0,
            total_depth=10.0, center=(0, 0, 0), axis_direction=(0, 0, 1),
        )
        matches, _, _ = match_annotations_to_features(
            [sample_thread_annotation], [hole]
        )
        assert len(matches) == 0

    def test_confidence_above_threshold(self, sample_thread_annotation, sample_hole_group):
        """All matches must have confidence >= MATCH_CONFIDENCE_THRESHOLD."""
        from drawmind.config import MATCH_CONFIDENCE_THRESHOLD
        matches, _, _ = match_annotations_to_features(
            [sample_thread_annotation], [sample_hole_group]
        )
        for m in matches:
            assert m.confidence >= MATCH_CONFIDENCE_THRESHOLD


class TestScoringEdgeCases:
    """Test edge cases in scoring."""

    def test_external_tolerance_penalized(self):
        """External tolerance class (lowercase letter) should score low."""
        ann = PDFAnnotation(
            id="ann_ext", raw_text="Ø10 h7",
            annotation_type=AnnotationType.DIAMETER,
            parsed={"value": 10.0, "tolerance_class": "h7"},
            bbox=BoundingBox(x0=0, y0=0, x1=50, y1=15, page=0),
        )
        feat = CylindricalFeature(
            id="feat_ext", face_ids=[1], radius=5.0, diameter=10.0,
            center=(0, 0, 0), axis_direction=(0, 0, 1),
            estimated_depth=10.0, surface_area=100.0,
        )
        hole = HoleGroup(
            id="hole_ext", features=[feat], primary_diameter=10.0,
            total_depth=10.0, center=(0, 0, 0), axis_direction=(0, 0, 1),
        )
        score = compute_match_score(ann, hole, [hole], [ann])
        # External tolerance = shaft, not a hole → low type_compatibility
        assert score["breakdown"]["type_compatibility"] <= 0.2

    def test_counterbore_type_match(self):
        """Counterbore annotation should score high on counterbore hole."""
        ann = PDFAnnotation(
            id="ann_cb", raw_text="⌳Ø18 ↧8",
            annotation_type=AnnotationType.COUNTERBORE,
            parsed={"diameter": 18.0, "depth": 8.0},
            bbox=BoundingBox(x0=0, y0=0, x1=50, y1=15, page=0),
        )
        feat1 = CylindricalFeature(
            id="feat_cb1", face_ids=[1], radius=5.0, diameter=10.0,
            center=(0, 0, 0), axis_direction=(0, 0, 1),
            estimated_depth=15.0, surface_area=100.0,
        )
        feat2 = CylindricalFeature(
            id="feat_cb2", face_ids=[2], radius=9.0, diameter=18.0,
            center=(0, 0, 0), axis_direction=(0, 0, 1),
            estimated_depth=8.0, surface_area=200.0,
        )
        hole = HoleGroup(
            id="hole_cb", features=[feat1, feat2], primary_diameter=10.0,
            secondary_diameter=18.0, total_depth=23.0,
            center=(0, 0, 0), axis_direction=(0, 0, 1),
            hole_type="counterbore",
        )
        score = compute_match_score(ann, hole, [hole], [ann])
        assert score["breakdown"]["type_compatibility"] == 1.0
        assert score["breakdown"]["diameter"] > 0.9
