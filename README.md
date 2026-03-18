# DrawMind3D

**GenAI-powered solution that links technical drawing annotations (PDF) to 3D CAD model features, with focus on drilled and threaded holes.**

Built for the Manukai AG Hackathon Challenge: _GenAI in Manufacturing_ (April 2026).

## Quick Start

```bash
# Docker (recommended)
cp .env.example .env          # Add your OPENROUTER_API_KEY
docker compose up --build     # Open http://localhost:8000

# — or local with uv —
uv sync
uv run python web/app.py      # Web UI at http://localhost:8000
uv run python run.py --pdf drawing.pdf --step model.step  # CLI
```

> The pipeline works without an API key (regex + OCR only). Add an [OpenRouter](https://openrouter.ai) key to enable Vision LLM enhancement.

## Architecture

```
PDF Drawing ──► PyMuPDF / OCR ──► Regex Parser ──► Annotations ─┐
                                       │                        │
                                 Vision LLM ─────────┘          │
                                 (Gemini Flash)            Matching ──► JSON Output
                                                                │
STEP Model ──► OCP (OpenCASCADE) ──► Cylindrical Features ──────┘
                                     (coaxial grouping,
                                      through-hole detection)
```

### Pipeline Steps

1. **PDF Text Extraction** — Native text + bounding boxes via PyMuPDF, with OCR fallback (Tesseract) for scanned drawings
2. **Annotation Parsing** — Regex-based classification of thread callouts (`M10x1.5-6H`), diameters (`Ø5.5`), depths, tolerances, counterbores/countersinks. Automatic inch↔mm conversion
3. **Vision LLM Enhancement** (optional) — Gemini Flash analyzes each PDF page as an image to detect annotations missed by regex (critical for vector-drawn PDFs where text extraction fails)
4. **3D Feature Extraction** — STEP file loaded via OCP (OpenCASCADE), cylindrical faces extracted, grouped into coaxial hole features, through-holes detected via bounding box analysis
5. **Multi-Factor Matching** — Hungarian Algorithm for optimal annotation-to-hole assignment, using weighted scoring (diameter 45%, type 22%, depth 18%, count 8%, uniqueness 4%, spatial 3%)
6. **Structured Output** — JSON with match results, confidence scores, scoring breakdown and evidence traces

### LLM Strategy (via OpenRouter)

| Task                       | Model            | Purpose                                       |
| -------------------------- | ---------------- | --------------------------------------------- |
| PDF page vision analysis   | Gemini 2.5 Flash | Detect annotations in drawing images          |
| Ambiguous match resolution | Gemini Flash     | Batch disambiguation of unmatched annotations |
| Unit system detection      | Gemini Flash     | Fallback when PDF text is insufficient        |
| Core pipeline              | Regex + rules    | Works fully without any LLM                   |

All LLM calls go through [OpenRouter](https://openrouter.ai) — single API key for any model.

### Prompt Strategy & Consistency

The system uses structured prompting with explicit extraction rules to ensure consistent results:

- **Vision extraction prompt** (`drawmind/llm/prompts.py`): Provides the LLM with a comprehensive whitelist of valid hole annotations (threads, diameters, depths, counterbores, countersinks) and an explicit blacklist of non-hole features to ignore (part dimensions, GD&T tolerance zones, chamfers, surface roughness). This prevents false positives from overall part dimensions being classified as hole callouts.
- **Unit-aware parsing**: The prompt instructs the LLM to report values exactly as shown (no implicit conversion), while the pipeline handles inch→mm conversion based on the detected unit system (from title block analysis or LLM fallback).
- **Structured JSON output**: Each LLM call requests a strict JSON schema with typed fields (`type`, `parsed`, `bbox_percent`, `confidence`, `multiplier`), enabling deterministic downstream processing regardless of LLM response variability.
- **Multi-layer validation**: Vision LLM annotations are cross-validated against the 3D model — annotations whose diameter has no plausible 3D match are filtered as false positives before scoring. This geometric validation layer ensures consistency between the LLM extraction and physical reality.
- **Disambiguation with context**: When annotations remain unmatched after the Hungarian Algorithm, a batch disambiguation prompt provides all candidates to the LLM simultaneously with explicit scoring guidance (drill diameter vs. nominal diameter for threads), preventing inconsistent one-at-a-time decisions.

## Web UI

Upload PDF + STEP files through the browser and get interactive results:

- **3D Viewer** (Three.js) — rotate model, highlighted hole features
- **PDF Viewer** (PDF.js) — annotation bounding box overlays
- **Matches Table** — confidence scores, click to link 2D↔3D views
- **Evaluation Tab** — filter by CTC, FTC and Synthetic with per-category charts
- **LLM Toggle** — enable/disable Vision LLM enhancement

## Examples

The `examples/` folder contains ready-to-use test cases. Each subfolder has a `drawing.pdf` and `model.stp` that can be uploaded directly in the web UI.

| Folder                                | Source    | Description                                       |
| ------------------------------------- | --------- | ------------------------------------------------- |
| CTC-01 … CTC-05                       | NIST      | Combinational tolerancing cases (metric and inch) |
| FTC-06 … FTC-11                       | NIST      | Fully-toleranced industrial cases                 |
| D2MI-904 … D2MI-908                   | NIST      | Design-to-Manufacturing (inch, machined housings) |
| SYN-01-SimpleBlock … SYN-05-ManyHoles | Synthetic | Parametric test parts with known ground truth     |

## Evaluation Results

Evaluated on **5 NIST CTC**, **6 NIST FTC** industrial test cases, **5 NIST D2MI** machined housings, and **5 synthetic** test cases with ground truth labels.

### With Vision LLM (Gemini Flash)

| Category               | Cases  | Precision | Recall    | F1        | Linking   | Confidence |
| ---------------------- | ------ | --------- | --------- | --------- | --------- | ---------- |
| CTC (Combinational)    | 5      | 72.7%     | 54.1%     | 58.5%     | 94.0%     | 86.1%      |
| FTC (Fully-Toleranced) | 6      | 89.3%     | 87.7%     | 87.5%     | 98.2%     | 70.9%      |
| D2MI (Design-to-Mfg)   | 5      | 47.1%     | 100.0%    | 61.8%     | 100.0%    | 87.2%      |
| Synthetic              | 5      | 78.0%     | 94.3%     | 85.0%     | 94.9%     | 94.2%      |
| **Overall (21 cases)** | **21** | **72.6%** | **84.2%** | **73.9%** | **96.8%** | **84.0%**  |

**Top performers:** SYN-05 (100% F1, 100% Linking), FTC-07 (91.7% F1, 95.8% Linking), SYN-03 (90.9% F1, 100% Linking), FTC-08/FTC-10 (87.5% F1, 100% Linking)

> FTC-11 (torus part, no drilled holes) correctly returns 0 annotations — both with and without LLM.

### Without LLM (Regex + OCR only)

| Category    | F1        | Linking   | Note                                              |
| ----------- | --------- | --------- | ------------------------------------------------- |
| CTC         | 0.0%      | 0.0%      | Vector-drawn PDFs, no extractable text            |
| FTC         | 40.0%     | 66.7%     | Only FTC-07, FTC-09, FTC-10 have extractable text |
| Synthetic   | 81.6%     | 100.0%    | Pure regex extraction, no vision needed           |
| D2MI        | 0.0%      | 0.0%      | Vector-drawn inch drawings, no extractable text   |
| **Overall** | **30.9%** | **42.9%** |                                                   |

**Key insight:** Most NIST cases use vector-drawn annotations without searchable text. The Vision LLM raises overall F1 from 30.9% to 73.9% and linking accuracy from 42.9% to 96.8%. Vision-based unit detection ensures correct inch→mm conversion even when PDF text extraction fails.

Evaluation charts: [`data/evaluation/presentation/`](data/evaluation/presentation/)

### Test Data

**Synthetic** — 5 parametric parts generated with OCP + PyMuPDF, each with known ground truth. See [`scripts/generate_synthetic.py`](scripts/generate_synthetic.py).

| Part   | Holes | Description                                     |
| ------ | ----- | ----------------------------------------------- |
| SYN-01 | 6     | Basic through-holes and blind holes             |
| SYN-02 | 7     | M6, M8 and M10 threads with varying depths      |
| SYN-03 | 5     | Imperial unit system (inch→mm conversion)       |
| SYN-04 | 9     | Counterbores, countersinks and threads combined |
| SYN-05 | 12    | Stress test with 12 unique holes                |

**NIST PMI** — 16 industrial test cases from the [NIST MBE PMI](https://www.nist.gov/ctl/smart-connected-systems-division/smart-connected-manufacturing-systems-group/mbe-pmi-0) benchmark suite, plus 5 [NIST D2MI](https://www.nist.gov/ctl/smart-connected-systems-division/smart-connected-manufacturing-systems-group/enabling-digital-0) machined housing parts (inch drawings). Ground truth in [`data/ground_truth/`](data/ground_truth/).

**Synthetic Data Generation Process** — The synthetic test parts are generated programmatically using [`scripts/generate_synthetic.py`](scripts/generate_synthetic.py):

1. **3D Model**: OCP (OpenCASCADE) creates a parametric base body (box), then cuts cylindrical holes using `BRepAlgoAPI_Cut` with known diameters, depths, and positions. Countersinks use `BRepPrimAPI_MakeCone`, counterbores use stepped cylinder cuts.
2. **PDF Drawing**: PyMuPDF generates a technical drawing with annotations placed via leader lines at known bounding box positions. Annotation text is rendered as rasterized images (not extractable text) to test the Vision LLM extraction pipeline.
3. **Ground Truth**: Each test case includes a `*_ground_truth.json` file mapping each annotation to its expected 3D feature match, enabling automated precision/recall/F1 evaluation.

## Output Format (JSON)

The pipeline produces a structured JSON file with the following key sections:

```json
{
  "metadata": {
    "pdf_file": "drawing.pdf",
    "step_file": "model.stp",
    "timestamp": "2026-03-18T10:00:00+00:00",
    "pipeline_version": "1.0.0",
    "llm_enhanced": true
  },
  "features": [
    {
      "id": "match_001",
      "annotation_id": "ann_001",
      "feature_id": "hole_001",
      "annotation_text": "M10×1.5-6H",
      "parsed_interpretation": {
        "thread_spec": "M10x1.5",
        "nominal_diameter": 10.0,
        "pitch": 1.5,
        "tolerance_class": "6H"
      },
      "feature_3d_ref": {
        "hole_group_id": "hole_001",
        "face_ids": [45, 67],
        "primary_diameter_mm": 8.376,
        "center": [10.5, 20.3, 5.0],
        "axis_direction": [0.0, 0.0, -1.0],
        "total_depth_mm": 15.0,
        "is_through_hole": false,
        "hole_type": "simple"
      },
      "confidence": 0.92,
      "confidence_level": "high",
      "scoring_breakdown": {
        "diameter": 0.95,
        "depth": 0.85,
        "type_compatibility": 1.0,
        "count_agreement": 0.5,
        "uniqueness": 1.0,
        "spatial": 0.7,
        "source_confidence": 0.9
      },
      "evidence": {
        "bbox": { "x0": 120.5, "y0": 85.3, "x1": 195.2, "y1": 97.7, "page": 0 },
        "source": "vision_llm",
        "multiplier": 1
      }
    }
  ],
  "unmatched_annotations": [],
  "unmatched_features": [],
  "summary": {
    "total_annotations_found": 8,
    "total_3d_holes": 6,
    "matched": 5,
    "high_confidence": 4,
    "needs_review": 1,
    "unmatched_annotations": 3,
    "unmatched_holes": 1,
    "avg_confidence": 0.89,
    "warnings": ["3 annotation(s) could not be matched to any 3D feature"]
  }
}
```

Each matched feature includes:

- **Unique ID** per hole feature (`match_001`, `match_002`, ...)
- **Annotation text** as found in the drawing + **parsed interpretation** (thread type, size, pitch, tolerance class, depth)
- **3D feature reference**: face IDs, center coordinates, axis direction, diameter and depth — sufficient to re-locate the feature in the CAD model
- **Confidence score** (0–1) with **confidence level** (high ≥0.8, review 0.6–0.8)
- **Scoring breakdown** per factor (diameter, depth, type, count, uniqueness, spatial)
- **Evidence trace**: bounding box coordinates and page reference in the PDF drawing

Full schema: [`drawmind/output/schema.py`](drawmind/output/schema.py)

## Setup

### Option A: Docker Compose (recommended)

```bash
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY

docker compose up --build
# Open http://localhost:8000
```

### Option B: Local with uv

```bash
# Install uv: https://docs.astral.sh/uv/getting-started/installation/
uv sync

# Configure API key (optional — pipeline works without LLM)
cp .env.example .env
# Edit .env and add your OPENROUTER_API_KEY

# Run Web UI
uv run python web/app.py

# Run CLI
uv run python run.py --pdf drawing.pdf --step model.step -o result.json
uv run python run.py --pdf drawing.pdf --step model.step --no-llm  # without LLM
uv run python run.py --pdf drawing.pdf --step model.step -v         # verbose
```

### Running Evaluation

```bash
uv run python scripts/evaluate.py          # Without LLM
uv run python scripts/evaluate.py --llm    # With Vision LLM
python scripts/generate_charts.py          # Presentation charts
```

To add custom test cases, place `MyPart.pdf`, `MyPart.stp` and `MyPart_ground_truth.json` in `data/synthetic/` — they are auto-discovered. See existing ground truth files for the JSON format.

## Technologies

| Component        | Technology                  | Purpose                                       |
| ---------------- | --------------------------- | --------------------------------------------- |
| 3D Analysis      | OCP (cadquery-ocp)          | STEP file parsing, B-Rep geometry             |
| PDF Extraction   | PyMuPDF + Tesseract         | Text, bounding boxes, OCR                     |
| Vision AI        | Gemini Flash (OpenRouter)   | Annotation detection in images                |
| Disambiguation   | Gemini Flash (OpenRouter)   | Batch disambiguation of unmatched annotations |
| Matching         | SciPy (Hungarian Algorithm) | Optimal assignment                            |
| Web Backend      | FastAPI + Uvicorn           | REST API                                      |
| 3D Viewer        | Three.js                    | Interactive 3D visualization                  |
| PDF Viewer       | PDF.js                      | PDF rendering with overlays                   |
| Package Manager  | uv                          | Fast dependency resolution                    |
| Containerization | Docker Compose              | Reproducible deployment                       |

## Project Structure

```
DrawMind3D/
├── run.py                    # CLI entry point
├── pyproject.toml            # Dependencies (uv)
├── Dockerfile                # Container setup
├── docker-compose.yml        # Docker Compose config
├── examples/                 # Ready-to-use test cases (PDF + STEP)
│   ├── CTC-01/ … CTC-05/    # NIST combinational tolerancing
│   ├── FTC-06/ … FTC-11/    # NIST fully-toleranced
│   ├── D2MI-904/ … D2MI-908/ # NIST design-to-manufacturing (inch)
│   └── SYN-01-SimpleBlock/ … SYN-05-ManyHoles/  # Synthetic test parts
├── drawmind/                 # Main Python package
│   ├── models.py             # Pydantic data models
│   ├── config.py             # Configuration & environment
│   ├── cli.py                # CLI orchestration
│   ├── pdf/                  # PDF annotation extraction
│   │   ├── extractor.py      # Text extraction (native + OCR)
│   │   ├── parser.py         # Regex-based annotation parsing
│   │   ├── vision.py         # Vision LLM integration
│   │   ├── patterns.py       # Regex pattern definitions
│   │   └── leader_lines.py   # Leader line detection & tracing
│   ├── cad/                  # 3D model analysis
│   │   ├── step_reader.py    # STEP file loading (OCP)
│   │   ├── feature_extractor.py  # Cylindrical face extraction
│   │   ├── mesh_exporter.py  # GLB mesh export for 3D viewer
│   │   └── thread_table.py   # ISO metric thread database
│   ├── matching/             # Annotation-to-feature matching
│   │   ├── matcher.py        # Hungarian Algorithm assignment
│   │   ├── scoring.py        # Multi-factor scoring
│   │   └── llm_resolver.py   # LLM-based ambiguity resolution
│   ├── llm/                  # LLM integration
│   │   ├── client.py         # OpenRouter API client
│   │   └── prompts.py        # Vision & disambiguation prompts
│   └── output/               # JSON output generation
│       ├── writer.py         # Output serialization
│       └── schema.py         # Output JSON schema
├── web/                      # Web UI
│   ├── app.py                # FastAPI backend
│   └── static/               # Frontend (JS/CSS/HTML)
├── tests/                    # Test suite
├── scripts/                  # Evaluation & utilities
└── data/                     # Ground truth and evaluation results
```

## License

Proprietary — see [LICENSE](LICENSE).
