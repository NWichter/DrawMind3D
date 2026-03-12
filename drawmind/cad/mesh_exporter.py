"""Export STEP models to web-viewable formats (GLB/glTF)."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from OCP.TopoDS import TopoDS, TopoDS_Shape
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from OCP.StlAPI import StlAPI_Writer


def export_stl(shape: TopoDS_Shape, output_path: str | Path, linear_deflection: float = 0.1) -> Path:
    """Export shape to STL format (simple fallback).

    Args:
        shape: The CAD shape to export
        output_path: Path for the output STL file
        linear_deflection: Mesh quality (smaller = finer mesh)

    Returns:
        Path to the written file
    """
    output_path = Path(output_path)
    mesh = BRepMesh_IncrementalMesh(shape, linear_deflection)
    mesh.Perform()

    writer = StlAPI_Writer()
    writer.SetASCIIMode(False)
    writer.Write(shape, str(output_path))

    return output_path


def tessellate_shape(shape: TopoDS_Shape, linear_deflection: float = 0.1) -> dict:
    """Tessellate a shape and return vertices/faces per face ID.

    Returns:
        Dict mapping face_id -> {"vertices": [...], "normals": [...], "indices": [...]}
    """
    mesh = BRepMesh_IncrementalMesh(shape, linear_deflection)
    mesh.Perform()

    face_meshes = {}
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_id = 0

    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)

        if triangulation is not None:
            vertices = []
            normals = []
            indices = []

            trsf = location.Transformation()
            nb_nodes = triangulation.NbNodes()
            nb_triangles = triangulation.NbTriangles()

            for i in range(1, nb_nodes + 1):
                node = triangulation.Node(i)
                node.Transform(trsf)
                vertices.extend([node.X(), node.Y(), node.Z()])

            if triangulation.HasNormals():
                for i in range(1, nb_nodes + 1):
                    normal = triangulation.Normal(i)
                    normals.extend([normal.X(), normal.Y(), normal.Z()])

            for i in range(1, nb_triangles + 1):
                tri = triangulation.Triangle(i)
                n1, n2, n3 = tri.Get()
                indices.extend([n1 - 1, n2 - 1, n3 - 1])

            face_meshes[face_id] = {
                "vertices": vertices,
                "normals": normals,
                "indices": indices,
            }

        face_id += 1
        explorer.Next()

    return face_meshes


def export_glb(shape: TopoDS_Shape, output_path: str | Path,
               linear_deflection: float = 0.1,
               highlight_face_ids: list[int] | None = None) -> Path:
    """Export shape to GLB (binary glTF) format for Three.js."""
    output_path = Path(output_path)
    face_meshes = tessellate_shape(shape, linear_deflection)

    if not face_meshes:
        raise RuntimeError("No tessellation data produced")

    all_vertices = []
    all_normals = []
    all_indices = []
    vertex_offset = 0

    for fid, mesh_data in sorted(face_meshes.items()):
        verts = mesh_data["vertices"]
        norms = mesh_data["normals"]
        idxs = mesh_data["indices"]

        all_vertices.extend(verts)
        if norms:
            all_normals.extend(norms)
        all_indices.extend([idx + vertex_offset for idx in idxs])
        vertex_offset += len(verts) // 3

    gltf = _build_gltf(all_vertices, all_normals, all_indices)

    gltf_json = json.dumps(gltf["json"], separators=(",", ":")).encode("utf-8")
    while len(gltf_json) % 4 != 0:
        gltf_json += b" "

    bin_data = gltf["bin"]
    while len(bin_data) % 4 != 0:
        bin_data += b"\x00"

    with open(output_path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(gltf_json) + 8 + len(bin_data)))
        f.write(struct.pack("<II", len(gltf_json), 0x4E4F534A))
        f.write(gltf_json)
        f.write(struct.pack("<II", len(bin_data), 0x004E4942))
        f.write(bin_data)

    return output_path


def _build_gltf(vertices: list[float], normals: list[float], indices: list[int]) -> dict:
    """Build a minimal glTF 2.0 JSON + binary buffer."""
    bin_parts = []

    idx_data = struct.pack(f"<{len(indices)}I", *indices)
    idx_offset = 0
    idx_length = len(idx_data)
    bin_parts.append(idx_data)

    padding = (4 - len(idx_data) % 4) % 4
    bin_parts.append(b"\x00" * padding)

    vert_offset = idx_length + padding
    vert_data = struct.pack(f"<{len(vertices)}f", *vertices)
    vert_length = len(vert_data)
    bin_parts.append(vert_data)

    total_bin = b"".join(bin_parts)

    xs = vertices[0::3]
    ys = vertices[1::3]
    zs = vertices[2::3]

    gltf_json = {
        "asset": {"version": "2.0", "generator": "DrawMind3D"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{
            "primitives": [{
                "attributes": {"POSITION": 1},
                "indices": 0,
                "material": 0,
            }]
        }],
        "materials": [{
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.7, 0.75, 0.8, 1.0],
                "metallicFactor": 0.3,
                "roughnessFactor": 0.6,
            },
            "doubleSided": True,
        }],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5125,
                "count": len(indices),
                "type": "SCALAR",
                "max": [max(indices)] if indices else [0],
                "min": [min(indices)] if indices else [0],
            },
            {
                "bufferView": 1,
                "componentType": 5126,
                "count": len(vertices) // 3,
                "type": "VEC3",
                "max": [max(xs), max(ys), max(zs)] if xs else [0, 0, 0],
                "min": [min(xs), min(ys), min(zs)] if xs else [0, 0, 0],
            },
        ],
        "bufferViews": [
            {
                "buffer": 0,
                "byteOffset": idx_offset,
                "byteLength": idx_length,
                "target": 34963,
            },
            {
                "buffer": 0,
                "byteOffset": vert_offset,
                "byteLength": vert_length,
                "target": 34962,
            },
        ],
        "buffers": [{"byteLength": len(total_bin)}],
    }

    if normals and len(normals) == len(vertices):
        norm_padding = (4 - len(total_bin) % 4) % 4
        norm_data = struct.pack(f"<{len(normals)}f", *normals)
        norm_offset = len(total_bin) + norm_padding

        total_bin += b"\x00" * norm_padding + norm_data

        gltf_json["accessors"].append({
            "bufferView": 2,
            "componentType": 5126,
            "count": len(normals) // 3,
            "type": "VEC3",
        })
        gltf_json["bufferViews"].append({
            "buffer": 0,
            "byteOffset": norm_offset,
            "byteLength": len(norm_data),
            "target": 34962,
        })
        gltf_json["meshes"][0]["primitives"][0]["attributes"]["NORMAL"] = 2
        gltf_json["buffers"][0]["byteLength"] = len(total_bin)

    return {"json": gltf_json, "bin": total_bin}
