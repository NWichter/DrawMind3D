# Evaluating DrawMind3D on Your Own Drawings

This guide is for a technical evaluation on your own infrastructure. It takes
about 15 minutes to get the first result on one of your own parts.

## 1. Install

Docker (recommended):

```bash
git clone https://github.com/NWichter/DrawMind3D.git
cd DrawMind3D
cp .env.example .env
docker compose up --build        # web UI at http://localhost:8000
```

Or locally with [uv](https://docs.astral.sh/uv/) and Python 3.12:

```bash
uv sync
uv run python web/app.py         # web UI at http://localhost:8000
```

To check the installation, open the web UI and run one of the bundled
examples (for example `SYN-02-ThreadedPlate` or `CTC-01`).

## 2. Choose where drawings are processed

| Mode              | Configuration (`.env`)                                           | Drawings leave your machine |
| ----------------- | ---------------------------------------------------------------- | --------------------------- |
| Offline           | nothing, or `--no-llm` on the CLI                                | No                          |
| Self-hosted model | `OPENROUTER_BASE_URL`, `OPENROUTER_API_KEY`, `VISION_MODEL`      | No                          |
| Hosted provider   | `OPENROUTER_API_KEY` from [openrouter.ai](https://openrouter.ai) | Yes, to the provider        |

**Offline** uses the PDF text layer, OCR and the 3D geometry only. It is the
safe starting point for confidential drawings, at lower accuracy on drawings
without a usable text layer.

**Self-hosted model**: any server with an OpenAI-compatible API works, for
example vLLM or Ollama. Point the pipeline at it:

```bash
OPENROUTER_BASE_URL=http://localhost:8001/v1
OPENROUTER_API_KEY=local            # any non-empty value
VISION_MODEL=<model name on your server>
VISION_MODEL_FALLBACK=<same or a larger model>
DISAMBIGUATE_MODEL=<same model>
```

The model needs image input. The section _Vision Model Comparison_ in the
README shows how different vision models perform on the test set.

**Hosted provider**: the default configuration uses Gemini 2.5 Flash through
OpenRouter and gives the best accuracy. The provider's terms apply to drawings
sent to it.

## 3. Run your drawings

Web UI: upload a PDF drawing and the matching STEP file. The PDF and the 3D
model are shown side by side; clicking a match highlights the callout in the
drawing and the hole in the model. The browser loads the 3D and PDF viewers
(three.js, pdf.js) from public CDNs; the drawings themselves stay on the
server. The command line needs no browser at all.

Command line, one part:

```bash
uv run python run.py --pdf part.pdf --step part.step -o part.json --no-llm
```

Command line, a folder of parts (`<name>.pdf` next to `<name>.step`):

```bash
for pdf in parts/*.pdf; do
  uv run python run.py --pdf "$pdf" --step "${pdf%.pdf}.step" -o "${pdf%.pdf}.json" --no-llm
done
```

Remove `--no-llm` to use the model configured in step 2. `--units metric` or
`--units inch` overrides unit detection if a drawing states no units.

## 4. Read the result

Each JSON file lists every hole callout found in the drawing with the 3D hole
it was linked to:

- `confidence_level`: `high` (0.8 and above) or `review` (0.6 to 0.8). In a
  review workflow, `review` matches are the ones to route to an engineer.
- `scoring_breakdown`: why the match was chosen (diameter, depth, type, count).
- `unmatched_annotations` and `unmatched_features`: callouts without a hole
  and holes without a callout.
- `summary.warnings`: notes on the run, for example unmatched items or a
  model that could not be reached.

The full format is described in the README under _Output Format_.

## 5. Suggested evaluation

A small, representative set gives a clearer answer than many similar parts:

1. Pick 10 to 20 PDF/STEP pairs that reflect your daily work: CAD exports and
   scans, simple and complex parts, and different drawing standards.
2. For each part, count the hole callouts that were linked correctly, linked
   wrongly and missed.
3. Note how much review time the result saves compared with doing the
   association by hand.

Worth checking early, because they are not covered by the current test set:

- Drawings in JIS notation (for example `4-φ6.6キリ` or `M5深10`). Support can
  be added on request.
- Scanned drawings of low quality.

Version 1.0.0 covers holes: simple, threaded, counterbored, countersunk and
stepped. Other features such as pockets or slots are not linked yet.

## 6. Feedback

Parts where the result is wrong are the most useful input. Where you can share
them, a PDF/STEP pair with a short note on what was expected makes it possible
to tell whether the gap is a quick adaptation or a larger change. Where you
cannot share them, the JSON output and a description of the callout are often
enough.

Contact: niklaswichter@gmail.com
