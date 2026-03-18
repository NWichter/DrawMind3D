"""Tests for STEP file reading and feature extraction."""

from drawmind.cad.thread_table import (
    get_thread_diameters,
    match_thread_to_diameter,
    get_clearance_hole_diameter,
)


class TestThreadTable:
    """Test ISO metric thread lookup table."""

    def test_get_m10_diameters(self):
        d = get_thread_diameters("M10")
        assert d is not None
        assert d["major_d"] == 10.0
        assert d["pitch_coarse"] == 1.5
        assert abs(d["pitch_d"] - 9.026) < 0.01
        assert d["drill_d"] == 8.5

    def test_get_m8_diameters(self):
        d = get_thread_diameters("M8")
        assert d is not None
        assert d["major_d"] == 8.0
        assert d["pitch_coarse"] == 1.25

    def test_get_unknown_thread(self):
        d = get_thread_diameters("M99")
        assert d is None

    def test_match_major_diameter(self):
        score, dtype = match_thread_to_diameter("M10", 10.0)
        assert score > 0.9
        assert dtype == "major"

    def test_match_pitch_diameter(self):
        score, dtype = match_thread_to_diameter("M10", 9.026)
        assert score > 0.9
        assert dtype == "pitch"

    def test_match_drill_diameter(self):
        score, dtype = match_thread_to_diameter("M10", 8.5)
        assert score > 0.9
        assert dtype == "drill"

    def test_no_match(self):
        score, dtype = match_thread_to_diameter("M10", 20.0)
        assert score == 0.0

    def test_clearance_hole(self):
        d = get_clearance_hole_diameter("M10", "medium")
        assert d == 11.0

    def test_clearance_hole_unknown(self):
        d = get_clearance_hole_diameter("M99")
        assert d is None
