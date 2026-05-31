"""Render a preview with armature bones converted to temporary visible curves."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Render a QWalk preview with visible bone curves.")
    parser.add_argument("--out", required=True, help="Output PNG path.")
    parser.add_argument("--resolution", type=int, default=1200, help="Square output resolution.")
    parser.add_argument(
        "--overlay-front",
        action="store_true",
        help="Project armature curves onto the camera-facing side so the mesh cannot occlude them.",
    )
    return parser.parse_args(script_args)


def material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = color
    return mat


def add_bone_curve(name: str, start: Vector, end: Vector, mat: bpy.types.Material, bevel: float) -> None:
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = bevel
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (start.x, start.y, start.z, 1.0)
    spline.points[1].co = (end.x, end.y, end.z, 1.0)
    obj = bpy.data.objects.new(name, curve)
    obj.data.materials.append(mat)
    bpy.context.collection.objects.link(obj)


def make_armatures_visible(overlay_front: bool) -> None:
    guide_mat = material("QWalk Preview Guide", (1.0, 0.48, 0.0, 1.0))
    rig_mat = material("QWalk Preview Rig", (0.02, 0.02, 0.02, 1.0))
    front_y = None
    if overlay_front:
        mins, maxs = scene_bounds()
        front_y = mins.y - max((maxs - mins).length * 0.04, 0.02)
    for armature in [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]:
        mat = guide_mat if armature.get("qwg_is_guide") else rig_mat
        bevel = 0.004 if armature.get("qwg_is_guide") else 0.003
        for bone in armature.data.bones:
            start = armature.matrix_world @ bone.head_local
            end = armature.matrix_world @ bone.tail_local
            if front_y is not None:
                start.y = front_y
                end.y = front_y
            add_bone_curve(f"preview_{armature.name}_{bone.name}", start, end, mat, bevel)


def scene_bounds() -> tuple[Vector, Vector]:
    points = []
    for obj in bpy.context.scene.objects:
        if obj.type not in {"MESH", "ARMATURE", "CURVE"}:
            continue
        for corner in obj.bound_box:
            points.append(obj.matrix_world @ Vector(corner))
    if not points:
        return Vector((-1, -1, -1)), Vector((1, 1, 1))
    mins = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maxs = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return mins, maxs


def setup_camera() -> None:
    mins, maxs = scene_bounds()
    center = (mins + maxs) * 0.5
    size = max((maxs - mins).x, (maxs - mins).z, 1.0)
    camera_data = bpy.data.cameras.new("QWalkBonePreviewCamera")
    camera = bpy.data.objects.new("QWalkBonePreviewCamera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = size * 1.25
    camera.location = (center.x, center.y - size * 4.0, center.z)
    camera.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    bpy.context.scene.camera = camera


def main() -> None:
    args = parse_args()
    output = Path(args.out).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    make_armatures_visible(args.overlay_front)
    setup_camera()
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.render.resolution_x = args.resolution
    scene.render.resolution_y = args.resolution
    scene.render.film_transparent = False
    scene.render.filepath = str(output)
    bpy.ops.render.render(write_still=True)
    print(f"Rendered bone preview to {output}")


if __name__ == "__main__":
    main()
