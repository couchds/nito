"""Apply QWalk's geometric fitting workflow to the open Blender file."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

import bpy

ADDON_MODULE = "quadruped_walk_cycle"


def parse_args() -> argparse.Namespace:
    script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Create QWalk guides/rig from the add-on geometric fitter.")
    parser.add_argument("--mesh", default="", help="Mesh object to fit. Defaults to the first mesh.")
    parser.add_argument("--output", default="", help="Output .blend path. Defaults to saving the current file.")
    parser.add_argument("--guides-only", action="store_true", help="Create only the editable guide armature.")
    parser.add_argument("--no-bind", action="store_true", help="Skip mesh binding.")
    parser.add_argument("--no-animate", action="store_true", help="Skip walk-cycle key generation.")
    parser.add_argument("--profile", default="AUTO", choices=("AUTO", "MEDIUM", "STOCKY", "HORSE"))
    parser.add_argument("--mesh-forward-axis", default="AUTO", choices=("AUTO", "POS_Y", "NEG_Y", "POS_X", "NEG_X"))
    return parser.parse_args(script_args)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def register_addon() -> None:
    root = repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    disable_loaded_addon()
    addon = importlib.import_module(ADDON_MODULE)
    try:
        addon.register()
    except ValueError as error:
        if "already registered" not in str(error):
            raise
        print(f"QWalk add-on was already registered; continuing with existing Blender registration: {error}")


def disable_loaded_addon() -> None:
    try:
        if ADDON_MODULE in bpy.context.preferences.addons:
            bpy.ops.preferences.addon_disable(module=ADDON_MODULE)
    except Exception as error:
        print(f"Could not disable existing QWalk add-on registration: {error}")

    addon = sys.modules.get(ADDON_MODULE)
    if addon and hasattr(addon, "unregister"):
        try:
            addon.unregister()
        except Exception as error:
            print(f"Could not unregister existing QWalk module cleanly: {error}")

    for module_name in sorted(
        [name for name in sys.modules if name == ADDON_MODULE or name.startswith(f"{ADDON_MODULE}.")],
        key=len,
        reverse=True,
    ):
        del sys.modules[module_name]


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


def select_active(*objects: bpy.types.Object, active: bpy.types.Object | None = None) -> None:
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    if active:
        bpy.context.view_layer.objects.active = active


def main() -> None:
    args = parse_args()
    register_addon()
    mesh = resolve_mesh(args.mesh)

    select_active(mesh, active=mesh)
    guide_result = bpy.ops.qwg.create_fit_guides(
        guide_name=f"{mesh.name}_QWalk_Geometric_Guides",
        body_profile=args.profile,
        mesh_forward_axis=args.mesh_forward_axis,
        fit_amount=0.88,
        robust_bounds=True,
        top_percentile=88.0,
    )
    if guide_result != {"FINISHED"}:
        raise RuntimeError(f"Create Fitting Guides failed: {guide_result}")
    guide = bpy.context.view_layer.objects.active
    rig = None

    if not args.guides_only:
        select_active(guide, active=guide)
        rig_result = bpy.ops.qwg.create_armature_from_guides(
            add_ik_constraints=True,
            map_after_create=True,
            hide_guides_after_create=False,
            replace_existing_generated=True,
            symmetrize_legs=True,
        )
        if rig_result != {"FINISHED"}:
            raise RuntimeError(f"Generate Armature From Guides failed: {rig_result}")
        rig = bpy.context.view_layer.objects.active

        if not args.no_bind:
            select_active(mesh, rig, active=rig)
            bind_result = bpy.ops.qwg.bind_selected_meshes(
                weighting_mode="NEAREST",
                replace_existing_armatures=True,
                max_influences=4,
            )
            if bind_result != {"FINISHED"}:
                raise RuntimeError(f"Bind Selected Meshes To Rig failed: {bind_result}")

        if not args.no_animate:
            select_active(rig, active=rig)
            settings = bpy.context.scene.qwg_settings
            settings.gait = "WALK" if args.profile == "HORSE" else "COMPACT_WALK"
            settings.generation_mode = "AUTO"
            settings.frame_start = 1
            settings.frame_end = 25
            settings.key_step = 2
            animate_result = bpy.ops.qwg.generate_walk_cycle()
            if animate_result != {"FINISHED"}:
                raise RuntimeError(f"Generate Walk Cycle failed: {animate_result}")

    output_path = Path(args.output).expanduser().resolve() if args.output else Path(bpy.data.filepath)
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
    print(
        "Applied geometric QWalk fit to {blend}. guide={guide} rig={rig} mesh={mesh}".format(
            blend=output_path,
            guide=guide.name,
            rig=rig.name if rig else "",
            mesh=mesh.name,
        )
    )


if __name__ == "__main__":
    main()
