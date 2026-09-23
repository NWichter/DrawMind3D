"""Run the evaluation once per vision model and compare the results.

Each model is evaluated in a separate process so its results land in a clean
environment, then the per-case scores are collected into one table.

Usage:
    uv run python scripts/compare_models.py --list
    uv run python scripts/compare_models.py                    # quick set, all models
    uv run python scripts/compare_models.py --set full         # all 21 cases
    uv run python scripts/compare_models.py --models google/gemini-2.5-flash qwen/qwen3-vl-235b-a22b-instruct
    uv run python scripts/compare_models.py --cases FTC-07 CTC-01
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from evaluate import CASE_SETS  # noqa: E402

# Experiments write into their own directory. The published benchmark under
# evaluation/results is the evidence behind the documented numbers and is
# never used as scratch space.
WORK_DIR = PROJECT_ROOT / "evaluation" / "model_comparison"
RESULTS_FILE = WORK_DIR / "results" / "evaluation_results_llm.json"
OUTPUT_FILE = WORK_DIR / "model_comparison.json"

# Picked from OpenRouter's vision-capable catalogue crossed with its usage
# rankings (checked 2026-09-22). Half are open-weight, so the table also says
# whether a self-hosted backend is viable, and the price spread is ~65x.
#
#   model                          $/Mtok in / out   weights
DEFAULT_MODELS = [
    "google/gemini-2.5-flash",  # 0.30 /  2.50   closed  (incumbent, README baseline)
    "google/gemini-3.8-flash",  # 0.75 /  3.75   closed
    "openai/gpt-5.6-luna",  # 0.20 /  1.20   closed
    "x-ai/grok-4.7",  # 1.60 /  4.80   closed
    "anthropic/claude-opus-5",  # 5.00 / 25.00   closed
    "openai/gpt-6-astra",  # 10.00 / 50.00   closed
    "z-ai/glm-5.3-flash",  # 0.15 /  0.50   open
    "deepseek/deepseek-v4.1-flash",  # 0.30 /  1.20   open
    "xiaomi/mimo-v2.6-pro",  # 0.43 /  0.87   closed (API-only)
    "qwen/qwen3.8-max-0902",  # 2.00 /  6.00   closed (API-only)
]

# Weights actually published on HuggingFace and small enough to serve on one
# or two GPUs. Decided by the catalogue's hugging_face_id field, not by the
# vendor's reputation: Qwen3.8-Max and MiMo-v2.6-Pro carry no repo and are
# API-only despite both vendors publishing other models. Verify each licence
# before shipping.
#
#   model                             HuggingFace repo                    params
SELF_HOSTABLE_MODELS = [
    "google/gemma-3-12b-it",  # google/gemma-3-12b-it                    12B
    "google/gemma-3-27b-it",  # google/gemma-3-27b-it                    27B
    "mistralai/ministral-8b-2512",  # mistralai/Ministral-3-8B-Instruct    8B
    "mistralai/ministral-14b-2512",  # mistralai/Ministral-3-14B-Instruct 14B
    "qwen/qwen3.8-27b",  # Qwen/Qwen3.8-27B                         27B
    "qwen/qwen3.6-35b-a3b",  # Qwen/Qwen3.6-35B-A3B       35B MoE, 3B active
    "inclusionai/ling-3.0-flash-vl",  # inclusionAI/Ling-3.0-flash-VL
    "xiaomi/mimo-v2.5",  # XiaomiMiMo/MiMo-V2.5
]

# Weights published but datacenter-scale: an upper bound for what open weights
# can do, not a deployment candidate.
LARGE_OPEN_MODELS = [
    "z-ai/glm-5.3-flash",
    "deepseek/deepseek-v4.1-flash",
    "moonshotai/kimi-k3",
    "qwen/qwen3.5-397b-a17b",
]

MODEL_GROUPS = {
    "default": DEFAULT_MODELS,
    "self-hostable": SELF_HOSTABLE_MODELS,
    "large-open": LARGE_OPEN_MODELS,
}

OPEN_WEIGHT_MODELS = set(SELF_HOSTABLE_MODELS) | set(LARGE_OPEN_MODELS)


def _run_one(model: str, extra_env: dict) -> list[dict] | None:
    env = {
        **os.environ,
        "VISION_MODEL": model,
        "VISION_MODEL_FALLBACK": model,
        "EVAL_OUTPUT_DIR": str(WORK_DIR),
        **extra_env,
    }

    if RESULTS_FILE.exists():
        RESULTS_FILE.unlink()

    started = time.time()
    proc = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "evaluate.py"), "--llm"],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    elapsed = time.time() - started

    if not RESULTS_FILE.exists():
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        print(f"  no results written ({elapsed:.0f}s): {' | '.join(tail)}")
        return None

    results = json.loads(RESULTS_FILE.read_text(encoding="utf-8"))
    for row in results:
        row["_model"] = model
        row["_elapsed_s"] = round(elapsed, 1)
    return results


def _metric(row: dict, section: str, key: str) -> float:
    """Read one score, refusing to turn a missing key into a zero."""
    values = row.get(section)
    if not isinstance(values, dict) or key not in values:
        raise KeyError(f"result row has no {section}.{key}: {sorted(row)}")
    return float(values[key] or 0.0)


def _f1(row: dict) -> float:
    return _metric(row, "extraction", "f1")


def _linking(row: dict) -> float:
    return _metric(row, "linking", "linking_accuracy")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", nargs="*", help="models to compare (default: the built-in list)")
    ap.add_argument("--cases", nargs="*", help="limit to these test cases")
    ap.add_argument(
        "--set",
        dest="case_set",
        default="quick",
        choices=sorted(CASE_SETS),
        help="named case subset (default: quick)",
    )
    ap.add_argument(
        "--group",
        default="default",
        choices=sorted(MODEL_GROUPS),
        help="which model group to run (default: default)",
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help="keep models already present in the output file and measure only the rest",
    )
    ap.add_argument("--list", action="store_true", help="print models and case sets, then exit")
    args = ap.parse_args()

    if args.list:
        for group, entries in MODEL_GROUPS.items():
            print(f"{group}:")
            for model in entries:
                print(f"  {model}")
        print("\ncase sets:")
        for name, cases in sorted(CASE_SETS.items()):
            count = len(cases.split(",")) if cases else "all"
            print(f"  {name:8} {count} cases")
        return 0

    models = args.models or MODEL_GROUPS[args.group]
    if args.cases:
        extra_env = {"EVAL_CASES": ",".join(args.cases)}
    else:
        extra_env = {"EVAL_SET": args.case_set}
    print(f"case set: {args.cases or args.case_set}\n")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    table = {}
    if args.resume and OUTPUT_FILE.exists():
        table = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        already = [m for m in models if m in table]
        if already:
            print(f"resuming, {len(already)} model(s) already measured\n")

    for index, model in enumerate(models, start=1):
        if model in table:
            print(f"[{index}/{len(models)}] {model} — already measured, skipping")
            continue
        print(f"[{index}/{len(models)}] {model}")
        results = _run_one(model, extra_env)
        if results:
            table[model] = results
            f1s = [_f1(r) for r in results]
            print(f"  {len(results)} cases, mean F1 {statistics.mean(f1s) * 100:.1f}%")
            # Written after every model: an interrupted comparison must not
            # throw away the runs that were already paid for.
            OUTPUT_FILE.write_text(json.dumps(table, indent=2, default=str), encoding="utf-8")

    if not table:
        print("\nNo model produced results. Check OPENROUTER_API_KEY.")
        return 1

    print(f"\n{'model':32}{'F1':>8}{'Link%':>8}{'cases':>7}{'secs':>7}  weights")
    ranked = sorted(table.items(), key=lambda kv: -statistics.mean([_f1(r) for r in kv[1]]))
    for model, results in ranked:
        f1 = statistics.mean([_f1(r) for r in results]) * 100
        link = statistics.mean([_linking(r) for r in results]) * 100
        if model in SELF_HOSTABLE_MODELS:
            weights = "open, self-hostable"
        elif model in LARGE_OPEN_MODELS:
            weights = "open, datacenter"
        else:
            weights = "closed"
        print(
            f"{model:32}{f1:7.1f}%{link:7.1f}%{len(results):7}"
            f"{results[0]['_elapsed_s']:7.0f}  {weights}"
        )

    print(f"\nWrote {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
