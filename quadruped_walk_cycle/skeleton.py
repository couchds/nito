import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy.types import Operator
from math import cos, pi, sin
from mathutils import Vector

from .constants import FK_FIELDS, IK_FIELDS, LEG_ORDER
from .rig_utils import store_base_pose


STANDARD_LEG_NAMES = {
    "fl": {
        "upper": "front_left_upper",
        "lower": "front_left_lower",
        "foot": "front_left_foot",
        "ik": "front_left_ik",
        "pole": "front_left_pole",
    },
    "fr": {
        "upper": "front_right_upper",
        "lower": "front_right_lower",
        "foot": "front_right_foot",
        "ik": "front_right_ik",
        "pole": "front_right_pole",
    },
    "rl": {
        "upper": "rear_left_upper",
        "lower": "rear_left_lower",
        "foot": "rear_left_foot",
        "ik": "rear_left_ik",
        "pole": "rear_left_pole",
    },
    "rr": {
        "upper": "rear_right_upper",
        "lower": "rear_right_lower",
        "foot": "rear_right_foot",
        "ik": "rear_right_ik",
        "pole": "rear_right_pole",
    },
}

GUIDE_LEG_BONES = {
    "fl": {
        "upper": "qwg_guide_front_left_upper",
        "lower": "qwg_guide_front_left_lower",
        "foot": "qwg_guide_front_left_foot",
    },
    "fr": {
        "upper": "qwg_guide_front_right_upper",
        "lower": "qwg_guide_front_right_lower",
        "foot": "qwg_guide_front_right_foot",
    },
    "rl": {
        "upper": "qwg_guide_rear_left_upper",
        "lower": "qwg_guide_rear_left_lower",
        "foot": "qwg_guide_rear_left_foot",
    },
    "rr": {
        "upper": "qwg_guide_rear_right_upper",
        "lower": "qwg_guide_rear_right_lower",
        "foot": "qwg_guide_rear_right_foot",
    },
}

GUIDE_SPINE_BONES = {
    "pelvis": "qwg_guide_pelvis",
    "spine": "qwg_guide_spine",
    "chest": "qwg_guide_chest",
    "neck": "qwg_guide_neck",
    "head": "qwg_guide_head",
    "tail": "qwg_guide_tail",
}

QUADRUPED_PROFILES = {
    "MEDIUM": {
        "label": "Medium Quadruped",
        "root": {"head": (-0.26, 0.0, 0.0), "tail": (0.26, 0.0, 0.0)},
        "body": {"head": (0.0, -0.78, 0.92), "tail": (0.0, 0.74, 1.02)},
        "spine": [
            ("pelvis", (0.0, -0.78, 0.88), (0.0, -0.36, 0.94)),
            ("spine_01", (0.0, -0.36, 0.94), (0.0, 0.16, 0.99)),
            ("chest", (0.0, 0.16, 0.99), (0.0, 0.76, 1.02)),
        ],
        "neck": {"head": (0.0, 0.76, 1.02), "tail": (0.0, 1.08, 1.16)},
        "head": {"head": (0.0, 1.08, 1.16), "tail": (0.0, 1.44, 1.08)},
        "tail": [
            ("tail_01", (0.0, -0.78, 0.88), (0.0, -1.12, 0.94)),
            ("tail_02", (0.0, -1.12, 0.94), (0.0, -1.48, 0.84)),
        ],
        "leg_width_front": 0.30,
        "leg_width_rear": 0.34,
        "front_leg": {
            "anchor_parent": "chest",
            "guide": "scapula",
            "guide_head": (0.0, 0.56, 1.03),
            "guide_tail": (0.0, 0.42, 0.80),
            "upper_head": (0.0, 0.42, 0.80),
            "upper_tail": (0.0, 0.35, 0.55),
            "lower_tail": (0.0, 0.52, 0.18),
            "foot_tail": (0.0, 0.74, 0.05),
            "pole": (0.0, -0.18, 0.55),
        },
        "rear_leg": {
            "anchor_parent": "pelvis",
            "guide": "hip",
            "guide_head": (0.0, -0.72, 0.88),
            "guide_tail": (0.0, -0.86, 0.72),
            "upper_head": (0.0, -0.86, 0.72),
            "upper_tail": (0.0, -0.78, 0.48),
            "lower_tail": (0.0, -0.58, 0.18),
            "foot_tail": (0.0, -0.36, 0.05),
            "pole": (0.0, -1.28, 0.50),
        },
        "control_scale": 1.0,
    },
    "STOCKY": {
        "label": "Stocky Quadruped",
        "root": {"head": (-0.28, 0.0, 0.0), "tail": (0.28, 0.0, 0.0)},
        "body": {"head": (0.0, -0.82, 1.12), "tail": (0.0, 0.74, 1.22)},
        "spine": [
            ("pelvis", (0.0, -0.82, 1.08), (0.0, -0.38, 1.14)),
            ("spine_01", (0.0, -0.38, 1.14), (0.0, 0.18, 1.20)),
            ("chest", (0.0, 0.18, 1.20), (0.0, 0.78, 1.22)),
        ],
        "neck": {"head": (0.0, 0.78, 1.22), "tail": (0.0, 1.06, 1.38)},
        "head": {"head": (0.0, 1.06, 1.38), "tail": (0.0, 1.34, 1.28)},
        "tail": [
            ("tail_01", (0.0, -0.82, 1.08), (0.0, -1.02, 1.06)),
            ("tail_02", (0.0, -1.02, 1.06), (0.0, -1.18, 0.98)),
        ],
        "leg_width_front": 0.34,
        "leg_width_rear": 0.36,
        "front_leg": {
            "anchor_parent": "chest",
            "guide": "scapula",
            "guide_head": (0.0, 0.58, 1.20),
            "guide_tail": (0.0, 0.44, 0.86),
            "upper_head": (0.0, 0.44, 0.86),
            "upper_tail": (0.0, 0.38, 0.58),
            "lower_tail": (0.0, 0.50, 0.18),
            "foot_tail": (0.0, 0.70, 0.05),
            "pole": (0.0, -0.18, 0.58),
        },
        "rear_leg": {
            "anchor_parent": "pelvis",
            "guide": "hip",
            "guide_head": (0.0, -0.76, 1.08),
            "guide_tail": (0.0, -0.90, 0.82),
            "upper_head": (0.0, -0.90, 0.82),
            "upper_tail": (0.0, -0.80, 0.55),
            "lower_tail": (0.0, -0.60, 0.18),
            "foot_tail": (0.0, -0.40, 0.05),
            "pole": (0.0, -1.30, 0.56),
        },
        "control_scale": 1.05,
    },
    "HORSE": {
        "label": "Horse",
        "root": {"head": (-0.34, 0.0, 0.0), "tail": (0.34, 0.0, 0.0)},
        "body": {"head": (0.0, -1.08, 1.28), "tail": (0.0, 0.98, 1.42)},
        "spine": [
            ("pelvis", (0.0, -1.08, 1.24), (0.0, -0.48, 1.32)),
            ("spine_01", (0.0, -0.48, 1.32), (0.0, 0.24, 1.40)),
            ("chest", (0.0, 0.24, 1.40), (0.0, 1.02, 1.42)),
        ],
        "neck": {"head": (0.0, 1.02, 1.42), "tail": (0.0, 1.46, 1.76)},
        "head": {"head": (0.0, 1.46, 1.76), "tail": (0.0, 1.88, 1.60)},
        "tail": [
            ("tail_01", (0.0, -1.08, 1.24), (0.0, -1.38, 1.12)),
            ("tail_02", (0.0, -1.38, 1.12), (0.0, -1.70, 0.96)),
        ],
        "leg_width_front": 0.30,
        "leg_width_rear": 0.34,
        "front_leg": {
            "anchor_parent": "chest",
            "guide": "scapula",
            "guide_head": (0.0, 0.78, 1.40),
            "guide_tail": (0.0, 0.56, 1.04),
            "upper_head": (0.0, 0.56, 1.04),
            "upper_tail": (0.0, 0.48, 0.74),
            "lower_tail": (0.0, 0.58, 0.26),
            "foot_tail": (0.0, 0.78, 0.06),
            "pole": (0.0, -0.20, 0.76),
        },
        "rear_leg": {
            "anchor_parent": "pelvis",
            "guide": "hip",
            "guide_head": (0.0, -1.00, 1.24),
            "guide_tail": (0.0, -1.10, 0.94),
            "upper_head": (0.0, -1.10, 0.94),
            "upper_tail": (0.0, -0.94, 0.62),
            "lower_tail": (0.0, -0.68, 0.24),
            "foot_tail": (0.0, -0.42, 0.06),
            "pole": (0.0, -1.56, 0.66),
        },
        "control_scale": 1.15,
    },
}


def scaled(point, scale):
    """Return a Vector point multiplied by the armature scale."""
    return Vector(point) * scale


def mirrored_point(point, x):
    """Return a profile point with an assigned X coordinate."""
    return (x, point[1], point[2])


def profile_items():
    """Return Blender enum items for available quadruped profiles."""
    return tuple((key, value["label"], "") for key, value in QUADRUPED_PROFILES.items())


def fit_profile_items():
    """Return enum items for mesh-fitted profile selection."""
    return (("AUTO", "Auto", "Choose a profile from the mesh proportions"),) + profile_items()


def profile_from_mesh(mesh_size, forward_axis):
    """Choose a broad body profile from mesh proportions."""
    if forward_axis in {"POS_Y", "NEG_Y"}:
        mesh_length = mesh_size.y
        mesh_width = mesh_size.x
    else:
        mesh_length = mesh_size.x
        mesh_width = mesh_size.y

    length_to_height = mesh_length / max(mesh_size.z, 0.001)
    width_to_height = mesh_width / max(mesh_size.z, 0.001)

    if length_to_height >= 2.45:
        return "HORSE"
    if length_to_height <= 2.15 or width_to_height >= 0.62:
        return "STOCKY"
    return "MEDIUM"


def clamp(value, minimum, maximum):
    """Clamp a number between two bounds."""
    return max(minimum, min(maximum, value))


def inset(value, center, amount):
    """Move a coordinate toward or away from a center."""
    return center + (value - center) * amount


def collect_profile_points(profile):
    """Collect key local-space points used to estimate profile bounds."""
    points = [
        profile["root"]["head"],
        profile["root"]["tail"],
        profile["body"]["head"],
        profile["body"]["tail"],
        profile["neck"]["head"],
        profile["neck"]["tail"],
        profile["head"]["head"],
        profile["head"]["tail"],
    ]
    for _, head, tail in profile["spine"]:
        points.extend((head, tail))
    for _, head, tail in profile["tail"]:
        points.extend((head, tail))

    for leg_key, width_key in (("front_leg", "leg_width_front"), ("rear_leg", "leg_width_rear")):
        leg_profile = profile[leg_key]
        for side in (-1.0, 1.0):
            x = side * profile[width_key]
            for point_key in (
                "guide_head",
                "guide_tail",
                "upper_head",
                "upper_tail",
                "lower_tail",
                "foot_tail",
                "pole",
            ):
                points.append(mirrored_point(leg_profile[point_key], x))
    return [Vector(point) for point in points]


def bounds_from_points(points):
    """Return min, max, and size vectors for a point collection."""
    min_corner = Vector((min(point.x for point in points), min(point.y for point in points), min(point.z for point in points)))
    max_corner = Vector((max(point.x for point in points), max(point.y for point in points), max(point.z for point in points)))
    return min_corner, max_corner, max_corner - min_corner


def percentile(values, amount):
    """Return an interpolated percentile from a list of values."""
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * (amount / 100.0)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    blend = position - lower
    return ordered[lower] * (1.0 - blend) + ordered[upper] * blend


def mesh_world_points(mesh_object, context):
    """Return evaluated mesh vertices in world space."""
    depsgraph = context.evaluated_depsgraph_get()
    evaluated = mesh_object.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        if mesh and mesh.vertices:
            return [evaluated.matrix_world @ vertex.co for vertex in mesh.vertices]
    finally:
        evaluated.to_mesh_clear()
    return [mesh_object.matrix_world @ Vector(corner) for corner in mesh_object.bound_box]


def mesh_world_bounds(mesh_object, context, robust=True, top_percentile=88.0):
    """Return world-space bounds for a mesh object."""
    points = mesh_world_points(mesh_object, context)
    if robust and len(points) >= 16:
        xs = [point.x for point in points]
        ys = [point.y for point in points]
        zs = [point.z for point in points]
        min_corner = Vector((percentile(xs, 1.0), percentile(ys, 1.0), min(zs)))
        max_corner = Vector((percentile(xs, 99.0), percentile(ys, 99.0), percentile(zs, top_percentile)))
        return min_corner, max_corner, max_corner - min_corner
    return bounds_from_points(points)


def robust_bounds_from_points(points, robust=True, top_percentile=88.0):
    """Return bounds from points, optionally trimming extreme silhouettes."""
    if robust and len(points) >= 16:
        xs = [point.x for point in points]
        ys = [point.y for point in points]
        zs = [point.z for point in points]
        min_corner = Vector((percentile(xs, 1.0), percentile(ys, 1.0), min(zs)))
        max_corner = Vector((percentile(xs, 99.0), percentile(ys, 99.0), percentile(zs, top_percentile)))
        return min_corner, max_corner, max_corner - min_corner
    return bounds_from_points(points)


def fitted_scale(mesh_size, profile_size, forward_axis, fit_amount):
    """Return a uniform scale that fits a profile inside mesh bounds."""
    if forward_axis in {"POS_Y", "NEG_Y"}:
        mesh_length = mesh_size.y
        mesh_width = mesh_size.x
    else:
        mesh_length = mesh_size.x
        mesh_width = mesh_size.y

    ratios = [
        mesh_length / max(profile_size.y, 0.001),
        mesh_width / max(profile_size.x, 0.001),
        mesh_size.z / max(profile_size.z, 0.001),
    ]
    return max(0.001, min(ratios) * fit_amount)


def forward_axis_rotation(forward_axis):
    """Return Z rotation that maps rig +Y to the mesh forward axis."""
    return {
        "POS_Y": 0.0,
        "NEG_Y": pi,
        "POS_X": -pi * 0.5,
        "NEG_X": pi * 0.5,
    }[forward_axis]


def rotate_z(point, angle):
    """Rotate a vector around the Z axis."""
    return Vector((point.x * cos(angle) - point.y * sin(angle), point.x * sin(angle) + point.y * cos(angle), point.z))


def mesh_points_in_fit_space(mesh_object, context, forward_axis):
    """Return mesh points in a +Y-forward fitting space."""
    angle = forward_axis_rotation(forward_axis)
    return [rotate_z(point, -angle) for point in mesh_world_points(mesh_object, context)], angle


def points_near_y(points, y_value, radius, fallback_count=12):
    """Return points inside a Y slice, falling back to nearest points."""
    band = [point for point in points if abs(point.y - y_value) <= radius]
    if len(band) >= 4:
        return band
    return sorted(points, key=lambda point: abs(point.y - y_value))[: min(fallback_count, len(points))]


def slice_landmarks(points, y_value, radius, high_percentile=88.0):
    """Measure low, high, and width landmarks from a Y slice."""
    band = points_near_y(points, y_value, radius)
    if not band:
        return {"low": 0.0, "high": 0.0, "width": 0.0, "count": 0}

    xs = [point.x for point in band]
    zs = [point.z for point in band]
    return {
        "low": percentile(zs, 8.0),
        "high": percentile(zs, high_percentile),
        "width": percentile(xs, 94.0) - percentile(xs, 6.0),
        "count": len(band),
    }


def measured_back_z(points, y_value, radius, fallback_z, high_percentile=84.0):
    """Return a spine height from the local top surface of the mesh."""
    landmarks = slice_landmarks(points, y_value, radius, high_percentile=high_percentile)
    depth = max(landmarks["high"] - landmarks["low"], 0.0)
    if landmarks["count"] < 4 or depth <= 0.0:
        return fallback_z
    return landmarks["high"] - depth * 0.08


def estimate_body_span(points, local_min, local_max, ground_z, height):
    """Estimate the main torso Y span from dense mid-body slices."""
    length = max(local_max.y - local_min.y, 0.001)
    bin_count = 44
    step = length / (bin_count - 1)
    radius = max(step * 0.8, length * 0.015)
    low_z = ground_z + height * 0.22
    high_z = ground_z + height * 0.78
    samples = []

    for index in range(bin_count):
        y_value = local_min.y + step * index
        band = [point for point in points_near_y(points, y_value, radius) if low_z <= point.z <= high_z]
        if len(band) < 4:
            samples.append((y_value, 0.0))
            continue

        xs = [point.x for point in band]
        zs = [point.z for point in band]
        width = percentile(xs, 92.0) - percentile(xs, 8.0)
        depth = percentile(zs, 92.0) - percentile(zs, 8.0)
        samples.append((y_value, max(0.0, width) * max(0.0, depth) * (len(band) ** 0.25)))

    max_score = max(score for _, score in samples)
    if max_score <= 0.0:
        return None

    active = [(y_value, score >= max_score * 0.38) for y_value, score in samples]
    best_start = best_end = None
    current_start = None
    for index, (_, is_active) in enumerate(active + [(0.0, False)]):
        if is_active and current_start is None:
            current_start = index
        elif not is_active and current_start is not None:
            current_end = index - 1
            if best_start is None or current_end - current_start > best_end - best_start:
                best_start, best_end = current_start, current_end
            current_start = None

    if best_start is None:
        return None

    span_min = samples[best_start][0] - radius * 0.35
    span_max = samples[best_end][0] + radius * 0.35
    if span_max - span_min < length * 0.28:
        return None
    return clamp(span_min, local_min.y, local_max.y), clamp(span_max, local_min.y, local_max.y)


def measured_leg_levels(points, foot_y, radius, ground_z, body_low_z, fallback_upper, fallback_lower):
    """Estimate leg joint heights from the mesh column over a foot."""
    column = [
        point
        for point in points_near_y(points, foot_y, radius)
        if ground_z <= point.z <= body_low_z
    ]
    if len(column) < 4:
        return fallback_upper, fallback_lower

    zs = [point.z for point in column]
    return percentile(zs, 68.0), percentile(zs, 32.0)


def build_landmark_profile(points, profile_key, fit_amount, robust=True, top_percentile=88.0):
    """Build a temporary profile from mesh-derived body and foot landmarks."""
    local_min, local_max, local_size = robust_bounds_from_points(points, robust, top_percentile)
    length = max(local_size.y, 0.001)
    width = max(local_size.x, 0.001)
    height = max(local_size.z, 0.001)

    ground_z = local_min.z
    body_low_z = ground_z + height * 0.24
    body_high_z = ground_z + height * 0.84
    torso_points = [point for point in points if body_low_z <= point.z <= body_high_z]
    if len(torso_points) < 12:
        torso_points = points

    body_span = estimate_body_span(points, local_min, local_max, ground_z, height)
    torso_y_values = [point.y for point in torso_points]
    if body_span:
        body_y_min, body_y_max = body_span
    else:
        body_y_min = percentile(torso_y_values, 18.0)
        body_y_max = percentile(torso_y_values, 82.0)
    if body_y_max - body_y_min < length * 0.35:
        body_y_min = local_min.y + length * 0.24
        body_y_max = local_max.y - length * 0.18

    body_center_y = (body_y_min + body_y_max) * 0.5
    body_y_min = inset(body_y_min, body_center_y, fit_amount)
    body_y_max = inset(body_y_max, body_center_y, fit_amount)
    body_length = max(body_y_max - body_y_min, length * 0.2)

    body_points = [
        point
        for point in points
        if body_y_min <= point.y <= body_y_max and ground_z + height * 0.16 <= point.z <= ground_z + height * 0.96
    ]
    if len(body_points) < 12:
        body_points = torso_points
    body_z_values = [point.z for point in body_points]
    belly_z = percentile(body_z_values, 10.0)
    back_z = percentile(body_z_values, 86.0)
    body_depth = max(back_z - belly_z, height * 0.25)

    slice_radius = max(body_length / 18.0, length / max(24.0, len(points) ** 0.5))
    pelvis_y = body_y_min
    spine_a_y = body_y_min + body_length * 0.32
    spine_b_y = body_y_min + body_length * 0.64
    chest_y = body_y_max
    fallback_spine_z = percentile(body_z_values, 82.0)
    spine_points = body_points if len(body_points) >= 12 else torso_points
    pelvis_z = measured_back_z(spine_points, pelvis_y, slice_radius, fallback_spine_z)
    spine_z = measured_back_z(spine_points, spine_a_y, slice_radius, fallback_spine_z)
    mid_spine_z = measured_back_z(spine_points, spine_b_y, slice_radius, fallback_spine_z)
    chest_z = measured_back_z(spine_points, chest_y, slice_radius, fallback_spine_z)

    low_points = [
        point
        for point in points
        if point.z <= ground_z + height * 0.18 and local_min.y + length * 0.06 <= point.y <= local_max.y - length * 0.06
    ]
    if len(low_points) >= 8:
        low_y_values = [point.y for point in low_points]
        rear_foot_y = percentile(low_y_values, 24.0)
        front_foot_y = percentile(low_y_values, 76.0)
    else:
        rear_foot_y = body_y_min + body_length * 0.14
        front_foot_y = body_y_max - body_length * 0.14

    rear_foot_y = clamp(rear_foot_y, local_min.y + length * 0.08, body_center_y - body_length * 0.08)
    front_foot_y = clamp(front_foot_y, body_center_y + body_length * 0.08, local_max.y - length * 0.08)
    rear_foot_y = inset(rear_foot_y, body_center_y, fit_amount)
    front_foot_y = inset(front_foot_y, body_center_y, fit_amount)

    full_tail_y = inset(local_min.y, body_center_y, min(fit_amount, 1.15))
    full_head_y = inset(local_max.y, body_center_y, min(fit_amount, 1.15))
    x_center = (local_min.x + local_max.x) * 0.5
    low_offsets = [abs(point.x - x_center) for point in low_points]
    if low_offsets:
        leg_width = max(percentile(low_offsets, 76.0) * fit_amount, height * 0.055)
    else:
        leg_width = max(width * 0.28 * fit_amount, height * 0.055)
    root_width = max(width * 0.34, height * 0.08)
    foot_z = ground_z + height * 0.035

    def rel(x, y, z):
        return (x - x_center, y - body_center_y, z - ground_z)

    neck_y = body_y_max + max((full_head_y - body_y_max) * 0.32, body_length * 0.10)
    head_y = body_y_max + max((full_head_y - body_y_max) * 0.78, body_length * 0.22)
    neck_z = measured_back_z(points, neck_y, slice_radius, chest_z + body_depth * 0.10)
    head_z = measured_back_z(points, head_y, slice_radius, neck_z - body_depth * 0.06)

    front_shoulder_y = clamp(front_foot_y + body_length * 0.03, body_y_max - body_length * 0.18, body_y_max + body_length * 0.08)
    front_elbow_y = front_foot_y - body_length * 0.06
    front_wrist_y = front_foot_y + body_length * 0.02
    front_toe_y = front_foot_y + body_length * 0.10

    rear_hip_y = clamp(rear_foot_y - body_length * 0.08, body_y_min - body_length * 0.08, body_y_min + body_length * 0.18)
    rear_stifle_y = rear_foot_y + body_length * 0.13
    rear_hock_y = rear_foot_y + body_length * 0.02
    rear_toe_y = rear_foot_y + body_length * 0.12
    leg_top_z = max(belly_z, ground_z + height * 0.42)
    front_upper_z, front_lower_z = measured_leg_levels(
        points,
        front_foot_y,
        slice_radius * 1.35,
        ground_z,
        leg_top_z,
        ground_z + (leg_top_z - ground_z) * 0.72,
        ground_z + (leg_top_z - ground_z) * 0.34,
    )
    rear_upper_z, rear_lower_z = measured_leg_levels(
        points,
        rear_foot_y,
        slice_radius * 1.35,
        ground_z,
        leg_top_z,
        ground_z + (leg_top_z - ground_z) * 0.72,
        ground_z + (leg_top_z - ground_z) * 0.34,
    )
    front_shoulder_z = min(measured_back_z(spine_points, front_shoulder_y, slice_radius, chest_z) - body_depth * 0.42, leg_top_z)
    rear_hip_z = min(measured_back_z(spine_points, rear_hip_y, slice_radius, pelvis_z) - body_depth * 0.36, leg_top_z)

    front_leg = {
        "anchor_parent": "chest",
        "guide": "scapula",
        "guide_head": rel(x_center, body_y_max - body_length * 0.06, chest_z),
        "guide_tail": rel(x_center, front_shoulder_y, front_shoulder_z),
        "upper_head": rel(x_center, front_shoulder_y, front_shoulder_z),
        "upper_tail": rel(x_center, front_elbow_y, front_upper_z),
        "lower_tail": rel(x_center, front_wrist_y, front_lower_z),
        "foot_tail": rel(x_center, front_toe_y, foot_z),
        "pole": rel(x_center, front_foot_y - body_length * 0.32, front_upper_z),
    }
    rear_leg = {
        "anchor_parent": "pelvis",
        "guide": "hip",
        "guide_head": rel(x_center, body_y_min + body_length * 0.06, pelvis_z),
        "guide_tail": rel(x_center, rear_hip_y, rear_hip_z),
        "upper_head": rel(x_center, rear_hip_y, rear_hip_z),
        "upper_tail": rel(x_center, rear_stifle_y, rear_upper_z),
        "lower_tail": rel(x_center, rear_hock_y, rear_lower_z),
        "foot_tail": rel(x_center, rear_toe_y, foot_z),
        "pole": rel(x_center, rear_foot_y - body_length * 0.36, rear_upper_z),
    }

    label = QUADRUPED_PROFILES.get(profile_key, QUADRUPED_PROFILES["MEDIUM"])["label"]
    profile = {
        "label": f"{label} Fit",
        "root": {"head": rel(x_center - root_width, body_center_y, ground_z), "tail": rel(x_center + root_width, body_center_y, ground_z)},
        "body": {"head": rel(x_center, body_y_min, pelvis_z), "tail": rel(x_center, body_y_max, chest_z)},
        "spine": [
            ("pelvis", rel(x_center, pelvis_y, pelvis_z), rel(x_center, spine_a_y, spine_z)),
            (
                "spine_01",
                rel(x_center, spine_a_y, spine_z),
                rel(x_center, spine_b_y, mid_spine_z),
            ),
            ("chest", rel(x_center, spine_b_y, mid_spine_z), rel(x_center, chest_y, chest_z)),
        ],
        "neck": {"head": rel(x_center, body_y_max, chest_z), "tail": rel(x_center, neck_y, neck_z)},
        "head": {"head": rel(x_center, neck_y, neck_z), "tail": rel(x_center, head_y, head_z)},
        "tail": [
            ("tail_01", rel(x_center, body_y_min, pelvis_z), rel(x_center, body_y_min - max((body_y_min - full_tail_y) * 0.45, body_length * 0.08), pelvis_z)),
            (
                "tail_02",
                rel(x_center, body_y_min - max((body_y_min - full_tail_y) * 0.45, body_length * 0.08), pelvis_z),
                rel(x_center, body_y_min - max((body_y_min - full_tail_y) * 0.82, body_length * 0.14), pelvis_z - height * 0.06),
            ),
        ],
        "leg_width_front": leg_width,
        "leg_width_rear": leg_width,
        "front_leg": front_leg,
        "rear_leg": rear_leg,
        "control_scale": max(height, length * 0.35),
    }
    return profile, Vector((x_center, body_center_y, ground_z)), local_min, local_max, local_size


def active_mesh(context):
    """Return the active mesh, or the first selected mesh."""
    if context.object and context.object.type == "MESH":
        return context.object
    for obj in context.selected_objects:
        if obj.type == "MESH":
            return obj
    return None


def active_guide_armature(context):
    """Return the active QWalk guide armature, or the first selected guide."""
    if context.object and context.object.type == "ARMATURE" and context.object.get("qwg_is_guide"):
        return context.object
    for obj in context.selected_objects:
        if obj.type == "ARMATURE" and obj.get("qwg_is_guide"):
            return obj
    return None


def add_edit_bone(edit_bones, name, head, tail, scale, parent=None, connected=False, deform=True):
    """Create an edit bone with common parent and deform settings."""
    bone = edit_bones.new(name)
    bone.head = scaled(head, scale)
    bone.tail = scaled(tail, scale)
    bone.parent = parent
    bone.use_connect = connected
    bone.use_deform = deform
    return bone


def world_point_from_fit(point, origin, angle):
    """Convert a fit-space profile point to world space."""
    return rotate_z(origin + Vector(point), angle)


def profile_side_point(profile, leg_key, point_key, side):
    """Return a profile leg point with left or right X applied."""
    width_key = "leg_width_front" if leg_key == "front_leg" else "leg_width_rear"
    return mirrored_point(profile[leg_key][point_key], side * profile[width_key])


def create_guide_bone(edit_bones, name, head, tail, parent=None, connected=False):
    """Create a non-deforming guide bone."""
    bone = edit_bones.new(name)
    bone.head = Vector(head)
    bone.tail = Vector(tail)
    bone.parent = parent
    bone.use_connect = connected
    bone.use_deform = False
    return bone


def leg_profile_point(profile, leg, leg_profile, point_key, x):
    """Return an exact per-leg point or mirrored shared profile point."""
    override = profile.get("leg_overrides", {}).get(leg)
    if override:
        return override[point_key]
    return mirrored_point(leg_profile[point_key], x)


def create_guide_armature(context, name, profile, origin, angle, source_mesh_name="", profile_key="MEDIUM"):
    """Create an editable QWalk guide armature from a fitted profile."""
    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    data = bpy.data.armatures.new(name)
    guide = bpy.data.objects.new(name, data)
    guide["qwg_is_guide"] = True
    guide["qwg_profile"] = profile_key
    guide["qwg_source_mesh"] = source_mesh_name
    guide.show_in_front = True
    data.display_type = "STICK"
    context.collection.objects.link(guide)

    bpy.ops.object.select_all(action="DESELECT")
    guide.select_set(True)
    context.view_layer.objects.active = guide
    guide.location = rotate_z(origin, angle)
    guide.rotation_euler.z = angle

    bpy.ops.object.mode_set(mode="EDIT")
    bones = data.edit_bones

    pelvis = create_guide_bone(bones, GUIDE_SPINE_BONES["pelvis"], profile["spine"][0][1], profile["spine"][0][2])
    spine = create_guide_bone(bones, GUIDE_SPINE_BONES["spine"], profile["spine"][1][1], profile["spine"][1][2], pelvis, True)
    chest = create_guide_bone(bones, GUIDE_SPINE_BONES["chest"], profile["spine"][2][1], profile["spine"][2][2], spine, True)
    neck = create_guide_bone(bones, GUIDE_SPINE_BONES["neck"], profile["neck"]["head"], profile["neck"]["tail"], chest, True)
    create_guide_bone(bones, GUIDE_SPINE_BONES["head"], profile["head"]["head"], profile["head"]["tail"], neck, True)
    create_guide_bone(bones, GUIDE_SPINE_BONES["tail"], profile["tail"][0][1], profile["tail"][-1][2], pelvis)

    for leg in LEG_ORDER:
        is_front = leg.startswith("f")
        side = 1.0 if leg.endswith("l") else -1.0
        leg_key = "front_leg" if is_front else "rear_leg"
        parent = chest if is_front else pelvis
        names = GUIDE_LEG_BONES[leg]
        upper = create_guide_bone(
            bones,
            names["upper"],
            profile_side_point(profile, leg_key, "upper_head", side),
            profile_side_point(profile, leg_key, "upper_tail", side),
            parent,
        )
        lower = create_guide_bone(
            bones,
            names["lower"],
            profile_side_point(profile, leg_key, "upper_tail", side),
            profile_side_point(profile, leg_key, "lower_tail", side),
            upper,
            True,
        )
        create_guide_bone(
            bones,
            names["foot"],
            profile_side_point(profile, leg_key, "lower_tail", side),
            profile_side_point(profile, leg_key, "foot_tail", side),
            lower,
            True,
        )

    for bone in bones:
        bone.select = True
        bone.select_head = True
        bone.select_tail = True

    return guide


def guide_bone_pair(guide, name):
    """Return local head and tail vectors for a guide bone."""
    bone = guide.data.bones.get(name)
    if not bone:
        raise ValueError(f"Guide bone missing: {name}")
    return bone.head_local.copy(), bone.tail_local.copy()


def average_vectors(vectors):
    """Return the arithmetic mean of vectors."""
    if not vectors:
        return Vector((0.0, 0.0, 0.0))
    total = Vector((0.0, 0.0, 0.0))
    for vector in vectors:
        total += vector
    return total / len(vectors)


def centered_point(point, origin):
    """Return a profile point centered on the guide origin."""
    return (0.0, point.y - origin.y, point.z - origin.z)


def build_profile_from_guides(guide):
    """Build a generated rig profile from an edited QWalk guide armature."""
    pelvis_head, pelvis_tail = guide_bone_pair(guide, GUIDE_SPINE_BONES["pelvis"])
    spine_head, spine_tail = guide_bone_pair(guide, GUIDE_SPINE_BONES["spine"])
    chest_head, chest_tail = guide_bone_pair(guide, GUIDE_SPINE_BONES["chest"])
    neck_head, neck_tail = guide_bone_pair(guide, GUIDE_SPINE_BONES["neck"])
    head_head, head_tail = guide_bone_pair(guide, GUIDE_SPINE_BONES["head"])
    tail_head, tail_tail = guide_bone_pair(guide, GUIDE_SPINE_BONES["tail"])

    center_points = [pelvis_head, pelvis_tail, spine_tail, chest_tail, neck_tail, head_tail, tail_tail]
    leg_points = []
    for leg in LEG_ORDER:
        for bone_name in GUIDE_LEG_BONES[leg].values():
            head, tail = guide_bone_pair(guide, bone_name)
            leg_points.extend((head, tail))

    foot_tails = [guide_bone_pair(guide, GUIDE_LEG_BONES[leg]["foot"])[1] for leg in LEG_ORDER]
    midline_x = average_vectors(center_points).x
    body_center_y = (pelvis_head.y + chest_tail.y) * 0.5
    ground_z = min(point.z for point in foot_tails)
    origin = Vector((midline_x, body_center_y, ground_z))

    def rel(point):
        return (point.x - origin.x, point.y - origin.y, point.z - origin.z)

    def centered(point):
        return centered_point(point, origin)

    def leg_average(leg_a, leg_b, bone_key, use_tail=False):
        index = 1 if use_tail else 0
        point_a = guide_bone_pair(guide, GUIDE_LEG_BONES[leg_a][bone_key])[index]
        point_b = guide_bone_pair(guide, GUIDE_LEG_BONES[leg_b][bone_key])[index]
        average = average_vectors((point_a, point_b))
        return Vector((origin.x, average.y, average.z))

    def leg_width(leg_a, leg_b):
        samples = []
        for leg in (leg_a, leg_b):
            for bone_key in ("upper", "foot"):
                head, tail = guide_bone_pair(guide, GUIDE_LEG_BONES[leg][bone_key])
                samples.extend((abs(head.x - origin.x), abs(tail.x - origin.x)))
        return max(sum(samples) / len(samples), 0.001)

    front_upper_head = leg_average("fl", "fr", "upper")
    front_upper_tail = leg_average("fl", "fr", "upper", True)
    front_lower_tail = leg_average("fl", "fr", "lower", True)
    front_foot_tail = leg_average("fl", "fr", "foot", True)
    rear_upper_head = leg_average("rl", "rr", "upper")
    rear_upper_tail = leg_average("rl", "rr", "upper", True)
    rear_lower_tail = leg_average("rl", "rr", "lower", True)
    rear_foot_tail = leg_average("rl", "rr", "foot", True)

    body_length = max(abs(chest_tail.y - pelvis_head.y), 0.1)
    guide_points = center_points + leg_points
    min_corner, max_corner, size = bounds_from_points(guide_points)
    root_width = max(size.x * 0.45, 0.12)
    control_scale = max(size.z, body_length * 0.35, 0.2)
    label = QUADRUPED_PROFILES.get(guide.get("qwg_profile", "MEDIUM"), QUADRUPED_PROFILES["MEDIUM"])["label"]

    front_leg = {
        "anchor_parent": "chest",
        "guide": "scapula",
        "guide_head": centered(chest_tail),
        "guide_tail": centered(front_upper_head),
        "upper_head": centered(front_upper_head),
        "upper_tail": centered(front_upper_tail),
        "lower_tail": centered(front_lower_tail),
        "foot_tail": centered(front_foot_tail),
        "pole": centered(Vector((origin.x, front_upper_tail.y - body_length * 0.22, front_upper_tail.z))),
    }
    rear_leg = {
        "anchor_parent": "pelvis",
        "guide": "hip",
        "guide_head": centered(pelvis_head),
        "guide_tail": centered(rear_upper_head),
        "upper_head": centered(rear_upper_head),
        "upper_tail": centered(rear_upper_tail),
        "lower_tail": centered(rear_lower_tail),
        "foot_tail": centered(rear_foot_tail),
        "pole": centered(Vector((origin.x, rear_upper_tail.y - body_length * 0.24, rear_upper_tail.z))),
    }

    def exact_leg_profile(leg, anchor_point, pole_factor):
        """Return a per-leg profile from one edited guide chain."""
        upper_head, upper_tail = guide_bone_pair(guide, GUIDE_LEG_BONES[leg]["upper"])
        _, lower_tail = guide_bone_pair(guide, GUIDE_LEG_BONES[leg]["lower"])
        _, foot_tail = guide_bone_pair(guide, GUIDE_LEG_BONES[leg]["foot"])
        pole = Vector((upper_tail.x, upper_tail.y - body_length * pole_factor, upper_tail.z))
        return {
            "guide_head": rel(anchor_point),
            "guide_tail": rel(upper_head),
            "upper_head": rel(upper_head),
            "upper_tail": rel(upper_tail),
            "lower_tail": rel(lower_tail),
            "foot_tail": rel(foot_tail),
            "pole": rel(pole),
        }

    profile = {
        "label": f"{label} Guide",
        "root": {"head": (-root_width, 0.0, 0.0), "tail": (root_width, 0.0, 0.0)},
        "body": {"head": centered(pelvis_head), "tail": centered(chest_tail)},
        "spine": [
            ("pelvis", centered(pelvis_head), centered(pelvis_tail)),
            ("spine_01", centered(spine_head), centered(spine_tail)),
            ("chest", centered(chest_head), centered(chest_tail)),
        ],
        "neck": {"head": centered(neck_head), "tail": centered(neck_tail)},
        "head": {"head": centered(head_head), "tail": centered(head_tail)},
        "tail": [
            ("tail_01", centered(tail_head), centered(average_vectors((tail_head, tail_tail)))),
            ("tail_02", centered(average_vectors((tail_head, tail_tail))), centered(tail_tail)),
        ],
        "leg_width_front": leg_width("fl", "fr"),
        "leg_width_rear": leg_width("rl", "rr"),
        "front_leg": front_leg,
        "rear_leg": rear_leg,
        "leg_overrides": {
            "fl": exact_leg_profile("fl", chest_tail, 0.22),
            "fr": exact_leg_profile("fr", chest_tail, 0.22),
            "rl": exact_leg_profile("rl", pelvis_head, 0.24),
            "rr": exact_leg_profile("rr", pelvis_head, 0.24),
        },
        "control_scale": control_scale,
    }
    return profile, origin


def get_widget_collection(context, armature_name):
    """Create a collection for generated control-shape objects."""
    collection_name = f"{armature_name}_widgets"
    collection = bpy.data.collections.get(collection_name)
    if not collection:
        collection = bpy.data.collections.new(collection_name)
        context.scene.collection.children.link(collection)
    return collection


def create_widget_object(collection, name, vertices, edges):
    """Create a hidden mesh object used as a custom bone shape."""
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, edges, [])
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.display_type = "WIRE"
    obj.hide_render = True
    obj.hide_viewport = True
    return obj


def circle_points(radius=1.0, segments=24, y_scale=1.0):
    """Return vertices and edges for a flat circle-like widget."""
    vertices = []
    edges = []
    for index in range(segments):
        angle = (index / segments) * 6.283185307179586
        vertices.append((radius * cos(angle), radius * y_scale * sin(angle), 0.0))
        edges.append((index, (index + 1) % segments))
    return vertices, edges


def make_widget_shapes(context, armature_name):
    """Build the custom control shapes used by the generated rig."""
    collection = get_widget_collection(context, armature_name)
    square_vertices = [(-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0)]
    square_edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
    diamond_vertices = [(0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)]
    diamond_edges = [(0, 1), (1, 2), (2, 3), (3, 0)]
    body_vertices, body_edges = circle_points(radius=1.0, segments=32, y_scale=1.6)

    return {
        "root": create_widget_object(collection, f"{armature_name}_root_shape", square_vertices, square_edges),
        "body": create_widget_object(collection, f"{armature_name}_body_shape", body_vertices, body_edges),
        "foot": create_widget_object(collection, f"{armature_name}_foot_shape", square_vertices, square_edges),
        "pole": create_widget_object(collection, f"{armature_name}_pole_shape", diamond_vertices, diamond_edges),
    }


def assign_custom_shape(pose_bone, shape, scale_xyz):
    """Assign a custom shape to a pose bone when Blender supports it."""
    pose_bone.custom_shape = shape
    if hasattr(pose_bone, "use_custom_shape_bone_size"):
        pose_bone.use_custom_shape_bone_size = False
    if hasattr(pose_bone, "custom_shape_scale_xyz"):
        pose_bone.custom_shape_scale_xyz = scale_xyz
    else:
        pose_bone.custom_shape_scale = max(scale_xyz)


def assign_control_shapes(context, armature_object, scale, control_scale=1.0):
    """Assign custom widgets to generated control bones."""
    shapes = make_widget_shapes(context, armature_object.name)
    widget_scale = scale * control_scale
    assign_custom_shape(armature_object.pose.bones["root"], shapes["root"], (0.32 * widget_scale, 0.32 * widget_scale, 0.32 * widget_scale))
    assign_custom_shape(armature_object.pose.bones["body"], shapes["body"], (0.46 * widget_scale, 0.24 * widget_scale, 0.46 * widget_scale))

    for leg in LEG_ORDER:
        names = STANDARD_LEG_NAMES[leg]
        assign_custom_shape(armature_object.pose.bones[names["ik"]], shapes["foot"], (0.17 * widget_scale, 0.12 * widget_scale, 0.17 * widget_scale))
        assign_custom_shape(armature_object.pose.bones[names["pole"]], shapes["pole"], (0.09 * widget_scale, 0.09 * widget_scale, 0.09 * widget_scale))


def assign_bone_groups(armature_object):
    """Color generated control and deform bones in Blender versions that support it."""
    if not hasattr(armature_object.pose, "bone_groups"):
        return

    control_group = armature_object.pose.bone_groups.new(name="QWalk Controls")
    control_group.color_set = "THEME09"
    deform_group = armature_object.pose.bone_groups.new(name="QWalk Deform")
    deform_group.color_set = "THEME04"

    control_names = {"root", "body"}
    for leg in LEG_ORDER:
        control_names.add(STANDARD_LEG_NAMES[leg]["ik"])
        control_names.add(STANDARD_LEG_NAMES[leg]["pole"])

    for pose_bone in armature_object.pose.bones:
        pose_bone.bone_group = control_group if pose_bone.name in control_names else deform_group


def activate_body_control(armature_object):
    """Make the body control active when Blender allows it."""
    try:
        armature_object.data.bones.active = armature_object.data.bones["body"]
    except Exception:
        pass


def apply_standard_mapping(settings):
    """Fill scene settings with the generated armature's bone names."""
    settings.root_bone = "root"
    settings.body_bone = "body"

    for leg in LEG_ORDER:
        names = STANDARD_LEG_NAMES[leg]
        setattr(settings, IK_FIELDS[leg], names["ik"])
        upper, lower, foot = FK_FIELDS[leg]
        setattr(settings, upper, names["upper"])
        setattr(settings, lower, names["lower"])
        setattr(settings, foot, names["foot"])


def create_standard_quadruped(
    context,
    name,
    scale=1.0,
    add_ik_constraints=True,
    display_type="STICK",
    profile_key="MEDIUM",
    profile_override=None,
):
    """Create and return a named quadruped armature object."""
    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    resolved_profile_key = profile_key if profile_key in QUADRUPED_PROFILES else "MEDIUM"
    profile = profile_override or QUADRUPED_PROFILES[resolved_profile_key]

    armature_data = bpy.data.armatures.new(name)
    armature_object = bpy.data.objects.new(name, armature_data)
    armature_object["qwg_profile"] = resolved_profile_key
    armature_object["qwg_profile_label"] = profile["label"]
    context.collection.objects.link(armature_object)

    bpy.ops.object.select_all(action="DESELECT")
    armature_object.select_set(True)
    context.view_layer.objects.active = armature_object

    armature_data.display_type = display_type
    armature_object.show_in_front = True

    bpy.ops.object.mode_set(mode="EDIT")
    bones = armature_data.edit_bones

    root = add_edit_bone(
        bones,
        "root",
        profile["root"]["head"],
        profile["root"]["tail"],
        scale,
        deform=False,
    )
    body = add_edit_bone(
        bones,
        "body",
        profile["body"]["head"],
        profile["body"]["tail"],
        scale,
        root,
        deform=False,
    )
    chain_parent = body
    named_bones = {"root": root, "body": body}
    for index, (bone_name, head, tail) in enumerate(profile["spine"]):
        bone = add_edit_bone(bones, bone_name, head, tail, scale, chain_parent, connected=index > 0)
        named_bones[bone_name] = bone
        chain_parent = bone

    neck = add_edit_bone(
        bones,
        "neck",
        profile["neck"]["head"],
        profile["neck"]["tail"],
        scale,
        named_bones["chest"],
        connected=True,
    )
    named_bones["neck"] = neck
    named_bones["head"] = add_edit_bone(
        bones,
        "head",
        profile["head"]["head"],
        profile["head"]["tail"],
        scale,
        neck,
        connected=True,
    )

    tail_parent = named_bones["pelvis"]
    for index, (bone_name, head, tail) in enumerate(profile["tail"]):
        tail_parent = add_edit_bone(bones, bone_name, head, tail, scale, tail_parent, connected=index > 0)
        named_bones[bone_name] = tail_parent

    leg_parents = {"fl": named_bones["chest"], "fr": named_bones["chest"], "rl": named_bones["pelvis"], "rr": named_bones["pelvis"]}
    helper_bone_names = []
    for leg in LEG_ORDER:
        names = STANDARD_LEG_NAMES[leg]
        side = 1.0 if leg.endswith("l") else -1.0
        is_front = leg.startswith("f")
        leg_profile = profile["front_leg"] if is_front else profile["rear_leg"]
        x = side * (profile["leg_width_front"] if is_front else profile["leg_width_rear"])
        point = lambda key: leg_profile_point(profile, leg, leg_profile, key, x)

        guide_name = f"{names['upper'].rsplit('_', 1)[0]}_{leg_profile['guide']}"
        guide = add_edit_bone(
            bones,
            guide_name,
            point("guide_head"),
            point("guide_tail"),
            scale,
            leg_parents[leg],
            deform=False,
        )
        helper_bone_names.append(guide_name)

        upper = add_edit_bone(
            bones,
            names["upper"],
            point("upper_head"),
            point("upper_tail"),
            scale,
            guide,
            True,
        )
        lower = add_edit_bone(
            bones,
            names["lower"],
            point("upper_tail"),
            point("lower_tail"),
            scale,
            upper,
            True,
        )
        add_edit_bone(
            bones,
            names["foot"],
            point("lower_tail"),
            point("foot_tail"),
            scale,
            lower,
            True,
        )
        foot_point = Vector(point("foot_tail"))
        foot_span = max((foot_point - Vector(point("lower_tail"))).length * 0.45, 0.08)
        add_edit_bone(
            bones,
            names["ik"],
            (foot_point.x, foot_point.y - foot_span, foot_point.z),
            (foot_point.x, foot_point.y + foot_span, foot_point.z),
            scale,
            root,
            deform=False,
        )
        pole_point = Vector(point("pole"))
        add_edit_bone(
            bones,
            names["pole"],
            (pole_point.x - 0.07 * side, pole_point.y, pole_point.z),
            (pole_point.x + 0.07 * side, pole_point.y, pole_point.z),
            scale,
            root,
            deform=False,
        )

    bpy.ops.object.mode_set(mode="POSE")
    for pose_bone in armature_object.pose.bones:
        pose_bone.rotation_mode = "XYZ"
    for bone_name in helper_bone_names:
        armature_object.data.bones[bone_name].hide = True
    store_base_pose(armature_object)

    if add_ik_constraints:
        for leg in LEG_ORDER:
            names = STANDARD_LEG_NAMES[leg]
            constraint = armature_object.pose.bones[names["foot"]].constraints.new(type="IK")
            constraint.name = "QWalk IK"
            constraint.target = armature_object
            constraint.subtarget = names["ik"]
            constraint.pole_target = armature_object
            constraint.pole_subtarget = names["pole"]
            constraint.chain_count = 3
            constraint.iterations = 24

    assign_control_shapes(context, armature_object, scale, profile.get("control_scale", 1.0))
    assign_bone_groups(armature_object)
    activate_body_control(armature_object)
    return armature_object


class QWG_OT_create_quadruped_armature(Operator):
    bl_idname = "qwg.create_quadruped_armature"
    bl_label = "Create Quadruped Armature"
    bl_description = "Create a starter quadruped armature compatible with QWalk"
    bl_options = {"REGISTER", "UNDO"}

    armature_name: StringProperty(
        name="Name",
        description="Name for the generated armature object and data",
        default="QWalk_Quadruped",
    )
    scale: FloatProperty(
        name="Scale",
        description="Overall size multiplier for the generated armature",
        default=1.0,
        min=0.01,
        soft_max=10.0,
    )
    body_profile: EnumProperty(
        name="Profile",
        description="Proportion template for the generated quadruped",
        items=profile_items(),
        default="MEDIUM",
    )
    add_ik_constraints: BoolProperty(
        name="Add IK Constraints",
        description="Add IK constraints from lower-leg bones to generated IK targets",
        default=True,
    )
    display_type: EnumProperty(
        name="Display",
        description="Viewport display style for the generated armature",
        items=(
            ("STICK", "Stick", "Clean rig-style display"),
            ("OCTAHEDRAL", "Octahedral", "Classic Blender bone shapes"),
            ("BBONE", "B-Bone", "Thick bendy-bone shapes"),
            ("WIRE", "Wire", "Wireframe bone shapes"),
        ),
        default="STICK",
    )
    map_after_create: BoolProperty(
        name="Map for QWalk",
        description="Fill QWalk bone mapping fields after creating the armature",
        default=True,
    )
    def execute(self, context):
        """Create the standard armature and optionally map it for QWalk."""
        armature = create_standard_quadruped(
            context,
            self.armature_name,
            self.scale,
            self.add_ik_constraints,
            self.display_type,
            self.body_profile,
        )

        if self.map_after_create:
            apply_standard_mapping(context.scene.qwg_settings)

        self.report({"INFO"}, f"Created quadruped armature {armature.name}.")
        return {"FINISHED"}


class QWG_OT_create_fitted_quadruped_armature(Operator):
    bl_idname = "qwg.create_fitted_quadruped_armature"
    bl_label = "Create Fitted Quadruped Armature"
    bl_description = "Create a quadruped armature scaled and placed to the selected mesh bounds"
    bl_options = {"REGISTER", "UNDO"}

    armature_name: StringProperty(
        name="Name",
        description="Name for the generated armature; leave blank to derive it from the mesh",
        default="",
    )
    body_profile: EnumProperty(
        name="Profile",
        description="Proportion template, or Auto to choose from mesh proportions",
        items=fit_profile_items(),
        default="AUTO",
    )
    mesh_forward_axis: EnumProperty(
        name="Mesh Forward",
        description="World axis pointing from tail toward head on the selected mesh",
        items=(
            ("POS_Y", "+Y", "Mesh faces toward positive Y"),
            ("NEG_Y", "-Y", "Mesh faces toward negative Y"),
            ("POS_X", "+X", "Mesh faces toward positive X"),
            ("NEG_X", "-X", "Mesh faces toward negative X"),
        ),
        default="POS_Y",
    )
    fit_amount: FloatProperty(
        name="Fit",
        description="Fraction of the mesh bounds filled by the generated armature",
        default=0.88,
        min=0.1,
        max=1.5,
    )
    robust_bounds: BoolProperty(
        name="Robust Bounds",
        description="Use vertex percentiles so horns, manes, fur, and tails do not dominate the fit",
        default=True,
    )
    top_percentile: FloatProperty(
        name="Top Percentile",
        description="Upper vertical percentile used when Robust Bounds is enabled",
        default=88.0,
        min=60.0,
        max=100.0,
    )
    add_ik_constraints: BoolProperty(
        name="Add IK Constraints",
        description="Add IK constraints from foot bones to generated IK targets",
        default=True,
    )
    display_type: EnumProperty(
        name="Display",
        description="Viewport display style for the generated armature",
        items=(
            ("STICK", "Stick", "Clean rig-style display"),
            ("OCTAHEDRAL", "Octahedral", "Classic Blender bone shapes"),
            ("BBONE", "B-Bone", "Thick bendy-bone shapes"),
            ("WIRE", "Wire", "Wireframe bone shapes"),
        ),
        default="STICK",
    )
    map_after_create: BoolProperty(
        name="Map for QWalk",
        description="Fill QWalk bone mapping fields after creating the armature",
        default=True,
    )
    @classmethod
    def poll(cls, context):
        """Enable the operator when a mesh is active or selected."""
        return active_mesh(context) is not None

    def execute(self, context):
        """Create a quadruped rig fitted to selected mesh bounds."""
        mesh_object = active_mesh(context)
        if not mesh_object:
            self.report({"ERROR"}, "Select a mesh to fit.")
            return {"CANCELLED"}

        fit_points, angle = mesh_points_in_fit_space(mesh_object, context, self.mesh_forward_axis)
        _, _, mesh_size = robust_bounds_from_points(
            fit_points,
            robust=self.robust_bounds,
            top_percentile=self.top_percentile,
        )
        profile_key = profile_from_mesh(mesh_size, "POS_Y") if self.body_profile == "AUTO" else self.body_profile
        profile, origin, _, _, _ = build_landmark_profile(
            fit_points,
            profile_key,
            self.fit_amount,
            robust=self.robust_bounds,
            top_percentile=self.top_percentile,
        )

        armature_name = self.armature_name.strip() or f"{mesh_object.name}_QWalk_Rig"
        armature = create_standard_quadruped(
            context,
            armature_name,
            1.0,
            self.add_ik_constraints,
            self.display_type,
            profile_key,
            profile_override=profile,
        )
        armature["qwg_fit_mesh"] = mesh_object.name
        armature["qwg_fit_profile_requested"] = self.body_profile

        rotated_origin = rotate_z(origin, angle)
        armature.rotation_euler.z = angle
        armature.location = rotated_origin

        store_base_pose(armature)
        if self.map_after_create:
            apply_standard_mapping(context.scene.qwg_settings)

        self.report({"INFO"}, f"Created fitted {profile['label']} armature for {mesh_object.name}.")
        return {"FINISHED"}


class QWG_OT_create_fit_guides(Operator):
    bl_idname = "qwg.create_fit_guides"
    bl_label = "Create Fitting Guides"
    bl_description = "Create an editable QWalk guide armature from the selected mesh"
    bl_options = {"REGISTER", "UNDO"}

    guide_name: StringProperty(
        name="Name",
        description="Name for the generated guide armature; leave blank to derive it from the mesh",
        default="",
    )
    body_profile: EnumProperty(
        name="Profile",
        description="Initial guide proportions, or Auto to choose from mesh proportions",
        items=fit_profile_items(),
        default="AUTO",
    )
    mesh_forward_axis: EnumProperty(
        name="Mesh Forward",
        description="World axis pointing from tail toward head on the selected mesh",
        items=(
            ("POS_Y", "+Y", "Mesh faces toward positive Y"),
            ("NEG_Y", "-Y", "Mesh faces toward negative Y"),
            ("POS_X", "+X", "Mesh faces toward positive X"),
            ("NEG_X", "-X", "Mesh faces toward negative X"),
        ),
        default="POS_Y",
    )
    fit_amount: FloatProperty(
        name="Fit",
        description="Fraction of the mesh bounds filled by the initial guide armature",
        default=0.88,
        min=0.1,
        max=1.5,
    )
    robust_bounds: BoolProperty(
        name="Robust Bounds",
        description="Use vertex percentiles so horns, manes, fur, and tails do not dominate the initial guide fit",
        default=True,
    )
    top_percentile: FloatProperty(
        name="Top Percentile",
        description="Upper vertical percentile used when Robust Bounds is enabled",
        default=88.0,
        min=60.0,
        max=100.0,
    )

    @classmethod
    def poll(cls, context):
        """Enable the operator when a mesh is active or selected."""
        return active_mesh(context) is not None

    def execute(self, context):
        """Create editable guide bones from the selected mesh."""
        mesh_object = active_mesh(context)
        if not mesh_object:
            self.report({"ERROR"}, "Select a mesh to fit.")
            return {"CANCELLED"}

        fit_points, angle = mesh_points_in_fit_space(mesh_object, context, self.mesh_forward_axis)
        _, _, mesh_size = robust_bounds_from_points(
            fit_points,
            robust=self.robust_bounds,
            top_percentile=self.top_percentile,
        )
        profile_key = profile_from_mesh(mesh_size, "POS_Y") if self.body_profile == "AUTO" else self.body_profile
        profile, origin, _, _, _ = build_landmark_profile(
            fit_points,
            profile_key,
            self.fit_amount,
            robust=self.robust_bounds,
            top_percentile=self.top_percentile,
        )

        guide_name = self.guide_name.strip() or f"{mesh_object.name}_QWalk_Guides"
        guide = create_guide_armature(
            context,
            guide_name,
            profile,
            origin,
            angle,
            source_mesh_name=mesh_object.name,
            profile_key=profile_key,
        )
        self.report({"INFO"}, f"Created editable QWalk guides for {mesh_object.name}.")
        return {"FINISHED"}


class QWG_OT_create_armature_from_guides(Operator):
    bl_idname = "qwg.create_armature_from_guides"
    bl_label = "Generate Armature From Guides"
    bl_description = "Generate a QWalk armature from the selected editable guide armature"
    bl_options = {"REGISTER", "UNDO"}

    armature_name: StringProperty(
        name="Name",
        description="Name for the generated armature; leave blank to derive it from the guides",
        default="",
    )
    add_ik_constraints: BoolProperty(
        name="Add IK Constraints",
        description="Add IK constraints from foot bones to generated IK targets",
        default=True,
    )
    display_type: EnumProperty(
        name="Display",
        description="Viewport display style for the generated armature",
        items=(
            ("STICK", "Stick", "Clean rig-style display"),
            ("OCTAHEDRAL", "Octahedral", "Classic Blender bone shapes"),
            ("BBONE", "B-Bone", "Thick bendy-bone shapes"),
            ("WIRE", "Wire", "Wireframe bone shapes"),
        ),
        default="STICK",
    )
    map_after_create: BoolProperty(
        name="Map for QWalk",
        description="Fill QWalk bone mapping fields after creating the armature",
        default=True,
    )
    hide_guides_after_create: BoolProperty(
        name="Hide Guides",
        description="Hide the guide armature after generating the final rig",
        default=True,
    )

    @classmethod
    def poll(cls, context):
        """Enable the operator when a QWalk guide armature is active or selected."""
        return active_guide_armature(context) is not None

    def execute(self, context):
        """Create the final QWalk armature from edited guide bones."""
        guide = active_guide_armature(context)
        if not guide:
            self.report({"ERROR"}, "Select a QWalk guide armature.")
            return {"CANCELLED"}
        if guide.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")

        try:
            profile, origin = build_profile_from_guides(guide)
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        profile_key = guide.get("qwg_profile", "MEDIUM")
        armature_name = self.armature_name.strip() or f"{guide.name}_Rig"
        armature = create_standard_quadruped(
            context,
            armature_name,
            1.0,
            self.add_ik_constraints,
            self.display_type,
            profile_key,
            profile_override=profile,
        )
        armature.location = guide.matrix_world @ origin
        armature.rotation_euler = guide.rotation_euler
        armature.scale = guide.scale
        armature["qwg_guides"] = guide.name
        armature["qwg_profile_requested"] = profile_key

        store_base_pose(armature)
        if self.map_after_create:
            apply_standard_mapping(context.scene.qwg_settings)
        if self.hide_guides_after_create:
            guide.hide_set(True)
            guide.hide_render = True
            guide.select_set(False)
            armature.select_set(True)
            context.view_layer.objects.active = armature

        self.report({"INFO"}, f"Generated QWalk armature from {guide.name}.")
        return {"FINISHED"}
