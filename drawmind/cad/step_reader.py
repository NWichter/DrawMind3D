"""STEP file reader using OCP (cadquery-ocp)."""

from pathlib import Path

from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDF import TDF_LabelSequence
from OCP.TCollection import TCollection_ExtendedString
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


def load_step_with_names(filepath: str | Path):
    """Load a STEP file preserving names and structure via XCAF.

    Args:
        filepath: Path to the STEP file

    Returns:
        Tuple of (document, shape_tool, label_sequence)
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"STEP file not found: {filepath}")

    doc = TDocStd_Document(TCollection_ExtendedString("drawmind3d-doc"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(True)

    status = reader.ReadFile(str(filepath))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"Error reading STEP file: {filepath}")

    reader.Transfer(doc)

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(labels)

    return doc, shape_tool, labels


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
