"""Turn evaluation results into one self-contained HTML report.

Reads the JSON written by evaluate.py and answers, in this order: how well
does it work, where does it fail, what did it cost, and under which
conditions were the numbers produced.

Usage:
    uv run python scripts/eval_report.py
    uv run python scripts/eval_report.py --results evaluation/model_comparison
"""

from __future__ import annotations

import argparse
import html
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from drawmind import __version__  # noqa: E402

EVAL_DIR = PROJECT_ROOT / "evaluation"

MODE_LABEL = {"llm": "With vision model", "nollm": "Offline (regex + OCR only)"}


def _load(results_dir: Path) -> dict[str, list[dict]]:
    modes = {}
    for variant in ("llm", "nollm"):
        path = results_dir / f"evaluation_results_{variant}.json"
        if path.exists():
            modes[variant] = json.loads(path.read_text(encoding="utf-8"))
    return modes


def _scorable(results: list[dict]) -> list[dict]:
    """Cases with at least one required ground-truth callout."""
    return [r for r in results if r["extraction"]["total_ground_truth"] > 0]


def _mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _aggregate(results: list[dict]) -> dict:
    scorable = _scorable(results)
    misses = [r["extraction"].get("missed_breakdown", {}) for r in results]
    return {
        "cases": len(results),
        "scorable": len(scorable),
        "precision": _mean([r["extraction"]["precision"] for r in scorable]),
        "recall": _mean([r["extraction"]["recall"] for r in scorable]),
        "f1": _mean([r["extraction"]["f1"] for r in scorable]),
        "linking": _mean([r["linking"]["linking_accuracy"] for r in scorable]),
        "confidence": _mean([r["avg_confidence"] for r in scorable]),
        "runtime": sum(r.get("runtime_seconds", 0) or 0 for r in results),
        "ground_truth": sum(r["extraction"]["total_ground_truth"] for r in results),
        "true_positives": sum(r["extraction"]["true_positives"] for r in results),
        "false_negatives": sum(r["extraction"]["false_negatives"] for r in results),
        "has_breakdown": any(m for m in misses),
        "not_read": sum(m.get("not_read_count", 0) for m in misses),
        "not_parsed": sum(m.get("read_but_not_parsed_count", 0) for m in misses),
        "timed": any(r.get("runtime_seconds") for r in results),
        "unit_overrides": sum(1 for r in results if r.get("unit_source") == "ground_truth"),
        "degraded": [
            (r["test_case"], s["name"], s.get("detail", ""))
            for r in results
            for s in r.get("stages", [])
            if s.get("status") in ("failed", "partial")
        ],
        "model": next((r.get("vision_model") for r in results if r.get("vision_model")), None),
    }


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _bar(value: float) -> str:
    width = max(0.0, min(1.0, value)) * 100
    return f'<span class="bar"><span class="bar-fill" style="width:{width:.1f}%"></span></span>'


def _verdict(modes: dict[str, dict]) -> str:
    best_key = "llm" if "llm" in modes else next(iter(modes))
    best = modes[best_key]
    found = best["true_positives"]
    total = best["ground_truth"]
    share = found / total if total else 0.0

    offline = modes.get("nollm")
    offline_line = ""
    if offline:
        offline_line = (
            f"<p>Fully offline, with no drawing leaving the machine, it reaches "
            f"<strong>{_pct(offline['f1'])} F1</strong> and "
            f"<strong>{_pct(offline['linking'])}</strong> linking accuracy.</p>"
        )

    degraded = [d for mode in modes.values() for d in mode["degraded"]]
    warning = ""
    if degraded:
        cases = sorted({case for case, _, _ in degraded})
        reasons = sorted({detail.split(":")[0] for _, _, detail in degraded if detail})
        warning = f"""
        <p class="warn"><strong>This run was degraded.</strong> A pipeline step failed on
        {len(cases)} of {best["cases"]} drawings ({html.escape(", ".join(cases))}), so the
        numbers below understate what the pipeline does when every step completes.
        Reported cause: {html.escape("; ".join(reasons) or "see the per-drawing table")}.
        Re-run before quoting these figures.</p>
        """

    return f"""
    <section class="verdict">
      <h2>What the measurement says</h2>
      {warning}
      <p>Across <strong>{best["cases"]} reference drawings</strong>, DrawMind3D found
      <strong>{found} of {total}</strong> required callouts ({_pct(share)}) and linked
      <strong>{_pct(best["linking"])}</strong> of them to the correct hole in the 3D model.</p>
      {offline_line}
      <p class="muted">Every number on this page comes from
      <code>evaluation/results/</code> and can be reproduced with
      <code>uv run python scripts/evaluate.py --llm</code>.</p>
    </section>
    """


def _mode_table(modes: dict[str, dict]) -> str:
    rows = []
    for key, agg in modes.items():
        per_case = (
            f"{agg['runtime'] / max(agg['cases'], 1):.1f} s" if agg["timed"] else "not recorded"
        )
        rows.append(
            f"""<tr>
              <td>{html.escape(MODE_LABEL.get(key, key))}</td>
              <td class="num">{_pct(agg["precision"])}</td>
              <td class="num">{_pct(agg["recall"])}</td>
              <td class="num">{_bar(agg["f1"])} {_pct(agg["f1"])}</td>
              <td class="num">{_bar(agg["linking"])} {_pct(agg["linking"])}</td>
              <td class="num">{per_case}</td>
            </tr>"""
        )
    return f"""
    <section>
      <h2>Operating modes</h2>
      <p>The offline mode exists for drawings that may not be sent to a third party.
      It is the same pipeline with every model call disabled.</p>
      <table>
        <thead><tr><th>Mode</th><th>Precision</th><th>Recall</th><th>F1</th>
        <th>Linking</th><th>Per drawing</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </section>
    """


def _failure_section(modes: dict[str, dict]) -> str:
    rows, notes = [], []
    for key, agg in modes.items():
        label = html.escape(MODE_LABEL.get(key, key))
        if not agg["false_negatives"]:
            notes.append(f"<p>{label}: no required callout was missed.</p>")
            continue
        if not agg["has_breakdown"]:
            notes.append(
                f"<p>{label}: <strong>{agg['false_negatives']}</strong> callouts missed. "
                "That result file predates the failure breakdown; re-run "
                "<code>scripts/evaluate.py</code> to split it by cause.</p>"
            )
            continue
        missed = agg["not_read"] + agg["not_parsed"]
        rows.append(
            f"""<tr>
              <td>{label}</td>
              <td class="num">{missed}</td>
              <td class="num">{agg["not_read"]} ({_pct(agg["not_read"] / missed)})</td>
              <td class="num">{agg["not_parsed"]} ({_pct(agg["not_parsed"] / missed)})</td>
            </tr>"""
        )

    table = ""
    if rows:
        table = f"""
        <table>
          <thead><tr><th>Mode</th><th>Callouts missed</th>
          <th>Never read from the page</th><th>Read but not understood</th></tr></thead>
          <tbody>{"".join(rows)}</tbody>
        </table>
        <p>A callout in the first column never reached the pipeline as text: it is drawn
        as path geometry or is unreadable by OCR, and better parsing cannot recover it.
        One in the second column was read and then not understood, which is a grammar gap
        and cheap to close. The split is found by searching the extracted text for the
        missing callout, so it is indicative rather than exact.</p>
        """

    return f"""<section><h2>Where it fails</h2>{table}{"".join(notes)}</section>"""


def _case_table(results: list[dict], mode_key: str) -> str:
    rows = []
    for r in sorted(results, key=lambda x: x["extraction"]["f1"]):
        e, link = r["extraction"], r["linking"]
        breakdown = e.get("missed_breakdown", {})
        missed = e.get("missed_annotations", [])
        missed_cell = (
            "<span class='ok'>none</span>"
            if not missed
            else html.escape(", ".join(missed[:6])) + ("…" if len(missed) > 6 else "")
        )
        cause_cell = (
            f' <span class="muted">({breakdown["not_read_count"]} unread, '
            f"{breakdown['read_but_not_parsed_count']} unparsed)</span>"
            if breakdown
            else ""
        )
        runtime = r.get("runtime_seconds")
        runtime_cell = f"{runtime:.1f} s" if runtime else "&ndash;"
        flags = []
        if r.get("unit_source") == "ground_truth":
            flags.append(
                "<span class='flag' title='Unit system taken from ground truth'>units</span>"
            )
        for stage in r.get("stages", []):
            if stage.get("status") in ("failed", "partial"):
                flags.append(
                    f"<span class='flag bad' title='{html.escape(str(stage.get('detail', '')))}'>"
                    f"{html.escape(stage.get('name', '?'))}</span>"
                )
        rows.append(
            f"""<tr>
              <td><strong>{html.escape(r["test_case"])}</strong> {" ".join(flags)}</td>
              <td class="num">{e["total_ground_truth"]}</td>
              <td class="num">{e["true_positives"]}</td>
              <td class="num">{e["false_positives"]}</td>
              <td class="num">{e["false_negatives"]}</td>
              <td class="num">{_pct(e["f1"])}</td>
              <td class="num">{_pct(link["linking_accuracy"])}</td>
              <td class="num">{runtime_cell}</td>
              <td class="missed">{missed_cell}{cause_cell}</td>
            </tr>"""
        )
    return f"""
    <section>
      <h2>Per drawing &mdash; {html.escape(MODE_LABEL.get(mode_key, mode_key))}</h2>
      <p>Sorted worst first, so the hard cases are visible without scrolling.</p>
      <div class="scroll">
      <table>
        <thead><tr><th>Case</th><th>Required</th><th>Found</th><th>False&nbsp;pos.</th>
        <th>Missed</th><th>F1</th><th>Linking</th><th>Time</th><th>Missed callouts</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
      </div>
    </section>
    """


def _provenance(modes: dict[str, dict], results_dir: Path) -> str:
    model = next((m.get("model") for m in modes.values() if m.get("model")), "not used")
    overrides = sum(m["unit_overrides"] for m in modes.values())
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""
    <section>
      <h2>How these numbers were produced</h2>
      <dl>
        <dt>Pipeline version</dt><dd>{html.escape(__version__)}</dd>
        <dt>Vision model</dt><dd><code>{html.escape(str(model))}</code></dd>
        <dt>Results read from</dt><dd><code>{html.escape(str(results_dir))}</code></dd>
        <dt>Report generated</dt><dd>{generated}</dd>
        <dt>Unit system taken from ground truth</dt>
        <dd>{overrides} case(s) &mdash; drawings whose text layer carries no unit evidence</dd>
      </dl>
      <h3>What this does not measure</h3>
      <ul>
        <li>Only cylindrical hole features are evaluated. Profiles, radii, surface finish
        and geometric tolerancing are extracted but not scored.</li>
        <li>The corpus is public reference data (NIST PMI, plus synthetic parts) and
        production drawings from a given shop may differ in notation and quality.</li>
        <li>Linking accuracy is measured against holes the STEP model actually contains;
        a drawing callout with no counterpart in the model cannot be scored.</li>
        <li>Cases where the unit system came from ground truth are flagged in the table;
        their extraction score would be lower without that assist.</li>
      </ul>
    </section>
    """


STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font: 15px/1.6 -apple-system, "Segoe UI", Roboto, sans-serif;
       margin: 0 auto; max-width: 1080px; padding: 32px 20px 64px;
       color: #1a1d23; background: #fff; }
h1 { font-size: 1.75rem; margin: 0 0 4px; }
h2 { font-size: 1.15rem; margin: 40px 0 12px; padding-bottom: 6px;
     border-bottom: 1px solid #e3e6ea; }
h3 { font-size: 1rem; margin: 24px 0 8px; }
.sub { color: #6b7280; margin: 0 0 8px; }
.verdict { background: #f4f7fb; border: 1px solid #d7e0ea; border-radius: 8px;
           padding: 4px 20px 16px; margin-top: 28px; }
.verdict h2 { border: none; margin-top: 16px; }
table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid #eceff3; }
th { font-weight: 600; color: #4b5563; font-size: 0.8rem; text-transform: uppercase;
     letter-spacing: 0.03em; }
td.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
td.missed { font-size: 0.82rem; color: #374151; }
tbody tr:hover { background: #f8fafc; }
.bar { display: inline-block; width: 52px; height: 7px; border-radius: 4px;
       background: #e3e8ee; vertical-align: middle; margin-right: 6px; overflow: hidden; }
.bar-fill { display: block; height: 100%; background: #2f6fed; }
.muted { color: #6b7280; font-size: 0.85rem; }
.warn { background: #fff4e5; border-left: 3px solid #d97706; padding: 10px 14px;
        border-radius: 4px; }
.ok { color: #15803d; }
.flag { display: inline-block; font-size: 0.68rem; padding: 1px 6px; border-radius: 9px;
        background: #eef2f7; color: #4b5563; vertical-align: middle; cursor: help; }
.flag.bad { background: #fdeaea; color: #b91c1c; }
.scroll { overflow-x: auto; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 20px; margin: 0; }
dt { color: #6b7280; }
dd { margin: 0; }
code { background: #f1f3f6; padding: 1px 5px; border-radius: 4px; font-size: 0.88em; }
@media (prefers-color-scheme: dark) {
  body { background: #14171c; color: #e6e8eb; }
  h2 { border-color: #2a2f38; }
  .verdict { background: #1a1f27; border-color: #2c333d; }
  th, td { border-color: #242932; }
  th { color: #9aa4b2; }
  tbody tr:hover { background: #1b2028; }
  .bar { background: #2a303a; }
  .muted, dt { color: #9aa4b2; }
  .flag { background: #232a34; color: #9aa4b2; }
  .flag.bad { background: #3a1f1f; color: #f87171; }
  .warn { background: #2e2314; border-left-color: #f59e0b; }
  code { background: #232a34; }
  .ok { color: #4ade80; }
}
@media print { body { max-width: none; } .verdict { background: none; } }
"""


def build_report(results_dir: Path, output_path: Path) -> Path:
    raw = _load(results_dir)
    if not raw:
        raise SystemExit(f"No evaluation results in {results_dir}. Run scripts/evaluate.py first.")

    modes = {key: _aggregate(results) for key, results in raw.items()}
    primary = "llm" if "llm" in raw else next(iter(raw))

    body = "".join(
        [
            "<h1>DrawMind3D &mdash; Evaluation Report</h1>",
            '<p class="sub">Linking annotations on 2D technical drawings to hole '
            "features in the matching 3D model.</p>",
            _verdict(modes),
            _mode_table(modes),
            _failure_section(modes),
            _case_table(raw[primary], primary),
            _provenance(modes, results_dir),
        ]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>DrawMind3D Evaluation Report</title>\n"
        f"<style>{STYLE}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n",
        encoding="utf-8",
    )
    return output_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--results",
        type=Path,
        default=EVAL_DIR / "results",
        help="Directory holding evaluation_results_*.json",
    )
    ap.add_argument("--out", type=Path, default=EVAL_DIR / "report.html")
    args = ap.parse_args()

    path = build_report(args.results, args.out)
    print(f"Report written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
