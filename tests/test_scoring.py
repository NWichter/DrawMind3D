"""Tests for the individual scoring factors."""

import pytest

from drawmind.matching.scoring import _format_thread_spec, _score_count, _score_spatial
from drawmind.models import (
    AnnotationType,
    BoundingBox,
    CylindricalFeature,
    HoleGroup,
    PDFAnnotation,
)


def _annotation(ann_type, parsed, bbox=None, multiplier=1, page=0):
    return PDFAnnotation(
        id="ann_001",
        raw_text="test",
        annotation_type=ann_type,
        parsed=parsed,
        bbox=bbox or BoundingBox(x0=0, y0=0, x1=10, y1=10, page=page),
        multiplier=multiplier,
    )


def _hole(hid, diameter, center):
    feat = CylindricalFeature(
        id=f"feat_{hid}",
        face_ids=[1],
        radius=diameter / 2,
        diameter=diameter,
        center=center,
        axis_direction=(0.0, 0.0, 1.0),
        estimated_depth=10.0,
        surface_area=100.0,
    )
    return HoleGroup(
        id=hid,
        features=[feat],
        primary_diameter=diameter,
        total_depth=10.0,
        center=center,
        axis_direction=(0.0, 0.0, 1.0),
    )


class TestCountFactor:
    def test_wrong_diameter_family_is_not_rewarded(self):
        """'4x Ø5' must not score a perfect count against an 8 mm hole."""
        holes = [_hole(f"h{i}", 8.0, (i * 20.0, 0.0, 0.0)) for i in range(4)]
        holes += [_hole(f"m{i}", 5.0, (i * 20.0, 40.0, 0.0)) for i in range(6)]
        annotation = _annotation(AnnotationType.DIAMETER, {"value": 5.0}, multiplier=4)

        wrong = _score_count(annotation, holes[0], holes)
        assert wrong < 1.0, "count factor rewarded a hole from the wrong diameter family"

    def test_matching_family_still_scores_well(self):
        holes = [_hole(f"h{i}", 8.0, (i * 20.0, 0.0, 0.0)) for i in range(4)]
        annotation = _annotation(AnnotationType.DIAMETER, {"value": 8.0}, multiplier=4)
        assert _score_count(annotation, holes[0], holes) == 1.0

    def test_no_multiplier_is_neutral(self):
        holes = [_hole("h0", 8.0, (0.0, 0.0, 0.0))]
        annotation = _annotation(AnnotationType.DIAMETER, {"value": 8.0})
        assert _score_count(annotation, holes[0], holes) == pytest.approx(0.5)


class TestSpatialFactor:
    """Leader targets and bbox centres must share one coordinate frame."""

    def _landscape_setup(self):
        # A3 landscape is 1191 x 842 pt, far from the Letter portrait literals.
        corner = BoundingBox(x0=0, y0=0, x1=1191, y1=842, page=0)
        others = [_annotation(AnnotationType.DIAMETER, {"value": 8.0}, corner)]
        # Spread over two axes, otherwise every projection is degenerate.
        holes = [
            _hole("h_left", 8.0, (0.0, 0.0, 0.0)),
            _hole("h_right", 8.0, (100.0, 50.0, 0.0)),
        ]
        return others, holes

    def test_leader_target_uses_the_same_page_size_as_the_bbox(self):
        others, holes = self._landscape_setup()
        bbox = BoundingBox(x0=890, y0=400, x1=910, y1=420, page=0)

        plain = _annotation(AnnotationType.DIAMETER, {"value": 8.0}, bbox)
        with_leader = _annotation(
            AnnotationType.DIAMETER,
            {"value": 8.0, "leader_target": {"x": 900.0, "y": 410.0}},
            bbox,
        )
        all_anns = others + [plain]

        assert _score_spatial(with_leader, holes[1], holes, all_anns) == pytest.approx(
            _score_spatial(plain, holes[1], holes, all_anns)
        ), "leader target normalized against a different page size than the bbox"

    def test_leader_target_overrides_the_bbox_position(self):
        """The callout text sits right; its leader points at the left hole."""
        others, holes = self._landscape_setup()
        bbox = BoundingBox(x0=1100, y0=760, x1=1150, y1=790, page=0)
        annotation = _annotation(
            AnnotationType.DIAMETER,
            {"value": 8.0, "leader_target": {"x": 40.0, "y": 30.0}},
            bbox,
        )
        all_anns = others + [annotation]

        left = _score_spatial(annotation, holes[0], holes, all_anns)
        right = _score_spatial(annotation, holes[1], holes, all_anns)
        assert left > right, "leader pointing at the left hole scored the right one higher"


class TestAssignment:
    """Below-threshold pairs must not consume a hole another annotation needs."""

    def test_swap_that_yields_two_matches_is_found(self):
        from drawmind.matching.matcher import match_annotations_to_features

        a = _annotation(AnnotationType.DIAMETER, {"value": 10.0, "depth": 10.0})
        a.id = "A"
        b = _annotation(AnnotationType.DIAMETER, {"value": 10.2, "depth": 8.0})
        b.id = "B"
        b.bbox = BoundingBox(x0=300, y0=0, x1=320, y1=20, page=0)

        holes = [_hole("H1", 10.0, (0.0, 0.0, 0.0)), _hole("H2", 10.0, (100.0, 0.0, 0.0))]
        holes[1].total_depth = 20.0
        holes[1].features[0].estimated_depth = 20.0

        matches, unmatched, _ = match_annotations_to_features([a, b], holes, use_llm_resolver=False)

        # A->H1 scores highest but strands B; A->H2 plus B->H1 keeps both.
        assert len(matches) == 2, f"only {len(matches)} matched, {[u.id for u in unmatched]} lost"

    def test_genuinely_unmatchable_annotation_stays_unmatched(self):
        from drawmind.matching.matcher import match_annotations_to_features

        annotation = _annotation(AnnotationType.DIAMETER, {"value": 10.0})
        annotation.id = "A"
        holes = [_hole("H1", 40.0, (0.0, 0.0, 0.0))]

        matches, unmatched, _ = match_annotations_to_features(
            [annotation], holes, use_llm_resolver=False
        )
        assert matches == []
        assert [u.id for u in unmatched] == ["A"]


class TestDiameterSanityCheck:
    def _holes(self):
        feat = CylindricalFeature(
            id="f1",
            face_ids=[1],
            radius=3.0,
            diameter=6.0,
            center=(0.0, 0.0, 0.0),
            axis_direction=(0.0, 0.0, 1.0),
            estimated_depth=10.0,
            surface_area=100.0,
        )
        counterbore = HoleGroup(
            id="cb",
            features=[feat],
            primary_diameter=6.0,
            secondary_diameter=18.0,
            total_depth=20.0,
            center=(0.0, 0.0, 0.0),
            axis_direction=(0.0, 0.0, 1.0),
            hole_type="counterbore",
        )
        return [counterbore]

    def test_bore_diameter_of_a_counterbore_is_not_rejected(self):
        """Ø6 matches the bore exactly; the 18 mm mouth must not veto it."""
        from drawmind.matching.scoring import compute_match_score

        holes = self._holes()
        annotation = _annotation(AnnotationType.DIAMETER, {"value": 6.0})
        result = compute_match_score(annotation, holes[0], holes, [annotation])

        assert result["breakdown"].get("rejected") is None
        assert result["total_score"] > 0.5

    def test_implausible_diameter_is_still_rejected(self):
        from drawmind.matching.scoring import compute_match_score

        holes = self._holes()
        annotation = _annotation(AnnotationType.DIAMETER, {"value": 100.0})
        result = compute_match_score(annotation, holes[0], holes, [annotation])

        assert result["breakdown"].get("rejected") == "diameter_ratio"


class TestMatcherRobustness:
    """The vision LLM can put anything into parsed."""

    @pytest.mark.parametrize("value", [[10], "10", None, "M10", {}])
    def test_matching_survives_non_numeric_thread_diameter(self, value):
        from drawmind.matching.matcher import match_annotations_to_features

        feat = CylindricalFeature(
            id="f1",
            face_ids=[1],
            radius=4.0,
            diameter=8.0,
            center=(0.0, 0.0, 0.0),
            axis_direction=(0.0, 0.0, 1.0),
            estimated_depth=10.0,
            surface_area=100.0,
        )
        hole = HoleGroup(
            id="h1",
            features=[feat],
            primary_diameter=8.0,
            total_depth=10.0,
            center=(0.0, 0.0, 0.0),
            axis_direction=(0.0, 0.0, 1.0),
        )
        annotation = _annotation(AnnotationType.THREAD, {"nominal_diameter": value}, multiplier=4)

        matches, _, _ = match_annotations_to_features([annotation], [hole], use_llm_resolver=False)
        assert isinstance(matches, list)


class TestLLMConfidence:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (0.8, 0.8),
            (85, 0.85),
            (1.5, 1.0),
            (-0.2, 0.0),
            ("0.7", 0.7),
            (None, 0.5),
            ("high", 0.5),
        ],
    )
    def test_clamped_into_range(self, raw, expected):
        from drawmind.matching.llm_resolver import _clamp_confidence

        assert _clamp_confidence(raw) == pytest.approx(expected)


class TestThreadSpecFormatting:
    """parsed is partly filled by the vision LLM, so it can hold junk."""

    @pytest.mark.parametrize("value", [None, [10], "M10", {}, float("nan")])
    def test_does_not_crash_on_non_numeric_diameter(self, value):
        annotation = _annotation(AnnotationType.THREAD, {"nominal_diameter": value})
        assert isinstance(_format_thread_spec(annotation), str)

    def test_normal_diameter_still_formats(self):
        annotation = _annotation(AnnotationType.THREAD, {"nominal_diameter": 10.0, "pitch": 1.5})
        assert "10" in _format_thread_spec(annotation)
