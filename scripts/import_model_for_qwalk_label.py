"""Import a generated 3D model into a clean Blender file for QWalk labeling."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


SUPPORTED_EXTENSIONS = {".glb", ".gltf", ".obj", ".fbx"}
FORWARD_AXIS_CHOICES = ("AUTO", "POS_Y", "NEG_Y", "POS_X", "NEG_X")
EXPLICIT_FORWARD_AXIS_CHOICES = ("POS_Y", "NEG_Y", "POS_X", "NEG_X")
FORWARD_AXIS_YAW = {
    "POS_Y": 0.0,
    "NEG_Y": math.pi,
    "POS_X": -math.pi * 0.5,
    "NEG_X": math.pi * 0.5,
}


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
    parser.add_argument(
        "--source-forward-axis",
        default="AUTO",
        choices=FORWARD_AXIS_CHOICES,
        help="Imported mesh tail-to-head world axis before normalization. AUTO chooses the dominant horizontal axis.",
    )
    parser.add_argument(
        "--target-forward-axis",
        default="POS_Y",
        choices=EXPLICIT_FORWARD_AXIS_CHOICES,
        help="Canonical tail-to-head world axis to write into the label blend.",
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


def remove_imported_armatures(label_mesh: bpy.types.Object) -> int:
    """Remove source-file rigs so the label blend opens with only Nito-generated guides."""
    label_mesh.parent = None
    for modifier in list(label_mesh.modifiers):
        if modifier.type == "ARMATURE":
            label_mesh.modifiers.remove(modifier)

    removed = 0
    for obj in list(bpy.context.scene.objects):
        if obj.type != "ARMATURE":
            continue
        if obj.get("qwg_is_guide") or obj.get("qwg_guides") or obj.name.startswith("Nito"):
            continue
        bpy.data.objects.remove(obj, do_unlink=True)
        removed += 1
    return removed


def select_active(obj: bpy.types.Object) -> None:
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def axis_angle(axis: str) -> float:
    """Return yaw angle from +Y to the requested horizontal axis."""
    return FORWARD_AXIS_YAW[axis]


def resolve_source_forward_axis(obj: bpy.types.Object, axis: str) -> str:
    if axis != "AUTO":
        return axis
    size = obj.dimensions
    return "POS_X" if size.x > size.y else "POS_Y"


def point_bounds(points: list[Vector]) -> tuple[Vector, Vector]:
    mins = Vector((min(point.x for point in points), min(point.y for point in points), min(point.z for point in points)))
    maxs = Vector((max(point.x for point in points), max(point.y for point in points), max(point.z for point in points)))
    return mins, maxs


def normalize_label_mesh(obj: bpy.types.Object, source_axis: str, target_axis: str) -> str:
    resolved_source_axis = resolve_source_forward_axis(obj, source_axis)
    yaw = axis_angle(target_axis) - axis_angle(resolved_source_axis)

    select_active(obj)
    rotation = Matrix.Rotation(yaw, 4, "Z")
    rotated_points = [rotation @ (obj.matrix_world @ vertex.co) for vertex in obj.data.vertices]

    mins, maxs = point_bounds(rotated_points)
    center = (mins + maxs) * 0.5
    offset = Vector((center.x, center.y, mins.z))

    obj.parent = None
    obj.matrix_world = Matrix.Identity(4)
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    for vertex, point in zip(obj.data.vertices, rotated_points):
        vertex.co = point - offset
    obj.data.update()

    obj["qwalk_source_forward_axis"] = resolved_source_axis
    obj["qwalk_canonical_forward_axis"] = target_axis
    obj["qwalk_orientation_standardized"] = True
    return resolved_source_axis


def main() -> None:
    args = parse_args()
    model_path = Path(args.model_file).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    if not model_path.exists():
        raise FileNotFoundError(model_path)

    clear_scene()
    import_model(model_path)
    label_mesh = make_label_mesh(imported_meshes(), args.mesh_name, join_meshes=not args.no_join_meshes)
    removed_armatures = remove_imported_armatures(label_mesh)
    resolved_source_axis = normalize_label_mesh(label_mesh, args.source_forward_axis, args.target_forward_axis)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
    print(
        f"Imported {model_path} into {output_path}; label mesh={label_mesh.name}; "
        f"normalized {resolved_source_axis} -> {args.target_forward_axis}; "
        f"removed imported armatures={removed_armatures}"
    )


if __name__ == "__main__":
    main()
