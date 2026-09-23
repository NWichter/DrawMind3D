"""Tests for Vision LLM annotation filters."""

import pytest
from drawmind.pdf.vision import _process_vision_results


class TestVisionFilters:
    """Test that non-hole annotations are correctly filtered."""

    def _make_item(self, text, ann_type="diameter", value=10.0, confidence=0.9):
        return {
            "text": text,
            "type": ann_type,
            "parsed": {"value": value},
            "bbox_percent": {"x": 50, "y": 50, "w": 10, "h": 5},
            "confidence": confidence,
        }

    def test_taper_ratio_filtered(self):
        items = [self._make_item("1.00 : 2.00", value=25.4)]
        result = _process_vision_results(items, 0, 612, 792, "metric", 0)
        assert len(result) == 0

    def test_radius_filtered(self):
        items = [self._make_item("4X R.032", value=0.032)]
        result = _process_vision_results(items, 0, 612, 792, "inch", 0)
        assert len(result) == 0

    def test_torus_id_filtered(self):
        items = [self._make_item("Ø32 ±0.3 AVG (I.D.)", value=32.0)]
        result = _process_vision_results(items, 0, 612, 792, "metric", 0)
        assert len(result) == 0

    def test_torus_od_filtered(self):
        items = [self._make_item("Ø63 ±0.5 AVG (O.D.)", value=63.0)]
        result = _process_vision_results(items, 0, 612, 792, "metric", 0)
        assert len(result) == 0

    def test_major_minor_filtered(self):
        items = [self._make_item("MAJOR DIA 50.0", value=50.0)]
        result = _process_vision_results(items, 0, 612, 792, "metric", 0)
        assert len(result) == 0

    def test_small_value_no_symbol_filtered(self):
        items = [self._make_item("0.3 F", value=0.3)]
        result = _process_vision_results(items, 0, 612, 792, "metric", 0)
        assert len(result) == 0

    def test_small_value_with_symbol_kept(self):
        """Ø5.0 is a real small hole, should be kept."""
        items = [self._make_item("Ø5.0", value=5.0)]
        result = _process_vision_results(items, 0, 612, 792, "metric", 0)
        assert len(result) == 1

    def test_real_diameter_kept(self):
        items = [self._make_item("Ø20 ±0.1", value=20.0)]
        result = _process_vision_results(items, 0, 612, 792, "metric", 0)
        assert len(result) == 1

    def test_thread_kept(self):
        items = [self._make_item("M10x1.5-6H", ann_type="thread", value=10.0)]
        items[0]["parsed"] = {"nominal_diameter": 10.0, "pitch": 1.5}
        result = _process_vision_results(items, 0, 612, 792, "metric", 0)
        assert len(result) == 1
        assert result[0].annotation_type.value == "thread"

    def test_low_confidence_filtered(self):
        items = [self._make_item("Ø20", confidence=0.3)]
        result = _process_vision_results(items, 0, 612, 792, "metric", 0)
        assert len(result) == 0

    def test_tolerance_type_filtered(self):
        items = [self._make_item("H7", ann_type="tolerance", value=0)]
        result = _process_vision_results(items, 0, 612, 792, "metric", 0)
        assert len(result) == 0

    def test_inch_conversion(self):
        items = [self._make_item("Ø.250", value=0.250)]
        result = _process_vision_results(items, 0, 612, 792, "inch", 0)
        assert len(result) == 1
        assert result[0].parsed["value"] == pytest.approx(6.35)

    def test_counterbore_kept(self):
        items = [
            {
                "text": "⌳Ø.438 ↧.250",
                "type": "counterbore",
                "parsed": {"diameter": 0.438, "depth": 0.250},
                "bbox_percent": {"x": 50, "y": 50, "w": 10, "h": 5},
                "confidence": 0.85,
            }
        ]
        result = _process_vision_results(items, 0, 612, 792, "inch", 0)
        assert len(result) == 1
        assert result[0].annotation_type.value == "counterbore"

    def test_multiplier_parsed(self):
        items = [self._make_item("4X Ø8.5", value=8.5)]
        items[0]["multiplier"] = 4
        result = _process_vision_results(items, 0, 612, 792, "metric", 0)
        assert len(result) == 1
        assert result[0].multiplier == 4

    def test_through_hole_detected(self):
        items = [self._make_item("Ø10 THRU", value=10.0)]
        items[0]["type"] = "through"
        items[0]["parsed"]["through"] = True
        result = _process_vision_results(items, 0, 612, 792, "metric", 0)
        assert len(result) == 1
        assert result[0].is_through is True
