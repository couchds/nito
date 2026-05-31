"""Import a synthetic or predicted QWalk sample JSON into Blender.

Run from Blender:

    blender --python scripts/import_synthetic_quadruped_sample.py -- data/synthetic_quadrupeds/train/syn_000000.json

Synthetic labels and ML predictions store guide bones in JSON because OBJ files
do not carry Blender bones. This helper reads the JSON, imports the OBJ mesh,
and creates an editable QWalk guide armature from the stored guide bones.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


SPINE_PARENT_ORDER = [
    "qwg_guide_pelvis",
    "qwg_guide_spine",
    "qwg_guide_chest",
    "qwg_guide_neck",
    "qwg_guide_head",
]

LEG_BONES = {
    "fl": [
        "qwg_guide_front_left_upper",
        "qwg_guide_front_left_lower",
        "qwg_guide_front_left_foot",
    ],
    "fr": [
        "qwg_guide_front_right_upper",
        "qwg_guide_front_right_lower",
        "qwg_guide_front_right_foot",
    ],
    "rl": [
        "qwg_guide_rear_left_upper",
        "qwg_guide_rear_left_lower",
        "qwg_guide_rear_left_foot",
    ],
    "rr": [
        "qwg_guide_rear_right_upper",
        "qwg_guide_rear_right_lower",
        "qwg_guide_rear_right_foot",
    ],
}


def parse_args() -> argparse.Namespace:
    script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Import one synthetic or predicted QWalk sample into Blender.")
    parser.add_argument("json_file", help="Path to a synthetic label JSON or prediction JSON file.")
    parser.add_argument("--no-mesh", action="store_true", help="Only create the guide armature.")
    return parser.parse_args(script_args)


def import_obj(obj_path: Path) -> list[bpy.types.Object]:
    before = set(bpy.context.scene.objects)
    if hasattr(bpy.ops.wm, "obj_import"):
        bpy.ops.wm.obj_import(filepath=str(obj_path), forward_axis="Y", up_axis="Z")
    else:
        bpy.ops.import_scene.obj(filepath=str(obj_path), axis_forward="Y", axis_up="Z")
    return [obj for obj in bpy.context.scene.objects if obj not in before]


def guide_bones_from_metadata(metadata: dict) -> dict:
    guide_bones = metadata.get("guide_bones") or metadata.get("predicted_guide_bones")
    if not guide_bones:
        raise ValueError("JSON must contain guide_bones or predicted_guide_bones.")
    return guide_bones


def source_mesh_path(json_path: Path, metadata: dict) -> Path | None:
    mesh_file = metadata.get("mesh_file")
    if not mesh_file:
        return None
    mesh_path = Path(mesh_file)
    if mesh_path.is_absolute():
        return mesh_path
    return (json_path.parent.parent / mesh_path).resolve()


def create_guide_armature(json_path: Path, metadata: dict) -> bpy.types.Object:
    guide_bones = guide_bones_from_metadata(metadata)
    suffix = "Predicted_Guides" if "predicted_guide_bones" in metadata else "QWalk_Guides"
    data = bpy.data.armatures.new(f"{metadata.get('id', json_path.stem)}_{suffix}")
    data.display_type = "STICK"
    guide = bpy.data.objects.new(data.name, data)
    guide.show_in_front = True
    guide["qwg_is_guide"] = True
    guide["qwg_profile"] = "MEDIUM"
    guide["qwg_source_mesh"] = metadata.get("mesh_file", "")
    guide["qwg_synthetic_label"] = str(json_path)
    guide["qwg_synthetic_animal_type"] = metadata.get("animal_type", metadata.get("predicted_animal_type", ""))
    guide["qwg_synthetic_morphology_type"] = metadata.get("morphology_type", metadata.get("predicted_morphology_type", ""))
    guide["qwg_ml_prediction"] = bool("predicted_guide_bones" in metadata)
    if "predicted_animal_confidence" in metadata:
        guide["qwg_ml_animal_confidence"] = metadata["predicted_animal_confidence"]
    if "predicted_morphology_confidence" in metadata:
        guide["qwg_ml_morphology_confidence"] = metadata["predicted_morphology_confidence"]
    bpy.context.collection.objects.link(guide)

    bpy.ops.object.select_all(action="DESELECT")
    guide.select_set(True)
    bpy.context.view_layer.objects.active = guide
    bpy.ops.object.mode_set(mode="EDIT")

    edit_bones: dict[str, bpy.types.EditBone] = {}
    for name, pair in guide_bones.items():
        bone = data.edit_bones.new(name)
        bone.head = Vector(pair["head"])
        bone.tail = Vector(pair["tail"])
        bone.use_deform = False
        edit_bones[name] = bone

    for parent_name, child_name in zip(SPINE_PARENT_ORDER, SPINE_PARENT_ORDER[1:]):
        edit_bones[child_name].parent = edit_bones[parent_name]
        edit_bones[child_name].use_connect = True
    edit_bones["qwg_guide_tail"].parent = edit_bones["qwg_guide_pelvis"]

    for leg, names in LEG_BONES.items():
        parent_name = "qwg_guide_chest" if leg.startswith("f") else "qwg_guide_pelvis"
        edit_bones[names[0]].parent = edit_bones[parent_name]
        edit_bones[names[1]].parent = edit_bones[names[0]]
        edit_bones[names[1]].use_connect = True
        edit_bones[names[2]].parent = edit_bones[names[1]]
        edit_bones[names[2]].use_connect = True

    bpy.ops.object.mode_set(mode="OBJECT")
    return guide


def main() -> None:
    args = parse_args()
    json_path = Path(args.json_file).expanduser().resolve()
    with json_path.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)

    imported_objects: list[bpy.types.Object] = []
    obj_path = source_mesh_path(json_path, metadata)
    if not args.no_mesh and obj_path and obj_path.exists():
        imported_objects = import_obj(obj_path)
        for obj in imported_objects:
            obj.name = f"{metadata.get('id', json_path.stem)}_{obj.name}"

    guide = create_guide_armature(json_path, metadata)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in imported_objects:
        obj.select_set(True)
    guide.select_set(True)
    bpy.context.view_layer.objects.active = guide

    print(
        "Imported {sample} as {animal}/{morphology} with {bone_count} guide bones.".format(
            sample=metadata.get("id", json_path.stem),
            animal=metadata.get("animal_type", metadata.get("predicted_animal_type", "unknown")),
            morphology=metadata.get("morphology_type", metadata.get("predicted_morphology_type", "unknown")),
            bone_count=len(guide_bones_from_metadata(metadata)),
        )
    )


if __name__ == "__main__":
    main()
