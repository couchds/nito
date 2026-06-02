"""Render a multi-angle QWalk guide review sheet for gold-label placement."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


VIEW_SPECS = ("left", "right", "front", "rear", "top", "quarter")
GUIDE_COLORS = {
    "body": (1.0, 0.44, 0.0, 1.0),
    "front": (0.05, 0.55, 1.0, 1.0),
    "rear": (0.95, 0.18, 0.18, 1.0),
    "tail": (0.85, 0.85, 0.05, 1.0),
}


def parse_args() -> argparse.Namespace:
    script_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description="Render a multi-angle QWalk label review.")
    parser.add_argument("--mesh", default="", help="Mesh object name. Defaults to the first mesh.")
    parser.add_argument("--guide", default="", help="QWalk guide armature. Defaults to the first QWalk guide.")
    parser.add_argument("--out-dir", required=True, help="Directory for rendered review PNGs and manifest.")
    parser.add_argument("--resolution", type=int, default=1200, help="Square PNG resolution for each view.")
    parser.add_argument(
        "--mesh-forward-axis",
        default="POS_Y",
        choices=("POS_X", "NEG_X", "POS_Y", "NEG_Y"),
        help="World axis pointing from tail toward head.",
    )
    parser.add_argument(
        "--mesh-alpha",
        type=float,
        default=0.42,
        help="Viewport alpha for the review mesh. Lower values expose more guide detail.",
    )
    return parser.parse_args(script_args)


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


def material(name: str, color: tuple[float, float, float, float]) -> bpy.types.Material:
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = color
    return mat


def bone_group(name: str) -> str:
    if "front_" in name:
        return "front"
    if "rear_" in name:
        return "rear"
    if name.endswith("_tail"):
        return "tail"
    return "body"


def add_curve(name: str, start: Vector, end: Vector, mat: bpy.types.Material, bevel: float) -> bpy.types.Object:
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
    return obj


def add_joint(name: str, point: Vector, mat: bpy.types.Material, radius: float) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=radius, location=point)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    return obj


def create_review_geometry(guide: bpy.types.Object, size_hint: float) -> list[bpy.types.Object]:
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode="OBJECT")
    mats = {key: material(f"QWalk Review {key.title()}", color) for key, color in GUIDE_COLORS.items()}
    created = []
    bevel = max(size_hint * 0.0035, 0.002)
    radius = max(size_hint * 0.010, 0.006)
    seen_points: set[tuple[int, int, int]] = set()

    for bone in guide.data.bones:
        group = bone_group(bone.name)
        mat = mats[group]
        start = guide.matrix_world @ bone.head_local
        end = guide.matrix_world @ bone.tail_local
        created.append(add_curve(f"review_curve_{bone.name}", start, end, mat, bevel))
        for point, suffix in ((start, "h"), (end, "t")):
            key = tuple(round(coord * 10000) for coord in point)
            if key in seen_points:
                continue
            seen_points.add(key)
            created.append(add_joint(f"review_joint_{bone.name}_{suffix}", point, mat, radius))
    return created


def object_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector, Vector]:
    points = []
    for obj in objects:
        for corner in obj.bound_box:
            points.append(obj.matrix_world @ Vector(corner))
    if not points:
        return Vector((-1, -1, -1)), Vector((1, 1, 1)), Vector((2, 2, 2))
    mins = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maxs = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    return mins, maxs, maxs - mins


def axes_from_forward(axis: str) -> tuple[Vector, Vector, Vector]:
    up = Vector((0.0, 0.0, 1.0))
    forward = {
        "POS_X": Vector((1.0, 0.0, 0.0)),
        "NEG_X": Vector((-1.0, 0.0, 0.0)),
        "POS_Y": Vector((0.0, 1.0, 0.0)),
        "NEG_Y": Vector((0.0, -1.0, 0.0)),
    }[axis]
    left = forward.cross(up).normalized()
    return forward, left, up


def view_direction(view_name: str, forward: Vector, left: Vector, up: Vector) -> Vector:
    directions = {
        "left": left,
        "right": -left,
        "front": forward,
        "rear": -forward,
        "top": up,
        "quarter": (forward + left + up * 0.45).normalized(),
    }
    return directions[view_name]


def create_camera(name: str, center: Vector, direction: Vector, distance: float, ortho_scale: float) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new(name)
    camera = bpy.data.objects.new(name, camera_data)
    bpy.context.collection.objects.link(camera)
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = ortho_scale
    camera.location = center + direction.normalized() * distance
    rotation_direction = center - camera.location
    camera.rotation_euler = rotation_direction.to_track_quat("-Z", "Y").to_euler()
    return camera


def apply_review_mesh_material(mesh: bpy.types.Object, alpha: float) -> None:
    mat = material("QWalk Review Mesh Ghost", (0.72, 0.72, 0.72, max(0.05, min(alpha, 1.0))))
    mesh.data.materials.clear()
    mesh.data.materials.append(mat)
    mesh.show_wire = True
    mesh.show_in_front = False


def setup_scene(resolution: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_xray = True
    scene.display.shading.xray_alpha = 0.42
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.film_transparent = False


def render_views(mesh: bpy.types.Object, guide: bpy.types.Object, out_dir: Path, resolution: int, axis: str, alpha: float) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    apply_review_mesh_material(mesh, alpha)
    mins, maxs, size = object_bounds([mesh, guide])
    center = (mins + maxs) * 0.5
    size_hint = max(size.x, size.y, size.z, 1.0)
    review_objects = create_review_geometry(guide, size_hint)
    forward, left, up = axes_from_forward(axis)
    setup_scene(resolution)

    manifest = {
        "blend_file": bpy.data.filepath,
        "mesh": mesh.name,
        "guide": guide.name,
        "mesh_forward_axis": axis,
        "views": [],
    }
    for view_name in VIEW_SPECS:
        direction = view_direction(view_name, forward, left, up)
        camera = create_camera(
            f"QWalkReview_{view_name}",
            center,
            direction,
            distance=size_hint * 4.0,
            ortho_scale=size_hint * 1.18,
        )
        bpy.context.scene.camera = camera
        path = out_dir / f"{view_name}.png"
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        manifest["views"].append({"name": view_name, "file": str(path)})

    (out_dir / "review_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Rendered {len(VIEW_SPECS)} QWalk review views to {out_dir}")

    for obj in review_objects:
        bpy.data.objects.remove(obj, do_unlink=True)


def main() -> None:
    args = parse_args()
    mesh = resolve_mesh(args.mesh)
    guide = resolve_guide(args.guide)
    render_views(
        mesh,
        guide,
        Path(args.out_dir).expanduser().resolve(),
        args.resolution,
        args.mesh_forward_axis,
        args.mesh_alpha,
    )


if __name__ == "__main__":
    main()
