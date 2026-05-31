#!/usr/bin/env python3
"""Generate synthetic quadruped meshes with QWalk guide labels.

The goal of this generator is not production art. It creates varied,
low-cost anatomy proxies with exact landmark labels for training an ML guide
initializer that can predict QWalk guide bones from a mesh or point cloud.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


GUIDE_SPINE_BONES = {
    "pelvis": "qwg_guide_pelvis",
    "spine": "qwg_guide_spine",
    "chest": "qwg_guide_chest",
    "neck": "qwg_guide_neck",
    "head": "qwg_guide_head",
    "tail": "qwg_guide_tail",
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

LEG_ORDER = ("fl", "fr", "rl", "rr")


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    def __add__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, amount: float) -> "Vec3":
        return Vec3(self.x * amount, self.y * amount, self.z * amount)

    def __truediv__(self, amount: float) -> "Vec3":
        return Vec3(self.x / amount, self.y / amount, self.z / amount)

    def dot(self, other: "Vec3") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vec3") -> "Vec3":
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length(self) -> float:
        return math.sqrt(self.dot(self))

    def normalized(self) -> "Vec3":
        length = self.length()
        if length <= 1e-8:
            return Vec3(0.0, 0.0, 1.0)
        return self / length

    def rotated_z(self, angle: float) -> "Vec3":
        cosine = math.cos(angle)
        sine = math.sin(angle)
        return Vec3(
            self.x * cosine - self.y * sine,
            self.x * sine + self.y * cosine,
            self.z,
        )

    def as_list(self) -> list[float]:
        return [round(self.x, 6), round(self.y, 6), round(self.z, 6)]


@dataclass
class MeshBuilder:
    vertices: list[Vec3]
    faces: list[tuple[int, ...]]

    def add_vertex(self, point: Vec3) -> int:
        self.vertices.append(point)
        return len(self.vertices) - 1

    def add_face(self, indices: tuple[int, ...]) -> None:
        self.faces.append(indices)

    def transformed(self, angle: float) -> "MeshBuilder":
        return MeshBuilder([vertex.rotated_z(angle) for vertex in self.vertices], list(self.faces))


def uniform(rng: random.Random, value_range: tuple[float, float]) -> float:
    return rng.uniform(value_range[0], value_range[1])


def midpoint(a: Vec3, b: Vec3) -> Vec3:
    return (a + b) * 0.5


def lerp(a: Vec3, b: Vec3, amount: float) -> Vec3:
    return a + (b - a) * amount


def jittered(point: Vec3, rng: random.Random, amount: float) -> Vec3:
    if amount <= 0.0:
        return point
    return Vec3(
        point.x + rng.uniform(-amount, amount),
        point.y + rng.uniform(-amount, amount),
        point.z + rng.uniform(-amount, amount),
    )


def add_ellipsoid(
    mesh: MeshBuilder,
    center: Vec3,
    radii: Vec3,
    rng: random.Random,
    rings: int = 8,
    segments: int = 14,
    noise: float = 0.0,
) -> None:
    """Add an axis-aligned ellipsoid elongated along its local Y pole."""
    rows: list[list[int]] = []
    for ring in range(rings + 1):
        phi = math.pi * ring / rings
        sin_phi = math.sin(phi)
        cos_phi = math.cos(phi)
        row = []
        for segment in range(segments):
            theta = math.tau * segment / segments
            scale_noise = 1.0 + rng.uniform(-noise, noise)
            local = Vec3(
                radii.x * math.cos(theta) * sin_phi * scale_noise,
                radii.y * cos_phi * scale_noise,
                radii.z * math.sin(theta) * sin_phi * scale_noise,
            )
            row.append(mesh.add_vertex(center + local))
        rows.append(row)

    for ring in range(rings):
        current = rows[ring]
        next_row = rows[ring + 1]
        for segment in range(segments):
            mesh.add_face(
                (
                    current[segment],
                    current[(segment + 1) % segments],
                    next_row[(segment + 1) % segments],
                    next_row[segment],
                )
            )


def tube_basis(start: Vec3, end: Vec3) -> tuple[Vec3, Vec3, Vec3]:
    axis = (end - start).normalized()
    reference = Vec3(0.0, 0.0, 1.0)
    if abs(axis.dot(reference)) > 0.92:
        reference = Vec3(1.0, 0.0, 0.0)
    side = axis.cross(reference).normalized()
    up = side.cross(axis).normalized()
    return axis, side, up


def add_tapered_tube(
    mesh: MeshBuilder,
    start: Vec3,
    end: Vec3,
    start_radius: float,
    end_radius: float,
    rng: random.Random,
    segments: int = 10,
    rings: int = 2,
    noise: float = 0.0,
) -> None:
    """Add a low-poly tube between two points."""
    if (end - start).length() <= 1e-5:
        return
    _, side, up = tube_basis(start, end)
    rows: list[list[int]] = []
    for ring in range(rings + 1):
        amount = ring / rings
        center = lerp(start, end, amount)
        radius = start_radius * (1.0 - amount) + end_radius * amount
        row = []
        for segment in range(segments):
            theta = math.tau * segment / segments
            radial = side * math.cos(theta) + up * math.sin(theta)
            point = center + radial * (radius * (1.0 + rng.uniform(-noise, noise)))
            row.append(mesh.add_vertex(point))
        rows.append(row)

    for ring in range(rings):
        current = rows[ring]
        next_row = rows[ring + 1]
        for segment in range(segments):
            mesh.add_face(
                (
                    current[segment],
                    current[(segment + 1) % segments],
                    next_row[(segment + 1) % segments],
                    next_row[segment],
                )
            )


SPECIES = {
    "horse": {
        "morphology_type": "ungulate",
        "body_length": (2.2, 2.9),
        "body_width": (0.44, 0.62),
        "body_depth": (0.58, 0.82),
        "shoulder_height": (1.25, 1.75),
        "hip_height": (1.18, 1.68),
        "neck_length": (0.62, 1.02),
        "neck_rise": (0.22, 0.55),
        "head_length": (0.34, 0.55),
        "tail_length": (0.45, 0.88),
        "front_width": (0.22, 0.34),
        "rear_width": (0.24, 0.38),
        "limb_radius": (0.045, 0.075),
        "foot_length": (0.16, 0.28),
        "foot_width": (0.045, 0.075),
        "body_noise": (0.00, 0.035),
        "features": ("ears", "mane"),
        "leg_style": "vertical",
    },
    "dog": {
        "morphology_type": "digitigrade",
        "body_length": (1.25, 2.0),
        "body_width": (0.32, 0.58),
        "body_depth": (0.42, 0.72),
        "shoulder_height": (0.72, 1.22),
        "hip_height": (0.68, 1.16),
        "neck_length": (0.28, 0.54),
        "neck_rise": (0.04, 0.18),
        "head_length": (0.28, 0.48),
        "tail_length": (0.28, 0.82),
        "front_width": (0.18, 0.34),
        "rear_width": (0.18, 0.36),
        "limb_radius": (0.035, 0.075),
        "foot_length": (0.15, 0.28),
        "foot_width": (0.055, 0.105),
        "body_noise": (0.00, 0.045),
        "features": ("ears",),
        "leg_style": "digitigrade",
    },
    "cat": {
        "morphology_type": "digitigrade",
        "body_length": (1.05, 1.75),
        "body_width": (0.24, 0.42),
        "body_depth": (0.30, 0.50),
        "shoulder_height": (0.48, 0.82),
        "hip_height": (0.50, 0.88),
        "neck_length": (0.18, 0.36),
        "neck_rise": (0.00, 0.12),
        "head_length": (0.18, 0.32),
        "tail_length": (0.55, 1.05),
        "front_width": (0.12, 0.22),
        "rear_width": (0.13, 0.24),
        "limb_radius": (0.025, 0.05),
        "foot_length": (0.11, 0.22),
        "foot_width": (0.045, 0.08),
        "body_noise": (0.00, 0.035),
        "features": ("ears",),
        "leg_style": "digitigrade",
    },
    "giraffe": {
        "morphology_type": "long_neck_ungulate",
        "body_length": (2.0, 2.8),
        "body_width": (0.40, 0.58),
        "body_depth": (0.54, 0.75),
        "shoulder_height": (2.15, 3.1),
        "hip_height": (1.95, 2.85),
        "neck_length": (1.45, 2.35),
        "neck_rise": (1.05, 1.85),
        "head_length": (0.34, 0.56),
        "tail_length": (0.35, 0.7),
        "front_width": (0.22, 0.34),
        "rear_width": (0.24, 0.38),
        "limb_radius": (0.035, 0.065),
        "foot_length": (0.14, 0.25),
        "foot_width": (0.04, 0.07),
        "body_noise": (0.00, 0.03),
        "features": ("ears", "ossicones"),
        "leg_style": "vertical",
    },
    "turtle": {
        "morphology_type": "shelled_sprawled",
        "body_length": (0.9, 1.55),
        "body_width": (0.62, 1.02),
        "body_depth": (0.26, 0.45),
        "shoulder_height": (0.26, 0.48),
        "hip_height": (0.25, 0.44),
        "neck_length": (0.18, 0.34),
        "neck_rise": (-0.04, 0.08),
        "head_length": (0.14, 0.26),
        "tail_length": (0.12, 0.32),
        "front_width": (0.38, 0.62),
        "rear_width": (0.40, 0.66),
        "limb_radius": (0.045, 0.085),
        "foot_length": (0.11, 0.22),
        "foot_width": (0.07, 0.14),
        "body_noise": (0.00, 0.025),
        "features": ("shell",),
        "leg_style": "sprawled",
    },
    "lizard": {
        "morphology_type": "sprawled",
        "body_length": (1.25, 2.35),
        "body_width": (0.22, 0.44),
        "body_depth": (0.20, 0.36),
        "shoulder_height": (0.28, 0.52),
        "hip_height": (0.28, 0.50),
        "neck_length": (0.16, 0.34),
        "neck_rise": (-0.03, 0.08),
        "head_length": (0.20, 0.38),
        "tail_length": (0.85, 1.75),
        "front_width": (0.28, 0.52),
        "rear_width": (0.30, 0.56),
        "limb_radius": (0.025, 0.055),
        "foot_length": (0.11, 0.24),
        "foot_width": (0.04, 0.09),
        "body_noise": (0.00, 0.05),
        "features": (),
        "leg_style": "sprawled",
    },
    "ram": {
        "morphology_type": "stocky_ungulate",
        "body_length": (1.35, 2.05),
        "body_width": (0.46, 0.76),
        "body_depth": (0.55, 0.86),
        "shoulder_height": (0.85, 1.28),
        "hip_height": (0.82, 1.24),
        "neck_length": (0.28, 0.52),
        "neck_rise": (0.08, 0.26),
        "head_length": (0.24, 0.42),
        "tail_length": (0.08, 0.24),
        "front_width": (0.24, 0.42),
        "rear_width": (0.26, 0.45),
        "limb_radius": (0.045, 0.085),
        "foot_length": (0.10, 0.2),
        "foot_width": (0.045, 0.08),
        "body_noise": (0.02, 0.075),
        "features": ("horns", "ears"),
        "leg_style": "vertical",
    },
}


def sample_parameters(animal_type: str, rng: random.Random) -> dict[str, float | str | tuple[str, ...]]:
    preset = SPECIES[animal_type]
    params: dict[str, float | str | tuple[str, ...]] = {
        "animal_type": animal_type,
        "morphology_type": preset["morphology_type"],
        "features": preset["features"],
        "leg_style": preset["leg_style"],
    }
    for key, value in preset.items():
        if isinstance(value, tuple) and value and isinstance(value[0], (int, float)):
            params[key] = uniform(rng, value)

    scale = uniform(rng, (0.82, 1.22))
    for key, value in list(params.items()):
        if isinstance(value, float) and key not in {"body_noise"}:
            params[key] = value * scale
    return params


def leg_points(
    leg: str,
    params: dict[str, float | str | tuple[str, ...]],
    body_length: float,
    shoulder_z: float,
    hip_z: float,
    rng: random.Random,
) -> tuple[Vec3, Vec3, Vec3, Vec3]:
    """Return guide upper-head, upper-tail, lower-tail, and foot-tail."""
    is_front = leg.startswith("f")
    is_left = leg.endswith("l")
    side = 1.0 if is_left else -1.0
    style = str(params["leg_style"])
    front_width = float(params["front_width"])
    rear_width = float(params["rear_width"])
    foot_width = front_width if is_front else rear_width
    foot_length = float(params["foot_length"])
    body_depth = float(params["body_depth"])

    anchor_y = body_length * (0.34 if is_front else -0.34)
    foot_y = anchor_y + uniform(rng, (-0.08, 0.16)) * body_length if is_front else anchor_y + uniform(rng, (-0.16, 0.08)) * body_length
    upper_z = (shoulder_z if is_front else hip_z) - body_depth * uniform(rng, (0.18, 0.36))
    upper_z = max(upper_z, body_depth * 0.45)

    if style == "sprawled":
        shoulder_x = side * foot_width * uniform(rng, (0.42, 0.62))
        elbow_x = side * foot_width * uniform(rng, (0.82, 1.08))
        ankle_x = side * foot_width * uniform(rng, (1.0, 1.18))
        foot_x = side * foot_width * uniform(rng, (1.05, 1.28))
        elbow_z = upper_z * uniform(rng, (0.45, 0.62))
        ankle_z = upper_z * uniform(rng, (0.18, 0.30))
        foot_tip_y = foot_y + (foot_length * 0.55 if is_front else -foot_length * 0.40)
        upper_head = Vec3(shoulder_x, anchor_y, upper_z)
        upper_tail = Vec3(elbow_x, anchor_y + uniform(rng, (-0.10, 0.10)) * body_length, elbow_z)
        lower_tail = Vec3(ankle_x, foot_y, ankle_z)
        foot_tail = Vec3(foot_x, foot_tip_y, 0.035)
        return upper_head, upper_tail, lower_tail, foot_tail

    x = side * foot_width
    bend_direction = -1.0 if is_front else 1.0
    if style == "digitigrade":
        elbow_y = anchor_y + bend_direction * uniform(rng, (0.05, 0.14)) * body_length
        ankle_y = foot_y - bend_direction * uniform(rng, (0.03, 0.10)) * body_length
        foot_tip_y = foot_y + uniform(rng, (0.05, 0.16)) * body_length
        elbow_z = upper_z * uniform(rng, (0.54, 0.68))
        ankle_z = upper_z * uniform(rng, (0.18, 0.30))
    else:
        elbow_y = anchor_y + bend_direction * uniform(rng, (0.02, 0.08)) * body_length
        ankle_y = foot_y - bend_direction * uniform(rng, (0.01, 0.07)) * body_length
        foot_tip_y = foot_y + (foot_length * uniform(rng, (0.40, 0.85)))
        elbow_z = upper_z * uniform(rng, (0.54, 0.70))
        ankle_z = upper_z * uniform(rng, (0.18, 0.28))

    side_noise = foot_width * uniform(rng, (-0.08, 0.08))
    upper_head = Vec3(x + side_noise, anchor_y, upper_z)
    upper_tail = Vec3(x + side_noise * 0.5, elbow_y, elbow_z)
    lower_tail = Vec3(x, ankle_y, ankle_z)
    foot_tail = Vec3(x, foot_tip_y, 0.035)
    return upper_head, upper_tail, lower_tail, foot_tail


def build_guide_bones(params: dict[str, float | str | tuple[str, ...]], rng: random.Random) -> dict[str, dict[str, Vec3]]:
    body_length = float(params["body_length"])
    body_depth = float(params["body_depth"])
    shoulder_height = float(params["shoulder_height"])
    hip_height = float(params["hip_height"])
    neck_length = float(params["neck_length"])
    neck_rise = float(params["neck_rise"])
    head_length = float(params["head_length"])
    tail_length = float(params["tail_length"])

    pelvis_head = Vec3(0.0, -body_length * 0.45, hip_height)
    pelvis_tail = Vec3(0.0, -body_length * 0.18, (hip_height * 0.72 + shoulder_height * 0.28))
    spine_tail = Vec3(0.0, body_length * 0.12, (hip_height + shoulder_height) * 0.5)
    chest_tail = Vec3(0.0, body_length * 0.45, shoulder_height)
    neck_tail = Vec3(
        0.0,
        chest_tail.y + neck_length * uniform(rng, (0.52, 0.78)),
        chest_tail.z + neck_rise,
    )
    head_tail = Vec3(
        0.0,
        neck_tail.y + head_length,
        neck_tail.z - body_depth * uniform(rng, (0.02, 0.18)),
    )
    tail_tail = Vec3(
        0.0,
        pelvis_head.y - tail_length,
        max(0.05, pelvis_head.z + uniform(rng, (-0.18, 0.12)) * body_depth),
    )

    guide_bones: dict[str, dict[str, Vec3]] = {
        GUIDE_SPINE_BONES["pelvis"]: {"head": pelvis_head, "tail": pelvis_tail},
        GUIDE_SPINE_BONES["spine"]: {"head": pelvis_tail, "tail": spine_tail},
        GUIDE_SPINE_BONES["chest"]: {"head": spine_tail, "tail": chest_tail},
        GUIDE_SPINE_BONES["neck"]: {"head": chest_tail, "tail": neck_tail},
        GUIDE_SPINE_BONES["head"]: {"head": neck_tail, "tail": head_tail},
        GUIDE_SPINE_BONES["tail"]: {"head": pelvis_head, "tail": tail_tail},
    }

    for leg in LEG_ORDER:
        upper_head, upper_tail, lower_tail, foot_tail = leg_points(
            leg,
            params,
            body_length,
            shoulder_height,
            hip_height,
            rng,
        )
        names = GUIDE_LEG_BONES[leg]
        guide_bones[names["upper"]] = {"head": upper_head, "tail": upper_tail}
        guide_bones[names["lower"]] = {"head": upper_tail, "tail": lower_tail}
        guide_bones[names["foot"]] = {"head": lower_tail, "tail": foot_tail}

    return guide_bones


def add_body_mesh(
    mesh: MeshBuilder,
    guide_bones: dict[str, dict[str, Vec3]],
    params: dict[str, float | str | tuple[str, ...]],
    rng: random.Random,
) -> None:
    body_length = float(params["body_length"])
    body_width = float(params["body_width"])
    body_depth = float(params["body_depth"])
    body_noise = float(params["body_noise"])
    features = tuple(params["features"]) if isinstance(params["features"], tuple) else ()

    pelvis = guide_bones[GUIDE_SPINE_BONES["pelvis"]]["head"]
    chest = guide_bones[GUIDE_SPINE_BONES["chest"]]["tail"]
    spine_center = midpoint(pelvis, chest)
    body_center = Vec3(0.0, spine_center.y, spine_center.z - body_depth * 0.22)

    add_ellipsoid(
        mesh,
        body_center,
        Vec3(body_width * 0.5, body_length * 0.52, body_depth * 0.52),
        rng,
        rings=9,
        segments=16,
        noise=body_noise,
    )

    if "shell" in features:
        shell_center = Vec3(0.0, body_center.y, body_center.z + body_depth * 0.18)
        add_ellipsoid(
            mesh,
            shell_center,
            Vec3(body_width * 0.62, body_length * 0.50, body_depth * 0.46),
            rng,
            rings=8,
            segments=18,
            noise=body_noise * 0.5,
        )


def add_head_neck_tail_mesh(
    mesh: MeshBuilder,
    guide_bones: dict[str, dict[str, Vec3]],
    params: dict[str, float | str | tuple[str, ...]],
    rng: random.Random,
) -> None:
    body_width = float(params["body_width"])
    body_depth = float(params["body_depth"])
    limb_radius = float(params["limb_radius"])
    head_length = float(params["head_length"])
    animal_type = str(params["animal_type"])
    features = tuple(params["features"]) if isinstance(params["features"], tuple) else ()

    neck = guide_bones[GUIDE_SPINE_BONES["neck"]]
    head = guide_bones[GUIDE_SPINE_BONES["head"]]
    tail = guide_bones[GUIDE_SPINE_BONES["tail"]]

    neck_radius = max(limb_radius * 1.2, body_width * (0.10 if animal_type != "giraffe" else 0.07))
    add_tapered_tube(mesh, neck["head"], neck["tail"], neck_radius * 1.2, neck_radius, rng, rings=3, noise=0.03)

    head_center = midpoint(head["head"], head["tail"])
    add_ellipsoid(
        mesh,
        head_center,
        Vec3(body_width * 0.18, head_length * 0.48, body_depth * 0.20),
        rng,
        rings=7,
        segments=12,
        noise=0.035,
    )

    tail_radius = max(limb_radius * 0.65, body_width * 0.035)
    add_tapered_tube(mesh, tail["head"], tail["tail"], tail_radius * 1.4, tail_radius * 0.35, rng, rings=4, noise=0.04)

    if "ears" in features:
        ear_base_y = head["tail"].y - head_length * 0.36
        ear_base_z = head_center.z + body_depth * 0.16
        for side in (-1.0, 1.0):
            base = Vec3(side * body_width * 0.08, ear_base_y, ear_base_z)
            tip = Vec3(side * body_width * 0.16, ear_base_y - head_length * 0.08, ear_base_z + body_depth * 0.24)
            add_tapered_tube(mesh, base, tip, limb_radius * 0.45, limb_radius * 0.10, rng, segments=8, rings=1)

    if "ossicones" in features:
        for side in (-1.0, 1.0):
            base = Vec3(side * body_width * 0.06, head_center.y, head_center.z + body_depth * 0.15)
            tip = base + Vec3(side * body_width * 0.02, 0.0, body_depth * 0.22)
            add_tapered_tube(mesh, base, tip, limb_radius * 0.32, limb_radius * 0.18, rng, segments=8, rings=1)

    if "horns" in features:
        for side in (-1.0, 1.0):
            base = Vec3(side * body_width * 0.10, head_center.y - head_length * 0.1, head_center.z + body_depth * 0.10)
            mid = base + Vec3(side * body_width * 0.20, -head_length * 0.12, body_depth * 0.06)
            tip = mid + Vec3(side * body_width * 0.08, -head_length * 0.18, -body_depth * 0.08)
            add_tapered_tube(mesh, base, mid, limb_radius * 0.55, limb_radius * 0.40, rng, segments=8, rings=1)
            add_tapered_tube(mesh, mid, tip, limb_radius * 0.40, limb_radius * 0.16, rng, segments=8, rings=1)

    if "mane" in features:
        for index in range(5):
            amount = index / 4.0
            point = lerp(neck["head"], neck["tail"], amount) + Vec3(0.0, 0.0, body_depth * 0.08)
            add_ellipsoid(mesh, point, Vec3(body_width * 0.045, body_width * 0.035, body_depth * 0.06), rng, rings=4, segments=8, noise=0.08)


def add_leg_mesh(
    mesh: MeshBuilder,
    guide_bones: dict[str, dict[str, Vec3]],
    params: dict[str, float | str | tuple[str, ...]],
    rng: random.Random,
) -> None:
    limb_radius = float(params["limb_radius"])
    foot_width = float(params["foot_width"])
    foot_length = float(params["foot_length"])
    style = str(params["leg_style"])
    for leg in LEG_ORDER:
        names = GUIDE_LEG_BONES[leg]
        upper = guide_bones[names["upper"]]
        lower = guide_bones[names["lower"]]
        foot = guide_bones[names["foot"]]

        add_tapered_tube(mesh, upper["head"], upper["tail"], limb_radius * 1.2, limb_radius, rng, rings=2, noise=0.04)
        add_tapered_tube(mesh, lower["head"], lower["tail"], limb_radius, limb_radius * 0.82, rng, rings=2, noise=0.04)
        add_tapered_tube(mesh, foot["head"], foot["tail"], limb_radius * 0.82, limb_radius * 0.55, rng, rings=1, noise=0.04)

        paw_center = midpoint(foot["head"], foot["tail"])
        paw_z = max(0.035, paw_center.z)
        lateral_scale = 1.2 if style == "sprawled" else 1.0
        add_ellipsoid(
            mesh,
            Vec3(paw_center.x, paw_center.y, paw_z),
            Vec3(foot_width * lateral_scale, foot_length * 0.33, limb_radius * 0.55),
            rng,
            rings=5,
            segments=10,
            noise=0.03,
        )


def build_landmarks(guide_bones: dict[str, dict[str, Vec3]]) -> dict[str, Vec3]:
    landmarks = {
        "pelvis": guide_bones[GUIDE_SPINE_BONES["pelvis"]]["head"],
        "spine": guide_bones[GUIDE_SPINE_BONES["spine"]]["tail"],
        "chest": guide_bones[GUIDE_SPINE_BONES["chest"]]["tail"],
        "neck": guide_bones[GUIDE_SPINE_BONES["neck"]]["tail"],
        "head": guide_bones[GUIDE_SPINE_BONES["head"]]["tail"],
        "tail": guide_bones[GUIDE_SPINE_BONES["tail"]]["tail"],
    }
    for leg in LEG_ORDER:
        prefix = {
            "fl": "front_left",
            "fr": "front_right",
            "rl": "rear_left",
            "rr": "rear_right",
        }[leg]
        names = GUIDE_LEG_BONES[leg]
        landmarks[f"{prefix}_upper"] = guide_bones[names["upper"]]["head"]
        landmarks[f"{prefix}_mid"] = guide_bones[names["upper"]]["tail"]
        landmarks[f"{prefix}_lower"] = guide_bones[names["lower"]]["tail"]
        landmarks[f"{prefix}_foot"] = guide_bones[names["foot"]]["tail"]
    return landmarks


def rotate_guide_bones(guide_bones: dict[str, dict[str, Vec3]], angle: float) -> dict[str, dict[str, Vec3]]:
    return {
        name: {
            "head": pair["head"].rotated_z(angle),
            "tail": pair["tail"].rotated_z(angle),
        }
        for name, pair in guide_bones.items()
    }


def serialize_guide_bones(guide_bones: dict[str, dict[str, Vec3]]) -> dict[str, dict[str, list[float]]]:
    return {
        name: {
            "head": pair["head"].as_list(),
            "tail": pair["tail"].as_list(),
        }
        for name, pair in guide_bones.items()
    }


def serialize_landmarks(landmarks: dict[str, Vec3]) -> dict[str, list[float]]:
    return {name: point.as_list() for name, point in landmarks.items()}


def write_obj(path: Path, mesh: MeshBuilder) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Synthetic QWalk quadruped\n")
        for vertex in mesh.vertices:
            handle.write(f"v {vertex.x:.6f} {vertex.y:.6f} {vertex.z:.6f}\n")
        for face in mesh.faces:
            indices = " ".join(str(index + 1) for index in face)
            handle.write(f"f {indices}\n")


def generate_sample(sample_id: str, sample_seed: int, random_yaw: bool) -> tuple[MeshBuilder, dict]:
    rng = random.Random(sample_seed)
    animal_type = rng.choice(tuple(SPECIES.keys()))
    params = sample_parameters(animal_type, rng)
    guide_bones = build_guide_bones(params, rng)

    mesh = MeshBuilder([], [])
    add_body_mesh(mesh, guide_bones, params, rng)
    add_head_neck_tail_mesh(mesh, guide_bones, params, rng)
    add_leg_mesh(mesh, guide_bones, params, rng)

    yaw = rng.uniform(-math.pi, math.pi) if random_yaw else 0.0
    if yaw:
        mesh = mesh.transformed(yaw)
        guide_bones = rotate_guide_bones(guide_bones, yaw)

    landmarks = build_landmarks(guide_bones)
    forward = Vec3(0.0, 1.0, 0.0).rotated_z(yaw)
    left = Vec3(1.0, 0.0, 0.0).rotated_z(yaw)
    metadata = {
        "id": sample_id,
        "source": "qwalk_synthetic_v1",
        "animal_type": params["animal_type"],
        "morphology_type": params["morphology_type"],
        "axes": {
            "forward": forward.as_list(),
            "left": left.as_list(),
            "up": [0.0, 0.0, 1.0],
        },
        "guide_bones": serialize_guide_bones(guide_bones),
        "landmarks": serialize_landmarks(landmarks),
        "parameters": {
            "sample_seed": sample_seed,
            "yaw_radians": round(yaw, 6),
            "features": list(params["features"]) if isinstance(params["features"], tuple) else [],
            "leg_style": params["leg_style"],
        },
    }
    return mesh, metadata


def split_for_index(index: int, count: int, train_ratio: float, val_ratio: float) -> str:
    fraction = (index + 0.5) / max(1, count)
    if fraction < train_ratio:
        return "train"
    if fraction < train_ratio + val_ratio:
        return "val"
    return "test"


def clean_generated_outputs(out_dir: Path) -> None:
    """Remove files this generator creates so reruns cannot leave stale samples."""
    for split in ("train", "val", "test"):
        split_dir = out_dir / split
        if not split_dir.exists():
            continue
        for pattern in ("syn_*.obj", "syn_*.json"):
            for path in split_dir.glob(pattern):
                if path.is_file():
                    path.unlink()

    for filename in ("manifest.jsonl", "dataset_info.json"):
        path = out_dir / filename
        if path.is_file():
            path.unlink()


def generate_dataset(args: argparse.Namespace) -> dict:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.clean:
        clean_generated_outputs(out_dir)
    for split in ("train", "val", "test"):
        (out_dir / split).mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    manifest_path = out_dir / "manifest.jsonl"
    animal_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()

    with manifest_path.open("w", encoding="utf-8") as manifest:
        for index in range(args.count):
            sample_id = f"syn_{index:06d}"
            split = split_for_index(index, args.count, args.train_ratio, args.val_ratio)
            sample_seed = rng.randrange(1, 2**31 - 1)
            mesh, metadata = generate_sample(sample_id, sample_seed, args.random_yaw)

            metadata["split"] = split
            metadata["mesh_file"] = f"{split}/{sample_id}.obj"
            metadata["label_file"] = f"{split}/{sample_id}.json"

            split_dir = out_dir / split
            if args.write_obj:
                write_obj(split_dir / f"{sample_id}.obj", mesh)
            with (split_dir / f"{sample_id}.json").open("w", encoding="utf-8") as label_file:
                json.dump(metadata, label_file, indent=2)
                label_file.write("\n")

            manifest.write(json.dumps(metadata, separators=(",", ":")) + "\n")
            animal_counts[str(metadata["animal_type"])] += 1
            split_counts[split] += 1

    info = {
        "source": "qwalk_synthetic_v1",
        "count": args.count,
        "seed": args.seed,
        "random_yaw": args.random_yaw,
        "write_obj": args.write_obj,
        "animal_counts": dict(sorted(animal_counts.items())),
        "split_counts": dict(sorted(split_counts.items())),
        "label_schema": {
            "animal_type": sorted(SPECIES.keys()),
            "morphology_type": sorted({str(item["morphology_type"]) for item in SPECIES.values()}),
            "guide_bones": "QWalk guide bone head/tail coordinates in mesh space",
            "landmarks": "Simplified joint/centerline landmarks derived from guide_bones",
            "axes": "forward, left, and up vectors in mesh space",
        },
    }
    with (out_dir / "dataset_info.json").open("w", encoding="utf-8") as info_file:
        json.dump(info, info_file, indent=2)
        info_file.write("\n")
    return info


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic QWalk quadruped training data.")
    parser.add_argument("--count", type=int, default=1000, help="Number of synthetic quadrupeds to generate.")
    parser.add_argument("--out", default="data/synthetic_quadrupeds", help="Output dataset directory.")
    parser.add_argument("--seed", type=int, default=20260531, help="Dataset RNG seed.")
    parser.add_argument("--train-ratio", type=float, default=0.80, help="Fraction of samples assigned to train.")
    parser.add_argument("--val-ratio", type=float, default=0.10, help="Fraction of samples assigned to validation.")
    parser.add_argument("--no-random-yaw", action="store_false", dest="random_yaw", help="Keep all meshes +Y forward.")
    parser.add_argument("--labels-only", action="store_false", dest="write_obj", help="Write labels and manifest, but skip OBJ meshes.")
    parser.add_argument("--no-clean", action="store_false", dest="clean", help="Do not remove old syn_*.obj/json outputs before writing.")
    parser.set_defaults(random_yaw=True, write_obj=True, clean=True)
    args = parser.parse_args()
    if args.count <= 0:
        parser.error("--count must be positive.")
    if args.train_ratio <= 0 or args.val_ratio < 0 or args.train_ratio + args.val_ratio >= 1.0:
        parser.error("--train-ratio and --val-ratio must leave a positive test split.")
    return args


def main() -> None:
    info = generate_dataset(parse_args())
    print(
        "Generated {count} synthetic quadrupeds at data root with splits {splits} and animal counts {animals}.".format(
            count=info["count"],
            splits=info["split_counts"],
            animals=info["animal_counts"],
        )
    )


if __name__ == "__main__":
    main()
