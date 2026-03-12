"""Central data models used across all modules."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AnnotationType(str, Enum):
    """Types of engineering drawing annotations."""
    THREAD = "thread"
    DIAMETER = "diameter"
    DEPTH = "depth"
    COUNTERBORE = "counterbore"
    COUNTERSINK = "countersink"
    TOLERANCE = "tolerance"
    FIT = "fit"
    GDT = "gdt"
    SURFACE_FINISH = "surface_finish"
    DIMENSION = "dimension"
    HOLE_CALLOUT = "hole_callout"


class BoundingBox(BaseModel):
    """Bounding box for a PDF annotation."""
    x0: float
    y0: float
    x1: float
    y1: float
    page: int = 0


class PDFAnnotation(BaseModel):
    """A parsed annotation extracted from a PDF technical drawing."""
    id: str
    raw_text: str
    annotation_type: AnnotationType
    parsed: dict = Field(default_factory=dict)
    bbox: BoundingBox
    confidence: float = 1.0
    source: str = "native"  # "native", "ocr", or "vision_llm"
    multiplier: int = 1  # e.g. "4x M8" -> multiplier=4
    is_through: bool = False
    unit_system: str = "metric"  # "metric" or "inch" — values are always stored in mm after conversion
    associated_annotations: list[str] = Field(default_factory=list)  # IDs of related annotations


class CylindricalFeature(BaseModel):
    """A cylindrical feature (potential hole) extracted from a 3D CAD model."""
    id: str
    face_ids: list[int] = Field(default_factory=list)
    radius: float  # mm
    diameter: float  # mm
    center: tuple[float, float, float]
    axis_direction: tuple[float, float, float]
    estimated_depth: float  # mm
    surface_area: float  # mm^2
    is_through_hole: bool = False
    is_conical: bool = False  # True for conical faces (countersinks)
    cone_half_angle: Optional[float] = None  # Half-angle in degrees (e.g., 45° for 90° countersink)
    group_id: Optional[str] = None  # Coaxial group identifier


class HoleGroup(BaseModel):
    """A group of coaxial cylindrical features forming one logical hole."""
    id: str
    features: list[CylindricalFeature]
    primary_diameter: float  # The main hole diameter
    total_depth: float
    center: tuple[float, float, float]
    axis_direction: tuple[float, float, float]
    is_through_hole: bool = False
    hole_type: str = "simple"  # "simple", "counterbore", "countersink", "stepped"


class MatchResult(BaseModel):
    """A matched pair of PDF annotation and 3D CAD feature."""
    id: str
    annotation_id: str
    feature_id: str  # HoleGroup or CylindricalFeature ID
    annotation_text: str
    parsed_interpretation: dict = Field(default_factory=dict)
    feature_3d_ref: dict = Field(default_factory=dict)
    confidence: float
    scoring_breakdown: dict = Field(default_factory=dict)
    evidence: dict = Field(default_factory=dict)


class PipelineOutput(BaseModel):
    """Complete pipeline output."""
    metadata: dict = Field(default_factory=dict)
    features: list[MatchResult] = Field(default_factory=list)
    unmatched_annotations: list[dict] = Field(default_factory=list)
    unmatched_features: list[dict] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)
