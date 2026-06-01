"""Apply precise QWalk guide bone coordinate edits to a Blender file.

The edit JSON may contain full or partial guide_bones data:

{
  "coordinate_space": "world",
  "mesh_forward_axis": "POS_X",
  "guide_bones": {
    "qwg_guide_front_left_foot": {"tail": [1.2, 0.0, 0.04]}
  }
}

When coordinate_space is "canonical", coordinates are interpreted as +Y-forward
training coordinates and converted back to the source Blender world space using
mesh_forward_axis.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Apply coordinate edits to a QWalk guide armature.")
    parser.add_argument("edits_json", help="JSON containing guide_bones edits.")
    parser.add_argument("--guide", default="", help="Guide armature name. Defaults to the first QWalk guide.")
    parser.add_argument("--output", default="", help="Output .blend path. Defaults to saving the current file.")
    parser.add_argument(
        "--coordinate-space",
        default="",
        choices=("", "world", "canonical"),
        help="Override coordinate_space from the edit JSON.",
    )
    parser.add_argument(
        "--mesh-forward-axis",
        default="",
        choices=("", "POS_X", "NEG_X", "POS_Y", "NEG_Y"),
        help="Override mesh_forward_axis from the edit JSON for canonical edits.",
    )
    return parser.parse_args(script_args)


def resolve_guide(name: str) -> bpy.types.Object:
    if name:
        obj = bpy.data.objects.get(name)
        if not obj or obj.type != "ARMATURE":
            raise ValueError(f"Guide armature not found: {name}")
        return obj

    guides = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE" and obj.get("qwg_is_guide")]
    if not guides:
        raise ValueError("Scene contains no QWalk guide armature.")
    if len(guides) > 1:
        names = ", ".join(obj.name for obj in guides)
        raise ValueError(f"Scene has multiple QWalk guides; pass --guide. Found: {names}")
    return guides[0]


def canonical_to_world(point: Vector, forward_axis: str) -> Vector:
    if forward_axis == "POS_Y":
        return point.copy()
    if forward_axis == "NEG_Y":
        return Vector((-point.x, -point.y, point.z))
    if forward_axis == "POS_X":
        return Vector((point.y, -point.x, point.z))
    if forward_axis == "NEG_X":
        return Vector((-point.y, point.x, point.z))
    raise ValueError(f"Unsupported mesh_forward_axis: {forward_axis}")


def edit_point(values: list[float], coordinate_space: str, forward_axis: str) -> Vector:
    point = Vector((float(values[0]), float(values[1]), float(values[2])))
    if coordinate_space == "world":
        return point
    if coordinate_space == "canonical":
        return canonical_to_world(point, forward_axis)
    raise ValueError(f"Unsupported coordinate_space: {coordinate_space}")


def apply_edits(guide: bpy.types.Object, metadata: dict, coordinate_space: str, forward_axis: str) -> None:
    guide_bones = metadata.get("guide_bones") or metadata.get("predicted_guide_bones")
    if not guide_bones:
        raise ValueError("Edit JSON must contain guide_bones or predicted_guide_bones.")

    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    guide.select_set(True)
    bpy.context.view_layer.objects.active = guide
    bpy.ops.object.mode_set(mode="EDIT")

    inverse = guide.matrix_world.inverted()
    try:
        for bone_name, endpoints in guide_bones.items():
            bone = guide.data.edit_bones.get(bone_name)
            if bone is None:
                raise ValueError(f"Guide bone missing: {bone_name}")

            if "tail" in endpoints:
                bone.tail = inverse @ edit_point(endpoints["tail"], coordinate_space, forward_axis)

        for bone_name, endpoints in guide_bones.items():
            bone = guide.data.edit_bones.get(bone_name)
            if "head" not in endpoints:
                continue
            desired_head = inverse @ edit_point(endpoints["head"], coordinate_space, forward_axis)
            if bone.use_connect and bone.parent:
                bone.parent.tail = desired_head
            else:
                bone.head = desired_head
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def main() -> None:
    args = parse_args()
    edits_path = Path(args.edits_json).expanduser().resolve()
    metadata = json.loads(edits_path.read_text(encoding="utf-8"))
    coordinate_space = args.coordinate_space or metadata.get("coordinate_space", "world")
    forward_axis = args.mesh_forward_axis or metadata.get("mesh_forward_axis", "POS_Y")
    guide = resolve_guide(args.guide)

    apply_edits(guide, metadata, coordinate_space, forward_axis)

    output_path = Path(args.output).expanduser().resolve() if args.output else Path(bpy.data.filepath)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
    print(f"Applied QWalk guide edits from {edits_path} to {output_path} guide={guide.name}")


if __name__ == "__main__":
    main()
