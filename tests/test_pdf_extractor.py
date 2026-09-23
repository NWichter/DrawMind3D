"""Tests for PDF annotation extraction and parsing."""

import pytest
from drawmind.pdf.parser import parse_annotations, _is_gdt_false_positive, _convert_value
from drawmind.pdf.patterns import THREAD_METRIC, DIAMETER_SYMBOL, DEPTH_TEXT
from drawmind.models import AnnotationType


class TestRegexPatterns:
    """Test regex patterns for engineering annotations."""

    def test_thread_metric_basic(self):
        match = THREAD_METRIC.search("M10")
        assert match
        assert match.group(1) == "10"

    def test_thread_metric_with_pitch(self):
        match = THREAD_METRIC.search("M10x1.5")
        assert match
        assert match.group(1) == "10"
        assert match.group(2) == "1.5"

    def test_thread_metric_with_tolerance(self):
        match = THREAD_METRIC.search("M10x1.5-6H")
        assert match
        assert match.group(1) == "10"
        assert match.group(2) == "1.5"
        assert match.group(3) == "6H"

    def test_thread_metric_tolerance_only(self):
        match = THREAD_METRIC.search("M12-6g")
        assert match
        assert match.group(1) == "12"
        assert match.group(3) == "6g"

    def test_thread_metric_multiplication_sign(self):
        match = THREAD_METRIC.search("M10\u00d71.5")
        assert match
        assert match.group(2) == "1.5"

    def test_diameter_symbol(self):
        match = DIAMETER_SYMBOL.search("\u230020")
        assert match
        assert match.group(1) == "20"

    def test_diameter_symbol_oslash(self):
        match = DIAMETER_SYMBOL.search("\u00d88.5")
        assert match
        assert match.group(1) == "8.5"

    def test_depth_text(self):
        match = DEPTH_TEXT.search("depth 15")
        assert match
        assert match.group(1) == "15"

    def test_depth_text_german(self):
        match = DEPTH_TEXT.search("Tiefe 20.5")
        assert match
        assert match.group(1) == "20.5"


class TestAnnotationParser:
    """Test the full annotation parser."""

    def _make_raw(self, text, page=0):
        return {
            "text": text,
            "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 20},
            "page": page,
            "source": "native",
        }

    def test_parse_thread(self):
        raw = [self._make_raw("M10x1.5-6H")]
        result = parse_annotations(raw)
        assert len(result) == 1
        assert result[0].annotation_type == AnnotationType.THREAD
        assert result[0].parsed["nominal_diameter"] == 10.0
        assert result[0].parsed["pitch"] == 1.5
        assert result[0].parsed["tolerance_class"] == "6H"

    def test_parse_diameter(self):
        raw = [self._make_raw("\u230020")]
        result = parse_annotations(raw)
        assert len(result) == 1
        assert result[0].annotation_type == AnnotationType.DIAMETER
        assert result[0].parsed["value"] == 20.0

    def test_parse_multiplier(self):
        raw = [self._make_raw("4x M8")]
        result = parse_annotations(raw)
        assert len(result) >= 1
        thread_ann = [a for a in result if a.annotation_type == AnnotationType.THREAD]
        assert len(thread_ann) == 1
        assert thread_ann[0].multiplier == 4

    def test_parse_through_hole(self):
        raw = [self._make_raw("M8 THRU")]
        result = parse_annotations(raw)
        thread_ann = [a for a in result if a.annotation_type == AnnotationType.THREAD]
        assert len(thread_ann) == 1
        assert thread_ann[0].is_through

    def test_parse_depth(self):
        raw = [self._make_raw("depth 15")]
        result = parse_annotations(raw)
        depth_ann = [a for a in result if a.annotation_type == AnnotationType.DEPTH]
        assert len(depth_ann) == 1
        assert depth_ann[0].parsed["value"] == 15.0

    def test_empty_input(self):
        result = parse_annotations([])
        assert result == []

    def test_irrelevant_text(self):
        raw = [self._make_raw("Part Number: 12345")]
        result = parse_annotations(raw)
        # Should not match any engineering annotation pattern
        assert len(result) == 0


class TestUnitConversion:
    """Test inch-to-mm unit conversion."""

    def _make_raw(self, text, page=0):
        return {
            "text": text,
            "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 20},
            "page": page,
            "source": "native",
        }

    def test_convert_value_metric(self):
        assert _convert_value(10.0, "metric") == 10.0

    def test_convert_value_inch(self):
        assert _convert_value(0.250, "inch") == pytest.approx(6.35)

    def test_convert_value_inch_small(self):
        assert _convert_value(1.0, "inch") == pytest.approx(25.4)

    def test_parse_diameter_inch(self):
        raw = [self._make_raw("\u00d8.250 +.003")]
        result = parse_annotations(raw, unit_system="inch")
        assert len(result) == 1
        assert result[0].annotation_type == AnnotationType.DIAMETER
        assert result[0].parsed["value"] == pytest.approx(6.35)
        assert result[0].parsed["original_inch"] == 0.250
        assert result[0].unit_system == "inch"

    def test_parse_diameter_metric_unchanged(self):
        raw = [self._make_raw("\u230020")]
        result = parse_annotations(raw, unit_system="metric")
        assert len(result) == 1
        assert result[0].parsed["value"] == 20.0
        assert "original_inch" not in result[0].parsed

    def test_parse_depth_inch(self):
        raw = [self._make_raw("depth .425")]
        result = parse_annotations(raw, unit_system="inch")
        depth_ann = [a for a in result if a.annotation_type == AnnotationType.DEPTH]
        assert len(depth_ann) == 1
        assert depth_ann[0].parsed["value"] == pytest.approx(0.425 * 25.4)

    def test_thread_not_converted(self):
        """Thread designations (M10) are always metric, should not convert."""
        raw = [self._make_raw("M10x1.5")]
        result = parse_annotations(raw, unit_system="inch")
        assert len(result) == 1
        assert result[0].parsed["nominal_diameter"] == 10.0  # Not converted


class TestNumberSeriesThreads:
    """Number-series UTS sizes (#0 to #12) are not diameters in inches."""

    def _make_raw(self, text, page=0):
        return {
            "text": text,
            "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 20},
            "page": page,
            "source": "native",
        }

    def test_number_size_uses_the_series_table(self):
        """#10 is 0.190 in across the major diameter, not 10 in."""
        result = parse_annotations([self._make_raw("#10-32 UNF")], unit_system="inch")
        threads = [a for a in result if a.annotation_type == AnnotationType.THREAD]
        assert len(threads) == 1
        assert threads[0].parsed["nominal_diameter"] == pytest.approx(4.826, abs=0.01)

    def test_smallest_number_size(self):
        result = parse_annotations([self._make_raw("#4-40 UNC")], unit_system="inch")
        threads = [a for a in result if a.annotation_type == AnnotationType.THREAD]
        assert threads[0].parsed["nominal_diameter"] == pytest.approx(2.845, abs=0.01)

    def test_fractional_size_still_parsed(self):
        result = parse_annotations([self._make_raw("1/4-20 UNC")], unit_system="inch")
        threads = [a for a in result if a.annotation_type == AnnotationType.THREAD]
        assert threads[0].parsed["nominal_diameter"] == pytest.approx(6.35, abs=0.01)

    def test_whole_inch_size_is_not_a_numbered_screw(self):
        """1-8 UNC is a one inch thread; the coarse TPI separates it from #1."""
        result = parse_annotations([self._make_raw("1-8 UNC")], unit_system="inch")
        threads = [a for a in result if a.annotation_type == AnnotationType.THREAD]
        assert threads[0].parsed["nominal_diameter"] == pytest.approx(25.4, abs=0.01)

    def test_fine_tpi_without_hash_is_a_numbered_screw(self):
        """1-64 UNC only exists as #1."""
        result = parse_annotations([self._make_raw("1-64 UNC")], unit_system="inch")
        threads = [a for a in result if a.annotation_type == AnnotationType.THREAD]
        assert threads[0].parsed["nominal_diameter"] == pytest.approx(1.854, abs=0.01)


class TestThreadFalsePositives:
    """Part numbers and shaft fits must not be read as threads."""

    def _make_raw(self, text, page=0):
        return {
            "text": text,
            "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 20},
            "page": page,
            "source": "native",
        }

    @pytest.mark.parametrize("text", ["ITEM8", "DWG-M8-001", "m6 shaft fit", "ITEM 8 OF 12"])
    def test_not_a_thread(self, text):
        result = parse_annotations([self._make_raw(text)])
        threads = [a for a in result if a.annotation_type == AnnotationType.THREAD]
        assert threads == [], f"{text!r} parsed as a thread"

    @pytest.mark.parametrize("text", ["M8", "4X M8 THRU", "M10x1.5-6H", "2X M3x0.5-6g"])
    def test_still_a_thread(self, text):
        result = parse_annotations([self._make_raw(text)])
        threads = [a for a in result if a.annotation_type == AnnotationType.THREAD]
        assert len(threads) == 1, f"{text!r} no longer parsed as a thread"


class TestCalloutModifiers:
    """Multiplier and through markers must survive the combined-callout path."""

    def _make_raw(self, text, page=0):
        return {
            "text": text,
            "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 20},
            "page": page,
            "source": "native",
        }

    def test_multiplier_without_space(self):
        """European drawings write 4xM8, not 4X M8."""
        result = parse_annotations([self._make_raw("4xM8")])
        threads = [a for a in result if a.annotation_type == AnnotationType.THREAD]
        assert threads[0].multiplier == 4

    @pytest.mark.parametrize("text", ["M8 THRU", "M8 durchgehend", "M8 THRU ALL"])
    def test_through_markers(self, text):
        result = parse_annotations([self._make_raw(text)])
        threads = [a for a in result if a.annotation_type == AnnotationType.THREAD]
        assert threads[0].is_through is True, f"{text!r} lost its through marker"


class TestCounterboreCallouts:
    """The generic combined pattern must not swallow the specific types."""

    def _make_raw(self, text, page=0):
        return {
            "text": text,
            "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 20},
            "page": page,
            "source": "native",
        }

    @pytest.mark.parametrize("text", ["CBORE Ø18 ↧8", "⌳Ø18 ↧8", "counterbore 18"])
    def test_counterbore_keeps_its_type(self, text):
        result = parse_annotations([self._make_raw(text)], unit_system="metric")
        types = {a.annotation_type for a in result}
        assert AnnotationType.COUNTERBORE in types, f"{text!r} lost its counterbore type"

    @pytest.mark.parametrize("text", ["CSINK Ø15 90°", "⌵15"])
    def test_countersink_keeps_its_type(self, text):
        result = parse_annotations([self._make_raw(text)], unit_system="metric")
        types = {a.annotation_type for a in result}
        assert AnnotationType.COUNTERSINK in types, f"{text!r} lost its countersink type"

    def test_plain_diameter_still_uses_the_combined_path(self):
        result = parse_annotations([self._make_raw("4X Ø8.5 THRU")], unit_system="metric")
        diameters = [a for a in result if a.annotation_type == AnnotationType.DIAMETER]
        assert len(diameters) == 1
        assert diameters[0].multiplier == 4
        assert diameters[0].is_through is True


class TestGDTDisambiguation:
    """Test GD&T false positive filtering."""

    def _make_raw(self, text, page=0):
        return {
            "text": text,
            "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 20},
            "page": page,
            "source": "native",
        }

    def test_gdt_small_value_filtered(self):
        """Small diameter-symbol values without multiplier/tolerance are GD&T."""
        assert _is_gdt_false_positive("\u00d8.015", 0.015, "inch") is True

    def test_gdt_small_value_metric_filtered(self):
        assert _is_gdt_false_positive("\u2300 0.5", 0.5, "metric") is True

    def test_small_metric_hole_is_not_gdt(self):
        """\u00d82.5 and \u00d82 are ordinary small holes, not tolerance zones."""
        assert _is_gdt_false_positive("\u23002.5", 2.5, "metric") is False
        assert _is_gdt_false_positive("\u23002", 2.0, "metric") is False

    def test_small_metric_hole_survives_the_parser(self):
        raw = {
            "text": "\u23002.5",
            "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 20},
            "page": 0,
            "source": "native",
        }
        result = parse_annotations([raw], unit_system="metric")
        diameters = [a for a in result if a.annotation_type == AnnotationType.DIAMETER]
        assert len(diameters) == 1
        assert diameters[0].parsed["value"] == 2.5

    def test_real_diameter_not_filtered(self):
        """Larger values are real diameters."""
        assert _is_gdt_false_positive("\u00d8.250 +.003", 0.250, "inch") is False

    def test_multiplier_diameter_not_filtered(self):
        """Values with multiplier prefix are real diameters."""
        assert _is_gdt_false_positive("4X \u00d8.173 +.005", 0.173, "inch") is False

    def test_bilateral_tol_not_filtered(self):
        """Values with bilateral tolerance are real diameters."""
        assert _is_gdt_false_positive("\u00d8.250 +.003", 0.250, "inch") is False

    def test_no_diameter_symbol_not_filtered(self):
        """Without diameter symbol, not a GD&T false positive."""
        assert _is_gdt_false_positive("depth .015", 0.015, "inch") is False

    def test_gdt_filtered_in_parser(self):
        """GD&T tolerance values should not appear as diameter annotations."""
        raw = [self._make_raw("\u00d8.015")]
        result = parse_annotations(raw, unit_system="inch")
        diameter_anns = [a for a in result if a.annotation_type == AnnotationType.DIAMETER]
        assert len(diameter_anns) == 0

    def test_real_diameter_parsed(self):
        """Real diameter values should be parsed."""
        raw = [self._make_raw("4X \u00d8.250 +.003")]
        result = parse_annotations(raw, unit_system="inch")
        diameter_anns = [a for a in result if a.annotation_type == AnnotationType.DIAMETER]
        assert len(diameter_anns) == 1
        assert diameter_anns[0].parsed["value"] == pytest.approx(6.35)
