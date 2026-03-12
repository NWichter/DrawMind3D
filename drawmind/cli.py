"""DrawMind3D CLI - Link PDF technical drawing annotations to 3D CAD features.

Usage:
    drawmind3d --pdf drawing.pdf --step model.step --output result.json
    drawmind3d --pdf drawing.pdf --step model.step --no-llm --verbose
"""

import argparse
import logging
import sys
from pathlib import Path

from drawmind.pdf.extractor import extract_all_text, detect_unit_system
from drawmind.pdf.parser import parse_annotations
from drawmind.cad.step_reader import load_step
from drawmind.cad.feature_extractor import (
    extract_cylindrical_faces,
    group_coaxial_features,
    detect_through_holes,
)
from drawmind.matching.matcher import match_annotations_to_features
from drawmind.output.writer import write_output
from drawmind.config import USE_VISION_LLM


def main():
    parser = argparse.ArgumentParser(
        description="DrawMind3D: Link PDF drawing annotations to 3D CAD features",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--pdf", required=True, help="Path to technical drawing PDF")
    parser.add_argument("--step", required=True, help="Path to 3D model (STEP/STP)")
    parser.add_argument("--output", "-o", default="output.json", help="Output JSON path")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM features")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("drawmind")

    # Validate inputs
    pdf_path = Path(args.pdf)
    step_path = Path(args.step)

    if not pdf_path.exists():
        logger.error(f"PDF file not found: {pdf_path}")
        sys.exit(1)
    if not step_path.exists():
        logger.error(f"STEP file not found: {step_path}")
        sys.exit(1)

    use_llm = USE_VISION_LLM and not args.no_llm

    # === Step 1: Extract PDF annotations ===
    logger.info(f"Extracting annotations from: {pdf_path}")
    raw_texts = extract_all_text(str(pdf_path))
    logger.info(f"  Found {len(raw_texts)} text elements")

    unit_system = detect_unit_system(str(pdf_path))
    if unit_system == "inch":
        logger.info("  Detected INCH unit system — values will be converted to mm")

    annotations = parse_annotations(raw_texts, unit_system=unit_system)
    logger.info(f"  Parsed {len(annotations)} engineering annotations")

    for ann in annotations:
        logger.debug(f"  [{ann.annotation_type.value}] '{ann.raw_text}' -> {ann.parsed}")

    # === Step 2: Vision LLM enrichment (optional, all pages) ===
    if use_llm:
        logger.info("Running vision LLM analysis...")
        try:
            import fitz as _fitz
            from drawmind.pdf.vision import analyze_page_with_vision
            _doc = _fitz.open(str(pdf_path))
            num_pages = len(_doc)
            _doc.close()
            for page_idx in range(num_pages):
                logger.info(f"  Vision LLM: analyzing page {page_idx + 1}/{num_pages}")
                annotations = analyze_page_with_vision(str(pdf_path), page_idx, annotations, unit_system=unit_system)
            logger.info(f"  After LLM enrichment: {len(annotations)} annotations")
        except Exception as e:
            logger.warning(f"Vision LLM failed, continuing without: {e}")

    # === Step 2b: Leader-line tracking ===
    try:
        from drawmind.pdf.leader_lines import extract_leader_targets
        annotations = extract_leader_targets(str(pdf_path), annotations)
    except Exception as e:
        logger.warning(f"Leader-line extraction failed: {e}")

    # === Step 3: Extract 3D features ===
    logger.info(f"Loading 3D model: {step_path}")
    shape = load_step(str(step_path))

    logger.info("Extracting cylindrical features...")
    features = extract_cylindrical_faces(shape)
    logger.info(f"  Found {len(features)} cylindrical faces")

    logger.info("Grouping coaxial features into holes...")
    holes = group_coaxial_features(features)
    logger.info(f"  Identified {len(holes)} hole groups")

    logger.info("Detecting through-holes...")
    holes = detect_through_holes(shape, holes)
    through_count = sum(1 for h in holes if h.is_through_hole)
    logger.info(f"  {through_count} through-holes detected")

    for hole in holes:
        logger.debug(
            f"  {hole.id}: D={hole.primary_diameter:.2f}mm, "
            f"depth={hole.total_depth:.2f}mm, type={hole.hole_type}, "
            f"through={hole.is_through_hole}"
        )

    # === Step 4: Match annotations to features ===
    logger.info("Matching annotations to 3D features...")
    matches, unmatched_ann, unmatched_holes = match_annotations_to_features(
        annotations, holes
    )
    logger.info(
        f"  {len(matches)} matches, "
        f"{len(unmatched_ann)} unmatched annotations, "
        f"{len(unmatched_holes)} unmatched holes"
    )

    # === Step 5: LLM disambiguation (optional) ===
    if use_llm and unmatched_ann:
        logger.info(
            f"Attempting LLM disambiguation for {len(unmatched_ann)} unmatched annotations..."
        )
        try:
            from drawmind.matching.llm_resolver import resolve_ambiguous_matches
            llm_matches = resolve_ambiguous_matches(
                unmatched_ann, unmatched_holes, str(pdf_path)
            )
            if llm_matches:
                matches.extend(llm_matches)
                resolved_ann_ids = {m.annotation_id for m in llm_matches}
                resolved_hole_ids = {m.feature_id for m in llm_matches}
                unmatched_ann = [a for a in unmatched_ann if a.id not in resolved_ann_ids]
                unmatched_holes = [h for h in unmatched_holes if h.id not in resolved_hole_ids]
                logger.info(f"  LLM resolved {len(llm_matches)} additional matches")
        except Exception as e:
            logger.warning(f"LLM disambiguation failed: {e}")

    # === Step 6: Write output ===
    output_path = write_output(
        matches=matches,
        unmatched_annotations=unmatched_ann,
        unmatched_holes=unmatched_holes,
        output_path=args.output,
        pdf_file=pdf_path.name,
        step_file=step_path.name,
        llm_enhanced=use_llm,
    )
    logger.info(f"Output written to: {output_path}")

    # Print summary
    print("\n" + "=" * 50)
    print("DrawMind3D - Results")
    print("=" * 50)
    print(f"Annotations found: {len(annotations)}")
    print(f"3D holes found:    {len(holes)}")
    print(f"Matched pairs:     {len(matches)}")
    if matches:
        avg_conf = sum(m.confidence for m in matches) / len(matches)
        print(f"Avg confidence:    {avg_conf:.1%}")
    print(f"Output:            {output_path}")
    print("=" * 50)


if __name__ == "__main__":
    main()
