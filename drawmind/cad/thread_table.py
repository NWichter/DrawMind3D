"""ISO metric thread reference table for matching thread annotations to diameters."""

from __future__ import annotations

# ISO 261 / ISO 724 Metric Thread Data
# major_d: Major (nominal) diameter in mm
# pitch_coarse: Standard coarse pitch in mm
# pitch_d: Pitch diameter for coarse thread in mm
# minor_d: Minor diameter (internal thread) for coarse thread in mm
# drill_d: Recommended tap drill diameter in mm
ISO_METRIC_THREADS: dict[str, dict] = {
    "M1": {
        "major_d": 1.0,
        "pitch_coarse": 0.25,
        "pitch_d": 0.838,
        "minor_d": 0.693,
        "drill_d": 0.75,
    },
    "M1.2": {
        "major_d": 1.2,
        "pitch_coarse": 0.25,
        "pitch_d": 1.038,
        "minor_d": 0.893,
        "drill_d": 0.95,
    },
    "M1.4": {
        "major_d": 1.4,
        "pitch_coarse": 0.3,
        "pitch_d": 1.205,
        "minor_d": 1.032,
        "drill_d": 1.1,
    },
    "M1.6": {
        "major_d": 1.6,
        "pitch_coarse": 0.35,
        "pitch_d": 1.373,
        "minor_d": 1.171,
        "drill_d": 1.25,
    },
    "M2": {"major_d": 2.0, "pitch_coarse": 0.4, "pitch_d": 1.740, "minor_d": 1.509, "drill_d": 1.6},
    "M2.5": {
        "major_d": 2.5,
        "pitch_coarse": 0.45,
        "pitch_d": 2.208,
        "minor_d": 1.948,
        "drill_d": 2.05,
    },
    "M3": {"major_d": 3.0, "pitch_coarse": 0.5, "pitch_d": 2.675, "minor_d": 2.387, "drill_d": 2.5},
    "M3.5": {
        "major_d": 3.5,
        "pitch_coarse": 0.6,
        "pitch_d": 3.110,
        "minor_d": 2.764,
        "drill_d": 2.9,
    },
    "M4": {"major_d": 4.0, "pitch_coarse": 0.7, "pitch_d": 3.545, "minor_d": 3.141, "drill_d": 3.3},
    "M5": {"major_d": 5.0, "pitch_coarse": 0.8, "pitch_d": 4.480, "minor_d": 4.019, "drill_d": 4.2},
    "M6": {"major_d": 6.0, "pitch_coarse": 1.0, "pitch_d": 5.350, "minor_d": 4.773, "drill_d": 5.0},
    "M7": {"major_d": 7.0, "pitch_coarse": 1.0, "pitch_d": 6.350, "minor_d": 5.773, "drill_d": 6.0},
    "M8": {
        "major_d": 8.0,
        "pitch_coarse": 1.25,
        "pitch_d": 7.188,
        "minor_d": 6.466,
        "drill_d": 6.8,
    },
    "M10": {
        "major_d": 10.0,
        "pitch_coarse": 1.5,
        "pitch_d": 9.026,
        "minor_d": 8.160,
        "drill_d": 8.5,
    },
    "M12": {
        "major_d": 12.0,
        "pitch_coarse": 1.75,
        "pitch_d": 10.863,
        "minor_d": 9.853,
        "drill_d": 10.2,
    },
    "M14": {
        "major_d": 14.0,
        "pitch_coarse": 2.0,
        "pitch_d": 12.701,
        "minor_d": 11.546,
        "drill_d": 12.0,
    },
    "M16": {
        "major_d": 16.0,
        "pitch_coarse": 2.0,
        "pitch_d": 14.701,
        "minor_d": 13.546,
        "drill_d": 14.0,
    },
    "M18": {
        "major_d": 18.0,
        "pitch_coarse": 2.5,
        "pitch_d": 16.376,
        "minor_d": 14.933,
        "drill_d": 15.5,
    },
    "M20": {
        "major_d": 20.0,
        "pitch_coarse": 2.5,
        "pitch_d": 18.376,
        "minor_d": 16.933,
        "drill_d": 17.5,
    },
    "M22": {
        "major_d": 22.0,
        "pitch_coarse": 2.5,
        "pitch_d": 20.376,
        "minor_d": 18.933,
        "drill_d": 19.5,
    },
    "M24": {
        "major_d": 24.0,
        "pitch_coarse": 3.0,
        "pitch_d": 22.051,
        "minor_d": 20.320,
        "drill_d": 21.0,
    },
    "M27": {
        "major_d": 27.0,
        "pitch_coarse": 3.0,
        "pitch_d": 25.051,
        "minor_d": 23.320,
        "drill_d": 24.0,
    },
    "M30": {
        "major_d": 30.0,
        "pitch_coarse": 3.5,
        "pitch_d": 27.727,
        "minor_d": 25.706,
        "drill_d": 26.5,
    },
    "M33": {
        "major_d": 33.0,
        "pitch_coarse": 3.5,
        "pitch_d": 30.727,
        "minor_d": 28.706,
        "drill_d": 29.5,
    },
    "M36": {
        "major_d": 36.0,
        "pitch_coarse": 4.0,
        "pitch_d": 33.402,
        "minor_d": 31.093,
        "drill_d": 32.0,
    },
    "M39": {
        "major_d": 39.0,
        "pitch_coarse": 4.0,
        "pitch_d": 36.402,
        "minor_d": 34.093,
        "drill_d": 35.0,
    },
    "M42": {
        "major_d": 42.0,
        "pitch_coarse": 4.5,
        "pitch_d": 39.077,
        "minor_d": 36.479,
        "drill_d": 37.5,
    },
    "M45": {
        "major_d": 45.0,
        "pitch_coarse": 4.5,
        "pitch_d": 42.077,
        "minor_d": 39.479,
        "drill_d": 40.5,
    },
    "M48": {
        "major_d": 48.0,
        "pitch_coarse": 5.0,
        "pitch_d": 44.752,
        "minor_d": 41.866,
        "drill_d": 43.0,
    },
    "M52": {
        "major_d": 52.0,
        "pitch_coarse": 5.0,
        "pitch_d": 48.752,
        "minor_d": 45.866,
        "drill_d": 47.0,
    },
    "M56": {
        "major_d": 56.0,
        "pitch_coarse": 5.5,
        "pitch_d": 52.428,
        "minor_d": 49.252,
        "drill_d": 50.5,
    },
    "M60": {
        "major_d": 60.0,
        "pitch_coarse": 5.5,
        "pitch_d": 56.428,
        "minor_d": 53.252,
        "drill_d": 54.5,
    },
    "M64": {
        "major_d": 64.0,
        "pitch_coarse": 6.0,
        "pitch_d": 60.103,
        "minor_d": 56.639,
        "drill_d": 58.0,
    },
}

# Common fine-pitch threads (subset)
ISO_METRIC_FINE_PITCHES: dict[str, list[float]] = {
    "M8": [1.0, 0.75],
    "M10": [1.25, 1.0, 0.75],
    "M12": [1.5, 1.25, 1.0],
    "M14": [1.5, 1.25, 1.0],
    "M16": [1.5, 1.0],
    "M18": [2.0, 1.5, 1.0],
    "M20": [2.0, 1.5, 1.0],
    "M22": [2.0, 1.5, 1.0],
    "M24": [2.0, 1.5, 1.0],
    "M27": [2.0, 1.5, 1.0],
    "M30": [2.0, 1.5],
    "M33": [2.0, 1.5],
    "M36": [3.0, 2.0, 1.5],
}


# UTS (Unified Thread Standard) Data — UNC/UNF threads
# Sizes are stored in mm (converted from inches)
# major_d: Nominal (major) diameter in mm
# tpi: Threads per inch
# pitch_d: Pitch diameter in mm
# minor_d: Minor diameter in mm
# drill_d: Tap drill diameter in mm
UTS_THREADS: dict[str, dict] = {
    # Number sizes
    "#0-80 UNF": {"major_d": 1.524, "tpi": 80, "pitch_d": 1.318, "minor_d": 1.181, "drill_d": 1.25},
    "#1-64 UNC": {"major_d": 1.854, "tpi": 64, "pitch_d": 1.599, "minor_d": 1.425, "drill_d": 1.50},
    "#1-72 UNF": {"major_d": 1.854, "tpi": 72, "pitch_d": 1.626, "minor_d": 1.473, "drill_d": 1.55},
    "#2-56 UNC": {"major_d": 2.184, "tpi": 56, "pitch_d": 1.890, "minor_d": 1.695, "drill_d": 1.80},
    "#2-64 UNF": {"major_d": 2.184, "tpi": 64, "pitch_d": 1.929, "minor_d": 1.755, "drill_d": 1.85},
    "#3-48 UNC": {"major_d": 2.515, "tpi": 48, "pitch_d": 2.172, "minor_d": 1.941, "drill_d": 2.10},
    "#4-40 UNC": {"major_d": 2.845, "tpi": 40, "pitch_d": 2.433, "minor_d": 2.157, "drill_d": 2.35},
    "#4-48 UNF": {"major_d": 2.845, "tpi": 48, "pitch_d": 2.502, "minor_d": 2.271, "drill_d": 2.40},
    "#5-40 UNC": {"major_d": 3.175, "tpi": 40, "pitch_d": 2.764, "minor_d": 2.487, "drill_d": 2.65},
    "#5-44 UNF": {"major_d": 3.175, "tpi": 44, "pitch_d": 2.798, "minor_d": 2.540, "drill_d": 2.70},
    "#6-32 UNC": {"major_d": 3.505, "tpi": 32, "pitch_d": 2.990, "minor_d": 2.642, "drill_d": 2.85},
    "#6-40 UNF": {"major_d": 3.505, "tpi": 40, "pitch_d": 3.094, "minor_d": 2.817, "drill_d": 2.95},
    "#8-32 UNC": {"major_d": 4.166, "tpi": 32, "pitch_d": 3.650, "minor_d": 3.302, "drill_d": 3.50},
    "#8-36 UNF": {"major_d": 4.166, "tpi": 36, "pitch_d": 3.708, "minor_d": 3.378, "drill_d": 3.50},
    "#10-24 UNC": {
        "major_d": 4.826,
        "tpi": 24,
        "pitch_d": 4.138,
        "minor_d": 3.683,
        "drill_d": 3.90,
    },
    "#10-32 UNF": {
        "major_d": 4.826,
        "tpi": 32,
        "pitch_d": 4.311,
        "minor_d": 3.962,
        "drill_d": 4.10,
    },
    "#12-24 UNC": {
        "major_d": 5.486,
        "tpi": 24,
        "pitch_d": 4.798,
        "minor_d": 4.344,
        "drill_d": 4.50,
    },
    "#12-28 UNF": {
        "major_d": 5.486,
        "tpi": 28,
        "pitch_d": 4.893,
        "minor_d": 4.470,
        "drill_d": 4.65,
    },
    # Fractional sizes
    "1/4-20 UNC": {
        "major_d": 6.350,
        "tpi": 20,
        "pitch_d": 5.537,
        "minor_d": 4.978,
        "drill_d": 5.10,
    },
    "1/4-28 UNF": {
        "major_d": 6.350,
        "tpi": 28,
        "pitch_d": 5.757,
        "minor_d": 5.334,
        "drill_d": 5.50,
    },
    "5/16-18 UNC": {
        "major_d": 7.938,
        "tpi": 18,
        "pitch_d": 7.034,
        "minor_d": 6.401,
        "drill_d": 6.60,
    },
    "5/16-24 UNF": {
        "major_d": 7.938,
        "tpi": 24,
        "pitch_d": 7.249,
        "minor_d": 6.795,
        "drill_d": 6.90,
    },
    "3/8-16 UNC": {
        "major_d": 9.525,
        "tpi": 16,
        "pitch_d": 8.509,
        "minor_d": 7.798,
        "drill_d": 7.94,
    },
    "3/8-24 UNF": {
        "major_d": 9.525,
        "tpi": 24,
        "pitch_d": 8.836,
        "minor_d": 8.382,
        "drill_d": 8.50,
    },
    "7/16-14 UNC": {
        "major_d": 11.112,
        "tpi": 14,
        "pitch_d": 9.963,
        "minor_d": 9.144,
        "drill_d": 9.35,
    },
    "7/16-20 UNF": {
        "major_d": 11.112,
        "tpi": 20,
        "pitch_d": 10.300,
        "minor_d": 9.740,
        "drill_d": 9.90,
    },
    "1/2-13 UNC": {
        "major_d": 12.700,
        "tpi": 13,
        "pitch_d": 11.430,
        "minor_d": 10.541,
        "drill_d": 10.80,
    },
    "1/2-20 UNF": {
        "major_d": 12.700,
        "tpi": 20,
        "pitch_d": 11.887,
        "minor_d": 11.328,
        "drill_d": 11.50,
    },
    "9/16-12 UNC": {
        "major_d": 14.288,
        "tpi": 12,
        "pitch_d": 12.913,
        "minor_d": 11.938,
        "drill_d": 12.20,
    },
    "9/16-18 UNF": {
        "major_d": 14.288,
        "tpi": 18,
        "pitch_d": 13.384,
        "minor_d": 12.751,
        "drill_d": 12.90,
    },
    "5/8-11 UNC": {
        "major_d": 15.875,
        "tpi": 11,
        "pitch_d": 14.376,
        "minor_d": 13.310,
        "drill_d": 13.50,
    },
    "5/8-18 UNF": {
        "major_d": 15.875,
        "tpi": 18,
        "pitch_d": 14.971,
        "minor_d": 14.338,
        "drill_d": 14.50,
    },
    "3/4-10 UNC": {
        "major_d": 19.050,
        "tpi": 10,
        "pitch_d": 17.399,
        "minor_d": 16.220,
        "drill_d": 16.50,
    },
    "3/4-16 UNF": {
        "major_d": 19.050,
        "tpi": 16,
        "pitch_d": 18.034,
        "minor_d": 17.323,
        "drill_d": 17.50,
    },
    "7/8-9 UNC": {
        "major_d": 22.225,
        "tpi": 9,
        "pitch_d": 20.391,
        "minor_d": 19.063,
        "drill_d": 19.45,
    },
    "7/8-14 UNF": {
        "major_d": 22.225,
        "tpi": 14,
        "pitch_d": 21.076,
        "minor_d": 20.257,
        "drill_d": 20.40,
    },
    "1-8 UNC": {
        "major_d": 25.400,
        "tpi": 8,
        "pitch_d": 23.338,
        "minor_d": 21.843,
        "drill_d": 22.25,
    },
    "1-12 UNF": {
        "major_d": 25.400,
        "tpi": 12,
        "pitch_d": 24.026,
        "minor_d": 23.051,
        "drill_d": 23.25,
    },
}


def get_thread_diameters(thread_designation: str) -> dict[str, float] | None:
    """Look up possible diameters for a thread designation.

    Supports both ISO metric (M10, M10x1.5) and UTS (1/4-20 UNC, #10-32 UNF).

    Args:
        thread_designation: e.g. "M10", "M10x1.5", "M8", "1/4-20 UNC", "#10-32 UNF"

    Returns:
        Dict with major_d, pitch_d, minor_d, drill_d or None if not found
    """
    designation = thread_designation.strip()

    # Check UTS threads first (fractional or number-size format)
    if not designation.upper().startswith("M"):
        # Try exact match in UTS table
        for key, data in UTS_THREADS.items():
            if designation.upper() == key.upper():
                return data
        # Try partial match (e.g., "1/4-20" matches "1/4-20 UNC")
        for key, data in UTS_THREADS.items():
            if key.upper().startswith(designation.upper()):
                return data
        return None

    # ISO metric threads
    base = designation.split("x")[0].split("X")[0].split("-")[0].strip()
    base = base.upper()

    return ISO_METRIC_THREADS.get(base)


def match_thread_to_diameter(
    thread_spec: str,
    measured_diameter: float,
    tolerance_mm: float = 0.5,
    pitch: float | None = None,
) -> tuple[float, str]:
    """Check if a measured diameter matches a thread specification.

    Args:
        thread_spec: Thread designation (e.g., "M10", "M10x1.5")
        measured_diameter: Measured diameter from the 3D model in mm
        tolerance_mm: Acceptable tolerance in mm
        pitch: Optional thread pitch in mm (for fine-pitch matching)

    Returns:
        Tuple of (score 0.0-1.0, matched_diameter_type)
        where matched_diameter_type is "major", "pitch", "minor", or "drill"
    """
    diameters = get_thread_diameters(thread_spec)
    if diameters is None:
        return 0.0, "unknown"

    # Build candidate diameters to check
    candidates = [
        ("major", diameters["major_d"]),
        ("pitch", diameters["pitch_d"]),
        ("minor", diameters["minor_d"]),
        ("drill", diameters["drill_d"]),
    ]

    # If a fine pitch is specified, add the fine-pitch drill diameter
    if pitch is not None:
        fine_drill = get_fine_pitch_drill_diameter(thread_spec, pitch)
        if fine_drill is not None and abs(fine_drill - diameters["drill_d"]) > 0.01:
            candidates.append(("fine_drill", fine_drill))

    best_score = 0.0
    best_type = "none"

    for dtype, dval in candidates:
        diff = abs(measured_diameter - dval)
        if diff <= tolerance_mm:
            # Linear score: 1.0 at exact match, 0.0 at tolerance boundary
            score = 1.0 - (diff / tolerance_mm)
            if score > best_score:
                best_score = score
                best_type = dtype

    return best_score, best_type


def get_fine_pitch_drill_diameter(thread_spec: str, pitch: float) -> float | None:
    """Calculate approximate drill diameter for a fine-pitch thread.

    Uses the simplified ISO 261 formula: drill_d ≈ major_d - pitch.
    For coarse pitch, returns the standard table value.

    Args:
        thread_spec: e.g. "M10", "M10x1.25"
        pitch: Thread pitch in mm

    Returns:
        Drill diameter in mm, or None if thread not found
    """
    diameters = get_thread_diameters(thread_spec)
    if diameters is None:
        return None

    coarse_pitch = diameters.get("pitch_coarse")
    if coarse_pitch and abs(pitch - coarse_pitch) < 0.01:
        return diameters["drill_d"]  # Standard coarse pitch

    major_d = diameters["major_d"]
    # ISO approximation: drill diameter = major diameter - pitch
    return round(major_d - pitch, 2)


def get_clearance_hole_diameter(thread_spec: str, fit: str = "medium") -> float | None:
    """Get the clearance hole diameter for a bolt/screw.

    Args:
        thread_spec: e.g. "M10"
        fit: "close", "medium", or "loose"

    Returns:
        Clearance hole diameter in mm, or None
    """
    # ISO 273 clearance holes for bolts and screws
    clearance = {
        "M1": {"close": 1.1, "medium": 1.2, "loose": 1.3},
        "M1.2": {"close": 1.3, "medium": 1.4, "loose": 1.5},
        "M1.4": {"close": 1.5, "medium": 1.6, "loose": 1.8},
        "M1.6": {"close": 1.7, "medium": 1.8, "loose": 2.0},
        "M2": {"close": 2.2, "medium": 2.4, "loose": 2.6},
        "M2.5": {"close": 2.7, "medium": 2.9, "loose": 3.1},
        "M3": {"close": 3.2, "medium": 3.4, "loose": 3.6},
        "M3.5": {"close": 3.7, "medium": 3.9, "loose": 4.2},
        "M4": {"close": 4.3, "medium": 4.5, "loose": 4.8},
        "M5": {"close": 5.3, "medium": 5.5, "loose": 5.8},
        "M6": {"close": 6.4, "medium": 6.6, "loose": 7.0},
        "M7": {"close": 7.4, "medium": 7.6, "loose": 8.0},
        "M8": {"close": 8.4, "medium": 9.0, "loose": 10.0},
        "M10": {"close": 10.5, "medium": 11.0, "loose": 12.0},
        "M12": {"close": 13.0, "medium": 13.5, "loose": 14.5},
        "M14": {"close": 15.0, "medium": 15.5, "loose": 16.5},
        "M16": {"close": 17.0, "medium": 17.5, "loose": 18.5},
        "M18": {"close": 19.0, "medium": 20.0, "loose": 21.0},
        "M20": {"close": 21.0, "medium": 22.0, "loose": 24.0},
        "M22": {"close": 23.0, "medium": 24.0, "loose": 26.0},
        "M24": {"close": 25.0, "medium": 26.0, "loose": 28.0},
        "M27": {"close": 28.0, "medium": 30.0, "loose": 32.0},
        "M30": {"close": 31.0, "medium": 33.0, "loose": 35.0},
        "M33": {"close": 34.0, "medium": 36.0, "loose": 38.0},
        "M36": {"close": 37.0, "medium": 39.0, "loose": 42.0},
        "M39": {"close": 40.0, "medium": 42.0, "loose": 45.0},
        "M42": {"close": 43.0, "medium": 45.0, "loose": 48.0},
        "M45": {"close": 46.0, "medium": 48.0, "loose": 52.0},
        "M48": {"close": 50.0, "medium": 52.0, "loose": 56.0},
        "M52": {"close": 54.0, "medium": 56.0, "loose": 62.0},
        "M56": {"close": 58.0, "medium": 62.0, "loose": 66.0},
        "M60": {"close": 62.0, "medium": 66.0, "loose": 70.0},
        "M64": {"close": 66.0, "medium": 70.0, "loose": 74.0},
    }

    base = thread_spec.split("x")[0].split("X")[0].split("-")[0].strip().upper()
    entry = clearance.get(base)
    if entry is None:
        return None
    return entry.get(fit)
