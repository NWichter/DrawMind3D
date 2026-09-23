# Evaluation

Everything measured about DrawMind3D lives here. Start with
**[report.html](report.html)** — open it in a browser; it is self-contained
and needs no server.

```
evaluation/
├── report.html         One page: headline numbers, failure causes, per-drawing detail
├── results/            Raw per-case JSON, one file per mode
├── charts/             Bar charts per mode and per case family
├── presentation/       Charts prepared for slides
└── model_comparison/   Experiments that rank vision models (never the published numbers)
```

## Reproducing the numbers

```bash
uv run python scripts/evaluate.py          # offline: regex + OCR, no model calls
uv run python scripts/evaluate.py --llm    # with the configured vision model
```

Both write `results/`, `charts/` and regenerate `report.html`.

A full run covers 21 drawings. For iteration, pick a named subset:

```bash
EVAL_SET=quick uv run python scripts/evaluate.py --llm    # 6 cases, both unit systems
EVAL_SET=smoke uv run python scripts/evaluate.py          # 2 cases
EVAL_CASES=CTC-01,FTC-07 uv run python scripts/evaluate.py
```

Available sets: `quick`, `metric`, `inch`, `vision`, `native`, `smoke`, `full`.
Run `uv run python scripts/compare_models.py --list` to print them with their
case counts.

Send results elsewhere with `--out` or `EVAL_OUTPUT_DIR`, which is how model
experiments keep out of the published results:

```bash
uv run python scripts/compare_models.py --set quick      # writes model_comparison/
```

## Rebuilding only the report

The report reads the stored JSON, so it can be regenerated without measuring
again:

```bash
uv run python scripts/eval_report.py
uv run python scripts/eval_report.py --results model_comparison/results
```

## What the two modes mean

| Mode              | Command             | What leaves the machine               |
| ----------------- | ------------------- | ------------------------------------- |
| Offline           | `evaluate.py`       | Nothing                               |
| With vision model | `evaluate.py --llm` | A rendered image of each drawing page |

The offline mode is the same pipeline with every model call disabled, which is
verified by a test rather than asserted (`tests/test_pipeline.py`).

## Reading the results

Each entry in `results/evaluation_results_*.json` carries:

- `extraction` — precision, recall, F1 against the required ground-truth callouts,
  plus `missed_breakdown`, which splits misses into callouts that were never read
  off the page and callouts that were read but not understood
- `linking` — share of extracted callouts tied to the correct hole in the STEP model
- `stages` — what each pipeline step did, so a degraded run cannot look like a clean one
- `unit_source` — `detected`, or `ground_truth` where the drawing carries no unit
  evidence and the reference value was supplied
- `runtime_seconds`, `vision_model`

Ground truth lives in `../data/ground_truth/`; the drawings and models are in
`../examples/`.
