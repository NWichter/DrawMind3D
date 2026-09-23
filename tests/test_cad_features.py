"""Tests for coaxial grouping and through-hole detection."""

import pytest

from drawmind.cad.feature_extractor import (
    detect_through_holes,
    extract_cylindrical_faces,
    group_coaxial_features,
)


class TestCoaxialGrouping:
    """Built from real solids: a feature's stored centre is the surface
    origin, not a midpoint, so hand-made features test the wrong contract."""

    def test_counterbore_is_one_hole(self):
        shape = _cut_cylinder(_plate(20.0), 30.0, 30.0, -1.0, 8.5, 22.0)
        shape = _cut_cylinder(shape, 30.0, 30.0, 14.0, 15.0, 7.0)

        groups = group_coaxial_features(extract_cylindrical_faces(shape))
        assert len(groups) == 1
        assert len(groups[0].features) == 2
        assert groups[0].secondary_diameter == pytest.approx(15.0, abs=0.1)

    def test_holes_far_apart_on_one_axis_stay_separate(self):
        """Two lugs drilled on a shared axis are two holes, not one."""
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCP.gp import gp_Pnt

        lower = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 20.0, 20.0, 10.0).Shape()
        upper = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 60), 20.0, 20.0, 10.0).Shape()
        shape = _cut_cylinder(BRepAlgoAPI_Fuse(lower, upper).Shape(), 10.0, 10.0, -1.0, 8.0, 80.0)

        groups = group_coaxial_features(extract_cylindrical_faces(shape))
        assert len(groups) == 2, "distinct holes on a shared axis were merged"

    def test_offset_axes_stay_separate(self):
        shape = _cut_cylinder(_plate(20.0), 20.0, 30.0, -1.0, 8.0, 22.0)
        shape = _cut_cylinder(shape, 45.0, 30.0, -1.0, 8.0, 22.0)
        assert len(group_coaxial_features(extract_cylindrical_faces(shape))) == 2


def _cut_cylinder(solid, x, y, z, diameter, length):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    axis = gp_Ax2(gp_Pnt(x, y, z), gp_Dir(0, 0, 1))
    tool = BRepPrimAPI_MakeCylinder(axis, diameter / 2, length).Shape()
    return BRepAlgoAPI_Cut(solid, tool).Shape()


def _plate(thickness, side=60.0):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt

    return BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), side, side, thickness).Shape()


def _l_bracket(foot_thickness=10.0, upright_height=100.0):
    """A foot with a tall upright, so the part is long along the hole axis."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt

    foot = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 60.0, 60.0, foot_thickness).Shape()
    upright = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 10.0, 60.0, upright_height).Shape()
    return BRepAlgoAPI_Fuse(foot, upright).Shape()


def _classify(shape):
    groups = group_coaxial_features(extract_cylindrical_faces(shape))
    assert groups, "no cylindrical feature found in the test solid"
    return detect_through_holes(shape, groups)


class TestConicalDepth:
    def test_countersink_depth_is_the_face_extent(self):
        """A 90 degree countersink from 15 to 8.5 mm is 3.25 mm deep."""
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

        plate = _plate(20.0)
        axis = gp_Ax2(gp_Pnt(30.0, 30.0, 20.0 - 3.25), gp_Dir(0, 0, 1))
        cone = BRepPrimAPI_MakeCone(axis, 4.25, 7.5, 3.25).Shape()
        shape = BRepAlgoAPI_Cut(plate, cone).Shape()

        cones = [f for f in extract_cylindrical_faces(shape) if f.is_conical]
        assert cones, "conical face not detected"
        assert cones[0].estimated_depth == pytest.approx(3.25, abs=0.2)


class TestThroughHoleDetection:
    def test_hole_through_a_flange_of_a_tall_part(self):
        """The hole clears the 10 mm foot, but the part is 100 mm along that axis."""
        shape = _cut_cylinder(_l_bracket(), 35.0, 30.0, -1.0, 6.0, 12.0)
        groups = _classify(shape)
        assert any(g.is_through_hole for g in groups), "through hole reported as blind"

    def test_deep_blind_hole_is_not_through(self):
        """19 mm into a 20 mm plate is 0.95 of the thickness but still blind."""
        shape = _cut_cylinder(_plate(20.0), 30.0, 30.0, 1.0, 6.0, 19.0)
        groups = _classify(shape)
        assert not any(g.is_through_hole for g in groups), "blind hole reported as through"

    @pytest.mark.parametrize("thickness", [8.0, 25.0])
    def test_plain_through_hole(self, thickness):
        shape = _cut_cylinder(_plate(thickness), 30.0, 30.0, -1.0, 6.0, thickness + 2.0)
        assert any(g.is_through_hole for g in _classify(shape))


class TestSecondReviewGeometry:
    def test_three_stacked_segments_form_one_bore(self):
        """Ø8, Ø12 and Ø18 stacked: the outer two only meet through the middle one."""
        shape = _cut_cylinder(_plate(15.0), 30.0, 30.0, -1.0, 8.0, 6.0)
        shape = _cut_cylinder(shape, 30.0, 30.0, 5.0, 12.0, 5.0)
        shape = _cut_cylinder(shape, 30.0, 30.0, 10.0, 18.0, 6.0)

        groups = group_coaxial_features(extract_cylindrical_faces(shape))
        assert len(groups) == 1, f"one stepped bore split into {len(groups)} groups"
        assert groups[0].hole_type == "stepped"
        assert groups[0].total_depth == pytest.approx(15.0, abs=0.1)

    def test_thin_floor_under_a_blind_hole(self):
        """1.2 mm deep into a 1.5 mm plate leaves a 0.3 mm floor: still blind."""
        shape = _cut_cylinder(_plate(1.5), 30.0, 30.0, 0.3, 6.0, 2.0)
        groups = _classify(shape)
        assert not any(g.is_through_hole for g in groups), "thin floor stepped over"
