"""STEP file reader using OCP (cadquery-ocp)."""

from pathlib import Path

from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopoDS import TopoDS_Shape
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib


def load_step(filepath: str | Path) -> TopoDS_Shape:
    """Load a STEP file and return the shape.

    Args:
        filepath: Path to the STEP file (.step or .stp)

    Returns:
        The loaded shape

    Raises:
        FileNotFoundError: If the file does not exist
        RuntimeError: If the STEP file cannot be read
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"STEP file not found: {filepath}")

    reader = STEPControl_Reader()
    status = reader.ReadFile(str(filepath))

    if status != IFSelect_RetDone:
        raise RuntimeError(f"Error reading STEP file: {filepath} (status={status})")

    reader.TransferRoots()
    shape = reader.OneShape()
    return shape


def get_bounding_box(
    shape: TopoDS_Shape,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Get the axis-aligned bounding box of a shape.

    Returns:
        Tuple of (min_corner, max_corner) as (x, y, z) tuples
    """
    bbox = Bnd_Box()
    BRepBndLib.Add_s(shape, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    return (xmin, ymin, zmin), (xmax, ymax, zmax)
