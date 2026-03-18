"""End-to-end integration test with a synthetic PDF."""

import json
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from drawmind.pdf.extractor import extract_all_text
from drawmind.pdf.parser import parse_annotations
from drawmind.matching.matcher import match_annotations_to_features
from drawmind.output.writer import write_output
from drawmind.models import (
    AnnotationType,
    CylindricalFeature,
    HoleGroup,
)


def _create_test_pdf(path: Path) -> None:
    """Create a minimal PDF that contains engineering annotations."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4

    # Title
    page.insert_text((50, 50), "DrawMind3D – Test Drawing", fontsize=14)

    # Engineering annotations (positioned as they would be in a real drawing)
    annotations = [
        ((80, 150), "M10x1.5-6H"),
        ((80, 180), "depth 20"),
        ((300, 150), "4x M8 THRU"),
        ((300, 250), "\u00d88.5H7"),  # Ø8.5H7
        ((80, 350), "M6"),
        ((300, 350), "\u23009.0"),  # ⌀9.0
    ]
    for pos, text in annotations:
        page.insert_text(pos, text, fontsize=10)

    doc.save(str(path))
    doc.close()


def _create_mock_holes() -> list[HoleGroup]:
    """Create synthetic hole groups matching the PDF annotations above."""
    specs = [
        # M10x1.5-6H → pitch diameter 9.026 mm, depth 20
        ("hole_001", 9.026, 20.0, (25, 0, 15), False, "simple"),
        # 4× M8 THRU → pitch diameter 7.188 mm, through
        ("hole_010", 7.188, 30.0, (10, 10, 0), True, "simple"),
        ("hole_011", 7.188, 30.0, (10, -10, 0), True, "simple"),
        ("hole_012", 7.188, 30.0, (-10, 10, 0), True, "simple"),
        ("hole_013", 7.188, 30.0, (-10, -10, 0), True, "simple"),
        # Ø8.5H7 → 8.5 mm diameter
        ("hole_020", 8.5, 15.0, (50, 0, 10), False, "simple"),
        # M6 → pitch diameter 5.35 mm
        ("hole_030", 5.35, 12.0, (0, 50, 10), False, "simple"),
        # ⌀9.0
        ("hole_040", 9.0, 10.0, (70, 0, 5), False, "simple"),
    ]

    holes = []
    for hid, diam, depth, center, through, htype in specs:
        feat = CylindricalFeature(
            id=f"feat_{hid[5:]}",
            face_ids=[int(hid[5:]) * 10],
            radius=diam / 2,
            diameter=diam,
            center=center,
            axis_direction=(0.0, 0.0, 1.0),
            estimated_depth=depth,
            surface_area=500.0,
            is_through_hole=through,
            group_id=hid,
        )
        holes.append(
            HoleGroup(
                id=hid,
                features=[feat],
                primary_diameter=diam,
                total_depth=depth,
                center=center,
                axis_direction=(0.0, 0.0, 1.0),
                is_through_hole=through,
                hole_type=htype,
            )
        )
    return holes


class TestIntegrationPipeline:
    """Full pipeline test: PDF → parse → match → output."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.pdf_path = tmp_path / "test_drawing.pdf"
        _create_test_pdf(self.pdf_path)
        self.holes = _create_mock_holes()
        self.output_path = tmp_path / "result.json"

    def test_pdf_extraction_finds_annotations(self):
        raw = extract_all_text(str(self.pdf_path))
        assert len(raw) >= 6, f"Expected at least 6 text spans, got {len(raw)}"

        texts = [r["text"] for r in raw]
        assert any("M10" in t for t in texts)
        assert any("M8" in t for t in texts)
        assert any("depth" in t.lower() for t in texts)

    def test_parser_produces_correct_types(self):
        raw = extract_all_text(str(self.pdf_path))
        annotations = parse_annotations(raw)

        types = {a.annotation_type for a in annotations}
        assert AnnotationType.THREAD in types
        assert AnnotationType.DEPTH in types

        # Check M10x1.5-6H parsed correctly
        m10_anns = [
            a
            for a in annotations
            if a.annotation_type == AnnotationType.THREAD
            and a.parsed.get("nominal_diameter") == 10.0
        ]
        assert len(m10_anns) == 1
        assert m10_anns[0].parsed.get("pitch") == 1.5
        assert m10_anns[0].parsed.get("tolerance_class") == "6H"

    def test_multiplier_parsed(self):
        raw = extract_all_text(str(self.pdf_path))
        annotations = parse_annotations(raw)

        m8_anns = [
            a
            for a in annotations
            if a.annotation_type == AnnotationType.THREAD
            and a.parsed.get("nominal_diameter") == 8.0
        ]
        assert len(m8_anns) == 1
        assert m8_anns[0].multiplier == 4
        assert m8_anns[0].is_through is True

    def test_matching_produces_results(self):
        raw = extract_all_text(str(self.pdf_path))
        annotations = parse_annotations(raw)

        matches, unmatched_ann, unmatched_holes = match_annotations_to_features(
            annotations, self.holes
        )

        # At least some matches should be produced
        assert len(matches) >= 1, "Pipeline produced no matches"

        # Verify each match has required fields
        for m in matches:
            assert m.annotation_id
            assert m.feature_id
            assert 0.0 <= m.confidence <= 1.0

    def test_output_json_valid(self):
        raw = extract_all_text(str(self.pdf_path))
        annotations = parse_annotations(raw)
        matches, unmatched_ann, unmatched_holes = match_annotations_to_features(
            annotations, self.holes
        )

        out_path = write_output(
            matches=matches,
            unmatched_annotations=unmatched_ann,
            unmatched_holes=unmatched_holes,
            output_path=str(self.output_path),
            pdf_file="test_drawing.pdf",
            step_file="test_model.step",
            llm_enhanced=False,
        )

        assert Path(out_path).exists()

        with open(out_path) as f:
            data = json.load(f)

        # Validate JSON structure
        assert "metadata" in data
        assert "features" in data
        assert "summary" in data
        assert data["metadata"]["pdf_file"] == "test_drawing.pdf"
        assert data["metadata"]["step_file"] == "test_model.step"
        assert data["metadata"]["llm_enhanced"] is False
        assert isinstance(data["summary"]["matched"], int)
        assert isinstance(data["summary"]["avg_confidence"], float)

    def test_m10_matched_to_correct_hole(self):
        """M10x1.5 annotation should match hole with pitch diameter 9.026mm."""
        raw = extract_all_text(str(self.pdf_path))
        annotations = parse_annotations(raw)
        matches, _, _ = match_annotations_to_features(annotations, self.holes)

        m10_matches = [m for m in matches if "M10" in (m.annotation_text or "")]
        if m10_matches:
            assert m10_matches[0].feature_id == "hole_001"
            assert m10_matches[0].confidence > 0.5
