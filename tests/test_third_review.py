"""Regression tests for the findings of the third outside review."""

import threading
import time

import pypdfium2 as pdfium

from drawmind.models import AnnotationType, BoundingBox, HoleGroup, PDFAnnotation
from drawmind.pdf import backend
from tests.pdf_builder import build_text_pdf


class TestPdfiumIsSerialised:
    def test_second_thread_waits_for_the_first_document(self, tmp_path):
        pdf = build_text_pdf(tmp_path / "a.pdf", [((50, 50), "M8", 10)])
        first_open = threading.Event()
        timeline = []

        def holder():
            with backend.open_document(pdf):
                first_open.set()
                time.sleep(0.2)
                timeline.append("first closed")

        def contender():
            first_open.wait()
            with backend.open_document(pdf):
                timeline.append("second opened")

        threads = [threading.Thread(target=holder), threading.Thread(target=contender)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)

        assert timeline == ["first closed", "second opened"]


class TestMultiplierIsBounded:
    def test_huge_count_does_not_size_the_assignment(self, monkeypatch):
        from drawmind.matching import matcher

        shapes = []
        real = matcher.linear_sum_assignment

        def spy(matrix):
            shapes.append(matrix.shape)
            return real(matrix)

        monkeypatch.setattr(matcher, "linear_sum_assignment", spy)

        ann = PDFAnnotation(
            id="ann_001",
            raw_text="100000X Ø8",
            annotation_type=AnnotationType.DIAMETER,
            parsed={"value": 8.0},
            bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10, page=0),
            multiplier=100000,
        )
        hole = HoleGroup(
            id="hole_001",
            features=[],
            primary_diameter=20.0,
            total_depth=10.0,
            center=(0.0, 0.0, 0.0),
            axis_direction=(0.0, 0.0, 1.0),
        )
        matcher.match_annotations_to_features([ann], [hole])

        assert shapes and all(rows <= 1 for rows, _ in shapes)


class TestTextByCharacterIndex:
    def test_lines_do_not_depend_on_the_bulk_text_call(self, tmp_path, monkeypatch):
        pdf = build_text_pdf(tmp_path / "a.pdf", [((50, 50), "4X M8 THRU", 10)])

        # get_text_range may legally insert characters; a shifted result must
        # not shift the text against its boxes.
        original = pdfium.PdfTextPage.get_text_range
        monkeypatch.setattr(
            pdfium.PdfTextPage,
            "get_text_range",
            lambda self, *a, **k: "﻿" + original(self, *a, **k),
        )

        with backend.open_document(pdf) as doc:
            (line,) = backend.text_lines(doc[0])
        assert line["text"] == "4X M8 THRU"


class TestGlbCache:
    def test_concurrent_requests_convert_once_and_never_see_a_partial_file(
        self, tmp_path, monkeypatch
    ):
        from web import app as webapp

        calls = []
        seen_partial = []
        glb = tmp_path / "cache" / "model.glb"

        def slow_convert(step_path, out_path):
            calls.append(out_path)
            out_path.write_bytes(b"glTF")
            time.sleep(0.2)
            if glb.exists():
                seen_partial.append(True)
            with open(out_path, "ab") as f:
                f.write(b"-complete")

        monkeypatch.setattr(webapp, "_convert_step_to_glb", slow_convert)

        threads = [
            threading.Thread(
                target=webapp._publish_cached_glb, args=("case", tmp_path / "m.step", glb)
            )
            for _ in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)

        assert len(calls) == 1
        assert not seen_partial
        assert glb.read_bytes() == b"glTF-complete"
        assert list(glb.parent.iterdir()) == [glb]


def _raw_pdf(path, text=b"BAB", crop=None):
    """One-page PDF whose font maps byte 'A' to U+1D719, outside the BMP."""
    cmap = (
        b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
        b"/CMapName /X def 1 begincodespacerange <00> <FF> endcodespacerange\n"
        b"2 beginbfchar <41> <D835DF19> <42> <0042> endbfchar\n"
        b"endcmap CMapName currentdict /CMap defineresource pop end end"
    )
    content = b"BT /F1 24 Tf 20 100 Td (" + text + b") Tj ET"
    cropbox = b"/CropBox [%s] " % crop if crop else b""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
        + cropbox
        + b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /ToUnicode 6 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(cmap), cmap),
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (
        len(objects) + 1,
        xref_at,
    )
    path.write_bytes(bytes(out))
    return path


class TestFollowUpReview:
    def test_characters_outside_the_bmp_survive_as_valid_utf8(self, tmp_path):
        pdf = _raw_pdf(tmp_path / "phi.pdf")
        with backend.open_document(pdf) as doc:
            (line,) = backend.text_lines(doc[0])

        assert line["text"] == "B\U0001d719B"
        line["text"].encode("utf-8")

    def test_crop_box_overhanging_the_media_box_does_not_shift_text(self, tmp_path):
        plain = _raw_pdf(tmp_path / "plain.pdf", text=b"BB")
        overhang = _raw_pdf(tmp_path / "overhang.pdf", text=b"BB", crop=b"-50 -50 250 250")

        with backend.open_document(plain) as doc:
            (a,) = backend.text_lines(doc[0])
        with backend.open_document(overhang) as doc:
            (b,) = backend.text_lines(doc[0])

        assert (b["x0"], b["y0"]) == (a["x0"], a["y0"])
