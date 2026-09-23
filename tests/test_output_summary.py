"""Tests for the summary counters in the pipeline output."""

import json

from drawmind.models import AnnotationType, BoundingBox, MatchResult, PDFAnnotation
from drawmind.output.writer import write_output


def _match(match_id, annotation_id, feature_id):
    return MatchResult(
        id=match_id,
        annotation_id=annotation_id,
        feature_id=feature_id,
        annotation_text="4x M8",
        confidence=0.9,
    )


def _annotation(ann_id):
    return PDFAnnotation(
        id=ann_id,
        raw_text="M6",
        annotation_type=AnnotationType.THREAD,
        parsed={"nominal_diameter": 6.0},
        bbox=BoundingBox(x0=0, y0=0, x1=10, y1=10, page=0),
    )


def _write(tmp_path, matches, unmatched):
    out = write_output(
        matches=matches,
        unmatched_annotations=unmatched,
        unmatched_holes=[],
        output_path=str(tmp_path / "result.json"),
        pdf_file="drawing.pdf",
        step_file="model.step",
        llm_enhanced=False,
    )
    with open(out) as handle:
        return json.load(handle)["summary"]


def test_multiplier_annotation_counts_once(tmp_path):
    """'4x M8' matches four holes but is one annotation on the drawing."""
    matches = [_match(f"m{i}", "ann_001", f"hole_{i}") for i in range(4)]
    summary = _write(tmp_path, matches, [_annotation("ann_002")])

    assert summary["total_annotations_found"] == 2
    assert summary["matched"] == 4


def test_distinct_annotations_are_all_counted(tmp_path):
    matches = [_match(f"m{i}", f"ann_{i:03d}", f"hole_{i}") for i in range(3)]
    summary = _write(tmp_path, matches, [_annotation("ann_900"), _annotation("ann_901")])

    assert summary["total_annotations_found"] == 5
