"""DrawMind3D CLI - Link PDF technical drawing annotations to 3D CAD features.

Usage:
    drawmind3d --pdf drawing.pdf --step model.step --output result.json
    drawmind3d --pdf drawing.pdf --step model.step --no-llm --verbose
"""

import argparse
import logging
import sys
from pathlib import Path

from drawmind.config import LLM_REVIEW_THRESHOLD, MATCH_CONFIDENCE_THRESHOLD
from drawmind.output.writer import write_output
from drawmind.pipeline import Settings, StageStatus, analyze

STATUS_MARK = {
    StageStatus.OK: "+",
    StageStatus.PARTIAL: "~",
    StageStatus.SKIPPED: "-",
    StageStatus.FAILED: "!",
}

CORE_STAGES = {"text_extraction", "cad_features", "matching"}


def main():
    parser = argparse.ArgumentParser(
        description="DrawMind3D: Link PDF drawing annotations to 3D CAD features",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--pdf", required=True, help="Path to technical drawing PDF")
    parser.add_argument("--step", required=True, help="Path to 3D model (STEP/STP)")
    parser.add_argument("--output", "-o", default="output.json", help="Output JSON path")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Disable all model calls; nothing leaves this machine",
    )
    parser.add_argument(
        "--units",
        choices=["metric", "inch"],
        help="Override unit detection",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("drawmind")

    pdf_path = Path(args.pdf)
    step_path = Path(args.step)

    settings = Settings(use_llm=not args.no_llm, unit_system=args.units)

    try:
        result = analyze(
            pdf_path,
            step_path,
            settings=settings,
            progress=lambda message, percent: logger.info(f"[{percent:3d}%] {message}"),
        )
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except (ValueError, RuntimeError) as e:
        # Unreadable or oversized input; the traceback only helps with -v.
        logger.error(f"Cannot analyse {pdf_path.name} / {step_path.name}: {e}")
        if args.verbose:
            logger.exception("Details")
        sys.exit(1)

    output_path = write_output(
        matches=result.matches,
        unmatched_annotations=result.unmatched_annotations,
        unmatched_holes=result.unmatched_holes,
        output_path=args.output,
        pdf_file=pdf_path.name,
        step_file=step_path.name,
        llm_enhanced=result.llm_used,
        stages=[s.as_dict() for s in result.stages],
        other_annotations=result.other_annotations,
    )
    logger.info(f"Output written to: {output_path}")

    high_conf = sum(1 for m in result.matches if m.confidence >= LLM_REVIEW_THRESHOLD)
    needs_review = sum(
        1
        for m in result.matches
        if MATCH_CONFIDENCE_THRESHOLD <= m.confidence < LLM_REVIEW_THRESHOLD
    )

    print("\n" + "=" * 50)
    print("DrawMind3D - Results")
    print("=" * 50)
    for stage in result.stages:
        print(f" [{STATUS_MARK[stage.status]}] {stage.name:20} {stage.detail}")
    # A "4x M8" callout matches four holes, so pairs can exceed annotations.
    matched_annotations = len({m.annotation_id for m in result.matches})
    other = len(result.other_annotations)

    print("-" * 50)
    print(f"Annotations found: {len(result.annotations)}")
    print(f"  linked to a hole:{matched_annotations:>4}")
    print(f"  no 3D match:     {len(result.unmatched_annotations):>4}")
    if other:
        print(f"  outside scope:   {other:>4} (depths, tolerances, finish)")
    print(f"3D holes found:    {len(result.holes)}")
    print(f"  with annotation: {len(result.holes) - len(result.unmatched_holes):>4}")
    print(f"  without:         {len(result.unmatched_holes):>4}")
    print(f"Matched pairs:     {len(result.matches)}")
    if result.matches:
        avg_conf = sum(m.confidence for m in result.matches) / len(result.matches)
        print(f"Avg confidence:    {avg_conf:.1%}")
        print(f"  High confidence: {high_conf}")
        if needs_review:
            print(f"  Needs review:    {needs_review}")
    print(f"Output:            {output_path}")
    print("=" * 50)

    # A failed optional step is reported but still yields a usable result;
    # only a failed core step makes the output meaningless. An image-only
    # drawing has no text layer, which the vision pass can make up for.
    failed = {s.name for s in result.stages if s.status is StageStatus.FAILED}
    if failed & (CORE_STAGES - {"text_extraction"}) or (
        "text_extraction" in failed and not result.annotations
    ):
        sys.exit(2)


if __name__ == "__main__":
    main()
