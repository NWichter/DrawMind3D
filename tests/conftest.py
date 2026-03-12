"""Test fixtures and sample data."""

import pytest
from drawmind.models import (
    PDFAnnotation, AnnotationType, BoundingBox,
    CylindricalFeature, HoleGroup,
)


@pytest.fixture
def sample_thread_annotation():
    return PDFAnnotation(
        id="ann_001",
        raw_text="M10x1.5-6H",
        annotation_type=AnnotationType.THREAD,
        parsed={
            "nominal_diameter": 10.0,
            "pitch": 1.5,
            "tolerance_class": "6H",
            "thread_type": "metric",
            "standard": "ISO_metric",
        },
        bbox=BoundingBox(x0=100, y0=50, x1=180, y1=65, page=0),
    )


@pytest.fixture
def sample_diameter_annotation():
    return PDFAnnotation(
        id="ann_002",
        raw_text="\u23008.5",
        annotation_type=AnnotationType.DIAMETER,
        parsed={"value": 8.5},
        bbox=BoundingBox(x0=200, y0=100, x1=250, y1=115, page=0),
    )


@pytest.fixture
def sample_multiplier_annotation():
    return PDFAnnotation(
        id="ann_003",
        raw_text="4x M8 THRU",
        annotation_type=AnnotationType.THREAD,
        parsed={
            "nominal_diameter": 8.0,
            "thread_type": "metric",
            "standard": "ISO_metric",
        },
        bbox=BoundingBox(x0=300, y0=150, x1=400, y1=165, page=0),
        multiplier=4,
        is_through=True,
    )


@pytest.fixture
def sample_cylindrical_feature():
    return CylindricalFeature(
        id="feat_001",
        face_ids=[10],
        radius=5.0,
        diameter=10.0,
        center=(25.0, 0.0, 15.0),
        axis_direction=(0.0, 0.0, 1.0),
        estimated_depth=20.0,
        surface_area=628.318,
    )


@pytest.fixture
def sample_hole_group():
    feat = CylindricalFeature(
        id="feat_001",
        face_ids=[10],
        radius=4.513,
        diameter=9.026,
        center=(25.0, 0.0, 15.0),
        axis_direction=(0.0, 0.0, 1.0),
        estimated_depth=20.0,
        surface_area=567.0,
        group_id="hole_001",
    )
    return HoleGroup(
        id="hole_001",
        features=[feat],
        primary_diameter=9.026,
        total_depth=20.0,
        center=(25.0, 0.0, 15.0),
        axis_direction=(0.0, 0.0, 1.0),
        hole_type="simple",
    )


@pytest.fixture
def sample_through_holes():
    """4 identical through-holes for testing multiplier matching."""
    holes = []
    positions = [
        (10, 10, 0), (10, -10, 0), (-10, 10, 0), (-10, -10, 0)
    ]
    for i, pos in enumerate(positions):
        feat = CylindricalFeature(
            id=f"feat_{i+10:03d}",
            face_ids=[20 + i],
            radius=3.594,  # M8 pitch diameter / 2
            diameter=7.188,
            center=pos,
            axis_direction=(0.0, 0.0, 1.0),
            estimated_depth=30.0,
            surface_area=678.0,
            is_through_hole=True,
            group_id=f"hole_{i+10:03d}",
        )
        holes.append(HoleGroup(
            id=f"hole_{i+10:03d}",
            features=[feat],
            primary_diameter=7.188,
            total_depth=30.0,
            center=pos,
            axis_direction=(0.0, 0.0, 1.0),
            is_through_hole=True,
            hole_type="simple",
        ))
    return holes
