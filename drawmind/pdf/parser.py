"""Parse raw PDF text into structured engineering annotations."""

from __future__ import annotations

import re

from drawmind.models import PDFAnnotation, AnnotationType, BoundingBox
from drawmind.pdf import patterns as pat
from drawmind.config import (
    MAX_HOLE_DIAMETER_MM,
    MAX_HOLE_DIAMETER_INCH,
    GDT_MAX_INCH_VALUE,
    GDT_MAX_METRIC_VALUE,
)

# Inch-to-mm conversion factor
INCH_TO_MM = 25.4


def parse_annotations(raw_texts: list[dict], unit_system: str = "metric") -> list[PDFAnnotation]:
    """Parse raw text spans into structured PDFAnnotation objects.

    Args:
        raw_texts: List of dicts from extractor with text, bbox, page, source
        unit_system: "metric" or "inch" — inch values are converted to mm

    Returns:
        List of parsed PDFAnnotation objects
    """
    annotations = []
    ann_counter = 0

    for raw in raw_texts:
        text = raw["text"]
        bbox_data = raw["bbox"]
        page = raw.get("page", 0)
        source = raw.get("source", "native")

        bbox = BoundingBox(
            x0=bbox_data["x0"],
            y0=bbox_data["y0"],
            x1=bbox_data["x1"],
            y1=bbox_data["y1"],
            page=page,
        )

        # Try combined hole callout first (most specific)
        combined = _parse_combined_callout(text, bbox, source, ann_counter, unit_system)
        if combined:
            annotations.extend(combined)
            ann_counter += len(combined)
            continue

        # Try individual patterns
        parsed = _parse_individual_patterns(text, bbox, source, ann_counter, unit_system)
        if parsed:
            annotations.extend(parsed)
            ann_counter += len(parsed)

    # Associate related annotations by spatial proximity
    annotations = _associate_nearby_annotations(annotations)

    return annotations


def _convert_value(value: float, unit_system: str) -> float:
    """Convert a dimension value to mm if needed."""
    if unit_system == "inch":
        return round(value * INCH_TO_MM, 4)
    return value


def _is_gdt_false_positive(text: str, value: float, unit_system: str) -> bool:
    """Check if a diameter-symbol-prefixed value is actually a GD&T tolerance zone.

    GD&T tolerance zones use the diameter symbol to indicate cylindrical zones
    (e.g., Ø.015, ⌀.020) but are very small values, not actual hole diameters.
    """
    # Only applies when text starts with or contains a diameter symbol
    has_dia_sym = bool(re.search(r"[\u2300\u00d8\u00f8\u2205\ufffd]", text))
    if not has_dia_sym:
        return False

    # Check if value is very small (likely GD&T tolerance, not a hole diameter)
    threshold = GDT_MAX_INCH_VALUE if unit_system == "inch" else GDT_MAX_METRIC_VALUE
    if value < threshold:
        # Diameter callouts typically have a multiplier (4X) or bilateral tolerance (+.003/-.001)
        has_multiplier = bool(pat.MULTIPLIER.search(text))
        has_bilateral_tol = bool(re.search(r"[+]\s*[\d.]", text))
        if not has_multiplier and not has_bilateral_tol:
            return True

    return False


def _parse_combined_callout(
    text: str, bbox: BoundingBox, source: str, counter: int, unit_system: str = "metric"
) -> list[PDFAnnotation]:
    """Try to parse text as a combined hole callout."""
    results = []

    # A counterbore or countersink carries a type and a second diameter that
    # the generic pattern cannot express, so leave those to the specific ones.
    if (
        pat.COUNTERBORE_SYMBOL.search(text)
        or pat.COUNTERBORE_TEXT.search(text)
        or pat.COUNTERSINK_SYMBOL.search(text)
        or pat.COUNTERSINK_TEXT.search(text)
    ):
        return results

    match = pat.HOLE_CALLOUT_COMBINED.search(text)
    if not match:
        return results

    groups = match.groups()
    multiplier_str, thread_d, thread_pitch, diameter, tol_class, depth, thru = groups

    multiplier = int(multiplier_str) if multiplier_str else 1
    # The pattern only captures a literal THRU; THROUGH_HOLE also covers
    # "THRU ALL" and the German markers.
    is_through = bool(thru) or bool(pat.THROUGH_HOLE.search(text))

    if thread_d:
        # Thread callout — thread designations are always metric (M10 = 10mm)
        counter += 1
        nom_d = float(thread_d.replace(",", "."))
        thread_spec = f"M{thread_d.replace(',', '.')}"
        if thread_pitch:
            thread_spec += f"x{thread_pitch.replace(',', '.')}"
        parsed = {
            "nominal_diameter": nom_d,
            "thread_type": "metric",
            "thread_spec": thread_spec,
            "standard": "ISO_metric",
        }
        if thread_pitch:
            parsed["pitch"] = float(thread_pitch.replace(",", "."))
        if tol_class:
            parsed["tolerance_class"] = tol_class

        results.append(
            PDFAnnotation(
                id=f"ann_{counter:03d}",
                raw_text=text,
                annotation_type=AnnotationType.THREAD,
                parsed=parsed,
                bbox=bbox,
                source=source,
                multiplier=multiplier,
                is_through=is_through,
                unit_system=unit_system,
            )
        )

    elif diameter:
        raw_value = float(diameter.replace(",", "."))

        # GD&T disambiguation: skip small \ufffd-prefixed values
        if _is_gdt_false_positive(text, raw_value, unit_system):
            return results

        # Diameter callout — convert to mm if inch drawing
        counter += 1
        converted = _convert_value(raw_value, unit_system)
        parsed = {"value": converted}
        if unit_system == "inch":
            parsed["original_inch"] = raw_value
        if tol_class:
            parsed["tolerance_class"] = tol_class

        results.append(
            PDFAnnotation(
                id=f"ann_{counter:03d}",
                raw_text=text,
                annotation_type=AnnotationType.DIAMETER,
                parsed=parsed,
                bbox=bbox,
                source=source,
                multiplier=multiplier,
                is_through=is_through,
                unit_system=unit_system,
            )
        )

    if depth:
        counter += 1
        raw_depth = float(depth.replace(",", "."))
        converted_depth = _convert_value(raw_depth, unit_system)
        depth_parsed = {"value": converted_depth}
        if unit_system == "inch":
            depth_parsed["original_inch"] = raw_depth
        results.append(
            PDFAnnotation(
                id=f"ann_{counter:03d}",
                raw_text=text,
                annotation_type=AnnotationType.DEPTH,
                parsed=depth_parsed,
                bbox=bbox,
                source=source,
                unit_system=unit_system,
            )
        )

    return results


def _parse_individual_patterns(
    text: str, bbox: BoundingBox, source: str, counter: int, unit_system: str = "metric"
) -> list[PDFAnnotation]:
    """Try individual regex patterns on the text."""
    results = []

    # Thread patterns — metric
    match = pat.THREAD_METRIC.search(text)
    if match:
        counter += 1
        nom_d = float(match.group(1).replace(",", "."))
        thread_spec = f"M{match.group(1).replace(',', '.')}"
        if match.group(2):
            thread_spec += f"x{match.group(2).replace(',', '.')}"
        parsed = {
            "nominal_diameter": nom_d,
            "thread_type": "metric",
            "thread_spec": thread_spec,
            "standard": "ISO_metric",
        }
        if match.group(2):
            parsed["pitch"] = float(match.group(2).replace(",", "."))
        if match.group(3):
            parsed["tolerance_class"] = match.group(3)

        # Check for multiplier prefix (try numeric "4X" first, then text "4 holes")
        mult_match = pat.MULTIPLIER.search(text[: match.start()])
        if not mult_match:
            mult_match = pat.MULTIPLIER_TEXT.search(text[: match.start()])
        multiplier = int(mult_match.group(1)) if mult_match else 1

        # Check for through-hole (including THRU ALL)
        is_through = bool(pat.THROUGH_HOLE.search(text))

        results.append(
            PDFAnnotation(
                id=f"ann_{counter:03d}",
                raw_text=text,
                annotation_type=AnnotationType.THREAD,
                parsed=parsed,
                bbox=bbox,
                source=source,
                multiplier=multiplier,
                is_through=is_through,
                unit_system=unit_system,
            )
        )
        return results

    # Thread patterns — UTS (Unified: UNC, UNF, UNEF)
    match = pat.THREAD_UNIFIED.search(text)
    if match:
        counter += 1
        size_str = match.group(1).strip()  # e.g., "1/4", "#10", "3/8"
        tpi = int(match.group(2))  # threads per inch
        series = match.group(3).upper()  # UNC, UNF, etc.
        thread_class = match.group(4)  # e.g., "2B" (optional)

        # Convert size to decimal inches then to mm
        if "/" in size_str:
            parts = size_str.split("/")
            nom_inch = float(parts[0]) / float(parts[1])
        elif size_str.startswith("#") or (size_str.isdigit() and tpi >= 24):
            # Number series #0 to #12: major diameter 0.060 + 0.013 per size.
            # Without the "#", the TPI separates them: no numbered screw is
            # coarser than 24, and no whole-inch UTS thread is finer than 20.
            num = int(size_str.lstrip("#"))
            nom_inch = 0.060 + num * 0.013
        else:
            nom_inch = float(size_str)

        nom_d_mm = round(nom_inch * INCH_TO_MM, 4)
        thread_spec_str = f"{size_str}-{tpi} {series}"
        if thread_class:
            thread_spec_str += f"-{thread_class}"

        parsed = {
            "nominal_diameter": nom_d_mm,
            "thread_type": "unified",
            "thread_spec": thread_spec_str,
            "standard": "UTS",
            "tpi": tpi,
            "series": series,
            "original_inch": nom_inch,
        }
        if thread_class:
            parsed["tolerance_class"] = thread_class

        mult_match = pat.MULTIPLIER.search(text[: match.start()])
        if not mult_match:
            mult_match = pat.MULTIPLIER_TEXT.search(text[: match.start()])
        multiplier = int(mult_match.group(1)) if mult_match else 1
        is_through = bool(pat.THROUGH_HOLE.search(text))

        results.append(
            PDFAnnotation(
                id=f"ann_{counter:03d}",
                raw_text=text,
                annotation_type=AnnotationType.THREAD,
                parsed=parsed,
                bbox=bbox,
                source=source,
                multiplier=multiplier,
                is_through=is_through,
                unit_system="inch",
            )
        )
        return results

    # Bare decimal with multiplier (e.g., "4X .500") — inch drawings only
    # This must come BEFORE regular diameter patterns to capture the multiplier
    if unit_system == "inch":
        match = pat.DIAMETER_BARE_WITH_MULT.search(text)
        if match:
            multiplier_val = int(match.group(1))
            raw_value = float(match.group(2).replace(",", "."))

            # Skip tiny values (tolerance zones, not diameters)
            if raw_value >= 0.1 and raw_value <= MAX_HOLE_DIAMETER_INCH:
                counter += 1
                converted = _convert_value(raw_value, unit_system)
                parsed = {"value": converted, "original_inch": raw_value}
                is_through = bool(pat.THROUGH_HOLE.search(text))

                results.append(
                    PDFAnnotation(
                        id=f"ann_{counter:03d}",
                        raw_text=text,
                        annotation_type=AnnotationType.DIAMETER,
                        parsed=parsed,
                        bbox=bbox,
                        source=source,
                        multiplier=multiplier_val,
                        is_through=is_through,
                        unit_system=unit_system,
                    )
                )
                return results

    # Diameter patterns (including decimal tolerance pattern for FTC drawings).
    # The counterbore and countersink blocks below are more specific, so a
    # callout carrying one of those markers skips the generic diameter path.
    is_stepped = bool(
        pat.COUNTERBORE_SYMBOL.search(text)
        or pat.COUNTERBORE_TEXT.search(text)
        or pat.COUNTERSINK_SYMBOL.search(text)
        or pat.COUNTERSINK_TEXT.search(text)
    )
    for dp in (
        [] if is_stepped else [pat.DIAMETER_SYMBOL, pat.DIAMETER_TEXT, pat.DIAMETER_DECIMAL_TOL]
    ):
        match = dp.search(text)
        if match:
            raw_value = float(match.group(1).replace(",", "."))

            # GD&T disambiguation: skip small \ufffd-prefixed values
            if _is_gdt_false_positive(text, raw_value, unit_system):
                continue

            # Skip very small values that are likely tolerances, not diameters
            if dp is pat.DIAMETER_DECIMAL_TOL and raw_value < 0.5 and unit_system == "inch":
                continue
            if dp is pat.DIAMETER_DECIMAL_TOL and raw_value < 1.0 and unit_system == "metric":
                continue

            # Skip implausibly large values (overall part dimensions, not holes)
            if dp is pat.DIAMETER_DECIMAL_TOL:
                max_d = MAX_HOLE_DIAMETER_INCH if unit_system == "inch" else MAX_HOLE_DIAMETER_MM
                if raw_value > max_d:
                    continue

            counter += 1
            converted = _convert_value(raw_value, unit_system)
            parsed = {"value": converted}
            if unit_system == "inch":
                parsed["original_inch"] = raw_value

            # Check for tolerance class after diameter
            tol_match = pat.TOLERANCE_CLASS.search(text[match.end() :])
            if tol_match:
                parsed["tolerance_class"] = tol_match.group(0)

            # Check for multiplier (try numeric "4X" first, then text "4 holes"/"4 PL")
            mult_match = pat.MULTIPLIER.search(text[: match.start()])
            if not mult_match:
                mult_match = pat.MULTIPLIER_TEXT.search(text[: match.start()])
            multiplier = int(mult_match.group(1)) if mult_match else 1

            is_through = bool(pat.THROUGH_HOLE.search(text))

            results.append(
                PDFAnnotation(
                    id=f"ann_{counter:03d}",
                    raw_text=text,
                    annotation_type=AnnotationType.DIAMETER,
                    parsed=parsed,
                    bbox=bbox,
                    source=source,
                    multiplier=multiplier,
                    is_through=is_through,
                    unit_system=unit_system,
                )
            )
            return results

    # Depth patterns. A stepped callout carries its own depth, so it is not
    # reduced to a bare depth annotation here.
    for dp in [] if is_stepped else [pat.DEPTH_SYMBOL, pat.DEPTH_TEXT]:
        match = dp.search(text)
        if match:
            counter += 1
            raw_value = float(match.group(1).replace(",", "."))
            converted = _convert_value(raw_value, unit_system)
            depth_parsed = {"value": converted}
            if unit_system == "inch":
                depth_parsed["original_inch"] = raw_value
            results.append(
                PDFAnnotation(
                    id=f"ann_{counter:03d}",
                    raw_text=text,
                    annotation_type=AnnotationType.DEPTH,
                    parsed=depth_parsed,
                    bbox=bbox,
                    source=source,
                    unit_system=unit_system,
                )
            )
            return results

    # Through-hole only. "Ø8 THRU CBORE Ø18" is a stepped hole, handled below.
    if not is_stepped and pat.THROUGH_HOLE.search(text):
        counter += 1
        results.append(
            PDFAnnotation(
                id=f"ann_{counter:03d}",
                raw_text=text,
                annotation_type=AnnotationType.DEPTH,
                parsed={"through": True},
                bbox=bbox,
                source=source,
                is_through=True,
                unit_system=unit_system,
            )
        )
        return results

    # Counterbore
    for cbp in [pat.COUNTERBORE_SYMBOL, pat.COUNTERBORE_TEXT]:
        match = cbp.search(text)
        if match:
            counter += 1
            raw_value = float(match.group(1).replace(",", "."))
            converted = _convert_value(raw_value, unit_system)
            cb_parsed = {"diameter": converted}
            if unit_system == "inch":
                cb_parsed["original_inch"] = raw_value
            depth_match = pat.DEPTH_SYMBOL.search(text) or pat.DEPTH_TEXT.search(text)
            if depth_match:
                cb_parsed["depth"] = _convert_value(
                    float(depth_match.group(1).replace(",", ".")), unit_system
                )
            multiplier, is_through = _stepped_hole_context(
                text, match.start(), cb_parsed, unit_system
            )
            results.append(
                PDFAnnotation(
                    id=f"ann_{counter:03d}",
                    raw_text=text,
                    annotation_type=AnnotationType.COUNTERBORE,
                    parsed=cb_parsed,
                    bbox=bbox,
                    source=source,
                    multiplier=multiplier,
                    is_through=is_through,
                    unit_system=unit_system,
                )
            )
            return results

    # Countersink
    for csp in [pat.COUNTERSINK_SYMBOL, pat.COUNTERSINK_TEXT]:
        match = csp.search(text)
        if match:
            counter += 1
            raw_value = float(match.group(1).replace(",", "."))
            converted = _convert_value(raw_value, unit_system)
            cs_parsed = {"diameter": converted}
            if unit_system == "inch":
                cs_parsed["original_inch"] = raw_value
            multiplier, is_through = _stepped_hole_context(
                text, match.start(), cs_parsed, unit_system
            )
            results.append(
                PDFAnnotation(
                    id=f"ann_{counter:03d}",
                    raw_text=text,
                    annotation_type=AnnotationType.COUNTERSINK,
                    parsed=cs_parsed,
                    bbox=bbox,
                    source=source,
                    multiplier=multiplier,
                    is_through=is_through,
                    unit_system=unit_system,
                )
            )
            return results

    # Fit specification
    match = pat.FIT_SPEC.search(text)
    if match:
        counter += 1
        results.append(
            PDFAnnotation(
                id=f"ann_{counter:03d}",
                raw_text=text,
                annotation_type=AnnotationType.FIT,
                parsed={
                    "hole_tolerance": match.group(1),
                    "shaft_tolerance": match.group(2),
                },
                bbox=bbox,
                source=source,
                unit_system=unit_system,
            )
        )
        return results

    # Surface roughness
    match = pat.SURFACE_ROUGHNESS.search(text)
    if match:
        counter += 1
        results.append(
            PDFAnnotation(
                id=f"ann_{counter:03d}",
                raw_text=text,
                annotation_type=AnnotationType.SURFACE_FINISH,
                parsed={
                    "parameter": match.group(0).split("=")[0].split("<")[0].split(">")[0].strip(),
                    "value": float(match.group(1).replace(",", ".")),
                },
                bbox=bbox,
                source=source,
                unit_system=unit_system,
            )
        )
        return results

    return results


def _stepped_hole_context(
    text: str, marker_start: int, parsed: dict, unit_system: str
) -> tuple[int, bool]:
    """Read what a counterbore/countersink callout says about the hole itself.

    In "4X Ø8 THRU CBORE Ø18" the count, the bore diameter and THRU sit in
    front of the marker. The bore diameter is stored as ``hole_diameter``.
    """
    prefix = text[:marker_start]

    mult_match = pat.MULTIPLIER.search(prefix) or pat.MULTIPLIER_TEXT.search(prefix)
    multiplier = int(mult_match.group(1)) if mult_match else 1

    bore = pat.DIAMETER_SYMBOL.search(prefix)
    if bore:
        raw = float(bore.group(1).replace(",", "."))
        parsed["hole_diameter"] = _convert_value(raw, unit_system)
        if unit_system == "inch":
            parsed["original_inch_hole_diameter"] = raw

    return multiplier, bool(pat.THROUGH_HOLE.search(text))


def _associate_nearby_annotations(
    annotations: list[PDFAnnotation], proximity_threshold: float = 50.0
) -> list[PDFAnnotation]:
    """Associate related annotations based on spatial proximity on the same page.

    E.g., a depth annotation near a thread annotation should be linked.
    """
    for i, ann_i in enumerate(annotations):
        for j, ann_j in enumerate(annotations):
            if i >= j:
                continue
            if ann_i.bbox.page != ann_j.bbox.page:
                continue

            # Check vertical proximity (annotations in same callout are usually stacked)
            vertical_dist = abs(ann_i.bbox.y1 - ann_j.bbox.y0)
            horizontal_overlap = min(ann_i.bbox.x1, ann_j.bbox.x1) - max(
                ann_i.bbox.x0, ann_j.bbox.x0
            )

            if vertical_dist < proximity_threshold and horizontal_overlap > 0:
                # These annotations are likely part of the same callout
                if ann_j.id not in ann_i.associated_annotations:
                    ann_i.associated_annotations.append(ann_j.id)
                if ann_i.id not in ann_j.associated_annotations:
                    ann_j.associated_annotations.append(ann_i.id)

    return annotations
