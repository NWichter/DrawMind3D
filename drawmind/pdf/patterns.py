"""Regex patterns for engineering drawing annotations."""

import re

# Common numeric value pattern that handles both metric (10.5) and inch (.250) formats
_NUM = r'(\d+(?:[.,]\d+)?|\.\d+)'  # matches: 10, 10.5, .250, 0.5

# === Thread Patterns ===

# Metric thread: M10, M10x1.5, M10x1.5-6H, M10-6H
THREAD_METRIC = re.compile(
    r'(?<![A-Za-z])'                    # negative lookbehind: no letter before M (prevents "Material", "Max")
    r'M(\d+(?:[.,]\d+)?)'              # M + nominal diameter
    r'(?:\s*[xX\u00d7]\s*'             # pitch separator (x, X, or multiplication sign)
    r'(\d+(?:[.,]\d+)?))?'             # pitch value
    r'(?:\s*[-\u2013]\s*'              # tolerance separator
    r'(\d[A-Za-z]\d?[A-Za-z]?))?',     # tolerance class (e.g., 6H, 6g, 4H5H)
)

# UNC/UNF thread: 1/4-20 UNC, 3/8-16 UNC-2B
THREAD_UNIFIED = re.compile(
    r'(\d+/?\d*)\s*[-\u2013]\s*'       # size (fraction or number)
    r'(\d+)\s*'                         # TPI
    r'(UN[CFE]S?)'                      # thread series
    r'(?:\s*[-\u2013]\s*'
    r'(\d[AB]))?',                      # class (optional)
    re.IGNORECASE
)

# === Diameter Patterns ===

# Diameter with various symbols: ⌀20, Ø20, ø20, ∅20, ⌀.250 (inch)
# \ufffd included because engineering PDFs often use custom fonts where
# the diameter symbol is extracted as a Unicode replacement character.
DIAMETER_SYMBOL = re.compile(
    r'[\u2300\u00d8\u00f8\u2205\ufffd]'  # diameter symbols (⌀, Ø, ø, ∅, replacement char)
    r'\s*' + _NUM,
)

# Diameter with text
DIAMETER_TEXT = re.compile(
    r'(?:diam\.?|diameter)\s*' + _NUM,
    re.IGNORECASE
)

# Decimal dimension with bilateral tolerance (no symbol, common in FTC drawings)
# e.g., "0.234 +/-.008", ".500 +.003/-.001"
DIAMETER_DECIMAL_TOL = re.compile(
    r'(?:^|(?<=\s))'                       # start or after whitespace
    + _NUM +                                # decimal value
    r'\s*(?:[\u00b1][.\d]+|'               # ±tol
    r'[+]\s*[.\d]+\s*/?\s*[-\u2013]\s*[.\d]+)',  # +upper/-lower
)

# Bare decimal dimension with multiplier prefix (no symbol, no tolerance)
# Captures inch values like "4X .500", "2X .750 THRU" where the multiplier
# strongly implies a hole callout even without a diameter symbol
DIAMETER_BARE_WITH_MULT = re.compile(
    r'(\d+)\s*[xX\u00d7]\s+'              # multiplier prefix: "4X "
    + _NUM,                                 # decimal value: ".500", "0.750"
)

# === Depth Patterns ===

# Depth with symbol: ↧15, ⌴15
DEPTH_SYMBOL = re.compile(
    r'[\u21a7\u2334]'                   # depth symbols (↧, ⌴)
    r'\s*' + _NUM,
)

# Depth with text
DEPTH_TEXT = re.compile(
    r'(?:depth|tiefe|tief|deep)\s*'
    r'[=:]?\s*' + _NUM,
    re.IGNORECASE
)

# Through-hole indicator (THRU ALL is ASME standard for "through entire part")
THROUGH_HOLE = re.compile(
    r'\b(THRU\s*ALL|THRU|through|durchgehend|durchgangsloch|durchgangsbohrung)\b',
    re.IGNORECASE
)

# === Counterbore / Countersink ===

# Counterbore symbol: ⌳
COUNTERBORE_SYMBOL = re.compile(
    r'[\u2333]'                          # ⌳
    r'\s*[\u2300\u00d8\u00f8\u2205\ufffd]?' # optional diameter symbol (incl. replacement char)
    r'\s*' + _NUM,
)

# Countersink symbol: ⌵
COUNTERSINK_SYMBOL = re.compile(
    r'[\u2335]'                          # ⌵
    r'\s*' + _NUM
    + r'(?:\s*[\u00b0\u00ba])?',         # optional degree symbol
)

# Counterbore text
COUNTERBORE_TEXT = re.compile(
    r'(?:counterbore|cbore|c[\'\u2019]bore|senkung)\s*'
    r'[\u2300\u00d8\ufffd]?\s*' + _NUM,
    re.IGNORECASE
)

# Countersink text
COUNTERSINK_TEXT = re.compile(
    r'(?:countersink|csink|c[\'\u2019]sink|ansenkung)\s*' + _NUM,
    re.IGNORECASE
)

# === Tolerance / Fit Patterns ===

# Tolerance class: H7, h6, G7, f6, etc.
TOLERANCE_CLASS = re.compile(
    r'\b([A-HJ-NP-Za-hj-np-z])(\d{1,2})\b'
)

# Fit specification: H7/h6, H7/g6
FIT_SPEC = re.compile(
    r'([A-Z]\d{1,2})\s*/\s*([a-z]\d{1,2})'
)

# Plus/minus tolerance: ±0.02, +0.05/-0.03
TOLERANCE_SYMMETRIC = re.compile(
    r'[\u00b1]\s*' + _NUM               # ±value
)

TOLERANCE_ASYMMETRIC = re.compile(
    r'[+]\s*' + _NUM + r'\s*'           # +upper
    r'/?\s*[-\u2013]\s*' + _NUM          # -lower
)

# === Multiplier Pattern ===

# Count prefix: 4x, 4X, 4×, "4 holes", "4 Bohrungen"
# Trailing space is optional to support "4xM8" (European style, no space)
MULTIPLIER = re.compile(
    r'(\d+)\s*[xX\u00d7]\s?',
)

MULTIPLIER_TEXT = re.compile(
    r'(\d+)\s*(?:holes?|Bohrungen?|Gewinde|tapped|PLACES?|PL)\b',
    re.IGNORECASE
)

# === GD&T Symbols ===

# Common GD&T symbols in Unicode
GDT_SYMBOLS = re.compile(
    r'[\u23e4\u23e5\u25cb\u232d\u2312\u2313'
    r'\u23ca\u2220\u2afd\u232f\u2316\u25ce\u2197\u2330]'
)

# === Surface Finish ===

SURFACE_ROUGHNESS = re.compile(
    r'(?:Ra|Rz|Rq)\s*[=<>]?\s*' + _NUM + r'\s*'
    r'(?:\u00b5m|um|micron)?',
    re.IGNORECASE
)

# === Combined hole callout (common in drawings) ===
# e.g., "⌀8.5 ↧15" or "M10x1.5 THRU" or "⌀10H7 ↧20" or "2X ⌀.250 +.003/-.001 THRU"
HOLE_CALLOUT_COMBINED = re.compile(
    r'(?:(\d+)\s*[xX\u00d7]\s+)?'       # optional multiplier
    r'(?:M(\d+(?:[.,]\d+)?)'             # thread designation
    r'(?:\s*[xX\u00d7]\s*(\d+(?:[.,]\d+)?))?'  # thread pitch
    r'|[\u2300\u00d8\u00f8\u2205\ufffd]\s*' # or diameter symbol (incl. replacement char)
    + _NUM + r')'                         # diameter value (supports .250)
    r'(?:\s*[-\u2013]?\s*'               # optional dash/en-dash separator
    r'(\d[A-Za-z]\d?[A-Za-z]?'           # thread tolerance (6H, 6g, 4H5H)
    r'|[A-Z]\d{1,2}))?'                  # or fit tolerance (H7, G6)
    r'(?:\s+[+\u00b1][\d.]+(?:\s*/?\s*[-\u2013]\s*[\d.]+)?)?' # optional bilateral tolerance (skip over)
    r'(?:\s*(?:[\u21a7\u2334]|depth)\s*' + _NUM + r')?' # optional depth
    r'(?:\s*(THRU))?',                    # optional through
    re.IGNORECASE
)

# All patterns grouped by annotation type
ALL_PATTERNS = {
    "thread": [THREAD_METRIC, THREAD_UNIFIED],
    "diameter": [DIAMETER_SYMBOL, DIAMETER_TEXT, DIAMETER_DECIMAL_TOL, DIAMETER_BARE_WITH_MULT],
    "depth": [DEPTH_SYMBOL, DEPTH_TEXT],
    "through": [THROUGH_HOLE],
    "counterbore": [COUNTERBORE_SYMBOL, COUNTERBORE_TEXT],
    "countersink": [COUNTERSINK_SYMBOL, COUNTERSINK_TEXT],
    "tolerance": [TOLERANCE_CLASS, FIT_SPEC, TOLERANCE_SYMMETRIC, TOLERANCE_ASYMMETRIC],
    "multiplier": [MULTIPLIER, MULTIPLIER_TEXT],
    "surface_finish": [SURFACE_ROUGHNESS],
    "gdt": [GDT_SYMBOLS],
    "hole_callout": [HOLE_CALLOUT_COMBINED],
}
