"""Prompt templates for LLM-assisted annotation extraction and matching."""

SYSTEM_ENGINEERING = (
    "You are an expert mechanical engineer specializing in technical drawings, "
    "GD&T (Geometric Dimensioning and Tolerancing), and ISO standards for "
    "threaded fasteners and precision holes. You analyze engineering drawings "
    "with extreme accuracy."
)

VISION_EXTRACT_PROMPT = """\
Analyze this engineering/technical drawing page. Extract ALL hole-related annotations you can find.

CRITICAL DISTINCTIONS:
- **Diameter callouts** (hole sizes): ⌀.250, 4X ⌀.250 +.003/-.001, ⌀8.5 — these specify actual hole diameters
- **GD&T tolerance zones**: ⌀.015, ⌀.020 followed by datum references (A, B, C) in feature control frames — these are geometric tolerance values, NOT hole diameters. Do NOT include GD&T tolerance zones.
- **Part dimensions**: 2.500, 1.750, 4.000 standing alone as overall sizes (length, width, height) — these are NOT hole diameters. Do NOT include overall part envelope dimensions.
- **Leader lines**: Follow leader lines from annotation text to the feature they reference. The same hole may be shown in multiple views.

Extract these annotation types:
1. **Thread callouts**
   - Metric: M10×1.5, M8-6H, M12x1.25-6H
   - Imperial/Unified: 1/4-20 UNC, 3/8-16 UNC-2B, #10-32 UNF, #6-32 UNC
   - IMPORTANT: For inch drawings, "1/4-20 UNC" = 1/4 inch diameter, 20 TPI, Unified Coarse
   - Number sizes: #0 through #12 (e.g., #10-32 UNF = screw size 10, 32 TPI, Unified Fine)
2. **Diameter dimensions**
   - Metric: Ø20, ⌀8.5
   - Inch: ⌀.250, .438 DIA, Ø.500 — decimal values often start with decimal point (no leading zero)
   - Values with bilateral tolerances: .234 +.003/-.001, .500 ±.002
   - Must be actual hole sizes, NOT GD&T tolerances or overall part dimensions
3. **Depth callouts** (↧15, depth .425, .500 DEEP, .750 DP)
4. **Through-hole indicators** (THRU, through, THRU ALL)
5. **Counterbore specs** (⌳⌀18 ↧8, CBORE .500 DP .250, counterbore diameter and depth)
6. **Countersink specs** (⌵⌀12×90°, CSINK 82°, CSK .500 X 82°)
7. **Tolerance classes** (H7, g6, H7/g6, 6H)
8. **Count prefixes** (4X, 6×, "4 holes", "4 PLACES", "4 PL")

UNIT AWARENESS:
- Inch drawings: .250, .438, .500, 1.250 (often WITHOUT leading zero)
- Metric drawings: 8.5, 10.0, 20 mm
- Report values exactly as shown — do NOT convert units
- Check title block for INCHES / MILLIMETERS declaration
- Fractional inch threads: report text as fraction, parsed as decimal (1/4 → 0.25)

COMPLETENESS: For each hole callout, capture the COMPLETE specification:
- Diameter or thread designation
- THRU or specific depth
- Count prefix (4X, 6×, "4 PL")
- Tolerance class or fit (H7, 6H)
- Bilateral tolerances (+.003/-.001)
- Counterbore/countersink if combined (e.g., ⌀.250 THRU ⌳⌀.438 ↧.250)

For each annotation found, return a JSON array with:
- "text": exact text from drawing
- "type": one of "thread", "diameter", "depth", "counterbore", "countersink", "tolerance", "through"
- "parsed": structured data:
  - Metric threads: {{"nominal_diameter": 10, "pitch": 1.5, "tolerance_class": "6H", "depth": 15.0, "through": false}}
  - Inch threads: {{"nominal_diameter": 0.25, "pitch": 0.05, "thread_spec": "1/4-20 UNC", "through": true}}
  - Diameters: {{"value": 0.250, "depth": 0.500, "through": false}}
  - Through-holes: {{"through": true}}
  - Counterbores: {{"diameter": 0.438, "depth": 0.250}}
  - Countersinks: {{"diameter": 0.500, "angle": 82}}
  - Always include "depth" or "through" when visible
- "bbox_percent": {{"x": 0-100, "y": 0-100, "w": width%, "h": height%}} relative to page
- "confidence": 0.0-1.0
- "multiplier": count prefix value (e.g., 4 for "4X"), otherwise 1

Return the JSON array only."""

DISAMBIGUATE_PROMPT = """\
You are matching engineering drawing annotations to 3D CAD features (cylindrical holes).

**Annotation from drawing:**
Text: "{annotation_text}"
Type: {annotation_type}
Parsed: {parsed_data}
Location on page: {bbox}

**Candidate 3D features:**
{candidates_json}

Which 3D feature does this annotation most likely describe? Consider:
1. Diameter match (for threads, consider major/pitch/minor/drill diameters)
2. Depth match
3. Hole type compatibility
4. Position plausibility

Return JSON with:
- "feature_id": the ID of the best matching feature
- "confidence": your confidence 0.0-1.0
- "reasoning": brief explanation of your choice"""

PARSE_ANNOTATION_PROMPT = """\
Parse this engineering annotation text into structured data:

Text: "{text}"

Identify:
- type: thread / diameter / depth / counterbore / countersink / tolerance / fit / surface_finish
- For threads: nominal_diameter (mm), pitch (mm), tolerance_class
- For diameters: value (mm), tolerance_class
- For depths: value (mm), or "through" if it indicates a through-hole
- For fits: hole_tolerance, shaft_tolerance
- multiplier: if prefixed with "4x" etc.

Return JSON with the parsed fields."""
