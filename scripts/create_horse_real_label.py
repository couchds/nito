"""Create a real QWalk label for Horse.blend.

This is intentionally a supervised bootstrap label, not an automatic result:
the guide points are hand-authored in canonical +Y-forward coordinates for the
stylized horse asset, then overlaid onto the original +X-forward Blender scene.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


SAMPLE_ID = "real_horse_000"
MESH_NAME = "tripo_node_06e956d7-e4d0-4801-82d3-8a6d1cd4a24d"
GUIDE_NAME = "Horse_Real_Label_Guides"


GUIDE_POINTS = {
    "pelvis_head": (0.0, -0.36, 0.56),
    "pelvis_tail": (0.0, -0.20, 0.59),
    "spine_tail": (0.0, 0.02, 0.60),
    "chest_tail": (0.0, 0.20, 0.63),
    "neck_tail": (0.0, 0.36, 0.80),
    "head_tail": (0.0, 0.49, 0.68),
    "tail_tail": (0.0, -0.50, 0.42),
    "front_left_upper": (0.075, 0.18, 0.55),
    "front_left_mid": (0.075, 0.17, 0.35),
    "front_left_lower": (0.075, 0.22, 0.13),
    "front_left_foot": (0.075, 0.25, 0.025),
    "front_right_upper": (-0.075, 0.18, 0.55),
    "front_right_mid": (-0.075, 0.17, 0.35),
    "front_right_lower": (-0.075, 0.22, 0.13),
    "front_right_foot": (-0.075, 0.25, 0.025),
    "rear_left_upper": (0.075, -0.34, 0.50),
    "rear_left_mid": (0.075, -0.26, 0.34),
    "rear_left_lower": (0.075, -0.31, 0.13),
    "rear_left_foot": (0.075, -0.23, 0.025),
    "rear_right_upper": (-0.075, -0.34, 0.50),
    "rear_right_mid": (-0.075, -0.26, 0.34),
    "rear_right_lower": (-0.075, -0.31, 0.13),
    "rear_right_foot": (-0.075, -0.23, 0.025),
}

GUIDE_BONES = {
    "qwg_guide_pelvis": ("pelvis_head", "pelvis_tail"),
    "qwg_guide_spine": ("pelvis_tail", "spine_tail"),
    "qwg_guide_chest": ("spine_tail", "chest_tail"),
    "qwg_guide_neck": ("chest_tail", "neck_tail"),
    "qwg_guide_head": ("neck_tail", "head_tail"),
    "qwg_guide_tail": ("pelvis_head", "tail_tail"),
    "qwg_guide_front_left_upper": ("front_left_upper", "front_left_mid"),
    "qwg_guide_front_left_lower": ("front_left_mid", "front_left_lower"),
    "qwg_guide_front_left_foot": ("front_left_lower", "front_left_foot"),
    "qwg_guide_front_right_upper": ("front_right_upper", "front_right_mid"),
    "qwg_guide_front_right_lower": ("front_right_mid", "front_right_lower"),
    "qwg_guide_front_right_foot": ("front_right_lower", "front_right_foot"),
    "qwg_guide_rear_left_upper": ("rear_left_upper", "rear_left_mid"),
    "qwg_guide_rear_left_lower": ("rear_left_mid", "rear_left_lower"),
    "qwg_guide_rear_left_foot": ("rear_left_lower", "rear_left_foot"),
    "qwg_guide_rear_right_upper": ("rear_right_upper", "rear_right_mid"),
    "qwg_guide_rear_right_lower": ("rear_right_mid", "rear_right_lower"),
    "qwg_guide_rear_right_foot": ("rear_right_lower", "rear_right_foot"),
}


def parse_args() -> argparse.Namespace:
    script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Create a real training label for Horse.blend.")
    parser.add_argument("--mesh", default=MESH_NAME)
    parser.add_argument("--out-blend", default="Horse_Real_Label_Guides.blend")
    parser.add_argument("--out-data", default="data/real_quadrupeds")
    return parser.parse_args(script_args)


def point(values: tuple[float, float, float]) -> Vector:
    return Vector(values)


def rotated_to_canonical(world_point: Vector) -> Vector:
    """Map the original +X-forward horse scene into +Y-forward training space."""
    return Vector((-world_point.y, world_point.x, world_point.z))


def create_guide_armature() -> bpy.types.Object:
    existing = bpy.data.objects.get(GUIDE_NAME)
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)

    data = bpy.data.armatures.new(GUIDE_NAME)
    data.display_type = "STICK"
    guide = bpy.data.objects.new(GUIDE_NAME, data)
    guide.show_in_front = True
    guide["qwg_is_guide"] = True
    guide["qwg_profile"] = "HORSE"
    guide["qwg_real_label"] = True
    guide["qwg_synthetic_animal_type"] = "horse"
    guide["qwg_synthetic_morphology_type"] = "ungulate"
    guide.rotation_euler.z = -math.pi * 0.5
    bpy.context.collection.objects.link(guide)

    bpy.ops.object.select_all(action="DESELECT")
    guide.select_set(True)
    bpy.context.view_layer.objects.active = guide
    bpy.ops.object.mode_set(mode="EDIT")

    edit_bones = {}
    for bone_name, (head_name, tail_name) in GUIDE_BONES.items():
        bone = data.edit_bones.new(bone_name)
        bone.head = point(GUIDE_POINTS[head_name])
        bone.tail = point(GUIDE_POINTS[tail_name])
        bone.use_deform = False
        edit_bones[bone_name] = bone

    for parent_name, child_name in (
        ("qwg_guide_pelvis", "qwg_guide_spine"),
        ("qwg_guide_spine", "qwg_guide_chest"),
        ("qwg_guide_chest", "qwg_guide_neck"),
        ("qwg_guide_neck", "qwg_guide_head"),
    ):
        edit_bones[child_name].parent = edit_bones[parent_name]
        edit_bones[child_name].use_connect = True
    edit_bones["qwg_guide_tail"].parent = edit_bones["qwg_guide_pelvis"]

    for parent_name, chain in (
        ("qwg_guide_chest", ("qwg_guide_front_left_upper", "qwg_guide_front_left_lower", "qwg_guide_front_left_foot")),
        ("qwg_guide_chest", ("qwg_guide_front_right_upper", "qwg_guide_front_right_lower", "qwg_guide_front_right_foot")),
        ("qwg_guide_pelvis", ("qwg_guide_rear_left_upper", "qwg_guide_rear_left_lower", "qwg_guide_rear_left_foot")),
        ("qwg_guide_pelvis", ("qwg_guide_rear_right_upper", "qwg_guide_rear_right_lower", "qwg_guide_rear_right_foot")),
    ):
        edit_bones[chain[0]].parent = edit_bones[parent_name]
        edit_bones[chain[1]].parent = edit_bones[chain[0]]
        edit_bones[chain[1]].use_connect = True
        edit_bones[chain[2]].parent = edit_bones[chain[1]]
        edit_bones[chain[2]].use_connect = True

    bpy.ops.object.mode_set(mode="OBJECT")
    return guide


def export_canonical_obj(mesh_object: bpy.types.Object, path: Path) -> None:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = mesh_object.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            handle.write(f"# Canonical +Y horse mesh from {bpy.data.filepath}\n")
            for vertex in mesh.vertices:
                point_value = rotated_to_canonical(evaluated.matrix_world @ vertex.co)
                handle.write(f"v {point_value.x:.6f} {point_value.y:.6f} {point_value.z:.6f}\n")
            for polygon in mesh.polygons:
                indices = " ".join(str(index + 1) for index in polygon.vertices)
                handle.write(f"f {indices}\n")
    finally:
        evaluated.to_mesh_clear()


def guide_bones_json() -> dict[str, dict[str, list[float]]]:
    return {
        bone_name: {
            "head": [round(value, 6) for value in GUIDE_POINTS[head_name]],
            "tail": [round(value, 6) for value in GUIDE_POINTS[tail_name]],
        }
        for bone_name, (head_name, tail_name) in GUIDE_BONES.items()
    }


def landmarks_json() -> dict[str, list[float]]:
    landmarks = {
        "pelvis": GUIDE_POINTS["pelvis_head"],
        "spine": GUIDE_POINTS["spine_tail"],
        "chest": GUIDE_POINTS["chest_tail"],
        "neck": GUIDE_POINTS["neck_tail"],
        "head": GUIDE_POINTS["head_tail"],
        "tail": GUIDE_POINTS["tail_tail"],
    }
    for prefix in ("front_left", "front_right", "rear_left", "rear_right"):
        landmarks[f"{prefix}_upper"] = GUIDE_POINTS[f"{prefix}_upper"]
        landmarks[f"{prefix}_mid"] = GUIDE_POINTS[f"{prefix}_mid"]
        landmarks[f"{prefix}_lower"] = GUIDE_POINTS[f"{prefix}_lower"]
        landmarks[f"{prefix}_foot"] = GUIDE_POINTS[f"{prefix}_foot"]
    return {name: [round(value, 6) for value in values] for name, values in landmarks.items()}


def export_label(mesh_object: bpy.types.Object, out_data: Path) -> None:
    split_dir = out_data / "train"
    split_dir.mkdir(parents=True, exist_ok=True)
    export_canonical_obj(mesh_object, split_dir / f"{SAMPLE_ID}.obj")
    metadata = {
        "id": SAMPLE_ID,
        "source": "real_qwalk_label_v2",
        "verified_label": False,
        "training_eligible": False,
        "animal_type": "horse",
        "morphology_type": "ungulate",
        "axes": {
            "forward": [0.0, 1.0, 0.0],
            "left": [1.0, 0.0, 0.0],
            "up": [0.0, 0.0, 1.0],
        },
        "guide_bones": guide_bones_json(),
        "landmarks": landmarks_json(),
        "parameters": {
            "blend_file": bpy.data.filepath,
            "mesh_object": mesh_object.name,
            "label_note": "Candidate horse label from visual side-view correction; inspect and correct before treating as final ground truth.",
        },
        "split": "train",
        "mesh_file": f"train/{SAMPLE_ID}.obj",
        "label_file": f"train/{SAMPLE_ID}.json",
    }
    label_path = split_dir / f"{SAMPLE_ID}.json"
    label_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (out_data / "manifest.jsonl").write_text(json.dumps(metadata, separators=(",", ":")) + "\n", encoding="utf-8")
    dataset_info = {
        "source": "real_qwalk_label_v2",
        "count": 1,
        "verified_count": 0,
        "animal_counts": {"horse": 1},
        "split_counts": {"train": 1},
        "label_schema": {
            "animal_type": ["horse"],
            "morphology_type": ["ungulate"],
            "guide_bones": "QWalk guide bone head/tail coordinates in canonical +Y mesh space",
            "landmarks": "Simplified joint/centerline landmarks derived from guide_bones",
            "axes": "forward, left, and up vectors in mesh space",
        },
    }
    (out_data / "dataset_info.json").write_text(json.dumps(dataset_info, indent=2) + "\n", encoding="utf-8")
    print(f"Exported real horse label to {label_path}")


def main() -> None:
    args = parse_args()
    mesh = bpy.data.objects.get(args.mesh)
    if not mesh or mesh.type != "MESH":
        raise ValueError(f"Mesh object not found: {args.mesh}")
    guide = create_guide_armature()
    export_label(mesh, Path(args.out_data).expanduser().resolve())
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    guide.select_set(True)
    bpy.context.view_layer.objects.active = guide
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.out_blend).expanduser().resolve()))
    print(f"Saved labeled horse guide preview to {args.out_blend}")


if __name__ == "__main__":
    main()
