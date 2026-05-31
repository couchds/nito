#!/usr/bin/env python3
"""Predict QWalk guide bones for an OBJ mesh using a trained initializer."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import torch

from train_guide_initializer import (
    PointNetGuideInitializer,
    TARGET_POINT_NAMES,
    guide_bones_from_points,
    read_obj_vertices,
    resolve_device,
)


LEG_POINT_GROUPS = {
    "front_left": ("front_left_upper", "front_left_mid", "front_left_lower", "front_left_foot"),
    "front_right": ("front_right_upper", "front_right_mid", "front_right_lower", "front_right_foot"),
    "rear_left": ("rear_left_upper", "rear_left_mid", "rear_left_lower", "rear_left_foot"),
    "rear_right": ("rear_right_upper", "rear_right_mid", "rear_right_lower", "rear_right_foot"),
}

CENTERLINE_POINTS = (
    "pelvis_head",
    "pelvis_tail",
    "spine_tail",
    "chest_tail",
    "neck_tail",
    "head_tail",
    "tail_tail",
)

MIRROR_POINT_PAIRS = (
    ("front_left_upper", "front_right_upper"),
    ("front_left_mid", "front_right_mid"),
    ("front_left_lower", "front_right_lower"),
    ("front_left_foot", "front_right_foot"),
    ("rear_left_upper", "rear_right_upper"),
    ("rear_left_mid", "rear_right_mid"),
    ("rear_left_lower", "rear_right_lower"),
    ("rear_left_foot", "rear_right_foot"),
)


def normalize_vertices(vertices: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    mins = vertices.min(axis=0)
    maxs = vertices.max(axis=0)
    center = ((mins + maxs) * 0.5).astype(np.float32)
    scale = float(np.max(maxs - mins))
    if scale <= 1e-8:
        scale = 1.0
    return ((vertices - center) / scale).astype(np.float32), center, scale


def rotate_z(points: np.ndarray, angle: float) -> np.ndarray:
    cosine = math.cos(angle)
    sine = math.sin(angle)
    rotated = points.copy()
    rotated[:, 0] = points[:, 0] * cosine - points[:, 1] * sine
    rotated[:, 1] = points[:, 0] * sine + points[:, 1] * cosine
    return rotated.astype(np.float32)


def alignment_angle(vertices: np.ndarray, forward_axis: str) -> tuple[float, str]:
    axis = forward_axis
    if axis == "AUTO":
        mins = vertices.min(axis=0)
        maxs = vertices.max(axis=0)
        size = maxs - mins
        axis = "POS_X" if size[0] >= size[1] else "POS_Y"
    angle = {
        "POS_Y": 0.0,
        "NEG_Y": math.pi,
        "POS_X": math.pi * 0.5,
        "NEG_X": -math.pi * 0.5,
    }[axis]
    return angle, axis


def sample_points(points: np.ndarray, count: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    replace = len(points) < count
    chosen = rng.choice(len(points), count, replace=replace)
    return points[chosen]


def softmax(values: torch.Tensor) -> list[float]:
    return torch.softmax(values, dim=0).detach().cpu().numpy().round(6).astype(float).tolist()


def load_model(checkpoint_path: Path, device: torch.device) -> tuple[PointNetGuideInitializer, dict]:
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    animal_types = checkpoint["animal_types"]
    morphology_types = checkpoint["morphology_types"]
    target_names = checkpoint.get("target_point_names", TARGET_POINT_NAMES)
    if target_names != TARGET_POINT_NAMES:
        raise ValueError("Checkpoint target point schema does not match this predictor.")

    model = PointNetGuideInitializer(len(TARGET_POINT_NAMES), len(animal_types), len(morphology_types)).to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    return model, checkpoint


def postprocess_canonical_points(points: dict[str, np.ndarray], vertices: np.ndarray, enabled: bool) -> dict[str, np.ndarray]:
    if not enabled:
        return points

    processed = {name: np.asarray(value, dtype=np.float32).copy() for name, value in points.items()}
    mins = vertices.min(axis=0)
    maxs = vertices.max(axis=0)
    extent = float(np.max(maxs - mins))
    ground_z = float(mins[2])
    foot_z = ground_z + max(extent * 0.01, 0.01)
    min_lower_gap = max(extent * 0.04, 0.035)
    midline_x = float(np.median([processed[name][0] for name in CENTERLINE_POINTS]))

    for name in CENTERLINE_POINTS:
        processed[name][0] = midline_x

    for left_name, right_name in MIRROR_POINT_PAIRS:
        left = processed[left_name]
        right = processed[right_name]
        side_distance = max(abs(float(left[0] - midline_x)), abs(float(right[0] - midline_x)), extent * 0.04)
        y = (float(left[1]) + float(right[1])) * 0.5
        z = (float(left[2]) + float(right[2])) * 0.5
        processed[left_name] = np.asarray([midline_x + side_distance, y, z], dtype=np.float32)
        processed[right_name] = np.asarray([midline_x - side_distance, y, z], dtype=np.float32)

    for names in LEG_POINT_GROUPS.values():
        upper, mid, lower, foot = names
        processed[foot][2] = foot_z
        processed[lower][2] = max(float(processed[lower][2]), foot_z + min_lower_gap)
        processed[mid][2] = max(float(processed[mid][2]), float(processed[lower][2]) + min_lower_gap)
        processed[upper][2] = max(float(processed[upper][2]), float(processed[mid][2]) + min_lower_gap)

    return processed


def serialize_points(points: dict[str, np.ndarray]) -> dict[str, list[float]]:
    return {
        name: [round(float(value), 6) for value in point]
        for name, point in points.items()
    }


@torch.no_grad()
def predict(args: argparse.Namespace) -> dict:
    obj_path = Path(args.obj).expanduser().resolve()
    checkpoint_path = Path(args.checkpoint).expanduser().resolve()
    device = resolve_device(args.device)
    model, checkpoint = load_model(checkpoint_path, device)

    vertices = read_obj_vertices(obj_path)
    align_angle, resolved_axis = alignment_angle(vertices, args.mesh_forward_axis)
    aligned_vertices = rotate_z(vertices, align_angle)
    normalized, center, scale = normalize_vertices(aligned_vertices)
    num_points = args.num_points or int(checkpoint.get("num_points", 1024))
    sampled = sample_points(normalized, num_points, args.seed)
    tensor = torch.from_numpy(sampled.T).unsqueeze(0).to(device)

    pred_points, pred_animal, pred_morphology = model(tensor.float())
    aligned_world_points = pred_points.reshape(len(TARGET_POINT_NAMES), 3).cpu().numpy() * scale + center
    aligned_points = {
        name: aligned_world_points[index]
        for index, name in enumerate(TARGET_POINT_NAMES)
    }
    aligned_points = postprocess_canonical_points(aligned_points, aligned_vertices, not args.no_postprocess)
    constrained_aligned_world = np.asarray([aligned_points[name] for name in TARGET_POINT_NAMES], dtype=np.float32)
    world_points = rotate_z(constrained_aligned_world, -align_angle)
    predicted_points = serialize_points(
        {
            name: world_points[index]
            for index, name in enumerate(TARGET_POINT_NAMES)
        }
    )

    animal_probs = softmax(pred_animal[0])
    morphology_probs = softmax(pred_morphology[0])
    animal_types = checkpoint["animal_types"]
    morphology_types = checkpoint["morphology_types"]
    animal_index = int(torch.argmax(pred_animal[0]).detach().cpu())
    morphology_index = int(torch.argmax(pred_morphology[0]).detach().cpu())

    result = {
        "source": "qwalk_guide_initializer_prediction_v1",
        "id": obj_path.stem,
        "mesh_file": str(obj_path),
        "checkpoint": str(checkpoint_path),
        "num_points": num_points,
        "postprocessed": not args.no_postprocess,
        "mesh_forward_axis": resolved_axis,
        "alignment_angle_radians": round(align_angle, 6),
        "predicted_animal_type": animal_types[animal_index],
        "predicted_animal_confidence": animal_probs[animal_index],
        "predicted_morphology_type": morphology_types[morphology_index],
        "predicted_morphology_confidence": morphology_probs[morphology_index],
        "animal_probabilities": dict(zip(animal_types, animal_probs)),
        "morphology_probabilities": dict(zip(morphology_types, morphology_probs)),
        "predicted_guide_points": predicted_points,
        "predicted_guide_bones": guide_bones_from_points(predicted_points),
        "normalization": {
            "center": [round(float(value), 6) for value in center],
            "scale": round(float(scale), 6),
        },
    }

    output_path = Path(args.out).expanduser().resolve() if args.out else obj_path.with_suffix(".qwalk_prediction.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")

    print(
        "Predicted {animal} ({animal_conf:.2f}) / {morphology} ({morph_conf:.2f}) guides for {mesh} -> {out}".format(
            animal=result["predicted_animal_type"],
            animal_conf=result["predicted_animal_confidence"],
            morphology=result["predicted_morphology_type"],
            morph_conf=result["predicted_morphology_confidence"],
            mesh=obj_path.name,
            out=output_path,
        )
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Predict QWalk guide bones for an OBJ mesh.")
    parser.add_argument("obj", help="OBJ mesh to predict guides for.")
    parser.add_argument(
        "--checkpoint",
        default="models/qwalk_guide_initializer/qwalk_guide_initializer.pt",
        help="Trained guide initializer checkpoint.",
    )
    parser.add_argument("--out", default="", help="Prediction JSON path. Defaults to <obj>.qwalk_prediction.json.")
    parser.add_argument("--num-points", type=int, default=0, help="Point samples. Defaults to checkpoint setting.")
    parser.add_argument(
        "--mesh-forward-axis",
        default="AUTO",
        choices=("AUTO", "POS_Y", "NEG_Y", "POS_X", "NEG_X"),
        help="World axis from tail toward head. AUTO uses the dominant horizontal extent.",
    )
    parser.add_argument("--device", default="auto", help="auto, cpu, cuda, or a torch device string.")
    parser.add_argument("--seed", type=int, default=20260531, help="Point sampling seed.")
    parser.add_argument("--no-postprocess", action="store_true", help="Skip foot-grounding and limb-height cleanup.")
    args = parser.parse_args()
    if args.num_points < 0:
        parser.error("--num-points cannot be negative.")
    return args


def main() -> None:
    predict(parse_args())


if __name__ == "__main__":
    main()
