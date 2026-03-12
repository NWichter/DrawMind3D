"""FastAPI web application for DrawMind3D."""

import os
import uuid
import shutil
import logging
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from drawmind.config import TEMP_DIR
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

app = FastAPI(title="DrawMind3D", version="0.1.0")

# Store job data in memory (for hackathon simplicity)
jobs: dict = {}

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
    job_id = str(uuid.uuid4())[:8]
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded files
    pdf_path = job_dir / pdf.filename
    step_path = job_dir / step.filename

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
    }

    return {"job_id": job_id, "status": "uploaded"}


@app.post("/api/analyze/{job_id}")
async def analyze(job_id: str, use_llm: bool = True):
    """Run the full analysis pipeline."""
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")

    job = jobs[job_id]
    job["status"] = "analyzing"

    try:
        pdf_path = job["pdf_path"]
        step_path = job["step_path"]
        job_dir = Path(job["dir"])

        # 1. PDF extraction
        raw_texts = extract_all_text(pdf_path)
        unit_system = detect_unit_system(pdf_path)
        annotations = parse_annotations(raw_texts, unit_system=unit_system)

        # 2. Vision LLM (optional, all pages)
        if USE_VISION_LLM and use_llm:
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

        # 2b. Leader-line tracking (extract target points for annotations)
        try:
            annotations = extract_leader_targets(pdf_path, annotations)
        except Exception as e:
            logger.warning(f"Leader-line extraction failed: {e}")

        # 3. 3D feature extraction
        shape = load_step(step_path)
        features = extract_cylindrical_faces(shape)
        holes = group_coaxial_features(features)
        holes = detect_through_holes(shape, holes)

        # 4. Export 3D model for web viewer
        glb_path = job_dir / "model.glb"
        try:
            export_glb(shape, glb_path)
        except Exception as e:
            logger.warning(f"GLB export failed, trying STL: {e}")
            stl_path = job_dir / "model.stl"
            export_stl(shape, stl_path)
            job["stl_path"] = str(stl_path)

        job["glb_path"] = str(glb_path)

        # 5. Matching (with LLM resolver when using LLM mode)
        matches, unmatched_ann, unmatched_holes = match_annotations_to_features(
            annotations, holes,
            pdf_path=pdf_path if use_llm else None,
            use_llm_resolver=use_llm and USE_VISION_LLM,
        )

        # 6. Write output
        output_path = job_dir / "result.json"
        write_output(
            matches, unmatched_ann, unmatched_holes,
            output_path, job["pdf_name"], job["step_name"],
            llm_enhanced=use_llm and USE_VISION_LLM,
        )

        # Store results for API access
        job["status"] = "complete"
        job["output_path"] = str(output_path)
        job["annotations"] = [a.model_dump() for a in annotations]
        job["holes"] = [h.model_dump() for h in holes]
        job["matches"] = [m.model_dump() for m in matches]
        job["summary"] = {
            "annotations_found": len(annotations),
            "holes_found": len(holes),
            "matched": len(matches),
            "unmatched_annotations": len(unmatched_ann),
            "unmatched_holes": len(unmatched_holes),
            "avg_confidence": (
                round(sum(m.confidence for m in matches) / len(matches), 3)
                if matches else 0.0
            ),
        }

        return {"job_id": job_id, "status": "complete", "summary": job["summary"]}

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise HTTPException(500, f"Analysis failed: {e}")


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
        raise HTTPException(404, "No evaluation results found. Run: uv run python scripts/evaluate.py")
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
        elif tc_id.startswith("SYN"):
            category = "SYN"
        else:
            category = "other"

        testcases.append({
            "id": tc_id,
            "category": category,
            "has_pdf": has_pdf,
            "has_step": has_step,
            "evaluation": eval_data.get(tc_id, {}),
        })

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


@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return {"status": jobs[job_id]["status"]}


if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
