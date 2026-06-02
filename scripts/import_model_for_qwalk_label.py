"""Import a generated 3D model into a clean Blender file for QWalk labeling."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy


SUPPORTED_EXTENSIONS = {".glb", ".gltf", ".obj", ".fbx"}


def parse_args() -> argparse.Namespace:
    script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Import a generated model into a QWalk labeling blend.")
    parser.add_argument("model_file", help="Model file to import: .glb, .gltf, .obj, or .fbx.")
    parser.add_argument("--output", required=True, help="Output .blend path.")
    parser.add_argument("--mesh-name", default="", help="Name for the selected/joined mesh object.")
    parser.add_argument(
        "--no-join-meshes",
        action="store_true",
        help="Keep imported meshes separate and choose the largest mesh as the label target.",
    )
    return parser.parse_args(script_args)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def import_model(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported model extension {suffix}. Expected one of {sorted(SUPPORTED_EXTENSIONS)}.")

    if suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif suffix == ".obj":
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=str(path), forward_axis="Y", up_axis="Z")
        else:
            bpy.ops.import_scene.obj(filepath=str(path), axis_forward="Y", axis_up="Z")


def mesh_volume_hint(obj: bpy.types.Object) -> float:
    size = obj.dimensions
    return float(size.x * size.y * size.z)


def imported_meshes() -> list[bpy.types.Object]:
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise ValueError("Imported file produced no mesh objects.")
    return sorted(meshes, key=mesh_volume_hint, reverse=True)


def make_label_mesh(meshes: list[bpy.types.Object], name: str, join_meshes: bool) -> bpy.types.Object:
    if join_meshes and len(meshes) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        active = meshes[0]
        for mesh in meshes:
            mesh.select_set(True)
        bpy.context.view_layer.objects.active = active
        bpy.ops.object.join()
        label_mesh = bpy.context.view_layer.objects.active
    else:
        label_mesh = meshes[0]

    if name:
        label_mesh.name = name
        label_mesh.data.name = f"{name}_MeshData"
    label_mesh["qwalk_label_target"] = True
    label_mesh.select_set(True)
    bpy.context.view_layer.objects.active = label_mesh
    return label_mesh


def main() -> None:
    args = parse_args()
    model_path = Path(args.model_file).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    if not model_path.exists():
        raise FileNotFoundError(model_path)

    clear_scene()
    import_model(model_path)
    label_mesh = make_label_mesh(imported_meshes(), args.mesh_name, join_meshes=not args.no_join_meshes)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
    print(f"Imported {model_path} into {output_path}; label mesh={label_mesh.name}")


if __name__ == "__main__":
    main()
