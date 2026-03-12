"""Prompt templates for LLM-assisted annotation extraction and matching."""

SYSTEM_ENGINEERING = (
    "You are an expert mechanical engineer specializing in technical drawings, "
    "GD&T (Geometric Dimensioning and Tolerancing), and ISO standards for "
    "threaded fasteners and precision holes. You analyze engineering drawings "
    "with extreme accuracy."
)

VISION_EXTRACT_PROMPT = """\
Analyze this engineering/technical drawing page. Extract ALL hole-related annotations you can find.

IMPORTANT DISTINCTIONS:
- **Diameter callouts** (hole sizes): ⌀.250, 4X ⌀.250 +.003/-.001, ⌀8.5 — these specify actual hole diameters
- **GD&T tolerance zones**: ⌀.015, ⌀.020 followed by datum references (A, B, C) — these are geometric tolerance values, NOT hole diameters. Do NOT include GD&T tolerance zones as diameter annotations.

Extract these annotation types:
1. **Thread callouts**
   - Metric: M10×1.5, M8-6H, M12x1.25-6H
   - Imperial/Unified: 1/4-20 UNC, 3/8-16 UNC-2B, #10-32 UNF
   - IMPORTANT: For inch drawings, thread callouts like "1/4-20 UNC" mean 1/4 inch diameter, 20 threads per inch, Unified Coarse
2. **Diameter dimensions**
   - Metric: Ø20, ⌀8.5
   - Inch: ⌀.250, .438 DIA, Ø.500 — decimal inch values often START with a decimal point (no leading zero)
   - Must be actual hole sizes, NOT GD&T tolerances
3. **Depth callouts** (↧15, depth .425, .500 DEEP, .750 DP)
4. **Through-hole indicators** (THRU, through, THRU ALL)
5. **Counterbore specs** (⌳⌀18 ↧8, CBORE .500 DP .250)
6. **Countersink specs** (⌵⌀12×90°, CSINK 82°, CSK .500 X 82°)
7. **Tolerance classes** (H7, g6, H7/g6, 6H)
8. **Count prefixes** (4x, 6×, "4 holes", "4 PLACES", "4 PL")

UNIT AWARENESS:
- Inch drawings use decimal inches: .250, .438, .500, 1.250 (often WITHOUT leading zero)
- Metric drawings use mm: 8.5, 10.0, 20
- Report ALL values exactly as shown in the drawing — do NOT convert units
- Pay attention to the title block for unit declarations (INCHES, MILLIMETERS)
- Fractional inch threads (1/4, 3/8, 1/2) should be reported as fractions in the text but as decimal in parsed values (1/4 = 0.25)

IMPORTANT: For each hole callout, try to capture the COMPLETE specification including:
- The diameter or thread designation
- Whether it goes THROUGH or has a specific depth
- Any count prefix (4X, 6×, "4 PL")
- Any tolerance class or fit specification
- Any bilateral tolerances (+.003/-.001)

For each annotation found, return a JSON array with:
- "text": the exact text as it appears in the drawing
- "type": one of "thread", "diameter", "depth", "counterbore", "countersink", "tolerance", "through"
- "parsed": structured interpretation. Include ALL available fields:
  - For metric threads: {{"nominal_diameter": 10, "pitch": 1.5, "tolerance_class": "6H", "depth": 15.0, "through": false}}
  - For inch threads: {{"nominal_diameter": 0.25, "pitch": 0.05, "thread_spec": "1/4-20 UNC", "through": true}}
  - For diameters: {{"value": 0.250, "depth": 0.500, "through": false}}
  - For through-holes: {{"through": true}}
  - For counterbores: {{"diameter": 18, "depth": 8}}
  - Always include "depth" (numeric in drawing units) or "through" (boolean) when visible in the callout
- "bbox_percent": approximate bounding box as {{"x": 0-100, "y": 0-100, "w": width%, "h": height%}} relative to page dimensions
- "confidence": your confidence 0.0-1.0
- "multiplier": count prefix if present (e.g., 4 for "4X"), otherwise 1

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
