"""Regression tests for the findings of the second outside review."""

import sys
from pathlib import Path

import pytest

from drawmind import pipeline
from drawmind.models import AnnotationType, BoundingBox, PDFAnnotation
from drawmind.pdf import backend
from drawmind.pdf.parser import parse_annotations
from tests.pdf_builder import build_text_pdf

ROOT = Path(__file__).parent.parent


def _ann(ann_type, parsed, ann_id="ann_001", page=0):
    return PDFAnnotation(
        id=ann_id,
        raw_text="x",
        annotation_type=ann_type,
        parsed=parsed,
        bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10, page=page),
    )


def _parse(text, unit_system="metric"):
    raw = [
        {
            "text": text,
            "bbox": {"x0": 0, "y0": 0, "x1": 50, "y1": 10},
            "page": 0,
            "source": "native",
            "font": "",
            "size": 0,
        }
    ]
    return parse_annotations(raw, unit_system=unit_system)


class TestUnitRecheck:
    def _result(self, source, annotations):
        result = pipeline.AnalysisResult(unit_system="metric", unit_source=source)
        result.annotations = annotations
        return result

    def test_declared_metric_is_never_overridden(self):
        small = [_ann(AnnotationType.DIAMETER, {"value": 0.5}, f"a{i}") for i in range(4)]
        result = self._result("declaration", small)

        pipeline._recheck_units(result, Path("unused.pdf"), llm_allowed=False)

        assert result.unit_system == "metric"

    def test_caller_supplied_units_are_never_overridden(self):
        small = [_ann(AnnotationType.DIAMETER, {"value": 0.5}, f"a{i}") for i in range(4)]
        result = self._result("caller", small)

        pipeline._recheck_units(result, Path("unused.pdf"), llm_allowed=False)

        assert result.unit_system == "metric"

    def test_roughness_and_depth_values_do_not_count_as_diameters(self):
        annotations = [
            _ann(AnnotationType.DIAMETER, {"value": 10.0}, "a1"),
            _ann(AnnotationType.SURFACE_FINISH, {"parameter": "Ra", "value": 0.8}, "a2"),
            _ann(AnnotationType.SURFACE_FINISH, {"parameter": "Ra", "value": 1.6}, "a3"),
            _ann(AnnotationType.SURFACE_FINISH, {"parameter": "Ra", "value": 0.4}, "a4"),
            _ann(AnnotationType.DEPTH, {"value": 1.0}, "a5"),
        ]
        result = self._result("default", annotations)

        pipeline._recheck_units(result, Path("unused.pdf"), llm_allowed=False)

        assert result.unit_system == "metric"

    def test_default_with_tiny_hole_diameters_still_switches(self):
        small = [_ann(AnnotationType.DIAMETER, {"value": 0.25}, f"a{i}") for i in range(3)]
        result = self._result("default", small)

        pipeline._recheck_units(result, Path("unused.pdf"), llm_allowed=False)

        assert result.unit_system == "inch"

    def test_detection_reports_its_source(self, tmp_path):
        from drawmind.pdf.extractor import detect_unit_system

        declared = build_text_pdf(tmp_path / "d.pdf", [((50, 50), "UNITS: MM", 10)])
        blank = build_text_pdf(tmp_path / "b.pdf", [((50, 50), "PART 42", 10)])
        report_declared: dict = {}
        report_blank: dict = {}

        assert detect_unit_system(declared, report=report_declared) == "metric"
        assert detect_unit_system(blank, report=report_blank) == "metric"
        assert report_declared["source"] == "declaration"
        assert report_blank["source"] == "default"


class TestSteppedCallouts:
    def test_thru_counterbore_is_not_reduced_to_a_bare_depth(self):
        (ann,) = _parse("Ø8 THRU CBORE Ø18")
        assert ann.annotation_type == AnnotationType.COUNTERBORE
        assert ann.is_through
        assert ann.parsed["diameter"] == 18.0
        assert ann.parsed["hole_diameter"] == 8.0

    def test_counterbore_keeps_its_count(self):
        (ann,) = _parse("4X Ø8 CBORE Ø18 DEPTH 8")
        assert ann.multiplier == 4
        assert ann.parsed["depth"] == 8.0

    def test_countersink_abbreviation_is_recognised(self):
        (ann,) = _parse("6X Ø4.5 THRU CSK Ø9")
        assert ann.annotation_type == AnnotationType.COUNTERSINK
        assert ann.multiplier == 6
        assert ann.parsed["hole_diameter"] == 4.5

    def test_inch_counterbore_converts_the_bore_too(self):
        (ann,) = _parse("4X Ø.339 THRU CBORE Ø.625", unit_system="inch")
        assert ann.parsed["hole_diameter"] == pytest.approx(8.6106)
        assert ann.parsed["original_inch_hole_diameter"] == 0.339

    def test_plain_through_hole_is_unchanged(self):
        (ann,) = _parse("4X Ø6.6 THRU")
        assert ann.annotation_type == AnnotationType.DIAMETER
        assert ann.multiplier == 4


class TestCropBox:
    def test_text_is_reported_relative_to_the_visible_page(self, tmp_path):
        items = [((100, 100), "M8", 10)]
        full = build_text_pdf(tmp_path / "full.pdf", items)
        cropped = build_text_pdf(tmp_path / "crop.pdf", items, cropbox=(50, 0, 545, 792))

        with backend.open_document(full) as doc:
            (a,) = backend.text_lines(doc[0])
        with backend.open_document(cropped) as doc:
            (b,) = backend.text_lines(doc[0])
            assert backend.page_size(doc[0]) == pytest.approx((495, 792))

        # Crop box starts 50 pt in from the left and 50 pt down from the top.
        assert b["x0"] == pytest.approx(a["x0"] - 50, abs=0.5)
        assert b["y0"] == pytest.approx(a["y0"] - 50, abs=0.5)


class TestPerPageSpatialScoring:
    def test_each_annotation_is_scored_against_its_own_sheet(self, monkeypatch, tmp_path):
        from drawmind.matching import matcher

        pdf = tmp_path / "two.pdf"
        pdf.write_bytes(b"%PDF")

        class _Doc:
            def __len__(self):
                return 2

            def __getitem__(self, i):
                return i

        class _Ctx:
            def __enter__(self):
                return _Doc()

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(backend, "open_document", lambda path: _Ctx())
        monkeypatch.setattr(
            backend, "page_size", lambda page: (842.0, 595.0) if page else (595.0, 842.0)
        )

        seen = {}
        real = matcher.compute_match_score

        def spy(ann, hole, holes, anns, page_size=None):
            seen[ann.bbox.page] = page_size
            return real(ann, hole, holes, anns, page_size)

        monkeypatch.setattr(matcher, "compute_match_score", spy)

        from drawmind.models import HoleGroup

        hole = HoleGroup(
            id="hole_001",
            features=[],
            primary_diameter=10.0,
            total_depth=20.0,
            center=(0.0, 0.0, 0.0),
            axis_direction=(0.0, 0.0, 1.0),
        )
        anns = [
            _ann(AnnotationType.DIAMETER, {"value": 10.0}, "a1", page=0),
            _ann(AnnotationType.DIAMETER, {"value": 10.0}, "a2", page=1),
        ]
        matcher.match_annotations_to_features(anns, [hole], pdf_path=str(pdf))

        assert seen[0] == (595.0, 842.0)
        assert seen[1] == (842.0, 595.0)


class TestCliExitCode:
    def _run(self, monkeypatch, tmp_path, result):
        from drawmind import cli

        monkeypatch.setattr(cli, "analyze", lambda *a, **k: result)
        monkeypatch.setattr(cli, "write_output", lambda **k: tmp_path / "out.json")
        monkeypatch.setattr(sys, "argv", ["drawmind3d", "--pdf", "a.pdf", "--step", "b.step"])
        cli.main()

    def _failed_text(self, annotations):
        result = pipeline.AnalysisResult()
        result.annotations = annotations
        pipeline._record(result, "text_extraction", pipeline.StageStatus.FAILED, "no text")
        pipeline._record(result, "vision_llm", pipeline.StageStatus.OK, "3 annotations")
        return result

    def test_vision_recovery_after_empty_text_layer_succeeds(self, monkeypatch, tmp_path):
        recovered = [_ann(AnnotationType.DIAMETER, {"value": 10.0})]
        self._run(monkeypatch, tmp_path, self._failed_text(recovered))

    def test_nothing_recovered_still_fails(self, monkeypatch, tmp_path):
        with pytest.raises(SystemExit) as exc:
            self._run(monkeypatch, tmp_path, self._failed_text([]))
        assert exc.value.code == 2


class TestEvaluationScripts:
    def test_requested_mode_names_the_artifacts(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import evaluate
        finally:
            sys.path.pop(0)

        failed_first = [{"llm_requested": True, "llm_enhanced": False}]
        assert evaluate._llm_requested(failed_first) is True
        assert evaluate._llm_requested([{"llm_enhanced": False}]) is False

    def test_presentation_charts_read_the_moved_results(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import generate_charts
        finally:
            sys.path.pop(0)

        for mode in ("nollm", "llm"):
            assert (generate_charts.RESULTS_DIR / f"evaluation_results_{mode}.json").exists()
