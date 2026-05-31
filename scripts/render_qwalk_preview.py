"""Render a quick orthographic viewport-style preview of a .blend file."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Render a quick QWalk preview PNG.")
    parser.add_argument("--out", required=True, help="Output PNG path.")
    parser.add_argument("--resolution", type=int, default=1200, help="Square output resolution.")
    return parser.parse_args(script_args)


def scene_bounds() -> tuple[Vector, Vector]:
    points = []
    for obj in bpy.context.scene.objects:
        if obj.type not in {"MESH", "ARMATURE"}:
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
    camera = bpy.data.objects.get("QWalkPreviewCamera")
    if not camera:
        camera_data = bpy.data.cameras.new("QWalkPreviewCamera")
        camera = bpy.data.objects.new("QWalkPreviewCamera", camera_data)
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
    print(f"Rendered preview to {output}")


if __name__ == "__main__":
    main()
