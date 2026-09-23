"""Snapshot the observable output of the PDF layer for regression comparison.

The PDF layer (text extraction, unit detection, page geometry, leader lines)
has no unit-test coverage, so replacing its backend needs a characterization
baseline. This script records what the layer produces today; after a backend
change, re-run it and diff against the stored baseline.

Usage:
    python scripts/pdf_layer_snapshot.py --out tests/golden/pdf_layer.json
    python scripts/pdf_layer_snapshot.py --compare tests/golden/pdf_layer.json

Only public pipeline functions are called, so the snapshot is backend-agnostic.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Vision-LLM fallbacks make the snapshot non-deterministic and cost API calls.
import drawmind.config as _config  # noqa: E402

_config.USE_VISION_LLM = False

from drawmind.pdf.extractor import (  # noqa: E402
    detect_unit_system,
    extract_all_text,
    get_page_as_image,
    get_page_dimensions,
)
from drawmind.pdf.leader_lines import extract_leader_targets  # noqa: E402
from drawmind.pdf.parser import parse_annotations  # noqa: E402

# A deliberately mixed corpus: metric and inch, vector and dense, single and
# multi-page, small and large.
CORPUS = [
    "data/synthetic/SYN-01-SimpleBlock.pdf",
    "data/synthetic/SYN-02-ThreadedPlate.pdf",
    "data/synthetic/SYN-03-InchPart.pdf",
    "data/synthetic/SYN-04-MixedFeatures.pdf",
    "data/synthetic/SYN-05-ManyHoles.pdf",
    "data/nist/NIST_MBE_PMI_FTC_Definitions/nist_ftc_06_asme1_rd.pdf",
    "data/nist/NIST_MBE_PMI_FTC_Definitions/nist_ftc_07_asme1_rd.pdf",
    "data/nist/NIST_MBE_PMI_FTC_Definitions/nist_ftc_08_asme1_rc.pdf",
    "data/nist/NIST_MBE_PMI_FTC_Definitions/nist_ftc_09_asme1_rd.pdf",
    "data/nist/NIST_MBE_PMI_FTC_Definitions/nist_ftc_10_asme1_rb.pdf",
    "data/nist/NIST_MBE_PMI_FTC_Definitions/nist_ftc_11_asme1_rb.pdf",
    "data/nist/NIST_MBE_PMI_FTC_Definitions/nist_ftc_assembly_7-8-9-10.pdf",
    "data/nist/NIST-HTC-PMI-v2/NIST_HTC_20240531.pdf",
]

# Text positions shift by sub-point amounts between PDF engines; comparing at
# 0.1pt resolution catches real layout errors without flagging rounding noise.
POS_DECIMALS = 1


def _round_bbox(bbox: dict) -> dict:
    return {k: round(float(v), POS_DECIMALS) for k, v in bbox.items()}


def _snapshot_pdf(pdf_path: Path) -> dict:
    texts = extract_all_text(pdf_path)

    # Order varies with the engine's internal block ordering; sort so the
    # diff reports content differences rather than traversal differences.
    text_rows = sorted(
        (
            {
                "text": t["text"],
                "bbox": _round_bbox(t["bbox"]),
                "page": t["page"],
                "source": t["source"],
            }
            for t in texts
        ),
        key=lambda r: (r["page"], r["bbox"]["y0"], r["bbox"]["x0"], r["text"]),
    )

    unit_system = detect_unit_system(pdf_path)
    annotations = parse_annotations(texts, unit_system=unit_system)
    annotations = extract_leader_targets(pdf_path, annotations)

    ann_rows = sorted(
        (
            {
                "raw_text": a.raw_text,
                "type": a.annotation_type.value,
                "multiplier": a.multiplier,
                "is_through": a.is_through,
                "page": a.bbox.page,
                "leader_target": (
                    {
                        "x": round(a.parsed["leader_target"]["x"], POS_DECIMALS),
                        "y": round(a.parsed["leader_target"]["y"], POS_DECIMALS),
                    }
                    if "leader_target" in a.parsed
                    else None
                ),
            }
            for a in annotations
        ),
        key=lambda r: (r["page"], r["raw_text"], r["type"]),
    )

    width, height = get_page_dimensions(pdf_path)

    png = get_page_as_image(pdf_path, page_num=0, dpi=150)
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(png))
        render = {"format": img.format, "width": img.width, "height": img.height}
    except Exception as exc:  # pragma: no cover - diagnostic only
        render = {"error": str(exc)}

    return {
        "text_count": len(text_rows),
        "texts": text_rows,
        "unit_system": unit_system,
        "annotation_count": len(ann_rows),
        "annotations": ann_rows,
        "page_size": [round(width, POS_DECIMALS), round(height, POS_DECIMALS)],
        "render": render,
    }


def build_snapshot() -> dict:
    snapshot = {}
    for rel in CORPUS:
        path = PROJECT_ROOT / rel
        if not path.exists():
            print(f"  skip (missing): {rel}")
            continue
        print(f"  {rel}")
        try:
            snapshot[rel] = _snapshot_pdf(path)
        except Exception as exc:
            snapshot[rel] = {"error": f"{type(exc).__name__}: {exc}"}
            print(f"    ERROR {type(exc).__name__}: {exc}")
    return snapshot


def _diff_pdf(rel: str, old: dict, new: dict) -> list[str]:
    issues = []

    for field in ("unit_system", "page_size", "text_count", "annotation_count"):
        if old.get(field) != new.get(field):
            issues.append(f"{rel}: {field} {old.get(field)!r} -> {new.get(field)!r}")

    old_render = old.get("render", {})
    new_render = new.get("render", {})
    for field in ("width", "height"):
        if old_render.get(field) != new_render.get(field):
            issues.append(
                f"{rel}: render.{field} {old_render.get(field)!r} -> {new_render.get(field)!r}"
            )

    old_texts = {t["text"] for t in old.get("texts", [])}
    new_texts = {t["text"] for t in new.get("texts", [])}
    lost = old_texts - new_texts
    gained = new_texts - old_texts
    if lost:
        issues.append(f"{rel}: {len(lost)} text strings lost, e.g. {sorted(lost)[:5]}")
    if gained:
        issues.append(f"{rel}: {len(gained)} text strings gained, e.g. {sorted(gained)[:5]}")

    old_anns = {(a["raw_text"], a["type"]) for a in old.get("annotations", [])}
    new_anns = {(a["raw_text"], a["type"]) for a in new.get("annotations", [])}
    if old_anns - new_anns:
        issues.append(f"{rel}: annotations lost: {sorted(old_anns - new_anns)[:5]}")
    if new_anns - old_anns:
        issues.append(f"{rel}: annotations gained: {sorted(new_anns - old_anns)[:5]}")

    old_leaders = sum(1 for a in old.get("annotations", []) if a["leader_target"])
    new_leaders = sum(1 for a in new.get("annotations", []) if a["leader_target"])
    if old_leaders != new_leaders:
        issues.append(f"{rel}: leader targets {old_leaders} -> {new_leaders}")

    return issues


def compare(baseline_path: Path) -> int:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    print("Rebuilding snapshot with the current backend...")
    current = build_snapshot()

    issues = []
    for rel in sorted(set(baseline) | set(current)):
        if rel not in baseline:
            issues.append(f"{rel}: present now, absent in baseline")
        elif rel not in current:
            issues.append(f"{rel}: in baseline, absent now")
        else:
            issues.extend(_diff_pdf(rel, baseline[rel], current[rel]))

    print()
    if not issues:
        print(f"IDENTICAL across {len(current)} PDFs.")
        return 0

    print(f"{len(issues)} difference(s):")
    for issue in issues:
        print(f"  - {issue}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, help="write a new baseline snapshot here")
    ap.add_argument("--compare", type=Path, help="compare current behaviour to this baseline")
    args = ap.parse_args()

    if args.compare:
        return compare(args.compare)

    out = args.out or PROJECT_ROOT / "tests" / "golden" / "pdf_layer.json"
    print("Building snapshot...")
    snapshot = build_snapshot()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out} ({len(snapshot)} PDFs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
