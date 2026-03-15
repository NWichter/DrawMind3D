"""Generate presentation-ready SVG charts for DrawMind3D evaluation results using matplotlib."""

from __future__ import annotations
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DATA_DIR = Path(__file__).parent.parent / "data"
EVAL_DIR = DATA_DIR / "evaluation"
OUTPUT_DIR = EVAL_DIR / "presentation"

# Dark theme colors matching the web UI
DARK_BG = "#0f172a"
DARK_FG = "#e2e8f0"
DARK_GRID = "#1e293b"
DARK_MUTED = "#64748b"

BLUE = "#3b82f6"
GREEN = "#22c55e"
AMBER = "#f59e0b"
PURPLE = "#a855f7"
RED = "#f87171"
LIGHT_BLUE = "#93c5fd"
LIGHT_GREEN = "#86efac"


def _apply_dark_theme():
    """Apply dark theme matching the web UI."""
    plt.rcParams.update(
        {
            "figure.facecolor": DARK_BG,
            "axes.facecolor": DARK_BG,
            "axes.edgecolor": DARK_GRID,
            "axes.labelcolor": DARK_MUTED,
            "xtick.color": DARK_MUTED,
            "ytick.color": DARK_MUTED,
            "text.color": DARK_FG,
            "grid.color": DARK_GRID,
            "grid.linewidth": 0.8,
            "font.family": "sans-serif",
            "font.size": 11,
        }
    )


def short_name(name: str) -> str:
    return (
        name.replace("SYN-0", "S")
        .replace("-SimpleBlock", "")
        .replace("-ThreadedPlate", "")
        .replace("-InchPart", "")
        .replace("-MixedFeatures", "")
        .replace("-ManyHoles", "")
        .replace("CTC-0", "C")
        .replace("FTC-0", "F")
        .replace("FTC-", "F")
        .replace("D2MI-", "D")
    )


def load_results():
    nollm = json.loads((EVAL_DIR / "evaluation_results_nollm.json").read_text())
    llm = json.loads((EVAL_DIR / "evaluation_results_llm.json").read_text())
    return nollm, llm


def filter_results(results, category):
    """Filter results by category: 'all', 'nist', 'syn', 'd2mi'."""
    # Always exclude FTC-11 (torus part, no real holes, 0 required GT)
    results = [r for r in results if r["test_case"] != "FTC-11"]
    if category == "all":
        return results
    if category == "nist":
        return [r for r in results if r["test_case"].startswith(("CTC", "FTC"))]
    if category == "d2mi":
        return [r for r in results if r["test_case"].startswith("D2MI")]
    if category == "syn":
        return [r for r in results if r["test_case"].startswith("SYN")]
    return results


def chart_comparison_f1(nollm, llm, output_path: Path):
    """Side-by-side F1 comparison: without vs with LLM."""
    _apply_dark_theme()
    cases = [short_name(r["test_case"]) for r in nollm]
    f1_no = [r["extraction"]["f1"] * 100 for r in nollm]
    f1_yes = [r["extraction"]["f1"] * 100 for r in llm]
    avg_no = np.mean(f1_no)
    avg_yes = np.mean(f1_yes)

    n = len(cases)
    x = np.arange(n)
    width = 0.35

    fig_width = max(10, n * 0.9 + 2)
    fig, ax = plt.subplots(figsize=(fig_width, 5))
    bars1 = ax.bar(
        x - width / 2,
        f1_no,
        width,
        label=f"Regex + OCR (Avg {avg_no:.0f}%)",
        color=BLUE,
        alpha=0.85,
        zorder=3,
        edgecolor="none",
    )
    bars2 = ax.bar(
        x + width / 2,
        f1_yes,
        width,
        label=f"+ Vision LLM (Avg {avg_yes:.0f}%)",
        color=GREEN,
        alpha=0.85,
        zorder=3,
        edgecolor="none",
    )

    # Value labels
    fontsize = 9 if n <= 9 else 7
    ax.bar_label(
        bars1, fmt="%.0f%%", padding=3, fontsize=fontsize, color=LIGHT_BLUE, fontweight="bold"
    )
    ax.bar_label(
        bars2, fmt="%.0f%%", padding=3, fontsize=fontsize, color=LIGHT_GREEN, fontweight="bold"
    )

    # Average lines
    ax.axhline(avg_no, color=BLUE, linewidth=1.2, linestyle="--", alpha=0.5, zorder=2)
    ax.axhline(avg_yes, color=GREEN, linewidth=1.2, linestyle="--", alpha=0.5, zorder=2)

    ax.set_xticks(x)
    rotation = 0 if n <= 9 else 30
    ha = "center" if n <= 9 else "right"
    ax.set_xticklabels(cases, fontsize=11, fontweight="600", rotation=rotation, ha=ha)
    ax.set_ylabel("F1-Score (%)")
    ax.set_ylim(0, 115)
    ax.set_title("F1-Score: Regex/OCR vs. Vision LLM", fontsize=16, fontweight="bold", pad=15)
    ax.legend(loc="upper left", fontsize=10, framealpha=0.3)
    ax.grid(axis="y", alpha=0.4, zorder=1)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(output_path, format="svg", bbox_inches="tight", transparent=False)
    plt.close(fig)


def chart_metrics_overview(llm_results, output_path: Path):
    """Horizontal bar chart showing P/R/F1/Linking for LLM mode."""
    _apply_dark_theme()
    cases = [short_name(r["test_case"]) for r in llm_results]
    metrics = [
        ("F1", [r["extraction"]["f1"] * 100 for r in llm_results], BLUE),
        ("Precision", [r["extraction"]["precision"] * 100 for r in llm_results], AMBER),
        ("Recall", [r["extraction"]["recall"] * 100 for r in llm_results], GREEN),
        ("Linking", [r["linking"]["linking_accuracy"] * 100 for r in llm_results], PURPLE),
    ]

    n = len(cases)
    n_metrics = len(metrics)
    height = 0.18
    y = np.arange(n)

    fig_height = max(5, n * 0.55 + 2)
    fig, ax = plt.subplots(figsize=(10, fig_height))
    for j, (name, vals, color) in enumerate(metrics):
        offset = (j - n_metrics / 2 + 0.5) * height
        bars = ax.barh(
            y + offset,
            vals,
            height,
            label=name,
            color=color,
            alpha=0.85,
            zorder=3,
            edgecolor="none",
        )
        fontsize = 8 if n <= 12 else 6
        ax.bar_label(bars, fmt="%.0f", padding=3, fontsize=fontsize, color=color, fontweight="bold")

    ax.set_yticks(y)
    ax.set_yticklabels(cases, fontsize=11, fontweight="600")
    ax.set_xlabel("Score (%)")
    ax.set_xlim(0, 115)
    ax.set_title(
        "DrawMind3D — Full Metrics (with Vision LLM)", fontsize=16, fontweight="bold", pad=15
    )
    ax.legend(loc="lower right", fontsize=10, framealpha=0.3, ncol=2)
    ax.grid(axis="x", alpha=0.4, zorder=1)
    ax.set_axisbelow(True)
    ax.invert_yaxis()

    fig.tight_layout()
    fig.savefig(output_path, format="svg", bbox_inches="tight", transparent=False)
    plt.close(fig)


def chart_llm_impact_highlight(nollm, llm, output_path: Path):
    """Horizontal bar chart highlighting LLM impact on F1 per case."""
    _apply_dark_theme()
    items = []
    for rn, rl in zip(nollm, llm):
        items.append(
            (
                short_name(rn["test_case"]),
                rn["extraction"]["f1"] * 100,
                rl["extraction"]["f1"] * 100,
            )
        )
    avg_no = np.mean([r["extraction"]["f1"] for r in nollm]) * 100
    avg_yes = np.mean([r["extraction"]["f1"] for r in llm]) * 100
    items.append(("AVG", avg_no, avg_yes))

    labels = [it[0] for it in items]
    vals_no = [it[1] for it in items]
    vals_yes = [it[2] for it in items]

    y = np.arange(len(labels))
    height = 0.35

    fig_height = max(5, len(labels) * 0.45 + 1.5)
    fig, ax = plt.subplots(figsize=(9, fig_height))
    bars1 = ax.barh(
        y + height / 2,
        vals_no,
        height,
        label="Regex/OCR",
        color=BLUE,
        alpha=0.8,
        zorder=3,
        edgecolor="none",
    )
    bars2 = ax.barh(
        y - height / 2,
        vals_yes,
        height,
        label="+ Vision LLM",
        color=GREEN,
        alpha=0.8,
        zorder=3,
        edgecolor="none",
    )

    ax.bar_label(bars1, fmt="%.0f%%", padding=4, fontsize=9, color=LIGHT_BLUE, fontweight="bold")
    ax.bar_label(bars2, fmt="%.0f%%", padding=4, fontsize=9, color=LIGHT_GREEN, fontweight="bold")

    # Separator line before AVG
    ax.axhline(len(items) - 1.5, color=DARK_MUTED, linewidth=1, linestyle="-")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=11, fontweight="600")
    ax.set_xlabel("F1-Score (%)")
    ax.set_xlim(0, 115)
    ax.set_title("Vision LLM Impact on F1-Score", fontsize=16, fontweight="bold", pad=15)
    ax.legend(loc="lower right", fontsize=10, framealpha=0.3)
    ax.grid(axis="x", alpha=0.4, zorder=1)
    ax.set_axisbelow(True)
    ax.invert_yaxis()

    fig.tight_layout()
    fig.savefig(output_path, format="svg", bbox_inches="tight", transparent=False)
    plt.close(fig)


def chart_summary_table(nollm, llm, output_path: Path):
    """Render results summary as a styled matplotlib table."""
    _apply_dark_theme()

    cols = [
        "Test Case",
        "P\n(no LLM)",
        "R\n(no LLM)",
        "F1\n(no LLM)",
        "P\n(LLM)",
        "R\n(LLM)",
        "F1\n(LLM)",
        "Link%",
        "Conf",
    ]

    def fmt(v):
        return f"{v:.0f}%"

    def cell_color(v):
        if v >= 85:
            return "#4ade80"
        if v >= 65:
            return "#facc15"
        return "#f87171"

    rows = []
    for rn, rl in zip(nollm, llm):
        en = rn["extraction"]
        el = rl["extraction"]
        link = rl["linking"]["linking_accuracy"] * 100
        conf = rl["avg_confidence"] * 100
        rows.append(
            [
                short_name(rn["test_case"]),
                en["precision"] * 100,
                en["recall"] * 100,
                en["f1"] * 100,
                el["precision"] * 100,
                el["recall"] * 100,
                el["f1"] * 100,
                link,
                conf,
            ]
        )

    # Average row
    n = len(rows)
    avg = ["AVG"] + [sum(r[j] for r in rows) / n for j in range(1, 9)]
    rows.append(avg)

    fig, ax = plt.subplots(figsize=(11, 0.5 * len(rows) + 2))
    ax.axis("off")

    cell_text = [[r[0]] + [fmt(v) for v in r[1:]] for r in rows]
    table = ax.table(
        cellText=cell_text, colLabels=cols, loc="center", cellLoc="center", colLoc="center"
    )

    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.6)

    # Style cells
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(DARK_GRID)
        if row == 0:
            # Header
            cell.set_facecolor("#1e293b")
            cell.set_text_props(color=DARK_MUTED, fontweight="bold", fontsize=9)
        elif row == len(rows):
            # Average row
            cell.set_facecolor("#0c1222")
            cell.set_text_props(fontweight="bold")
            if col > 0:
                val = rows[row - 1][col]
                cell.set_text_props(color=cell_color(val), fontweight="bold")
            else:
                cell.set_text_props(color=DARK_FG, fontweight="bold")
        else:
            # Data rows
            cell.set_facecolor(DARK_BG if row % 2 == 1 else "#0c1222")
            if col == 0:
                cell.set_text_props(color=DARK_FG, fontweight="600")
            elif col > 0:
                val = rows[row - 1][col]
                cell.set_text_props(color=cell_color(val))

    n_cases = len(rows) - 1  # exclude AVG row
    nist_count = sum(1 for r in rows[:-1] if r[0].startswith(("C", "F")))
    syn_count = n_cases - nist_count
    if nist_count == 0:
        subtitle = f"{syn_count} Synthetic Test Cases"
    elif syn_count == 0:
        subtitle = f"{nist_count} NIST Industrial Test Cases"
    else:
        subtitle = f"{nist_count} NIST Industrial + {syn_count} Synthetic Test Cases"
    ax.set_title(
        f"Evaluation Results Summary\n{subtitle}",
        fontsize=14,
        fontweight="bold",
        pad=20,
        color=DARK_FG,
    )

    fig.tight_layout()
    fig.savefig(
        output_path, format="svg", bbox_inches="tight", transparent=False, facecolor=DARK_BG
    )
    plt.close(fig)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    nollm, llm = load_results()

    categories = [
        ("", "all"),
        ("_nist", "nist"),
        ("_d2mi", "d2mi"),
        ("_syn", "syn"),
    ]

    count = 0
    for suffix, cat in categories:
        nollm_f = filter_results(nollm, cat)
        llm_f = filter_results(llm, cat)
        if not nollm_f or not llm_f:
            continue

        chart_comparison_f1(nollm_f, llm_f, OUTPUT_DIR / f"01_f1_comparison{suffix}.svg")
        chart_metrics_overview(llm_f, OUTPUT_DIR / f"02_metrics_overview{suffix}.svg")
        chart_llm_impact_highlight(nollm_f, llm_f, OUTPUT_DIR / f"03_llm_impact{suffix}.svg")
        chart_summary_table(nollm_f, llm_f, OUTPUT_DIR / f"04_summary_table{suffix}.svg")
        count += 4
        print(f"  {cat}: 4 charts")

    print(f"\n{count} presentation charts generated in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
