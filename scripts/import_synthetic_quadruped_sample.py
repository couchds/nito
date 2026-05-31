"""Import a synthetic QWalk sample JSON into Blender as mesh + guide armature.

Run from Blender:

    blender --python scripts/import_synthetic_quadruped_sample.py -- data/synthetic_quadrupeds/train/syn_000000.json

The synthetic dataset stores the armature labels in JSON because OBJ files do
not carry Blender bones. This helper reads the sidecar label file, imports the
OBJ mesh, and creates an editable QWalk guide armature from the labeled bones.
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
    parser = argparse.ArgumentParser(description="Import one synthetic QWalk sample into Blender.")
    parser.add_argument("label_file", help="Path to a synthetic sample JSON label file.")
    parser.add_argument("--no-mesh", action="store_true", help="Only create the guide armature.")
    return parser.parse_args(script_args)


def import_obj(obj_path: Path) -> list[bpy.types.Object]:
    before = set(bpy.context.scene.objects)
    if hasattr(bpy.ops.wm, "obj_import"):
        bpy.ops.wm.obj_import(filepath=str(obj_path), forward_axis="Y", up_axis="Z")
    else:
        bpy.ops.import_scene.obj(filepath=str(obj_path), axis_forward="Y", axis_up="Z")
    return [obj for obj in bpy.context.scene.objects if obj not in before]


def create_guide_armature(label_path: Path, metadata: dict) -> bpy.types.Object:
    guide_bones = metadata["guide_bones"]
    data = bpy.data.armatures.new(f"{metadata['id']}_QWalk_Guides")
    data.display_type = "STICK"
    guide = bpy.data.objects.new(data.name, data)
    guide.show_in_front = True
    guide["qwg_is_guide"] = True
    guide["qwg_profile"] = "MEDIUM"
    guide["qwg_source_mesh"] = metadata.get("mesh_file", "")
    guide["qwg_synthetic_label"] = str(label_path)
    guide["qwg_synthetic_animal_type"] = metadata.get("animal_type", "")
    guide["qwg_synthetic_morphology_type"] = metadata.get("morphology_type", "")
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
    label_path = Path(args.label_file).expanduser().resolve()
    with label_path.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)

    imported_objects: list[bpy.types.Object] = []
    obj_path = (label_path.parent.parent / metadata["mesh_file"]).resolve()
    if not args.no_mesh and obj_path.exists():
        imported_objects = import_obj(obj_path)
        for obj in imported_objects:
            obj.name = f"{metadata['id']}_{obj.name}"

    guide = create_guide_armature(label_path, metadata)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in imported_objects:
        obj.select_set(True)
    guide.select_set(True)
    bpy.context.view_layer.objects.active = guide

    print(
        "Imported {sample} as {animal}/{morphology} with {bone_count} guide bones.".format(
            sample=metadata["id"],
            animal=metadata.get("animal_type", "unknown"),
            morphology=metadata.get("morphology_type", "unknown"),
            bone_count=len(metadata["guide_bones"]),
        )
    )


if __name__ == "__main__":
    main()
