"""FastAPI web application for DrawMind3D."""

import os
import time
import uuid
import shutil
import logging
import threading
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from drawmind.config import (
    TEMP_DIR,
    LLM_REVIEW_THRESHOLD,
    MATCH_CONFIDENCE_THRESHOLD,
    MAX_UPLOAD_BYTES,
)
from drawmind.cad.step_reader import load_step
from drawmind.cad.mesh_exporter import export_stl, export_glb
from drawmind.output.writer import write_output
from drawmind.pipeline import Settings, analyze as run_analysis

logger = logging.getLogger(__name__)

app = FastAPI(
    title="DrawMind3D",
    version="1.0.0",
    description=(
        "GenAI-powered linking of PDF technical drawing annotations to 3D CAD hole features. "
        "Upload a PDF drawing and STEP model, then run the analysis pipeline to get structured "
        "JSON output with matched annotation-to-feature pairs, confidence scores, and evidence traces."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# Store job data in memory with TTL cleanup
MAX_JOBS = 50
MAX_CONCURRENT_ANALYSES = int(os.getenv("MAX_CONCURRENT_ANALYSES", "4"))
JOB_TTL_SECONDS = 3600  # 1 hour
jobs: dict = {}


RUNNING_STATUSES = {"analyzing"}


def _discard_job(job_id: str):
    """Drop a job and its working directory."""
    job = jobs.pop(job_id, None)
    if not job:
        return
    job_dir = job.get("dir")
    if job_dir and Path(job_dir).exists():
        shutil.rmtree(job_dir, ignore_errors=True)


def _cleanup_old_jobs():
    """Expire old jobs and keep the job table bounded.

    Jobs still being analyzed are never removed; their files are in use.
    """
    now = time.time()

    for job_id, job in list(jobs.items()):
        if job.get("status") in RUNNING_STATUSES:
            continue
        if now - job.get("created_at", 0) > JOB_TTL_SECONDS:
            _discard_job(job_id)

    if len(jobs) <= MAX_JOBS:
        return

    evictable = sorted(
        (jid for jid, j in jobs.items() if j.get("status") not in RUNNING_STATUSES),
        key=lambda jid: jobs[jid].get("created_at", 0),
    )
    for job_id in evictable[: len(jobs) - MAX_JOBS]:
        _discard_job(job_id)


PROJECT_ROOT = Path(__file__).parent.parent
EVAL_DIR = PROJECT_ROOT / "evaluation"
EVAL_RESULTS_DIR = EVAL_DIR / "results"
EXAMPLES_DIR = PROJECT_ROOT / "examples"

# Serve static files
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/api/upload")
async def upload_files(
    pdf: UploadFile = File(...),
    step: UploadFile = File(...),
):
    """Upload PDF drawing and STEP model files."""
    _cleanup_old_jobs()
    if len(jobs) >= MAX_JOBS:
        raise HTTPException(503, "Server busy: too many jobs held, try again later")

    job_id = str(uuid.uuid4())[:8]
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Fixed names on disk: the client's filenames are kept as metadata only,
    # so they can neither collide nor escape the job directory.
    step_suffix = Path(step.filename or "").suffix.lower()
    if step_suffix not in (".step", ".stp"):
        step_suffix = ".step"
    pdf_path = job_dir / "drawing.pdf"
    step_path = job_dir / f"model{step_suffix}"

    try:
        _save_upload(pdf, pdf_path)
        _save_upload(step, step_path)
    except BaseException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise

    jobs[job_id] = {
        "pdf_path": str(pdf_path),
        "step_path": str(step_path),
        "pdf_name": pdf.filename,
        "step_name": step.filename,
        "status": "uploaded",
        "dir": str(job_dir),
        "created_at": time.time(),
    }

    return {"job_id": job_id, "status": "uploaded"}


def _convert_step_to_glb(step_path: Path, glb_path: Path) -> None:
    export_glb(load_step(str(step_path)), glb_path)


_glb_locks: dict[str, threading.Lock] = {}
_glb_locks_guard = threading.Lock()


def _publish_cached_glb(key: str, step_path: Path, glb_path: Path) -> None:
    """Convert once per cache entry and make the file visible only when complete.

    Concurrent requests for the same model wait for the first conversion
    instead of starting their own or serving a half-written file.
    """
    with _glb_locks_guard:
        lock = _glb_locks.setdefault(key, threading.Lock())
    with lock:
        if glb_path.exists():
            return
        glb_path.parent.mkdir(parents=True, exist_ok=True)
        partial = glb_path.with_name(f".{uuid.uuid4().hex}.partial.glb")
        try:
            _convert_step_to_glb(step_path, partial)
            os.replace(partial, glb_path)
        finally:
            partial.unlink(missing_ok=True)


def _admit() -> None:
    """Gate every analysis route through the same capacity check."""
    running = sum(1 for j in jobs.values() if j.get("status") in RUNNING_STATUSES)
    if running >= MAX_CONCURRENT_ANALYSES:
        raise HTTPException(503, "Server busy: analysis capacity reached, try again later")


def _save_upload(upload: UploadFile, dest: Path, limit: int | None = None) -> None:
    """Stream an upload to disk, refusing anything over the limit."""
    limit = MAX_UPLOAD_BYTES if limit is None else limit
    written = 0
    with open(dest, "wb") as f:
        while chunk := upload.file.read(1024 * 1024):
            written += len(chunk)
            if written > limit:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"{upload.filename} exceeds the {limit} byte upload limit")
            f.write(chunk)


def _update_progress(job: dict, step: int, total: int, message: str, percent: int) -> None:
    """Update job progress for status polling."""
    job["progress"] = {
        "step": step,
        "total": total,
        "message": message,
        "percent": percent,
    }


TOTAL_STEPS = 6


def _run_pipeline(job: dict, use_llm: bool) -> None:
    """Run the analysis pipeline and store results in the job dict."""
    job_dir = Path(job["dir"])
    step_counter = {"n": 0}

    def on_progress(message: str, percent: int) -> None:
        step_counter["n"] += 1
        _update_progress(job, step_counter["n"], TOTAL_STEPS, message, percent)

    result = run_analysis(
        job["pdf_path"],
        job["step_path"],
        settings=Settings(use_llm=use_llm),
        progress=on_progress,
    )

    # Export the solid for the web viewer; the pipeline already loaded it.
    glb_path = job_dir / "model.glb"
    try:
        export_glb(result.shape, glb_path)
        job["glb_path"] = str(glb_path)
    except Exception as e:
        logger.warning(f"GLB export failed, trying STL: {e}")
        stl_path = job_dir / "model.stl"
        export_stl(result.shape, stl_path)
        job["stl_path"] = str(stl_path)

    output_path = job_dir / "result.json"
    stages = [s.as_dict() for s in result.stages]
    write_output(
        result.matches,
        result.unmatched_annotations,
        result.unmatched_holes,
        output_path,
        job["pdf_name"],
        job["step_name"],
        llm_enhanced=result.llm_used,
        stages=stages,
        other_annotations=result.other_annotations,
    )

    _update_progress(job, TOTAL_STEPS, TOTAL_STEPS, "Complete", 100)
    job["status"] = "complete"
    job["output_path"] = str(output_path)
    job["annotations"] = [a.model_dump() for a in result.annotations]
    job["holes"] = [h.model_dump() for h in result.holes]
    job["matches"] = [m.model_dump() for m in result.matches]
    job["stages"] = stages

    matches = result.matches
    high_conf = sum(1 for m in matches if m.confidence >= LLM_REVIEW_THRESHOLD)
    needs_review = sum(
        1 for m in matches if MATCH_CONFIDENCE_THRESHOLD <= m.confidence < LLM_REVIEW_THRESHOLD
    )
    job["summary"] = {
        "annotations_found": len(result.annotations),
        "holes_found": len(result.holes),
        "matched": len(matches),
        "high_confidence": high_conf,
        "needs_review": needs_review,
        "unmatched_annotations": len(result.unmatched_annotations),
        "unmatched_holes": len(result.unmatched_holes),
        "avg_confidence": (
            round(sum(m.confidence for m in matches) / len(matches), 3) if matches else 0.0
        ),
        "llm_used": result.llm_used,
        "unit_system": result.unit_system,
        "stages": stages,
    }


def _run_pipeline_thread(job: dict, use_llm: bool) -> None:
    """Wrapper to run pipeline in a thread with error handling."""
    try:
        _run_pipeline(job, use_llm)
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        job["progress"] = {"step": 0, "total": 0, "message": f"Error: {e}", "percent": 0}
        logger.error(f"Analysis failed: {e}", exc_info=True)


@app.post("/api/analyze/{job_id}")
async def analyze(job_id: str, use_llm: bool = True):
    """Run the full analysis pipeline on uploaded files."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    job = jobs[job_id]
    if job.get("status") in RUNNING_STATUSES:
        raise HTTPException(409, "Analysis already running for this job")

    _admit()

    job["status"] = "analyzing"
    _update_progress(job, 0, 1, "Starting analysis...", 0)

    thread = threading.Thread(target=_run_pipeline_thread, args=(job, use_llm), daemon=True)
    thread.start()

    return {"job_id": job_id, "status": "analyzing"}


@app.get("/api/results/{job_id}")
async def get_results(job_id: str):
    """Get analysis results."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    job = jobs[job_id]
    if job["status"] != "complete":
        return {"status": job["status"], "error": job.get("error")}

    return {
        "status": "complete",
        "summary": job["summary"],
        "stages": job.get("stages", []),
        "matches": job["matches"],
        "annotations": job["annotations"],
        "holes": job["holes"],
    }


@app.get("/api/model/{job_id}")
async def get_model(job_id: str):
    """Serve the 3D model file (GLB or STL)."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    job = jobs[job_id]
    glb_path = job.get("glb_path")
    if glb_path and Path(glb_path).exists():
        return FileResponse(glb_path, media_type="model/gltf-binary")

    stl_path = job.get("stl_path")
    if stl_path and Path(stl_path).exists():
        return FileResponse(stl_path, media_type="model/stl")

    raise HTTPException(404, "Model file not ready")


@app.get("/api/pdf/{job_id}")
async def get_pdf(job_id: str):
    """Serve the original PDF file."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    pdf_path = jobs[job_id]["pdf_path"]
    return FileResponse(pdf_path, media_type="application/pdf")


@app.get("/api/status/health")
async def health():
    return {"status": "ok"}


@app.get("/api/evaluation")
async def get_evaluation():
    """Serve pre-computed evaluation results."""
    results = {}
    for variant in ["llm", "nollm"]:
        json_path = EVAL_RESULTS_DIR / f"evaluation_results_{variant}.json"
        if json_path.exists():
            import json

            with open(json_path) as f:
                results[variant] = json.load(f)
    if not results:
        raise HTTPException(
            404, "No evaluation results found. Run: uv run python scripts/evaluate.py"
        )
    return results


@app.get("/api/evaluation/chart/{filename}")
async def get_evaluation_chart(filename: str):
    """Serve evaluation chart SVGs."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")
    for d in [EVAL_DIR / "presentation", EVAL_DIR / "charts"]:
        path = d / filename
        if path.exists() and path.suffix == ".svg":
            return FileResponse(str(path), media_type="image/svg+xml")
    raise HTTPException(404, "Chart not found")


@app.get("/api/testcases")
async def list_testcases():
    """List all available test cases from examples/ directory."""
    import json as _json

    examples_dir = Path(__file__).parent.parent / "examples"
    if not examples_dir.exists():
        return []

    # Load evaluation data for metric merging
    eval_data: dict = {}
    for variant in ["llm", "nollm"]:
        json_path = EVAL_RESULTS_DIR / f"evaluation_results_{variant}.json"
        if json_path.exists():
            with open(json_path) as f:
                for entry in _json.load(f):
                    key = entry["test_case"]
                    if key not in eval_data:
                        eval_data[key] = {}
                    eval_data[key][variant] = {
                        "precision": entry["extraction"]["precision"],
                        "recall": entry["extraction"]["recall"],
                        "f1": entry["extraction"]["f1"],
                        "linking_accuracy": entry["linking"]["linking_accuracy"],
                        "avg_confidence": entry["avg_confidence"],
                    }

    testcases = []
    for folder in sorted(examples_dir.iterdir()):
        if not folder.is_dir():
            continue
        tc_id = folder.name
        has_pdf = (folder / "drawing.pdf").exists()
        has_step = any((folder / f"model.{ext}").exists() for ext in ["stp", "step"])

        if tc_id.startswith("CTC"):
            category = "CTC"
        elif tc_id.startswith("FTC"):
            category = "FTC"
        elif tc_id.startswith("D2MI"):
            category = "D2MI"
        elif tc_id.startswith("SYN"):
            category = "SYN"
        else:
            category = "other"

        testcases.append(
            {
                "id": tc_id,
                "category": category,
                "has_pdf": has_pdf,
                "has_step": has_step,
                "evaluation": eval_data.get(tc_id, {}),
            }
        )

    return testcases


def _testcase_dir(tc_id: str) -> Path:
    """Resolve a test case ID to its folder, accepting only direct children of examples/."""
    root = EXAMPLES_DIR.resolve()
    tc_dir = (root / tc_id).resolve()
    if tc_dir.parent != root or not tc_dir.is_dir():
        raise HTTPException(404, f"Unknown test case {tc_id!r}")
    return tc_dir


@app.get("/api/testcases/{tc_id}/pdf")
async def get_testcase_pdf(tc_id: str):
    """Serve the PDF drawing for a test case."""
    pdf_path = _testcase_dir(tc_id) / "drawing.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, f"PDF not found for {tc_id}")
    return FileResponse(str(pdf_path), media_type="application/pdf")


@app.get("/api/testcases/{tc_id}/model")
async def get_testcase_model(tc_id: str):
    """Serve the 3D model (GLB) for a test case, converting from STEP on demand."""
    tc_dir = _testcase_dir(tc_id)
    step_path = None
    for ext in ["stp", "step"]:
        candidate = tc_dir / f"model.{ext}"
        if candidate.exists():
            step_path = candidate
            break
    if not step_path:
        raise HTTPException(404, f"STEP model not found for {tc_id}")

    # Check cache
    cache_dir = TEMP_DIR / "testcase_cache" / tc_id
    glb_path = cache_dir / "model.glb"

    if not glb_path.exists():
        try:
            # Conversion takes seconds; keep it off the event loop.
            await run_in_threadpool(_publish_cached_glb, tc_id, step_path, glb_path)
        except Exception as e:
            logger.error(f"GLB conversion failed for {tc_id}: {e}")
            raise HTTPException(500, f"Model conversion failed: {e}")

    return FileResponse(str(glb_path), media_type="model/gltf-binary")


@app.post("/api/testcases/{tc_id}/analyze")
async def analyze_testcase(tc_id: str, use_llm: bool = True):
    """Run the analysis pipeline on a built-in test case."""
    tc_dir = _testcase_dir(tc_id)
    pdf_path = tc_dir / "drawing.pdf"
    step_path = None
    for ext in ["stp", "step"]:
        candidate = tc_dir / f"model.{ext}"
        if candidate.exists():
            step_path = candidate
            break

    if not pdf_path.exists() or not step_path:
        raise HTTPException(404, f"Test case {tc_id} not found or incomplete")

    # Create a job for this test case
    _cleanup_old_jobs()
    _admit()
    if len(jobs) >= MAX_JOBS:
        raise HTTPException(503, "Server busy: too many jobs held, try again later")

    job_id = f"tc-{tc_id.lower()}-{str(uuid.uuid4())[:4]}"
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    jobs[job_id] = {
        "pdf_path": str(pdf_path),
        "step_path": str(step_path),
        "pdf_name": f"{tc_id}/drawing.pdf",
        "step_name": f"{tc_id}/model.stp",
        "status": "analyzing",
        "dir": str(job_dir),
        "created_at": time.time(),
    }

    job = jobs[job_id]
    _update_progress(job, 0, 1, "Starting analysis...", 0)

    thread = threading.Thread(target=_run_pipeline_thread, args=(job, use_llm), daemon=True)
    thread.start()

    return {"job_id": job_id, "status": "analyzing"}


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    job = jobs[job_id]
    result = {"status": job["status"]}
    if "progress" in job:
        result["progress"] = job["progress"]
    if job["status"] == "complete" and "summary" in job:
        result["summary"] = job["summary"]
    if job["status"] == "error":
        result["error"] = job.get("error", "Unknown error")
    return result


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("PORT", 8000))
    # The application has no authentication. Bind loopback unless the
    # operator opts into exposing it.
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)
