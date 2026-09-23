"""Tests for in-memory job bookkeeping in the web app."""

import time
from pathlib import Path

import pytest

from web import app as webapp

EXAMPLE = Path(__file__).parent.parent / "examples" / "SYN-01-SimpleBlock"


def _seed(count, status="complete", age=0.0, tmp_path=None):
    webapp.jobs.clear()
    for i in range(count):
        job_dir = None
        if tmp_path is not None:
            job_dir = tmp_path / f"job_{i}"
            job_dir.mkdir()
            (job_dir / "drawing.pdf").write_bytes(b"x")
            job_dir = str(job_dir)
        webapp.jobs[f"job_{i}"] = {
            "status": status,
            "created_at": time.time() - age,
            "dir": job_dir,
        }


class TestJobCleanup:
    def teardown_method(self):
        webapp.jobs.clear()

    def test_expired_jobs_are_removed_below_the_cap(self):
        """Age-based expiry must not wait for the job count to exceed MAX_JOBS."""
        _seed(3, age=webapp.JOB_TTL_SECONDS + 60)
        webapp._cleanup_old_jobs()
        assert webapp.jobs == {}

    def test_job_count_is_actually_capped(self):
        """Fresh jobs are not expired, so only a cap can bound memory."""
        _seed(webapp.MAX_JOBS + 40, age=0.0)
        webapp._cleanup_old_jobs()
        assert len(webapp.jobs) <= webapp.MAX_JOBS

    def test_running_job_is_never_evicted(self):
        """A long analysis must keep its files, however old the job is."""
        _seed(1, status="analyzing", age=webapp.JOB_TTL_SECONDS * 5)
        webapp._cleanup_old_jobs()
        assert "job_0" in webapp.jobs

    def test_running_job_survives_pressure_from_the_cap(self):
        _seed(webapp.MAX_JOBS + 20, age=0.0)
        webapp.jobs["job_0"]["status"] = "analyzing"
        webapp.jobs["job_0"]["created_at"] = time.time() - webapp.JOB_TTL_SECONDS * 5
        webapp._cleanup_old_jobs()
        assert "job_0" in webapp.jobs

    def test_evicted_job_directory_is_deleted(self, tmp_path):
        from pathlib import Path

        _seed(2, age=webapp.JOB_TTL_SECONDS + 60, tmp_path=tmp_path)
        dirs = [Path(j["dir"]) for j in webapp.jobs.values()]
        webapp._cleanup_old_jobs()
        assert not any(d.exists() for d in dirs)

    def test_recent_finished_jobs_are_kept(self):
        _seed(3, age=10.0)
        webapp._cleanup_old_jobs()
        assert len(webapp.jobs) == 3


class TestAnalyzeReentry:
    def teardown_method(self):
        webapp.jobs.clear()

    def test_second_analyze_call_is_rejected(self):
        """Two pipelines over one job would race on the same output file."""
        from fastapi.testclient import TestClient

        webapp.jobs.clear()
        webapp.jobs["job_1"] = {"status": "analyzing", "created_at": time.time(), "dir": None}

        response = TestClient(webapp.app).post("/api/analyze/job_1")
        assert response.status_code == 409

    def test_analysis_capacity_is_bounded(self):
        """Cleanup cannot bound anything while every job is still running."""
        from fastapi.testclient import TestClient

        webapp.jobs.clear()
        for i in range(webapp.MAX_CONCURRENT_ANALYSES):
            webapp.jobs[f"busy_{i}"] = {
                "status": "analyzing",
                "created_at": time.time(),
                "dir": None,
            }
        webapp.jobs["waiting"] = {"status": "uploaded", "created_at": time.time(), "dir": None}

        response = TestClient(webapp.app).post("/api/analyze/waiting")
        assert response.status_code == 503
        assert webapp.jobs["waiting"]["status"] == "uploaded"

    def test_testcase_route_shares_the_capacity_gate(self):
        """The built-in test cases run the same pipeline and must queue the same way."""
        from fastapi.testclient import TestClient

        webapp.jobs.clear()
        for i in range(webapp.MAX_CONCURRENT_ANALYSES):
            webapp.jobs[f"busy_{i}"] = {
                "status": "analyzing",
                "created_at": time.time(),
                "dir": None,
            }

        response = TestClient(webapp.app).post("/api/testcases/SYN-01-SimpleBlock/analyze")
        assert response.status_code == 503
        assert len(webapp.jobs) == webapp.MAX_CONCURRENT_ANALYSES


@pytest.mark.skipif(not EXAMPLE.exists(), reason="example files not present")
class TestAnalysisIntegration:
    """The web route must run the same pipeline the CLI does and report its stages."""

    def teardown_method(self):
        webapp.jobs.clear()

    def test_testcase_analysis_reports_real_stages(self):
        from fastapi.testclient import TestClient

        webapp.jobs.clear()
        client = TestClient(webapp.app)

        started = client.post("/api/testcases/SYN-01-SimpleBlock/analyze?use_llm=false")
        assert started.status_code == 200
        job_id = started.json()["job_id"]

        for _ in range(120):
            status = client.get(f"/api/status/{job_id}").json()
            if status["status"] in ("complete", "error"):
                break
            time.sleep(0.25)

        assert status["status"] == "complete", status.get("error")

        results = client.get(f"/api/results/{job_id}").json()
        stages = {s["name"]: s for s in results["stages"]}

        assert stages["cad_features"]["status"] == "ok"
        assert stages["vision_llm"]["status"] == "skipped"
        assert results["summary"]["llm_used"] is False
        assert results["summary"]["holes_found"] > 0


class TestUploadLimits:
    def teardown_method(self):
        webapp.jobs.clear()

    def test_oversized_upload_is_refused(self, monkeypatch):
        from fastapi.testclient import TestClient

        webapp.jobs.clear()
        monkeypatch.setattr(webapp, "MAX_UPLOAD_BYTES", 1024)

        oversized = b"x" * 4096
        response = TestClient(webapp.app).post(
            "/api/upload",
            files={
                "pdf": ("drawing.pdf", oversized, "application/pdf"),
                "step": ("model.stp", b"tiny", "application/step"),
            },
        )

        assert response.status_code == 413
        assert not webapp.jobs, "a refused upload must not leave a job behind"
