"""FastAPI web application for DrawMind3D."""

import os
import time
import uuid
import shutil
import logging
import threading
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from drawmind.config import TEMP_DIR, LLM_REVIEW_THRESHOLD, MATCH_CONFIDENCE_THRESHOLD
from drawmind.pdf.extractor import extract_all_text, detect_unit_system
from drawmind.pdf.parser import parse_annotations
from drawmind.cad.step_reader import load_step
from drawmind.cad.feature_extractor import (
    extract_cylindrical_faces,
    group_coaxial_features,
    detect_through_holes,
)
from drawmind.cad.mesh_exporter import export_stl, export_glb
from drawmind.matching.matcher import match_annotations_to_features
from drawmind.output.writer import write_output
from drawmind.pdf.leader_lines import extract_leader_targets
from drawmind.config import USE_VISION_LLM

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
JOB_TTL_SECONDS = 3600  # 1 hour
jobs: dict = {}


def _cleanup_old_jobs():
    """Remove expired jobs to prevent memory leaks."""
    if len(jobs) <= MAX_JOBS:
        return
    now = time.time()
    expired = [jid for jid, j in jobs.items() if now - j.get("created_at", 0) > JOB_TTL_SECONDS]
    for jid in expired:
        job_dir = jobs[jid].get("dir")
        if job_dir and Path(job_dir).exists():
            shutil.rmtree(job_dir, ignore_errors=True)
        del jobs[jid]


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
    job_id = str(uuid.uuid4())[:8]
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded files (sanitize filenames to prevent path traversal)
    pdf_name = Path(pdf.filename).name.replace("..", "")
    step_name = Path(step.filename).name.replace("..", "")
    pdf_path = job_dir / pdf_name
    step_path = job_dir / step_name

    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(pdf.file, f)
    with open(step_path, "wb") as f:
        shutil.copyfileobj(step.file, f)

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


def _update_progress(job: dict, step: int, total: int, message: str, percent: int) -> None:
    """Update job progress for status polling."""
    job["progress"] = {
        "step": step,
        "total": total,
        "message": message,
        "percent": percent,
    }


def _run_pipeline(job: dict, use_llm: bool) -> None:
    """Run the full analysis pipeline and store results in job dict."""
    pdf_path = job["pdf_path"]
    step_path = job["step_path"]
    job_dir = Path(job["dir"])
    total_steps = 6 if (USE_VISION_LLM and use_llm) else 5

    # 1. PDF extraction
    step_num = 1
    _update_progress(job, step_num, total_steps, "Extracting text from PDF", 10)
    raw_texts = extract_all_text(pdf_path)
    unit_system = detect_unit_system(pdf_path)
    annotations = parse_annotations(raw_texts, unit_system=unit_system)

    # 2. Vision LLM (optional, all pages)
    if USE_VISION_LLM and use_llm:
        step_num += 1
        _update_progress(job, step_num, total_steps, "Analyzing pages with Vision LLM", 25)
        try:
            import fitz
            from drawmind.pdf.vision import analyze_page_with_vision

            doc = fitz.open(pdf_path)
            num_pages = len(doc)
            doc.close()
            for page_idx in range(num_pages):
                annotations = analyze_page_with_vision(
                    pdf_path, page_idx, annotations, unit_system=unit_system
                )
        except Exception as e:
            logger.warning(f"Vision LLM failed: {e}")

    # 3. Parsing annotations
    step_num += 1
    _update_progress(job, step_num, total_steps, "Parsing annotations", 45)

    # 3b. Leader-line tracking
    try:
        annotations = extract_leader_targets(pdf_path, annotations)
    except Exception as e:
        logger.warning(f"Leader-line extraction failed: {e}")

    # 4. 3D feature extraction
    step_num += 1
    _update_progress(job, step_num, total_steps, "Extracting 3D features from STEP", 60)
    shape = load_step(step_path)
    features = extract_cylindrical_faces(shape)
    holes = group_coaxial_features(features)
    holes = detect_through_holes(shape, holes)

    # 4b. Export 3D model for web viewer
    glb_path = job_dir / "model.glb"
    try:
        export_glb(shape, glb_path)
    except Exception as e:
        logger.warning(f"GLB export failed, trying STL: {e}")
        stl_path = job_dir / "model.stl"
        export_stl(shape, stl_path)
        job["stl_path"] = str(stl_path)

    job["glb_path"] = str(glb_path)

    # 5. Matching
    step_num += 1
    _update_progress(job, step_num, total_steps, "Matching annotations to features", 80)
    matches, unmatched_ann, unmatched_holes = match_annotations_to_features(
        annotations,
        holes,
        pdf_path=pdf_path if use_llm else None,
        use_llm_resolver=use_llm and USE_VISION_LLM,
    )

    # 6. Write output
    step_num += 1
    _update_progress(job, step_num, total_steps, "Generating output", 95)
    output_path = job_dir / "result.json"
    write_output(
        matches,
        unmatched_ann,
        unmatched_holes,
        output_path,
        job["pdf_name"],
        job["step_name"],
        llm_enhanced=use_llm and USE_VISION_LLM,
    )

    # Store results
    _update_progress(job, step_num, total_steps, "Complete", 100)
    job["status"] = "complete"
    job["output_path"] = str(output_path)
    job["annotations"] = [a.model_dump() for a in annotations]
    job["holes"] = [h.model_dump() for h in holes]
    job["matches"] = [m.model_dump() for m in matches]
    high_conf = sum(1 for m in matches if m.confidence >= LLM_REVIEW_THRESHOLD)
    needs_review = sum(
        1 for m in matches if MATCH_CONFIDENCE_THRESHOLD <= m.confidence < LLM_REVIEW_THRESHOLD
    )
    job["summary"] = {
        "annotations_found": len(annotations),
        "holes_found": len(holes),
        "matched": len(matches),
        "high_confidence": high_conf,
        "needs_review": needs_review,
        "unmatched_annotations": len(unmatched_ann),
        "unmatched_holes": len(unmatched_holes),
        "avg_confidence": (
            round(sum(m.confidence for m in matches) / len(matches), 3) if matches else 0.0
        ),
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
    eval_dir = Path(__file__).parent.parent / "data" / "evaluation"
    results = {}
    for variant in ["llm", "nollm"]:
        json_path = eval_dir / f"evaluation_results_{variant}.json"
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
    eval_dir = Path(__file__).parent.parent / "data" / "evaluation"
    # Check presentation dir first, then eval dir
    for d in [eval_dir / "presentation", eval_dir]:
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
    eval_dir = Path(__file__).parent.parent / "data" / "evaluation"
    for variant in ["llm", "nollm"]:
        json_path = eval_dir / f"evaluation_results_{variant}.json"
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


@app.get("/api/testcases/{tc_id}/pdf")
async def get_testcase_pdf(tc_id: str):
    """Serve the PDF drawing for a test case."""
    if ".." in tc_id or "/" in tc_id or "\\" in tc_id:
        raise HTTPException(400, "Invalid test case ID")
    pdf_path = Path(__file__).parent.parent / "examples" / tc_id / "drawing.pdf"
    if not pdf_path.exists():
        raise HTTPException(404, f"PDF not found for {tc_id}")
    return FileResponse(str(pdf_path), media_type="application/pdf")


@app.get("/api/testcases/{tc_id}/model")
async def get_testcase_model(tc_id: str):
    """Serve the 3D model (GLB) for a test case, converting from STEP on demand."""
    if ".." in tc_id or "/" in tc_id or "\\" in tc_id:
        raise HTTPException(400, "Invalid test case ID")

    tc_dir = Path(__file__).parent.parent / "examples" / tc_id
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
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            shape = load_step(str(step_path))
            export_glb(shape, glb_path)
        except Exception as e:
            logger.error(f"GLB conversion failed for {tc_id}: {e}")
            raise HTTPException(500, f"Model conversion failed: {e}")

    return FileResponse(str(glb_path), media_type="model/gltf-binary")


@app.post("/api/testcases/{tc_id}/analyze")
async def analyze_testcase(tc_id: str, use_llm: bool = True):
    """Run the analysis pipeline on a built-in test case."""
    if ".." in tc_id or "/" in tc_id or "\\" in tc_id:
        raise HTTPException(400, "Invalid test case ID")

    tc_dir = Path(__file__).parent.parent / "examples" / tc_id
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
    uvicorn.run(app, host="0.0.0.0", port=port)
