# DrawMind3D

**GenAI-powered solution that links technical drawing annotations (PDF) to 3D CAD model features, with focus on drilled and threaded holes.**

### Highlights

- **Clean licensing** — PDF handling via PDFium; no copyleft component in the product ([THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md))
- **One pipeline** — CLI, web app and evaluation share `drawmind.pipeline.analyze()`, usable as a library, with a status for every stage so degraded runs are visible
- **Robust on real drawings** — unit detection, counterbore and countersink callouts, stepped bores, through-hole detection, cropped and multi-page PDFs
- **Hardened web app** — upload and page limits, thread-safe PDF handling, model output never rendered as raw HTML
- **Evaluation** — 21 NIST and synthetic cases with a generated report, case subsets and a vision model comparison
- **Tests** — 245 automated tests

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

To evaluate it on your own drawings, including offline and with a self-hosted model, see [EVALUATION.md](EVALUATION.md).

## Architecture

```
PDF Drawing ──► PDFium / OCR ──► Regex Parser ──► Annotations ─┐
                                       │                        │
                                 Vision LLM ─────────┘          │
                                 (Gemini Flash)            Matching ──► JSON Output
                                                                │
STEP Model ──► OCP (OpenCASCADE) ──► Cylindrical Features ──────┘
                                     (coaxial grouping,
                                      through-hole detection)
```

### Pipeline Steps

1. **PDF Text Extraction** — Native text + bounding boxes via PDFium, with OCR fallback (Tesseract) for scanned drawings
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
- **Evaluation Tab** — filter by CTC, FTC, D2MI and Synthetic with per-category charts
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
| CTC (Combinational)    | 5      | 68.0%     | 54.1%     | 56.8%     | 90.7%     | 87.3%      |
| FTC (Fully-Toleranced) | 5      | 95.3%     | 86.8%     | 90.2%     | 93.7%     | 85.6%      |
| D2MI (Design-to-Mfg)   | 5      | 42.9%     | 92.0%     | 56.0%     | 97.8%     | 84.1%      |
| Synthetic              | 5      | 79.2%     | 94.3%     | 85.8%     | 97.1%     | 93.8%      |
| **Overall**            | **20** | **71.3%** | **81.8%** | **72.2%** | **94.8%** | **87.7%**  |

Across the corpus that is 115 of 138 required callouts found, at 19.2 s per
drawing. Averages are per case over the twenty cases that have at least one
required callout. FTC-11 is the twenty-first: a torus part with no drilled
holes, where the pipeline correctly returns zero annotations both with and
without the model, so it carries no F1 to average.

These figures move by a few points between runs because the model is sampled,
not deterministic. Treat any single number as one sample: the per-case spread
between two consecutive runs of the same code reached ±13 points, while the
average moved by less than one.

**Top performers:** SYN-05 (100% F1, 100% Linking), FTC-07 (91.7% F1, 95.8% Linking), SYN-03 (90.9% F1, 100% Linking), FTC-08/FTC-10 (87.5% F1, 100% Linking)

### Vision Model Comparison

The same pipeline with only the vision model swapped, on the six-case `quick`
set (CTC-01, D2MI-904, FTC-07, FTC-10, SYN-02, SYN-03). Raw results are in
`evaluation/model_comparison/`.

| Model                        | F1    | Linking | Price $/Mtok in / out | Weights                |
| ---------------------------- | ----- | ------- | --------------------- | ---------------------- |
| openai/gpt-6-astra           | 80.0% | 97.6%   | 10.00 / 50.00         | closed                 |
| openai/gpt-5.6-luna          | 79.7% | 92.3%   | 0.20 / 1.20           | closed                 |
| xiaomi/mimo-v2.6-pro         | 77.7% | 97.6%   | 0.43 / 0.87           | closed (API only)      |
| x-ai/grok-4.7                | 76.8% | 100.0%  | 1.60 / 4.80           | closed                 |
| anthropic/claude-opus-5      | 75.2% | 95.2%   | 5.00 / 25.00          | closed                 |
| google/gemini-2.5-flash      | 75.0% | 94.4%   | 0.30 / 2.50           | closed (default)       |
| deepseek/deepseek-v4.1-flash | 73.3% | 96.1%   | 0.30 / 1.20           | open, datacenter-scale |
| google/gemini-3.8-flash      | 69.2% | 79.6%   | 0.75 / 3.75           | closed                 |
| z-ai/glm-5.3-flash           | 65.4% | 81.0%   | 0.15 / 0.50           | open, datacenter-scale |

qwen/qwen3.8-max was also run but produced no usable result: after 57 minutes
its answers still were not valid JSON on every page, so it has no row.

F1 measures how well the model reads the hole callouts off the drawing;
linking measures how many of the callouts it found end up on the right 3D
feature. The two can disagree: grok-4.7 links everything it reads correctly
but reads fewer callouts than the two OpenAI models.

Read the table as tiers, not as a ranking. Six cases are a small sample, and
Gemini 2.5 Flash scored 79.5% and 75.0% in two runs of identical code — a
spread larger than most gaps between neighbouring rows. What the table does
support:

- The top six are close. Price buys no measurable accuracy here: gpt-5.6-luna
  is within a point of gpt-6-astra at about a fiftieth of the price.
- Gemini 2.5 Flash, the default, holds its own against models costing many
  times more; its successor 3.8 Flash scores lower.
- The best open-weight model, DeepSeek V4.1 Flash, is within the same band as
  the closed models, but it needs datacenter hardware. The open-weight models
  small enough for one or two GPUs (`--group self-hostable`) have not been
  measured.

The gap between the two tables below is the point: the vision model is not an
enhancement layer, it is the component that reads the drawing. The NIST
drawings carry their callouts as vector artwork rather than text, and stock
Tesseract recognises none of the diameter symbols on them — raising the render
resolution from 300 to 600 DPI does not change that. Any replacement backend,
self-hosted or otherwise, has to be competitive at reading dense engineering
drawings or accuracy falls back to the regex-and-OCR baseline.

### Without LLM (Regex + OCR only)

| Category    | F1        | Linking   | Note                                              |
| ----------- | --------- | --------- | ------------------------------------------------- |
| CTC         | 0.0%      | 0.0%      | Vector-drawn PDFs, no extractable text            |
| FTC         | 27.9%     | 60.0%     | Only FTC-07, FTC-09, FTC-10 have extractable text |
| Synthetic   | 81.6%     | 100.0%    | Pure regex extraction, no vision needed           |
| D2MI        | 0.0%      | 0.0%      | Vector-drawn inch drawings, no extractable text   |
| **Overall** | **27.4%** | **40.0%** |                                                   |

**Why the offline numbers split so sharply:** ten of the twenty scorable NIST
cases carry their callouts as pure path geometry rather than text. AutoCAD's
single-stroke SHX fonts — long the default for dimension text in DWG-based
mechanical drawings — are emitted with no font object and no `ToUnicode` map,
so the glyph outline is drawn correctly while the character code never exists
in the file. No amount of rendering resolution recovers it, which is why OCR
does not close the gap either: the text is also rotated and sheared by the 3D
projection. This is a property of how those drawings were exported, not of the
parser, and it is the reason the vision model lifts overall F1 from 27.4% to
72.2% and linking from 40.0% to 94.8%. Drawings exported with TrueType
annotation text land in the synthetic-case range instead.

The failure breakdown in [`evaluation/report.html`](evaluation/README.md) splits
every missed callout into "never read from the page" and "read but not
understood". Offline that split is 73 to 17; with the vision model it is 20 to 3.
In both modes the gap is dominated by reading, not by parsing.

Full report: [`evaluation/report.html`](evaluation/README.md) · presentation charts: [`evaluation/presentation/`](evaluation/presentation/)

### Test Data

**Synthetic** — 5 parametric parts, each with known ground truth. The fixtures are committed; [`scripts/generate_synthetic.py`](scripts/generate_synthetic.py) regenerates them and is a development tool rather than part of the product, with its own note in [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md).

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
2. **PDF Drawing**: a technical drawing is generated with annotations placed via leader lines at known bounding box positions. Most annotations are written as extractable text; a few in SYN-01 and SYN-02 are rendered as rasterized images, so the fixtures also exercise the OCR and vision path the NIST drawings depend on.
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

Full schema: [`drawmind/output/schema.py`](drawmind/output/schema.py). The
schema is checked against real pipeline output by `tests/test_output_schema.py`,
so it documents the contract rather than describing an intention.

## Using It as a Library

`drawmind.pipeline.analyze()` is the whole product in one call. The CLI and the
web application are thin wrappers around it and have no capabilities of their own.

```python
from drawmind.pipeline import Settings, analyze

result = analyze("drawing.pdf", "model.stp", settings=Settings(use_llm=False))

for match in result.matches:
    print(match.annotation_text, "->", match.feature_id, f"{match.confidence:.0%}")
```

`Settings` controls behaviour; nothing is read from global state at call time:

| Field         | Effect                                                                |
| ------------- | --------------------------------------------------------------------- |
| `use_llm`     | `False` guarantees no model provider is contacted anywhere in the run |
| `unit_system` | `"metric"` or `"inch"` to override automatic detection                |

The returned `AnalysisResult` carries `matches`, `holes`, `annotations`,
`unmatched_annotations`, `unmatched_holes`, the loaded `shape`, and a `stages`
list recording what every step actually did:

```python
for stage in result.stages:
    print(stage.name, stage.status.value, stage.detail)
# text_extraction    ok      8 native, 0 OCR text elements
# ocr                skipped native text layer was sufficient
# unit_detection     ok      metric
# annotation_parsing ok      6 engineering annotations
# vision_llm         skipped disabled by caller
# leader_lines       ok      6 annotations with a traced target
# cad_features       ok      6 hole groups (4 through) from 6 faces
# matching           ok      5 matched pairs
# llm_disambiguation skipped disabled by caller
```

`result.llm_used` is derived from those outcomes, not from the request, so a
provider that was unreachable never reads as a successful enhancement.

### Processing without sending drawings anywhere

`Settings(use_llm=False)` disables every outbound call, including the vision
fallback inside unit detection. This is covered by a test that forces a
configured API key and then asserts no provider is contacted
(`tests/test_pipeline.py`). Offline accuracy is reported separately in
[`evaluation/report.html`](evaluation/README.md).

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

Everything measured lives in [`evaluation/`](evaluation/README.md). The
generated `evaluation/report.html` is a single self-contained page with the
headline numbers, the failure causes and the per-drawing detail.

```bash
uv run python scripts/evaluate.py          # Offline: regex + OCR, no model calls
uv run python scripts/evaluate.py --llm    # With the configured vision model
uv run python scripts/eval_report.py       # Rebuild the report from stored results
uv run python scripts/generate_charts.py   # Presentation charts
```

A full LLM run costs real money and takes minutes, so named subsets keep iteration cheap. `quick` holds one case per family and covers both unit systems and both extraction paths, so a result on it still says something about the whole corpus:

| Set      | Cases | Use                                                          |
| -------- | ----- | ------------------------------------------------------------ |
| `smoke`  | 2     | does the pipeline run at all                                 |
| `quick`  | 6     | default for iterating and for model comparison               |
| `metric` | 5     | metric drawings only                                         |
| `inch`   | 5     | imperial drawings only                                       |
| `vision` | 6     | cases with no usable native text — measures the vision model |
| `native` | 4     | cases whose text layer is readable — measures the regex path |
| `full`   | 21    | the whole corpus, for reported numbers                       |

```bash
EVAL_SET=quick uv run python scripts/evaluate.py --llm
EVAL_CASES=SYN-01-SimpleBlock,FTC-07 uv run python scripts/evaluate.py --llm   # explicit list
```

To add custom test cases, place `MyPart.pdf`, `MyPart.stp` and `MyPart_ground_truth.json` in `data/synthetic/` — they are auto-discovered. See existing ground truth files for the JSON format.

### Comparing Vision Models

The vision model is the component that reads the drawing, so it dominates accuracy. `scripts/compare_models.py` runs the full evaluation once per model and prints a ranked table:

```bash
uv run python scripts/compare_models.py --list     # show the candidate models and case sets
uv run python scripts/compare_models.py            # run all of them
uv run python scripts/compare_models.py --set quick                # 6 representative cases instead of 21
uv run python scripts/compare_models.py --group self-hostable      # only open-weight models that fit on 1-2 GPUs
uv run python scripts/compare_models.py --models google/gemini-2.5-flash openai/gpt-5.6-luna
uv run python scripts/compare_models.py --cases SYN-01-SimpleBlock FTC-07   # cheap smoke run first
uv run python scripts/compare_models.py --set quick --resume       # continue an interrupted run
```

Results are saved after every model, so an interrupted run loses at most the model in progress; `--resume` skips the ones already stored.

Per-model results are written to `evaluation/model_comparison/`, kept separate from the published benchmark so an experiment can never overwrite the evidence behind the documented numbers. The candidate list spans price tiers and vendors, including open-weight models, so the table also informs whether a self-hosted backend is viable.

### Regression Safety Net

The PDF layer has a characterisation baseline over 13 drawings covering metric and imperial, single and multi-page, rotated and upright, native-text and OCR-only:

```bash
uv run python scripts/pdf_layer_snapshot.py --compare tests/golden/pdf_layer.json
```

It reports differences in extracted text, annotations, unit detection, page geometry and leader-line targets. Regenerate the baseline with `--out` after an intentional change.

## Technologies

| Component        | Technology                  | Purpose                                       |
| ---------------- | --------------------------- | --------------------------------------------- |
| 3D Analysis      | OCP (cadquery-ocp)          | STEP file parsing, B-Rep geometry             |
| PDF Extraction   | PDFium + Tesseract          | Text, bounding boxes, vector paths, OCR       |
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
├── EVALUATION.md             # Guide for evaluating on your own drawings
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
│   ├── pipeline.py           # analyze(): the one pipeline behind CLI, web and evaluation
│   ├── cli.py                # Command-line interface
│   ├── pdf/                  # PDF annotation extraction
│   │   ├── backend.py        # PDF engine access (PDFium): text, paths, raster
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
├── tests/                    # Test suite (245 tests)
│   ├── pdf_builder.py        # Minimal PDF writer for fixtures
│   └── golden/               # PDF layer characterisation baseline
├── scripts/                  # Evaluation & utilities
│   ├── evaluate.py           # Precision/recall/F1 over the test cases
│   ├── eval_report.py        # Build evaluation/report.html from the results
│   ├── compare_models.py     # Rank vision models on the same corpus
│   ├── pdf_layer_snapshot.py # PDF layer regression baseline
│   ├── generate_charts.py    # Presentation charts
│   └── generate_synthetic.py # Regenerate synthetic fixtures
├── evaluation/               # report.html, results, charts, model experiments
└── data/                     # Ground truth, source drawings, synthetic fixtures
```

## Deployment Notes

The web application is an evaluation and demonstration front end. It has no
authentication, so it binds `127.0.0.1` by default and Docker Compose publishes
the port on loopback only. To expose it, put an authenticated reverse proxy in
front and set `BIND_ADDRESS=0.0.0.0`.

Resource limits apply to every entry point and are configurable:

| Variable                  | Default | Effect                                                |
| ------------------------- | ------- | ----------------------------------------------------- |
| `MAX_UPLOAD_BYTES`        | 64 MiB  | Rejects larger uploads with 413                       |
| `MAX_PDF_PAGES`           | 50      | Rejects larger documents before rendering             |
| `MAX_CONCURRENT_ANALYSES` | 4       | Both analysis routes share this gate; excess gets 503 |
| `LLM_TIMEOUT_SECONDS`     | 120     | Bounds a hung provider call                           |

## Third-Party Licences

No runtime dependency is under GPL or AGPL. Most are permissive (MIT, BSD,
Apache-2.0); two are MPL-2.0 (file-level copyleft, no effect while unmodified)
and the OpenCASCADE geometry core is LGPL-2.1 with the OpenCASCADE exception,
used as an unmodified dynamically linked library. None of these require
disclosing the source of a calling application; all of them require
attribution on redistribution.

See [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md) for the full dependency
list and the per-component notes.

## License

Proprietary — see [LICENSE](LICENSE).
