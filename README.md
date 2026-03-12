# DrawMind3D

**GenAI-powered solution that links technical drawing annotations (PDF) to 3D CAD model features, with focus on drilled and threaded holes.**

Built for the Manukai AG Hackathon Challenge: *GenAI in Manufacturing* (April 2026).

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
4. **3D Feature Extraction** — STEP file loaded via OCP (OpenCASCADE), cylindrical faces extracted, grouped into coaxial hole features, through-holes detected via ray casting
5. **Multi-Factor Matching** — Hungarian Algorithm for optimal annotation-to-hole assignment, using weighted scoring (diameter 45%, type 20%, depth 20%, uniqueness 10%, count 5%)
6. **Structured Output** — JSON with match results, confidence scores, scoring breakdown and evidence traces

### LLM Strategy (via OpenRouter)

| Task | Model | Purpose |
|------|-------|---------|
| PDF page vision analysis | Gemini 2.5 Flash | Detect annotations in drawing images |
| Ambiguous match resolution | Claude Sonnet | Reasoning about spatial context |
| Text parsing edge cases | Claude Haiku | Cheap text classification |
| Core pipeline | Regex + rules | Works fully without any LLM |

All LLM calls go through [OpenRouter](https://openrouter.ai) — single API key for any model.

## Web UI

Upload PDF + STEP files through the browser and get interactive results:

- **3D Viewer** (Three.js) — rotate model, highlighted hole features
- **PDF Viewer** (PDF.js) — annotation bounding box overlays
- **Matches Table** — confidence scores, click to link 2D↔3D views
- **Evaluation Tab** — filter by CTC, FTC and Synthetic with per-category charts
- **LLM Toggle** — enable/disable Vision LLM enhancement

## Examples

The `examples/` folder contains ready-to-use test cases. Each subfolder has a `drawing.pdf` and `model.stp` that can be uploaded directly in the web UI.

| Folder | Source | Description |
|--------|--------|-------------|
| CTC-01 … CTC-05 | NIST | Combinational tolerancing cases (metric and inch) |
| FTC-06 … FTC-11 | NIST | Fully-toleranced industrial cases |
| SYN-01 … SYN-05 | Synthetic | Parametric test parts with known ground truth |

## Evaluation Results

Evaluated on **5 NIST CTC**, **6 NIST FTC** industrial test cases and **5 synthetic** test cases with ground truth labels.

### With Vision LLM (Gemini Flash)

| Category | Cases | Precision | Recall | F1 | Linking | Confidence |
|----------|-------|-----------|--------|-----|---------|------------|
| CTC (Combinational) | 5 | 46.7% | 50.7% | 47.5% | 64.0% | 79.7% |
| FTC (Fully-Toleranced) | 6 | 70.1% | 98.1% | 79.7% | 77.0% | 81.1% |
| Synthetic | 5 | 78.7% | 92.1% | 84.8% | 94.9% | 92.0% |
| **Overall (16 cases)** | **16** | **65.4%** | **81.4%** | **71.2%** | **79.9%** | **84.1%** |

**Top performers:** FTC-08 (94.7% F1, 95.2% Linking), SYN-05 (100% F1, 100% Linking), FTC-09 (90.9% F1, 94.4% Linking)

### Without LLM (Regex + OCR only)

| Category | F1 | Linking | Note |
|----------|----|---------|------|
| CTC | 0.0% | 0.0% | Vector-drawn PDFs, no extractable text |
| FTC | 23.3% | 55.4% | Only FTC-07, FTC-09, FTC-10 have extractable text |
| Synthetic | 81.6% | 100.0% | Pure regex extraction, no vision needed |
| **Overall** | **34.2%** | **47.8%** | |

**Key insight:** Most NIST cases use vector-drawn annotations without searchable text. The Vision LLM raises overall F1 from 34.2% to 71.2%. Multi-factor scoring with secondary diameter support and UTS thread matching ensures accurate linking of complex features.

Evaluation charts: [`data/evaluation/presentation/`](data/evaluation/presentation/)

### Test Data

**Synthetic** — 5 parametric parts generated with OCP + PyMuPDF, each with known ground truth. See [`scripts/generate_synthetic.py`](scripts/generate_synthetic.py).

| Part | Holes | Description |
|------|-------|-------------|
| SYN-01 | 6 | Basic through-holes and blind holes |
| SYN-02 | 7 | M6, M8 and M10 threads with varying depths |
| SYN-03 | 5 | Imperial unit system (inch→mm conversion) |
| SYN-04 | 9 | Counterbores, countersinks and threads combined |
| SYN-05 | 12 | Stress test with 12 unique holes |

**NIST PMI** — 11 industrial test cases from the [NIST MBE PMI](https://www.nist.gov/ctl/smart-connected-systems-division/smart-connected-manufacturing-systems-group/mbe-pmi-0) benchmark suite. Ground truth in [`data/ground_truth/`](data/ground_truth/).

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

| Component | Technology | Purpose |
|-----------|-----------|---------|
| 3D Analysis | OCP (cadquery-ocp) | STEP file parsing, B-Rep geometry |
| PDF Extraction | PyMuPDF + Tesseract | Text, bounding boxes, OCR |
| Vision AI | Gemini Flash (OpenRouter) | Annotation detection in images |
| Disambiguation | Claude Sonnet (OpenRouter) | Ambiguous match resolution |
| Matching | SciPy (Hungarian Algorithm) | Optimal assignment |
| Web Backend | FastAPI + Uvicorn | REST API |
| 3D Viewer | Three.js | Interactive 3D visualization |
| PDF Viewer | PDF.js | PDF rendering with overlays |
| Package Manager | uv | Fast dependency resolution |
| Containerization | Docker Compose | Reproducible deployment |

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
│   └── SYN-01/ … SYN-05/    # Synthetic test parts
├── drawmind/                 # Main Python package
│   ├── models.py             # Pydantic data models
│   ├── config.py             # Configuration & environment
│   ├── cli.py                # CLI orchestration
│   ├── pdf/                  # PDF annotation extraction
│   │   ├── extractor.py      # Text extraction (native + OCR)
│   │   ├── parser.py         # Regex-based annotation parsing
│   │   ├── vision.py         # Vision LLM integration
│   │   └── patterns.py       # Regex pattern definitions
│   ├── cad/                  # 3D model analysis
│   │   ├── step_reader.py    # STEP file loading (OCP)
│   │   ├── feature_extractor.py  # Cylindrical face extraction
│   │   └── thread_table.py   # ISO metric thread database
│   ├── matching/             # Annotation-to-feature matching
│   │   ├── matcher.py        # Hungarian Algorithm assignment
│   │   └── scoring.py        # Multi-factor scoring
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
