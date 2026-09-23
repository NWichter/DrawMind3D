"""Tests for the PDF engine layer.

These cover the contract the rest of the pipeline relies on: text with
top-down bounding boxes, page geometry, rasterisation and vector segments.
"""

import io

import pytest
from PIL import Image

from drawmind.pdf import backend
from drawmind.pdf.extractor import (
    detect_unit_system,
    extract_all_text,
    get_page_as_image,
    get_page_dimensions,
)
from tests.pdf_builder import build_text_pdf


@pytest.fixture
def drawing(tmp_path):
    path = tmp_path / "drawing.pdf"
    build_text_pdf(
        path,
        [
            ((50, 40), "UNITS: MILLIMETERS", 9),
            ((80, 150), "4X M10x1.5-6H", 10),
            ((300, 150), "Ø8.5 H7", 10),
            ((80, 400), "depth 20", 10),
        ],
        width=400,
        height=500,
        strokes=[((120, 160), (200, 260))],
    )
    return path


class TestTextLines:
    def test_extracts_every_line(self, drawing):
        with backend.open_document(drawing) as doc:
            lines = backend.text_lines(doc[0])

        assert [line["text"] for line in lines] == [
            "UNITS: MILLIMETERS",
            "4X M10x1.5-6H",
            "Ø8.5 H7",
            "depth 20",
        ]

    def test_boxes_are_top_down(self, drawing):
        """y grows downwards, so a line placed lower has a larger y0."""
        with backend.open_document(drawing) as doc:
            lines = {line["text"]: line for line in backend.text_lines(doc[0])}

        assert lines["UNITS: MILLIMETERS"]["y0"] < lines["4X M10x1.5-6H"]["y0"]
        assert lines["4X M10x1.5-6H"]["y0"] < lines["depth 20"]["y0"]

    def test_box_matches_requested_position(self, drawing):
        with backend.open_document(drawing) as doc:
            lines = {line["text"]: line for line in backend.text_lines(doc[0])}

        box = lines["4X M10x1.5-6H"]
        assert box["x0"] == pytest.approx(80, abs=2)
        assert box["y1"] == pytest.approx(150, abs=2)
        assert box["x1"] > box["x0"]
        assert box["y1"] > box["y0"]

    def test_decimal_point_does_not_split_a_line(self, tmp_path):
        """A period has a tiny glyph box and must not end the line."""
        path = build_text_pdf(tmp_path / "d.pdf", [((50, 100), "M6x1.0 THRU", 10)])
        with backend.open_document(path) as doc:
            lines = backend.text_lines(doc[0])

        assert [line["text"] for line in lines] == ["M6x1.0 THRU"]

    def test_distant_callouts_stay_separate(self, tmp_path):
        """Two callouts on one baseline are different annotations."""
        path = build_text_pdf(
            tmp_path / "d.pdf", [((50, 100), "M6 THRU", 10), ((300, 100), "M8 THRU", 10)]
        )
        with backend.open_document(path) as doc:
            texts = [line["text"] for line in backend.text_lines(doc[0])]

        assert texts == ["M6 THRU", "M8 THRU"]

    def test_symbols_survive_via_tounicode(self, tmp_path):
        """CAD exports map engineering symbols through a ToUnicode table."""
        path = build_text_pdf(tmp_path / "d.pdf", [((50, 100), "⌀9.0 und Ø8.5", 10)])
        with backend.open_document(path) as doc:
            texts = [line["text"] for line in backend.text_lines(doc[0])]

        assert texts == ["⌀9.0 und Ø8.5"]

    def test_empty_page_yields_no_lines(self, tmp_path):
        path = build_text_pdf(tmp_path / "blank.pdf", [])
        with backend.open_document(path) as doc:
            assert backend.text_lines(doc[0]) == []


class TestRotatedPages:
    """Landscape CAD drawings are stored rotated; coordinates must not swap."""

    def test_text_is_read_in_order(self, tmp_path):
        path = build_text_pdf(
            tmp_path / "rot.pdf",
            [((60, 100), "4X M10x1.5-6H", 10)],
            width=400,
            height=500,
            rotate=270,
        )
        with backend.open_document(path) as doc:
            texts = [line["text"] for line in backend.text_lines(doc[0])]

        assert texts == ["4X M10x1.5-6H"]

    def test_page_size_reports_rotated_dimensions(self, tmp_path):
        path = build_text_pdf(tmp_path / "rot.pdf", [], width=400, height=500, rotate=270)
        with backend.open_document(path) as doc:
            assert backend.page_size(doc[0]) == (500, 400)
            assert backend.page_height(doc[0]) == 500


class TestPageGeometry:
    def test_dimensions(self, drawing):
        assert get_page_dimensions(drawing) == (400, 500)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            get_page_dimensions(tmp_path / "nope.pdf")


class TestRendering:
    def test_png_scales_with_dpi(self, drawing):
        image = Image.open(io.BytesIO(get_page_as_image(drawing, dpi=144)))

        assert image.format == "PNG"
        # 400pt at 144 dpi is 800px, give or take the renderer's rounding.
        assert image.width == pytest.approx(800, abs=2)
        assert image.height == pytest.approx(1000, abs=2)


class TestLineSegments:
    def test_finds_a_drawn_segment(self, drawing):
        with backend.open_document(drawing) as doc:
            segments = backend.line_segments(doc[0])

        assert any(
            start == pytest.approx((120, 160), abs=1) and end == pytest.approx((200, 260), abs=1)
            for start, end in segments
        )

    def test_thick_strokes_are_ignored(self, tmp_path):
        """Frame lines and hatching are not leader lines."""
        path = build_text_pdf(
            tmp_path / "thick.pdf", [], strokes=[((10, 10), (200, 200))], stroke_width=8.0
        )
        with backend.open_document(path) as doc:
            assert backend.line_segments(doc[0]) == []


class TestUnitDetection:
    def test_explicit_millimetres(self, drawing):
        assert detect_unit_system(drawing) == "metric"

    def test_unc_thread_implies_inch(self, tmp_path):
        path = build_text_pdf(tmp_path / "inch.pdf", [((50, 100), "1/4-20 UNC THRU", 10)])
        assert detect_unit_system(path) == "inch"


class TestExtractAllText:
    def test_returns_pipeline_shape(self, drawing):
        texts = extract_all_text(drawing)

        assert texts
        for item in texts:
            assert set(item) >= {"text", "bbox", "page", "source"}
            assert set(item["bbox"]) == {"x0", "y0", "x1", "y1"}
            assert item["page"] == 0
