"""Export one Blender mesh object's world-space geometry as a simple OBJ."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy


def parse_args() -> argparse.Namespace:
    script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Export one mesh object as OBJ.")
    parser.add_argument("--mesh", default="", help="Mesh object name. Defaults to the first mesh in the scene.")
    parser.add_argument("--out", required=True, help="Output OBJ path.")
    return parser.parse_args(script_args)


def resolve_mesh(name: str) -> bpy.types.Object:
    if name:
        obj = bpy.data.objects.get(name)
        if not obj or obj.type != "MESH":
            raise ValueError(f"Mesh object not found: {name}")
        return obj

    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise ValueError("Scene contains no mesh objects.")
    if len(meshes) > 1:
        names = ", ".join(obj.name for obj in meshes)
        raise ValueError(f"Scene has multiple meshes; pass --mesh. Found: {names}")
    return meshes[0]


def export_obj(mesh_object: bpy.types.Object, out_path: Path) -> None:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = mesh_object.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as handle:
            handle.write(f"# Exported from {bpy.data.filepath} object {mesh_object.name}\n")
            for vertex in mesh.vertices:
                point = evaluated.matrix_world @ vertex.co
                handle.write(f"v {point.x:.6f} {point.y:.6f} {point.z:.6f}\n")
            for polygon in mesh.polygons:
                indices = " ".join(str(index + 1) for index in polygon.vertices)
                handle.write(f"f {indices}\n")
    finally:
        evaluated.to_mesh_clear()


def main() -> None:
    args = parse_args()
    mesh = resolve_mesh(args.mesh)
    out_path = Path(args.out).expanduser().resolve()
    export_obj(mesh, out_path)
    print(f"Exported {mesh.name} to {out_path}")


if __name__ == "__main__":
    main()
