"""Evaluation script: Precision/Recall/F1 for DrawMind3D annotation extraction and linking.

Usage:
    uv run python scripts/evaluate.py [--llm] [--save-charts]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# Add project root and this script's directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from drawmind.pdf.extractor import (
    _has_engineering_content,
    detect_unit_system,
    extract_all_text,
)
from drawmind.config import VISION_MODEL
from drawmind.pipeline import Settings, StageStatus, analyze


PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EVAL_DIR = PROJECT_ROOT / "evaluation"
NIST_DIR = DATA_DIR / "nist" / "NIST-PMI-STEP-Files"
GT_DIR = DATA_DIR / "ground_truth"
SYNTH_DIR = DATA_DIR / "synthetic"


# Named subsets for cheap iteration. "quick" holds one case per family and
# covers both unit systems and both extraction paths (native text vs
# vision-only), so a result on it still says something about the whole corpus.
CASE_SETS = {
    "quick": "CTC-01,FTC-07,FTC-10,D2MI-904,SYN-02-ThreadedPlate,SYN-03-InchPart",
    "metric": "CTC-01,CTC-02,FTC-10,SYN-01-SimpleBlock,SYN-02-ThreadedPlate",
    "inch": "FTC-06,FTC-07,FTC-08,D2MI-904,SYN-03-InchPart",
    "vision": "CTC-01,CTC-03,FTC-06,FTC-08,D2MI-905,D2MI-907",
    "native": "FTC-07,FTC-10,SYN-01-SimpleBlock,SYN-05-ManyHoles",
    "smoke": "SYN-01-SimpleBlock,FTC-07",
    "full": "",
}


def _build_test_cases() -> list[tuple]:
    """Build test case list from NIST + synthetic data."""
    cases = [
        # CTC (Combinational Tolerancing Cases)
        (
            "CTC-01",
            NIST_DIR / "PDF" / "nist_ctc_01_asme1_rd.pdf",
            NIST_DIR / "AP203 geometry only" / "nist_ctc_01_asme1_rd.stp",
            GT_DIR / "ctc01_ground_truth.json",
        ),
        (
            "CTC-02",
            NIST_DIR / "PDF" / "nist_ctc_02_asme1_rc.pdf",
            NIST_DIR / "AP203 geometry only" / "nist_ctc_02_asme1_rc.stp",
            GT_DIR / "ctc02_ground_truth.json",
        ),
        (
            "CTC-03",
            NIST_DIR / "PDF" / "nist_ctc_03_asme1_rc.pdf",
            NIST_DIR / "AP203 geometry only" / "nist_ctc_03_asme1_rc.stp",
            GT_DIR / "ctc03_ground_truth.json",
        ),
        (
            "CTC-04",
            NIST_DIR / "PDF" / "nist_ctc_04_asme1_rd.pdf",
            NIST_DIR / "AP203 geometry only" / "nist_ctc_04_asme1_rd.stp",
            GT_DIR / "ctc04_ground_truth.json",
        ),
        (
            "CTC-05",
            NIST_DIR / "PDF" / "nist_ctc_05_asme1_rd.pdf",
            NIST_DIR / "AP203 geometry only" / "nist_ctc_05_asme1_rd.stp",
            GT_DIR / "ctc05_ground_truth.json",
        ),
        # FTC (Fully-Toleranced Cases)
        (
            "FTC-06",
            NIST_DIR / "PDF" / "nist_ftc_06_asme1_rd.pdf",
            NIST_DIR / "AP203 geometry only" / "nist_ftc_06_asme1_rd.stp",
            GT_DIR / "ftc06_ground_truth.json",
        ),
        (
            "FTC-07",
            NIST_DIR / "PDF" / "nist_ftc_07_asme1_rd.pdf",
            NIST_DIR / "AP203 geometry only" / "nist_ftc_07_asme1_rd.stp",
            GT_DIR / "ftc07_ground_truth.json",
        ),
        (
            "FTC-08",
            NIST_DIR / "PDF" / "nist_ftc_08_asme1_rc.pdf",
            NIST_DIR / "AP203 geometry only" / "nist_ftc_08_asme1_rc.stp",
            GT_DIR / "ftc08_ground_truth.json",
        ),
        (
            "FTC-09",
            NIST_DIR / "PDF" / "nist_ftc_09_asme1_rd.pdf",
            NIST_DIR / "AP203 geometry only" / "nist_ftc_09_asme1_rd.stp",
            GT_DIR / "ftc09_ground_truth.json",
        ),
        (
            "FTC-10",
            NIST_DIR / "PDF" / "nist_ftc_10_asme1_rb.pdf",
            NIST_DIR / "AP203 geometry only" / "nist_ftc_10_asme1_rb.stp",
            GT_DIR / "ftc10_ground_truth.json",
        ),
        (
            "FTC-11",
            NIST_DIR / "PDF" / "nist_ftc_11_asme1_rb.pdf",
            NIST_DIR / "AP203 geometry only" / "nist_ftc_11_asme1_rb.stp",
            GT_DIR / "ftc11_ground_truth.json",
        ),
    ]

    # Add D2MI test cases from examples/
    EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
    for part in ["904", "905", "906", "907", "908"]:
        tc_dir = EXAMPLES_DIR / f"D2MI-{part}"
        gt_file = GT_DIR / f"d2mi{part}_ground_truth.json"
        if tc_dir.exists() and gt_file.exists():
            cases.append(
                (
                    f"D2MI-{part}",
                    tc_dir / "drawing.pdf",
                    tc_dir / "model.stp",
                    gt_file,
                )
            )

    # Add synthetic test cases
    if SYNTH_DIR.exists():
        for gt_file in sorted(SYNTH_DIR.glob("*_ground_truth.json")):
            name = gt_file.stem.replace("_ground_truth", "")
            pdf_path = SYNTH_DIR / f"{name}.pdf"
            step_path = SYNTH_DIR / f"{name}.stp"
            if pdf_path.exists() and step_path.exists():
                cases.append((name, pdf_path, step_path, gt_file))

    selected = os.getenv("EVAL_CASES", "").strip()
    if not selected:
        selected = CASE_SETS.get(os.getenv("EVAL_SET", "").strip().lower(), "")

    if selected:
        wanted = {name.strip() for name in selected.split(",") if name.strip()}
        cases = [c for c in cases if c[0] in wanted]

    return cases


TEST_CASES = _build_test_cases()


def load_ground_truth(gt_path: Path) -> dict:
    """Load ground truth labels."""
    with open(gt_path) as f:
        return json.load(f)


def evaluate_extraction(
    extracted_annotations: list,
    ground_truth: dict,
    diameter_tolerance_mm: float = 1.0,
) -> dict:
    """Evaluate annotation extraction against ground truth.

    Matches extracted annotations to ground truth by diameter (within tolerance).

    Returns:
        Dict with precision, recall, f1, and per-annotation details
    """
    all_gt_annotations = ground_truth["expected_annotations"]
    # Filter out optional annotations (convex features, reference dims, etc.)
    gt_annotations = [gt for gt in all_gt_annotations if not gt.get("optional", False)]
    optional_gt = [gt for gt in all_gt_annotations if gt.get("optional", False)]
    gt_matched = set()
    ext_matched = set()

    # Try to match each extracted annotation to a ground truth annotation
    match_details = []
    for i, ext in enumerate(extracted_annotations):
        # Get extracted diameter in mm
        ext_diameter = None
        ext_thread = None
        if hasattr(ext, "parsed"):
            parsed = ext.parsed
        else:
            parsed = ext.get("parsed", {})

        if isinstance(parsed, dict):
            ext_diameter = (
                parsed.get("value") or parsed.get("nominal_diameter") or parsed.get("diameter")
            )
            ext_thread = parsed.get("thread_spec") or parsed.get("thread")

        if ext_diameter is None:
            continue

        try:
            ext_diameter = float(ext_diameter)
        except (ValueError, TypeError):
            continue

        # Find best matching ground truth annotation
        best_gt_idx = None
        best_diff = float("inf")
        for j, gt in enumerate(gt_annotations):
            if j in gt_matched:
                continue

            # Thread-aware matching: if both have thread info, match by thread designation
            gt_thread = gt.get("thread")
            if ext_thread and gt_thread:
                # Normalize thread designations for comparison (M8x1.0 → M8, etc.)
                ext_thread_base = ext_thread.split("x")[0].split("X")[0].strip().upper()
                gt_thread_base = gt_thread.strip().upper()
                if ext_thread_base == gt_thread_base:
                    best_diff = 0.0
                    best_gt_idx = j
                    break  # Exact thread match — highest priority
                else:
                    continue  # Different thread types — skip

            gt_diameter = gt["diameter_mm"]
            diff = abs(ext_diameter - gt_diameter)
            if diff < best_diff and diff <= diameter_tolerance_mm:
                best_diff = diff
                best_gt_idx = j

        if best_gt_idx is not None:
            gt_matched.add(best_gt_idx)
            ext_matched.add(i)
            match_details.append(
                {
                    "extracted": getattr(ext, "raw_text", str(ext)),
                    "ground_truth": gt_annotations[best_gt_idx].get(
                        "text", gt_annotations[best_gt_idx].get("description", "")
                    ),
                    "ext_diameter_mm": ext_diameter,
                    "gt_diameter_mm": gt_annotations[best_gt_idx]["diameter_mm"],
                    "diff_mm": best_diff,
                    "correct": True,
                }
            )

        # Check if this annotation matches an optional GT (don't count as FP)
        if best_gt_idx is None and optional_gt:
            for opt in optional_gt:
                opt_d = opt["diameter_mm"]
                if abs(ext_diameter - opt_d) <= diameter_tolerance_mm:
                    ext_matched.add(i)  # Matched optional — not a false positive
                    break

    # Calculate metrics
    true_positives = len(gt_matched)
    false_positives = len(extracted_annotations) - len(ext_matched)
    false_negatives = len(gt_annotations) - len(gt_matched)

    # If all GT annotations are optional (no required annotations), treat as perfect
    # when no false positives are generated, or N/A when there are
    if not gt_annotations:
        precision = 1.0 if false_positives == 0 else 0.0
        recall = 1.0
        f1 = 1.0 if false_positives == 0 else 0.0
    else:
        precision = (
            true_positives / (true_positives + false_positives)
            if (true_positives + false_positives) > 0
            else 0.0
        )
        recall = (
            true_positives / (true_positives + false_negatives)
            if (true_positives + false_negatives) > 0
            else 0.0
        )
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # List missed ground truth annotations
    missed = [gt_annotations[j] for j in range(len(gt_annotations)) if j not in gt_matched]

    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "total_extracted": len(extracted_annotations),
        "total_ground_truth": len(gt_annotations),
        "match_details": match_details,
        "missed_annotations": [m.get("text", m.get("description", "unknown")) for m in missed],
        "missed_entries": missed,
    }


def diagnose_misses(missed: list[dict], raw_texts: list[dict]) -> dict:
    """Split missed callouts into "never read" and "read but not understood".

    This is the distinction that decides where work pays off: a callout that
    never appeared in the extracted text is a reading problem (vector artwork,
    OCR), while one that was read but produced no annotation is a parsing
    problem. Matching is textual and therefore approximate.
    """
    haystack = " ".join(str(t.get("text", "")) for t in raw_texts).upper()
    haystack = re.sub(r"\s+", "", haystack)

    not_read, not_parsed = [], []
    for entry in missed:
        label = entry.get("text") or entry.get("description") or "unknown"
        needles = []
        if entry.get("thread"):
            needles.append(str(entry["thread"]).upper().replace(" ", ""))
        diameter = entry.get("diameter_mm")
        if diameter is not None:
            needles.extend([f"{float(diameter):.2f}".rstrip("0").rstrip("."), f"{diameter}"])
        if entry.get("text"):
            needles.append(str(entry["text"]).upper().replace(" ", ""))

        if any(n and n in haystack for n in needles):
            not_parsed.append(label)
        else:
            not_read.append(label)

    return {
        "not_read": not_read,
        "read_but_not_parsed": not_parsed,
        "not_read_count": len(not_read),
        "read_but_not_parsed_count": len(not_parsed),
    }


def evaluate_linking(
    matches: list,
    ground_truth: dict,
    holes: list,
    diameter_tolerance_mm: float = 1.0,
) -> dict:
    """Evaluate annotation-to-feature linking accuracy.

    For each match, check if the linked 3D feature has the correct diameter.

    Returns:
        Dict with linking precision, recall, and per-match accuracy
    """
    all_gt_annotations = ground_truth["expected_annotations"]
    gt_annotations = [gt for gt in all_gt_annotations if not gt.get("optional", False)]
    correct_links = 0
    total_links = len(matches)
    link_details = []

    for match in matches:
        if hasattr(match, "parsed_interpretation"):
            parsed = match.parsed_interpretation
            feature_ref = match.feature_3d_ref
            confidence = match.confidence
        else:
            parsed = match.get("parsed_interpretation", {})
            feature_ref = match.get("feature_3d_ref", {})
            confidence = match.get("confidence", 0)

        # Get the annotation diameter and thread info
        ann_diameter = None
        ann_thread = None
        if isinstance(parsed, dict):
            ann_diameter = (
                parsed.get("value") or parsed.get("nominal_diameter") or parsed.get("diameter")
            )
            ann_thread = parsed.get("thread_spec") or parsed.get("thread_type")

        if ann_diameter is None:
            link_details.append({"correct": False, "reason": "no annotation diameter"})
            continue

        try:
            ann_diameter = float(ann_diameter)
        except (ValueError, TypeError):
            link_details.append({"correct": False, "reason": "invalid diameter"})
            continue

        # Get the 3D feature diameter (check both primary and secondary)
        if isinstance(feature_ref, dict):
            feature_diameter = feature_ref.get("primary_diameter_mm", 0)
            feature_secondary = feature_ref.get("secondary_diameter_mm")
        else:
            feature_diameter = 0
            feature_secondary = None

        # Check if the annotation diameter matches a ground truth annotation
        # Use thread-aware matching when both have thread info
        gt_match = None
        if ann_thread:
            ann_thread_base = ann_thread.split("x")[0].split("X")[0].strip().upper()
            for gt in gt_annotations:
                gt_thread = gt.get("thread", "")
                if gt_thread and gt_thread.strip().upper() == ann_thread_base:
                    gt_match = gt
                    break

        if gt_match is None:
            for gt in gt_annotations:
                if abs(ann_diameter - gt["diameter_mm"]) <= diameter_tolerance_mm:
                    gt_match = gt
                    break

        if gt_match is None:
            link_details.append(
                {
                    "correct": False,
                    "reason": f"no GT for diameter {ann_diameter:.2f}mm",
                    "confidence": confidence,
                }
            )
            continue

        # Check if the 3D feature diameter is compatible with the ground truth
        # For threads, use drill_diameter_mm (physical hole size) for 3D comparison
        # Check BOTH primary and secondary diameter — counterbore annotations
        # reference the outer (secondary) diameter
        gt_feature_diameter = gt_match.get("drill_diameter_mm", gt_match["diameter_mm"])
        is_correct = abs(feature_diameter - gt_feature_diameter) <= diameter_tolerance_mm
        if not is_correct and feature_secondary:
            is_correct = abs(feature_secondary - gt_feature_diameter) <= diameter_tolerance_mm
        # Also check against the GT annotation diameter (not just drill diameter)
        if not is_correct:
            gt_ann_diameter = gt_match["diameter_mm"]
            is_correct = abs(feature_diameter - gt_ann_diameter) <= diameter_tolerance_mm
            if not is_correct and feature_secondary:
                is_correct = abs(feature_secondary - gt_ann_diameter) <= diameter_tolerance_mm
        if is_correct:
            correct_links += 1

        link_details.append(
            {
                "correct": is_correct,
                "ann_diameter": ann_diameter,
                "feature_diameter": feature_diameter,
                "gt_diameter": gt_match["diameter_mm"],
                "confidence": confidence,
            }
        )

    # If no required GT annotations exist, treat as perfect when no links made
    if not gt_annotations and total_links == 0:
        linking_accuracy = 1.0
    else:
        linking_accuracy = correct_links / total_links if total_links > 0 else 0.0

    return {
        "correct_links": correct_links,
        "total_links": total_links,
        "linking_accuracy": round(linking_accuracy, 4),
        "link_details": link_details,
    }


def run_evaluation(use_llm: bool = False) -> list[dict]:
    """Run full evaluation on all test cases."""
    import logging

    logging.basicConfig(level=logging.WARNING)

    results = []

    for name, pdf_path, step_path, gt_path in TEST_CASES:
        if not gt_path.exists():
            print(f"  {name}: No ground truth file, skipping")
            continue
        if not pdf_path.exists() or not step_path.exists():
            print(f"  {name}: Missing input files, skipping")
            continue

        print(f"\n{'=' * 60}")
        print(f"  Evaluating: {name}")
        print(f"{'=' * 60}")

        # Load ground truth
        gt = load_ground_truth(gt_path)

        # Drawings that carry their callouts as vector artwork leave unit
        # detection nothing to work with. Taking the unit system from the
        # ground truth there keeps the extraction score meaningful, but it is
        # an assist and every result records whether it was used.
        unit_override = None
        gt_unit = gt.get("unit_system")
        if gt_unit and not _has_engineering_content(extract_all_text(str(pdf_path))):
            if gt_unit != detect_unit_system(str(pdf_path)):
                print(f"  Unit override from ground truth: {gt_unit}")
                unit_override = gt_unit

        started = time.time()
        analysis = analyze(
            pdf_path,
            step_path,
            settings=Settings(use_llm=use_llm, unit_system=unit_override),
        )
        elapsed = time.time() - started

        annotations = analysis.annotations
        holes = analysis.holes
        matches = analysis.matches

        for stage in analysis.stages:
            if stage.status is StageStatus.FAILED:
                print(f"  ! {stage.name} failed: {stage.detail}")
            elif stage.status is StageStatus.PARTIAL:
                print(f"  ~ {stage.name} partly failed: {stage.detail}")

        extraction_eval = evaluate_extraction(annotations, gt)
        linking_eval = evaluate_linking(matches, gt, holes)
        extraction_eval["missed_breakdown"] = diagnose_misses(
            extraction_eval.pop("missed_entries", []), analysis.raw_texts
        )

        avg_confidence = sum(m.confidence for m in matches) / len(matches) if matches else 0.0

        result = {
            "test_case": name,
            "unit_system": analysis.unit_system,
            "unit_source": "ground_truth" if unit_override else "detected",
            "llm_enhanced": analysis.llm_used,
            "llm_requested": use_llm,
            "vision_model": VISION_MODEL if use_llm else None,
            "runtime_seconds": round(elapsed, 2),
            "stages": [s.as_dict() for s in analysis.stages],
            "extraction": extraction_eval,
            "linking": linking_eval,
            "annotations_found": len(annotations),
            "holes_found": len(holes),
            "matches_found": len(matches),
            "avg_confidence": round(avg_confidence, 4),
        }
        results.append(result)

        # Print extraction results
        e = extraction_eval
        print("\n  Annotation Extraction:")
        print(f"    Extracted:    {e['total_extracted']}")
        print(f"    Ground Truth: {e['total_ground_truth']}")
        print(
            f"    TP: {e['true_positives']}, FP: {e['false_positives']}, FN: {e['false_negatives']}"
        )
        print(f"    Precision:    {e['precision']:.1%}")
        print(f"    Recall:       {e['recall']:.1%}")
        print(f"    F1:           {e['f1']:.1%}")

        if e["missed_annotations"]:
            print(f"    Missed: {', '.join(e['missed_annotations'][:5])}")

        # Print linking results
        link = linking_eval
        print("\n  Linking Accuracy:")
        print(f"    Total Links:  {link['total_links']}")
        print(f"    Correct:      {link['correct_links']}")
        print(f"    Accuracy:     {link['linking_accuracy']:.1%}")
        print(f"    Avg Conf:     {avg_confidence:.1%}")

    return results


def _llm_requested(results: list[dict]) -> bool:
    row = results[0]
    return bool(row.get("llm_requested", row.get("llm_enhanced", False)))


def _generate_single_chart(results: list[dict], output_path: Path, title_suffix: str = ""):
    """Generate a single evaluation bar chart for given results."""
    import matplotlib.pyplot as plt
    import numpy as np

    if not results:
        return

    cases = [r["test_case"] for r in results]
    llm_label = "with LLM" if _llm_requested(results) else "without LLM"

    metrics = {
        "Precision": ([r["extraction"]["precision"] * 100 for r in results], "#4ade80"),
        "Recall": ([r["extraction"]["recall"] * 100 for r in results], "#60a5fa"),
        "F1": ([r["extraction"]["f1"] * 100 for r in results], "#facc15"),
        "Linking": ([r["linking"]["linking_accuracy"] * 100 for r in results], "#f87171"),
        "Confidence": ([r["avg_confidence"] * 100 for r in results], "#a78bfa"),
    }

    n = len(cases)
    width = 0.15 if n > 3 else 0.12
    fig_width = max(6, min(14, n * 1.2 + 2))
    x = np.arange(n)
    fig, ax = plt.subplots(figsize=(fig_width, 5))

    for j, (name, (vals, color)) in enumerate(metrics.items()):
        offset = (j - 2) * width
        bars = ax.bar(
            x + offset, vals, width, label=name, color=color, alpha=0.85, zorder=3, edgecolor="none"
        )
        fontsize = 7 if n <= 8 else 6
        ax.bar_label(bars, fmt="%.0f", padding=2, fontsize=fontsize, color=color, fontweight="bold")

    ax.set_xticks(x)
    rotation = 20 if n <= 8 else 35
    ax.set_xticklabels(cases, fontsize=10, fontweight="bold", rotation=rotation, ha="right")
    ax.set_ylabel("Score (%)")
    ax.set_ylim(0, 115)
    title = f"DrawMind3D Evaluation ({llm_label})"
    if title_suffix:
        title += f" - {title_suffix}"
    ax.set_title(title, fontsize=14, fontweight="bold", color="#60a5fa", pad=15)
    ax.legend(loc="upper left", fontsize=9, framealpha=0.3, ncol=5)
    ax.grid(axis="y", alpha=0.4, zorder=1)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(output_path, format="svg", bbox_inches="tight", transparent=False)
    plt.close(fig)
    print(f"  Chart saved: {output_path}")


def generate_charts(results: list[dict], output_dir: Path):
    """Generate evaluation charts using matplotlib - all, and per-category."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    # Dark theme
    plt.rcParams.update(
        {
            "figure.facecolor": "#0f1117",
            "axes.facecolor": "#0f1117",
            "axes.edgecolor": "#2a2d3a",
            "axes.labelcolor": "#888",
            "xtick.color": "#888",
            "ytick.color": "#888",
            "text.color": "#e0e0e0",
            "grid.color": "#2a2d3a",
            "font.family": "sans-serif",
        }
    )

    # The requested mode names the files: a provider failure on the first case
    # must not make an --llm run overwrite the offline results.
    suffix = "_llm" if _llm_requested(results) else "_nollm"

    # All results chart
    _generate_single_chart(results, charts_dir / f"evaluation_chart{suffix}.svg")

    # Per-category charts
    categories = {
        "ctc": ("CTC", [r for r in results if r["test_case"].startswith("CTC")]),
        "ftc": ("FTC", [r for r in results if r["test_case"].startswith("FTC")]),
        "syn": ("Synthetic", [r for r in results if r["test_case"].startswith("SYN")]),
    }

    for cat_key, (cat_label, cat_results) in categories.items():
        if cat_results:
            _generate_single_chart(
                cat_results,
                charts_dir / f"evaluation_chart{suffix}_{cat_key}.svg",
                title_suffix=cat_label,
            )

    # Save results JSON
    results_dir = output_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / f"evaluation_results{suffix}.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results saved: {json_path}")


def main():
    parser = argparse.ArgumentParser(description="DrawMind3D Evaluation")
    parser.add_argument("--llm", action="store_true", help="Use Vision LLM")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(os.getenv("EVAL_OUTPUT_DIR") or EVAL_DIR),
        help="Directory for results, charts and the HTML report",
    )
    args = parser.parse_args()

    print("DrawMind3D Evaluation")
    print(f"Mode: {'With Vision LLM' if args.llm else 'Regex + OCR only'}")

    results = run_evaluation(use_llm=args.llm)

    if not results:
        print("\nNo results to evaluate.")
        return

    # Print summary table
    print(f"\n{'=' * 70}")
    print("  SUMMARY")
    print(f"{'=' * 70}")
    print(f"{'Case':<10} {'P':>8} {'R':>8} {'F1':>8} {'Link%':>8} {'Conf':>8}")
    print("-" * 50)
    for r in results:
        print(
            f"{r['test_case']:<10} "
            f"{r['extraction']['precision']:>7.1%} "
            f"{r['extraction']['recall']:>7.1%} "
            f"{r['extraction']['f1']:>7.1%} "
            f"{r['linking']['linking_accuracy']:>7.1%} "
            f"{r['avg_confidence']:>7.1%}"
        )

    # Averages (exclude test cases with 0 required GT annotations)
    scorable = [r for r in results if r["extraction"]["total_ground_truth"] > 0]
    n_scorable = len(scorable) if scorable else 1
    avg_p = sum(r["extraction"]["precision"] for r in scorable) / n_scorable
    avg_r = sum(r["extraction"]["recall"] for r in scorable) / n_scorable
    avg_f1 = sum(r["extraction"]["f1"] for r in scorable) / n_scorable
    avg_link = sum(r["linking"]["linking_accuracy"] for r in scorable) / n_scorable
    avg_conf = sum(r["avg_confidence"] for r in scorable) / n_scorable
    print("-" * 50)
    print(
        f"{'AVG':<10} {avg_p:>7.1%} {avg_r:>7.1%} {avg_f1:>7.1%} {avg_link:>7.1%} {avg_conf:>7.1%}"
    )

    args.out.mkdir(parents=True, exist_ok=True)
    generate_charts(results, args.out)

    from eval_report import build_report

    print(f"Report written: {build_report(args.out / 'results', args.out / 'report.html')}")


if __name__ == "__main__":
    main()
