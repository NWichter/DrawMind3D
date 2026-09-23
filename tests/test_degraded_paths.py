"""Failures on the degraded paths must be visible, and bad input must stay contained."""

from pathlib import Path

import pytest

from drawmind.pdf.vision import _process_vision_results
from web import app as webapp

EXAMPLES = Path(__file__).parent.parent / "examples"


class TestMalformedVisionItems:
    GOOD = {
        "text": "Ø10 THRU",
        "type": "diameter",
        "parsed": {"value": 10.0},
        "bbox_percent": {"x": 50, "y": 50, "w": 10, "h": 5},
        "confidence": 0.9,
    }

    @pytest.mark.parametrize(
        "bad",
        [
            "Ø8 THRU",
            None,
            {"type": None, "text": "Ø8"},
            {"type": "diameter", "text": None, "parsed": {"value": 8}},
            {"type": "diameter", "text": "Ø8", "parsed": None},
            {"type": "diameter", "text": "Ø8", "parsed": {"value": 8}, "bbox_percent": None},
            {"type": "diameter", "text": "Ø8", "parsed": {"value": 8}, "confidence": "high"},
            {"type": "diameter", "text": "Ø8", "parsed": {"value": 8}, "multiplier": None},
        ],
    )
    def test_one_bad_item_does_not_cost_the_page(self, bad):
        result = _process_vision_results([bad, self.GOOD], 0, 612, 792, "metric", 0)
        assert any(a.raw_text == "Ø10 THRU" for a in result)

    def test_numeric_strings_are_accepted(self):
        item = dict(self.GOOD, confidence="0.9", multiplier="4")
        (ann,) = _process_vision_results([item], 0, 612, 792, "metric", 0)
        assert ann.confidence == 0.9
        assert ann.multiplier == 4


class TestDisambiguationFailureIsReported:
    def _pair(self):
        from drawmind.models import AnnotationType, BoundingBox, HoleGroup, PDFAnnotation

        ann = PDFAnnotation(
            id="ann_001",
            raw_text="Ø10",
            annotation_type=AnnotationType.DIAMETER,
            parsed={"value": 10.0},
            bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10, page=0),
        )
        hole = HoleGroup(
            id="hole_001",
            features=[],
            primary_diameter=10.0,
            total_depth=20.0,
            center=(0.0, 0.0, 0.0),
            axis_direction=(0.0, 0.0, 1.0),
        )
        return ann, hole

    def test_resolver_counts_failed_batches(self, monkeypatch):
        from drawmind.matching import llm_resolver

        class _Broken:
            available = True

            def complete_json(self, *args, **kwargs):
                raise TimeoutError("provider timed out")

        monkeypatch.setattr(llm_resolver, "get_llm_client", lambda: _Broken())
        ann, hole = self._pair()
        report: dict = {}

        assert llm_resolver.resolve_ambiguous_matches([ann], [hole], report=report) == []
        assert report["batches"] == 1
        assert report["failed_batches"] == 1
        assert "timed out" in report["error"]

    def test_pipeline_records_failed_not_skipped(self, monkeypatch):
        from drawmind import pipeline
        from drawmind.matching import matcher

        def fake_match(annotations, holes, pdf_path=None, use_llm_resolver=False, llm_report=None):
            llm_report.update(batches=1, failed_batches=1, error="provider timed out")
            return [], annotations, holes

        monkeypatch.setattr(matcher, "match_annotations_to_features", fake_match)
        result = pipeline.AnalysisResult()
        pipeline._run_matching(result, Path("unused.pdf"), llm_allowed=True)

        stage = result.stage("llm_disambiguation")
        assert stage.status == pipeline.StageStatus.FAILED
        assert "timed out" in stage.detail

    def test_missing_provider_is_skipped_like_vision(self, monkeypatch):
        from drawmind import pipeline
        from drawmind.matching import llm_resolver, matcher

        class _NoProvider:
            available = False

        monkeypatch.setattr(llm_resolver, "get_llm_client", lambda: _NoProvider())

        def fake_match(annotations, holes, pdf_path=None, use_llm_resolver=False, llm_report=None):
            llm_resolver.resolve_ambiguous_matches(*self._pair_lists(), report=llm_report)
            return [], annotations, holes

        monkeypatch.setattr(matcher, "match_annotations_to_features", fake_match)
        result = pipeline.AnalysisResult()
        pipeline._run_matching(result, Path("unused.pdf"), llm_allowed=True)

        assert result.stage("llm_disambiguation").status == pipeline.StageStatus.SKIPPED

    def _pair_lists(self):
        ann, hole = self._pair()
        return [ann], [hole]


class TestOcrFailureIsReported:
    def test_crash_is_recorded_per_page(self, monkeypatch):
        from drawmind.pdf import extractor

        def crash(page, page_num):
            raise RuntimeError("bad TSV")

        monkeypatch.setattr(extractor, "_tesseract_available", lambda: True)
        monkeypatch.setattr(extractor, "_extract_page_ocr", crash)
        report: dict = {}

        extractor.extract_all_text(EXAMPLES / "CTC-01" / "drawing.pdf", report=report)

        assert report["ocr_pages"] >= 1
        assert report["ocr_errors"] and "bad TSV" in report["ocr_errors"][0]


class TestRetryDecision:
    def test_client_error_mentioning_a_retry_word_is_not_retried(self):
        from drawmind.llm import client as client_module

        calls = {"n": 0}

        class _BadRequest(Exception):
            status_code = 400

        class _FakeCompletions:
            def create(self, **kwargs):
                calls["n"] += 1
                raise _BadRequest("model could not generate: moderate content")

        class _FakeClient:
            chat = type("chat", (), {"completions": _FakeCompletions()})()

        llm = client_module.LLMClient()
        llm._client = _FakeClient()

        with pytest.raises(_BadRequest):
            llm.complete("prompt")
        assert calls["n"] == 1


class TestUploadNames:
    @pytest.fixture(autouse=True)
    def _isolated(self, monkeypatch, tmp_path):
        monkeypatch.setattr(webapp, "TEMP_DIR", tmp_path)
        webapp.jobs.clear()
        yield
        webapp.jobs.clear()

    def _upload(self, pdf_name, step_name):
        from fastapi.testclient import TestClient

        return TestClient(webapp.app).post(
            "/api/upload",
            files={
                "pdf": (pdf_name, b"%PDF-1.7 drawing", "application/pdf"),
                "step": (step_name, b"ISO-10303-21; model", "application/step"),
            },
        )

    def test_same_filename_for_both_files_keeps_both(self):
        response = self._upload("same.bin", "same.bin")
        assert response.status_code == 200
        job = webapp.jobs[response.json()["job_id"]]

        assert Path(job["pdf_path"]).read_bytes().startswith(b"%PDF")
        assert Path(job["step_path"]).read_bytes().startswith(b"ISO-10303")
        assert job["pdf_name"] == "same.bin"

    @pytest.mark.parametrize("name", ["..", "", "../../etc/passwd"])
    def test_hostile_filenames_stay_inside_the_job_dir(self, name, tmp_path):
        response = self._upload(name or "x", name or "x")
        assert response.status_code == 200
        job = webapp.jobs[response.json()["job_id"]]
        for key in ("pdf_path", "step_path"):
            assert Path(job[key]).resolve().parent == Path(job["dir"]).resolve()


class TestTestcaseIds:
    @pytest.mark.parametrize("tc_id", ["..", "C:", "nonexistent", "SYN-01-SimpleBlock/.."])
    def test_unknown_or_escaping_ids_are_rejected(self, tc_id):
        from fastapi.testclient import TestClient

        response = TestClient(webapp.app).get(f"/api/testcases/{tc_id}/pdf")
        assert response.status_code in (404, 405)

    def test_known_id_is_served(self):
        from fastapi.testclient import TestClient

        response = TestClient(webapp.app).get("/api/testcases/SYN-01-SimpleBlock/pdf")
        assert response.status_code == 200
