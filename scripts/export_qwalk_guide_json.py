"""Dump a QWalk guide armature (and optionally the mesh) to web-editable JSON/OBJ.

Run inside Blender on a label-work file. Writes the guide bone head/tail
coordinates in canonical +Y-forward space so the Nito web editor can load and
edit them without Blender. Label-work blends are already normalized to the
canonical frame, so for those files world space equals canonical space.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


GUIDE_BONE_NAMES = [
    "qwg_guide_pelvis",
    "qwg_guide_spine",
    "qwg_guide_chest",
    "qwg_guide_neck",
    "qwg_guide_head",
    "qwg_guide_tail",
    "qwg_guide_front_left_upper",
    "qwg_guide_front_left_lower",
    "qwg_guide_front_left_foot",
    "qwg_guide_front_right_upper",
    "qwg_guide_front_right_lower",
    "qwg_guide_front_right_foot",
    "qwg_guide_rear_left_upper",
    "qwg_guide_rear_left_lower",
    "qwg_guide_rear_left_foot",
    "qwg_guide_rear_right_upper",
    "qwg_guide_rear_right_lower",
    "qwg_guide_rear_right_foot",
]


def parse_args() -> argparse.Namespace:
    script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Dump QWalk guide bones to canonical JSON.")
    parser.add_argument("--guide", default="", help="Guide armature name. Defaults to the marked QWalk guide.")
    parser.add_argument("--out", required=True, help="Output guide JSON path.")
    parser.add_argument("--mesh", default="", help="Optional mesh object name to export as canonical OBJ.")
    parser.add_argument("--mesh-out", default="", help="Output OBJ path when --mesh is set.")
    parser.add_argument(
        "--mesh-forward-axis",
        default="POS_Y",
        choices=("POS_X", "NEG_X", "POS_Y", "NEG_Y"),
        help="World axis pointing from tail toward head. Output is canonicalized to +Y.",
    )
    return parser.parse_args(script_args)


def resolve_guide(name: str) -> bpy.types.Object:
    if name:
        obj = bpy.data.objects.get(name)
        if obj and obj.type == "ARMATURE":
            return obj
    guides = [obj for obj in bpy.data.objects if obj.type == "ARMATURE" and obj.get("qwg_is_guide")]
    if len(guides) == 1:
        return guides[0]
    if name:
        raise ValueError(f"Guide armature not found: {name}")
    if not guides:
        raise ValueError("Scene contains no QWalk guide armature.")
    names = ", ".join(obj.name for obj in guides)
    raise ValueError(f"Scene has multiple QWalk guides; pass --guide. Found: {names}")


def canonical_point(point: Vector, forward_axis: str) -> Vector:
    if forward_axis == "POS_Y":
        return point.copy()
    if forward_axis == "NEG_Y":
        return Vector((-point.x, -point.y, point.z))
    if forward_axis == "POS_X":
        return Vector((-point.y, point.x, point.z))
    if forward_axis == "NEG_X":
        return Vector((point.y, -point.x, point.z))
    raise ValueError(f"Unsupported forward axis: {forward_axis}")


def point_list(vector: Vector) -> list[float]:
    return [round(float(vector.x), 6), round(float(vector.y), 6), round(float(vector.z), 6)]


def export_guide_bones(guide: bpy.types.Object, forward_axis: str) -> dict[str, dict[str, list[float]]]:
    guide_bones = {}
    missing = []
    for name in GUIDE_BONE_NAMES:
        bone = guide.data.bones.get(name)
        if not bone:
            missing.append(name)
            continue
        guide_bones[name] = {
            "head": point_list(canonical_point(guide.matrix_world @ bone.head_local, forward_axis)),
            "tail": point_list(canonical_point(guide.matrix_world @ bone.tail_local, forward_axis)),
        }
    if missing:
        raise ValueError(f"Guide is missing required bones: {', '.join(missing)}")
    return guide_bones


def write_canonical_obj(mesh_name: str, path: Path, forward_axis: str) -> None:
    mesh_object = bpy.data.objects.get(mesh_name)
    if not mesh_object or mesh_object.type != "MESH":
        raise ValueError(f"Mesh object not found: {mesh_name}")
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = mesh_object.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            handle.write(f"# Canonical QWalk mesh from {bpy.data.filepath} object {mesh_object.name}\n")
            for vertex in mesh.vertices:
                point = canonical_point(evaluated.matrix_world @ vertex.co, forward_axis)
                handle.write(f"v {point.x:.6f} {point.y:.6f} {point.z:.6f}\n")
            for polygon in mesh.polygons:
                indices = " ".join(str(index + 1) for index in polygon.vertices)
                handle.write(f"f {indices}\n")
    finally:
        evaluated.to_mesh_clear()


def main() -> None:
    args = parse_args()
    guide = resolve_guide(args.guide)
    out_path = Path(args.out).expanduser().resolve()
    guide_bones = export_guide_bones(guide, args.mesh_forward_axis)
    payload = {
        "coordinate_space": "canonical",
        "mesh_forward_axis": "POS_Y",
        "source_blend": bpy.data.filepath,
        "guide_object": guide.name,
        "guide_bones": guide_bones,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Exported guide JSON for {guide.name} to {out_path}")

    if args.mesh and args.mesh_out:
        mesh_out = Path(args.mesh_out).expanduser().resolve()
        write_canonical_obj(args.mesh, mesh_out, args.mesh_forward_axis)
        print(f"Exported canonical mesh OBJ to {mesh_out}")


if __name__ == "__main__":
    main()
