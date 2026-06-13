"""Export a QWalk guide armature and mesh as a training OBJ/JSON pair."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qwalk_label_common import (
    GUIDE_BONE_NAMES,
    build_label_metadata,
    write_manifest_and_info,
)


def parse_args() -> argparse.Namespace:
    script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Export a QWalk guide armature label.")
    parser.add_argument("--mesh", required=True, help="Mesh object name to export.")
    parser.add_argument("--guide", required=True, help="QWalk guide armature object name.")
    parser.add_argument("--out-dir", required=True, help="Output directory containing train/val/test split folders.")
    parser.add_argument("--id", required=True, help="Sample id, e.g. real_horse_000.")
    parser.add_argument("--split", default="train", choices=("train", "val", "test"))
    parser.add_argument("--animal-type", required=True)
    parser.add_argument("--morphology-type", required=True)
    parser.add_argument("--source", default="real_qwalk_label_v1")
    parser.add_argument(
        "--mesh-forward-axis",
        default="POS_Y",
        choices=("POS_X", "NEG_X", "POS_Y", "NEG_Y"),
        help="World axis pointing from tail toward head. Output is canonicalized to +Y.",
    )
    parser.add_argument(
        "--verified",
        action="store_true",
        help="Mark the exported label as reviewed ground truth and eligible for real-data training.",
    )
    return parser.parse_args(script_args)


def resolve_object(name: str, expected_type: str) -> bpy.types.Object:
    obj = bpy.data.objects.get(name)
    if obj and obj.type == expected_type:
        return obj
    if expected_type == "ARMATURE":
        guides = [candidate for candidate in bpy.data.objects if candidate.type == "ARMATURE" and candidate.get("qwg_is_guide")]
        if len(guides) == 1:
            guide = guides[0]
            print(f"Guide object not found by stored name {name!r}; using marked guide {guide.name!r}.")
            return guide
    if not obj or obj.type != expected_type:
        raise ValueError(f"{expected_type} object not found: {name}")
    return obj


def write_obj(mesh_object: bpy.types.Object, path: Path, forward_axis: str) -> None:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = mesh_object.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            handle.write(f"# Real QWalk training mesh from {bpy.data.filepath} object {mesh_object.name}\n")
            for vertex in mesh.vertices:
                point = canonical_point(evaluated.matrix_world @ vertex.co, forward_axis)
                handle.write(f"v {point.x:.6f} {point.y:.6f} {point.z:.6f}\n")
            for polygon in mesh.polygons:
                indices = " ".join(str(index + 1) for index in polygon.vertices)
                handle.write(f"f {indices}\n")
    finally:
        evaluated.to_mesh_clear()


def point_list(vector) -> list[float]:
    return [round(float(vector.x), 6), round(float(vector.y), 6), round(float(vector.z), 6)]


def canonical_point(point: Vector, forward_axis: str) -> Vector:
    """Rotate a world-space point into canonical +Y-forward training space."""
    if forward_axis == "POS_Y":
        return point.copy()
    if forward_axis == "NEG_Y":
        return Vector((-point.x, -point.y, point.z))
    if forward_axis == "POS_X":
        return Vector((-point.y, point.x, point.z))
    if forward_axis == "NEG_X":
        return Vector((point.y, -point.x, point.z))
    raise ValueError(f"Unsupported forward axis: {forward_axis}")


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


def main() -> None:
    args = parse_args()
    mesh = resolve_object(args.mesh, "MESH")
    guide = resolve_object(args.guide, "ARMATURE")
    out_dir = Path(args.out_dir).expanduser().resolve()
    split_dir = out_dir / args.split
    split_dir.mkdir(parents=True, exist_ok=True)
    obj_path = split_dir / f"{args.id}.obj"
    json_path = split_dir / f"{args.id}.json"

    write_obj(mesh, obj_path, args.mesh_forward_axis)
    guide_bones = export_guide_bones(guide, args.mesh_forward_axis)
    metadata = build_label_metadata(
        sample_id=args.id,
        source=args.source,
        verified=args.verified,
        animal_type=args.animal_type,
        morphology_type=args.morphology_type,
        guide_bones=guide_bones,
        split=args.split,
        parameters={
            "blend_file": bpy.data.filepath,
            "mesh_object": mesh.name,
            "guide_object": guide.name,
            "source_mesh_forward_axis": args.mesh_forward_axis,
            "label_note": (
                "Reviewed ground-truth label."
                if args.verified
                else "Candidate label; inspect and correct before using for training."
            ),
        },
    )
    json_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    write_manifest_and_info(out_dir, metadata)
    print(f"Exported real QWalk label {args.id} to {json_path}")


if __name__ == "__main__":
    main()
