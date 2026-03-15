"""Vision LLM integration for extracting annotations from drawing images."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from drawmind.models import PDFAnnotation, AnnotationType, BoundingBox
from drawmind.pdf.extractor import get_page_as_image, get_page_dimensions
from drawmind.pdf.parser import _is_gdt_false_positive, INCH_TO_MM
from drawmind.llm.client import get_llm_client
from drawmind.llm.prompts import VISION_EXTRACT_PROMPT, SYSTEM_ENGINEERING
from drawmind.config import VISION_MODEL, VISION_MODEL_FALLBACK, VISION_FALLBACK_MIN_ANNOTATIONS

logger = logging.getLogger(__name__)

TYPE_MAP = {
    "thread": AnnotationType.THREAD,
    "diameter": AnnotationType.DIAMETER,
    "depth": AnnotationType.DEPTH,
    "counterbore": AnnotationType.COUNTERBORE,
    "countersink": AnnotationType.COUNTERSINK,
    "tolerance": AnnotationType.TOLERANCE,
    "fit": AnnotationType.FIT,
    "through": AnnotationType.DEPTH,
}

# Parsed keys that hold dimension values needing unit conversion
_DIMENSION_KEYS = {"value", "nominal_diameter", "diameter", "depth", "pitch"}


def _safe_float(val) -> float | None:
    """Try to convert a value to float."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _convert_parsed_values(parsed: dict, unit_system: str) -> dict:
    """Convert dimension values in a parsed dict from inches to mm if needed."""
    if unit_system != "inch":
        return parsed

    converted = dict(parsed)
    for key in _DIMENSION_KEYS:
        if key in converted:
            val = _safe_float(converted[key])
            if val is not None:
                converted[f"original_inch_{key}"] = val
                converted[key] = round(val * INCH_TO_MM, 4)
    return converted


def analyze_page_with_vision(
    pdf_path: str | Path,
    page_num: int,
    existing_annotations: list[PDFAnnotation],
    unit_system: str = "metric",
) -> list[PDFAnnotation]:
    """Use a vision LLM to extract annotations from a drawing page.

    Merges with existing regex-detected annotations, deduplicating by overlap.

    Args:
        pdf_path: Path to the PDF
        page_num: Page number to analyze
        existing_annotations: Already-detected annotations to merge with
        unit_system: "metric" or "inch" — inch values are converted to mm

    Returns:
        Merged list of annotations
    """
    client = get_llm_client()
    if not client.available:
        logger.warning("No LLM API key available, skipping vision analysis")
        return existing_annotations

    try:
        img_bytes = get_page_as_image(pdf_path, page_num, dpi=150)
        page_w, page_h = get_page_dimensions(pdf_path, page_num)

        result = client.complete_json(
            VISION_EXTRACT_PROMPT,
            images=[img_bytes],
            system=SYSTEM_ENGINEERING,
        )

        if not isinstance(result, list):
            logger.warning("Vision LLM did not return a list")
            return existing_annotations

        # Convert vision results to PDFAnnotation objects
        ann_counter = max(
            (int(a.id.split("_")[-1]) for a in existing_annotations),
            default=0,
        )

        vision_annotations = _process_vision_results(
            result, page_num, page_w, page_h, unit_system, ann_counter
        )

        # Deduplicate vision annotations among themselves first
        vision_deduped = _deduplicate_vision_batch(vision_annotations)

        # Merge: add vision annotations that don't overlap with existing ones
        # Track which existing annotations have been "consumed" by a vision
        # duplicate, so separate callouts with the same diameter are preserved.
        # When a vision annotation overlaps with an existing regex annotation,
        # enhance the existing one with any additional data from vision
        # (e.g., multiplier, depth, through-hole info).
        merged = list(existing_annotations)
        consumed: set[int] = set()
        for v_ann in vision_deduped:
            overlap_idx = _find_overlap_idx(v_ann, existing_annotations, consumed)
            if overlap_idx is not None:
                consumed.add(overlap_idx)  # This existing ann is "used up"
                # Enhance existing annotation with vision data
                ex = merged[overlap_idx]
                # If vision found a multiplier that regex missed, adopt it
                if v_ann.multiplier > 1 and ex.multiplier <= 1:
                    ex.multiplier = v_ann.multiplier
                # If vision found through-hole info that regex missed
                if v_ann.is_through and not ex.is_through:
                    ex.is_through = True
                # If vision found depth info that regex missed
                v_depth = v_ann.parsed.get("depth")
                if v_depth is not None and "depth" not in ex.parsed:
                    ex.parsed["depth"] = v_depth
            else:
                merged.append(v_ann)

        new_count = len(merged) - len(existing_annotations)
        logger.info(
            f"Vision LLM found {len(vision_annotations)} annotations, "
            f"{len(vision_deduped)} after internal dedup, "
            f"{new_count} new after merge"
        )

        # Fallback: if very few hole annotations found, re-analyze with stronger model
        hole_types = {
            AnnotationType.THREAD,
            AnnotationType.DIAMETER,
            AnnotationType.HOLE_CALLOUT,
            AnnotationType.COUNTERBORE,
            AnnotationType.COUNTERSINK,
        }
        hole_ann_count = sum(1 for a in merged if a.annotation_type in hole_types)

        if (
            hole_ann_count < VISION_FALLBACK_MIN_ANNOTATIONS
            and VISION_MODEL_FALLBACK != VISION_MODEL
        ):
            logger.info(
                f"Only {hole_ann_count} hole annotations found, "
                f"re-analyzing with stronger model ({VISION_MODEL_FALLBACK})..."
            )
            try:
                # Higher DPI for better detail
                img_hq = get_page_as_image(pdf_path, page_num, dpi=200)
                fallback_prompt = (
                    VISION_EXTRACT_PROMPT + "\n\n"
                    "IMPORTANT: A previous analysis found very few hole annotations. "
                    "Please look VERY carefully at ALL views on this page. "
                    "Check for small holes, threaded holes, counterbored holes, "
                    "and any diameter callouts with leader lines pointing to circular features."
                )
                result2 = client.complete_json(
                    fallback_prompt,
                    images=[img_hq],
                    system=SYSTEM_ENGINEERING,
                    model=VISION_MODEL_FALLBACK,
                )
                if isinstance(result2, list) and len(result2) > len(vision_annotations):
                    # Process fallback results through same pipeline
                    fallback_anns = _process_vision_results(
                        result2, page_num, page_w, page_h, unit_system, ann_counter
                    )
                    fallback_deduped = _deduplicate_vision_batch(fallback_anns)
                    # Merge fallback into existing merged list
                    for fb_ann in fallback_deduped:
                        overlap = _find_overlap_idx(fb_ann, merged, set())
                        if overlap is None:
                            merged.append(fb_ann)
                    new_from_fallback = len(merged) - len(existing_annotations) - new_count
                    if new_from_fallback > 0:
                        logger.info(
                            f"Fallback model found {new_from_fallback} additional annotations"
                        )
            except Exception as fb_err:
                logger.warning(f"Fallback vision analysis failed: {fb_err}")

        return merged

    except Exception as e:
        logger.error(f"Vision analysis failed: {e}")
        return existing_annotations


def _process_vision_results(
    items: list[dict],
    page_num: int,
    page_w: float,
    page_h: float,
    unit_system: str,
    start_counter: int,
) -> list[PDFAnnotation]:
    """Process raw Vision LLM results into PDFAnnotation objects with filtering."""
    annotations = []
    ann_counter = start_counter

    for item in items:
        ann_type_str = item.get("type", "").lower()
        ann_type = TYPE_MAP.get(ann_type_str)
        if ann_type is None:
            continue

        conf = item.get("confidence", 0.7)
        if conf < 0.4:
            continue

        if ann_type == AnnotationType.TOLERANCE:
            continue

        text = item.get("text", "")

        # Skip taper/ratio, radius, torus/ring dimensions
        if re.search(r"\d+\.?\d*\s*:\s*\d+\.?\d*", text) and not re.search(r"[Øø⌀MmXx#]", text):
            continue
        if re.search(r"\bR\s*\.?\d", text, re.IGNORECASE) and not re.search(r"[Øø⌀]", text):
            continue
        if re.search(r"\b(I\.?D\.?|O\.?D\.?|AVG|MAJOR|MINOR)\b", text, re.IGNORECASE):
            continue

        # Skip small values without diameter symbol
        if ann_type == AnnotationType.DIAMETER:
            raw_value = _safe_float(item.get("parsed", {}).get("value"))
            has_dia_sym = bool(re.search(r"[Øø⌀\u2300]", text))
            if raw_value is not None and raw_value < 3.0 and not has_dia_sym:
                continue

        raw_parsed = item.get("parsed", {})

        # GD&T disambiguation
        if ann_type == AnnotationType.DIAMETER:
            raw_value = _safe_float(raw_parsed.get("value"))
            if raw_value is not None and _is_gdt_false_positive(text, raw_value, unit_system):
                continue

        parsed = _convert_parsed_values(raw_parsed, unit_system)

        bbox_pct = item.get("bbox_percent", {})
        bbox = BoundingBox(
            x0=bbox_pct.get("x", 0) * page_w / 100,
            y0=bbox_pct.get("y", 0) * page_h / 100,
            x1=(bbox_pct.get("x", 0) + bbox_pct.get("w", 5)) * page_w / 100,
            y1=(bbox_pct.get("y", 0) + bbox_pct.get("h", 3)) * page_h / 100,
            page=page_num,
        )

        ann_counter += 1
        is_through = ann_type_str == "through" or bool(raw_parsed.get("through", False))

        llm_depth = _safe_float(raw_parsed.get("depth"))
        if llm_depth is not None and "depth" not in parsed:
            if unit_system == "inch":
                parsed["depth"] = round(llm_depth * INCH_TO_MM, 4)
                parsed["original_inch_depth"] = llm_depth
            else:
                parsed["depth"] = llm_depth

        multiplier = item.get("multiplier", 1)
        if isinstance(multiplier, str):
            try:
                multiplier = int(multiplier)
            except ValueError:
                multiplier = 1

        annotations.append(
            PDFAnnotation(
                id=f"ann_{ann_counter:03d}",
                raw_text=text,
                annotation_type=ann_type,
                parsed=parsed,
                bbox=bbox,
                confidence=conf,
                source="vision_llm",
                multiplier=multiplier,
                is_through=is_through,
                unit_system=unit_system,
            )
        )

    return annotations


def _get_ann_diameter(ann: PDFAnnotation) -> float | None:
    """Extract the diameter value from an annotation for dedup."""
    p = ann.parsed
    if ann.annotation_type == AnnotationType.THREAD:
        val = p.get("nominal_diameter")
    elif ann.annotation_type in (AnnotationType.DIAMETER, AnnotationType.HOLE_CALLOUT):
        val = p.get("value")
    elif ann.annotation_type in (AnnotationType.COUNTERBORE, AnnotationType.COUNTERSINK):
        val = p.get("diameter")
    else:
        return None
    return _safe_float(val)


def _deduplicate_vision_batch(
    annotations: list[PDFAnnotation],
    diameter_tol_mm: float = 0.5,
) -> list[PDFAnnotation]:
    """Remove duplicates within a single batch of vision annotations.

    The LLM often returns the same callout multiple times with slightly
    different text/bbox. Two annotations are duplicates if they match on
    type + diameter AND are spatially close. The proximity threshold is
    dynamic based on annotation density to avoid over-merging on dense pages.
    """
    if not annotations:
        return []

    # Dynamic threshold: scale based on annotation density
    # Dense drawings need tighter thresholds to avoid merging distinct callouts
    n_ann = len(annotations)
    if n_ann <= 5:
        base_threshold = 60  # Generous for sparse pages
    elif n_ann <= 15:
        base_threshold = 40  # Moderate for medium density
    else:
        base_threshold = 25  # Tight for dense pages

    kept: list[PDFAnnotation] = []
    for ann in annotations:
        dia = _get_ann_diameter(ann)
        is_dup = False
        for i, ex in enumerate(kept):
            ex_dia = _get_ann_diameter(ex)

            # Exact text match on same page = definite duplicate
            if (
                ann.raw_text.strip() == ex.raw_text.strip()
                and ann.bbox.page == ex.bbox.page
                and ann.annotation_type == ex.annotation_type
            ):
                is_dup = True
                if ann.confidence > ex.confidence:
                    kept[i] = ann
                break

            # Same type + diameter + proximity = likely duplicate
            if (
                ann.annotation_type == ex.annotation_type
                and ann.bbox.page == ex.bbox.page
                and ann.multiplier == ex.multiplier
                and dia is not None
                and ex_dia is not None
                and abs(dia - ex_dia) < diameter_tol_mm
            ):
                cx1 = (ann.bbox.x0 + ann.bbox.x1) / 2
                cy1 = (ann.bbox.y0 + ann.bbox.y1) / 2
                cx2 = (ex.bbox.x0 + ex.bbox.x1) / 2
                cy2 = (ex.bbox.y0 + ex.bbox.y1) / 2
                dist = ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5
                if dist < base_threshold:
                    is_dup = True
                    if ann.confidence > ex.confidence:
                        kept[i] = ann
                    break
        if not is_dup:
            kept.append(ann)
    return kept


def _find_overlap_idx(
    new_ann: PDFAnnotation,
    existing: list[PDFAnnotation],
    consumed: set[int],
    iou_threshold: float = 0.3,
    diameter_tol_mm: float = 0.5,
) -> int | None:
    """Find the first unconsumed existing annotation that overlaps with new_ann.

    Returns the index into `existing`, or None if no overlap found.
    Already-consumed indices are skipped so that each existing annotation
    can only "absorb" one vision duplicate.
    """
    new_dia = _get_ann_diameter(new_ann)

    for idx, ex in enumerate(existing):
        if idx in consumed:
            continue
        if ex.bbox.page != new_ann.bbox.page:
            continue

        # Check text similarity first (faster)
        if ex.raw_text.strip().lower() == new_ann.raw_text.strip().lower():
            return idx

        # Check diameter + type match (multiplier ignored — LLM often misparsed)
        ex_dia = _get_ann_diameter(ex)
        if (
            new_dia is not None
            and ex_dia is not None
            and new_ann.annotation_type == ex.annotation_type
            and abs(new_dia - ex_dia) < diameter_tol_mm
        ):
            return idx

        # Check bounding box IoU
        iou = _compute_iou(new_ann.bbox, ex.bbox)
        if iou > iou_threshold:
            return idx

    return None


def _compute_iou(box1: BoundingBox, box2: BoundingBox) -> float:
    """Compute Intersection over Union of two bounding boxes."""
    x_overlap = max(0, min(box1.x1, box2.x1) - max(box1.x0, box2.x0))
    y_overlap = max(0, min(box1.y1, box2.y1) - max(box1.y0, box2.y0))
    intersection = x_overlap * y_overlap

    area1 = (box1.x1 - box1.x0) * (box1.y1 - box1.y0)
    area2 = (box2.x1 - box2.x0) * (box2.y1 - box2.y0)
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0
