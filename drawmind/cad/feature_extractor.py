"""Extract cylindrical and conical features (holes, countersinks) from a 3D CAD model."""

from __future__ import annotations

import math

import numpy as np
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere, GeomAbs_Torus
from OCP.TopoDS import TopoDS, TopoDS_Shape
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp

from drawmind.models import CylindricalFeature, HoleGroup
from drawmind.cad.step_reader import get_bounding_box
from drawmind.config import COAXIAL_ANGLE_TOLERANCE_DEG, COAXIAL_DISTANCE_TOLERANCE_MM


def extract_cylindrical_faces(shape: TopoDS_Shape) -> list[CylindricalFeature]:
    """Extract cylindrical and conical faces (holes only, not shafts) from a shape.

    Uses face orientation to distinguish concave (hole) from convex (shaft) surfaces.
    Also extracts conical faces for countersink detection.

    Args:
        shape: The loaded CAD shape

    Returns:
        List of cylindrical features with radius, center, axis, depth, etc.
    """
    features = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_id = 0
    feat_counter = 0

    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        adaptor = BRepAdaptor_Surface(face)
        surf_type = adaptor.GetType()

        if surf_type == GeomAbs_Cylinder:
            # Check concavity: reversed face orientation = concave = hole
            # In B-Rep, a face whose orientation is REVERSED relative to the
            # surface normal points inward → concave (a hole, not a shaft).
            is_concave = face.Orientation() == TopAbs_REVERSED

            if not is_concave:
                face_id += 1
                explorer.Next()
                continue  # Skip convex faces (shafts, bosses)

            cylinder = adaptor.Cylinder()
            axis = cylinder.Axis()
            location = axis.Location()
            direction = axis.Direction()
            radius = cylinder.Radius()

            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)
            area = props.Mass()

            # Depth from area: A = 2*pi*r*h => h = A/(2*pi*r)
            estimated_depth = area / (2 * math.pi * radius) if radius > 1e-6 else 0.0

            feat_counter += 1
            features.append(CylindricalFeature(
                id=f"feat_{feat_counter:03d}",
                face_ids=[face_id],
                radius=round(radius, 4),
                diameter=round(radius * 2, 4),
                center=(
                    round(location.X(), 4),
                    round(location.Y(), 4),
                    round(location.Z(), 4),
                ),
                axis_direction=(
                    round(direction.X(), 6),
                    round(direction.Y(), 6),
                    round(direction.Z(), 6),
                ),
                estimated_depth=round(estimated_depth, 4),
                surface_area=round(area, 4),
            ))

        elif surf_type == GeomAbs_Cone:
            # Conical faces → countersinks
            is_concave = face.Orientation() == TopAbs_REVERSED
            if not is_concave:
                face_id += 1
                explorer.Next()
                continue

            cone = adaptor.Cone()
            axis = cone.Axis()
            location = axis.Location()
            direction = axis.Direction()
            # Use the average radius of the cone for grouping
            semi_angle = cone.SemiAngle()
            ref_radius = cone.RefRadius()

            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)
            area = props.Mass()

            # Approximate depth from cone geometry
            estimated_depth = ref_radius / math.tan(abs(semi_angle)) if abs(semi_angle) > 0.01 else 0.0

            feat_counter += 1
            features.append(CylindricalFeature(
                id=f"feat_{feat_counter:03d}",
                face_ids=[face_id],
                radius=round(ref_radius, 4),
                diameter=round(ref_radius * 2, 4),
                center=(
                    round(location.X(), 4),
                    round(location.Y(), 4),
                    round(location.Z(), 4),
                ),
                axis_direction=(
                    round(direction.X(), 6),
                    round(direction.Y(), 6),
                    round(direction.Z(), 6),
                ),
                estimated_depth=round(estimated_depth, 4),
                surface_area=round(area, 4),
                is_conical=True,
                cone_half_angle=round(math.degrees(abs(semi_angle)), 2),
            ))

        elif surf_type == GeomAbs_Sphere:
            # Spherical faces → ball-end holes, spherical countersinks
            is_concave = face.Orientation() == TopAbs_REVERSED
            if not is_concave:
                face_id += 1
                explorer.Next()
                continue

            sphere = adaptor.Sphere()
            center_pt = sphere.Location()
            radius = sphere.Radius()

            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)
            area = props.Mass()

            # Approximate depth as radius (hemisphere depth)
            estimated_depth = radius

            feat_counter += 1
            features.append(CylindricalFeature(
                id=f"feat_{feat_counter:03d}",
                face_ids=[face_id],
                radius=round(radius, 4),
                diameter=round(radius * 2, 4),
                center=(
                    round(center_pt.X(), 4),
                    round(center_pt.Y(), 4),
                    round(center_pt.Z(), 4),
                ),
                axis_direction=(0.0, 0.0, 1.0),  # Default axis for spherical
                estimated_depth=round(estimated_depth, 4),
                surface_area=round(area, 4),
            ))

        elif surf_type == GeomAbs_Torus:
            # Toroidal faces → torus inner/outer bore
            is_concave = face.Orientation() == TopAbs_REVERSED
            if not is_concave:
                face_id += 1
                explorer.Next()
                continue

            torus = adaptor.Torus()
            axis = torus.Axis()
            location = axis.Location()
            direction = axis.Direction()
            major_r = torus.MajorRadius()
            minor_r = torus.MinorRadius()

            # Inner bore diameter = (major - minor) * 2
            inner_diameter = (major_r - minor_r) * 2
            # Outer diameter = (major + minor) * 2
            # Use inner diameter as the primary feature (the bore)
            if inner_diameter > 0.1:  # Skip degenerate tori
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, props)
                area = props.Mass()

                feat_counter += 1
                features.append(CylindricalFeature(
                    id=f"feat_{feat_counter:03d}",
                    face_ids=[face_id],
                    radius=round(inner_diameter / 2, 4),
                    diameter=round(inner_diameter, 4),
                    center=(
                        round(location.X(), 4),
                        round(location.Y(), 4),
                        round(location.Z(), 4),
                    ),
                    axis_direction=(
                        round(direction.X(), 6),
                        round(direction.Y(), 6),
                        round(direction.Z(), 6),
                    ),
                    estimated_depth=round(minor_r * 2, 4),  # Torus cross-section
                    surface_area=round(area, 4),
                ))

        face_id += 1
        explorer.Next()

    return features


def _axes_parallel(dir1: tuple, dir2: tuple, tolerance_deg: float) -> bool:
    """Check if two axis directions are parallel (or anti-parallel)."""
    d1 = np.array(dir1)
    d2 = np.array(dir2)
    d1 = d1 / (np.linalg.norm(d1) + 1e-12)
    d2 = d2 / (np.linalg.norm(d2) + 1e-12)
    cos_angle = abs(np.dot(d1, d2))
    angle_deg = math.degrees(math.acos(min(cos_angle, 1.0)))
    return angle_deg < tolerance_deg


def _centers_coaxial(
    center1: tuple, center2: tuple, axis: tuple, distance_tol: float
) -> bool:
    """Check if two centers lie on the same axis (within tolerance)."""
    c1 = np.array(center1)
    c2 = np.array(center2)
    ax = np.array(axis)
    ax = ax / (np.linalg.norm(ax) + 1e-12)

    diff = c2 - c1
    proj = np.dot(diff, ax) * ax
    perp = diff - proj
    perp_dist = np.linalg.norm(perp)

    return perp_dist < distance_tol


def group_coaxial_features(features: list[CylindricalFeature]) -> list[HoleGroup]:
    """Group cylindrical features that share the same axis into hole groups.

    Coaxial features (e.g., counterbore = wide cylinder + narrow cylinder on same axis)
    are grouped into a single HoleGroup.
    """
    if not features:
        return []

    used = set()
    groups = []
    group_counter = 0

    for i, feat_i in enumerate(features):
        if i in used:
            continue

        group_members = [feat_i]
        used.add(i)

        for j, feat_j in enumerate(features):
            if j in used:
                continue

            if (_axes_parallel(feat_i.axis_direction, feat_j.axis_direction,
                               COAXIAL_ANGLE_TOLERANCE_DEG)
                and _centers_coaxial(feat_i.center, feat_j.center,
                                     feat_i.axis_direction,
                                     COAXIAL_DISTANCE_TOLERANCE_MM)):
                group_members.append(feat_j)
                used.add(j)

        group_counter += 1
        group_id = f"hole_{group_counter:03d}"

        for m in group_members:
            m.group_id = group_id

        diameters = sorted(set(round(m.diameter, 2) for m in group_members))
        has_conical = any(m.is_conical for m in group_members)

        if len(diameters) == 1 and not has_conical:
            hole_type = "simple"
        elif has_conical:
            hole_type = "countersink"
        elif len(diameters) == 2:
            hole_type = "counterbore"
        else:
            hole_type = "stepped"

        primary_d = min(m.diameter for m in group_members)
        max_d = max(m.diameter for m in group_members)
        secondary_d = round(max_d, 4) if len(diameters) > 1 and max_d > primary_d + 0.1 else None
        total_depth = sum(m.estimated_depth for m in group_members)

        primary_feat = min(group_members, key=lambda f: f.diameter)

        groups.append(HoleGroup(
            id=group_id,
            features=group_members,
            primary_diameter=round(primary_d, 4),
            secondary_diameter=secondary_d,
            total_depth=round(total_depth, 4),
            center=primary_feat.center,
            axis_direction=primary_feat.axis_direction,
            hole_type=hole_type,
        ))

    return groups


def detect_through_holes(
    shape: TopoDS_Shape, groups: list[HoleGroup]
) -> list[HoleGroup]:
    """Detect which hole groups are through-holes based on bounding box analysis."""
    bb_min, bb_max = get_bounding_box(shape)
    body_dims = np.array(bb_max) - np.array(bb_min)

    for group in groups:
        axis = np.abs(np.array(group.axis_direction))
        body_depth_along_axis = float(np.dot(axis, body_dims))

        if body_depth_along_axis > 0:
            depth_ratio = group.total_depth / body_depth_along_axis
            if depth_ratio >= 0.9:
                group.is_through_hole = True
                for feat in group.features:
                    feat.is_through_hole = True

    return groups
