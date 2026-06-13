"""Pure-Python helpers shared by Blender and web label export paths.

This module must not import bpy so the web export path can run without Blender.
"""

from __future__ import annotations

import json
from pathlib import Path


GUIDE_BONE_NAMES = [
    "qwg_guide_pelvis",
    "qwg_guide_spine",
    "qwg_guide_chest",
    "qwg_guide_neck",
    "qwg_guide_head",
    "qwg_guide_tail",
    "qwg_guide_front_left_upper",
    "qwg_guide_front_left_lower",
    "qwg_guide_front_left_foot",
    "qwg_guide_front_right_upper",
    "qwg_guide_front_right_lower",
    "qwg_guide_front_right_foot",
    "qwg_guide_rear_left_upper",
    "qwg_guide_rear_left_lower",
    "qwg_guide_rear_left_foot",
    "qwg_guide_rear_right_upper",
    "qwg_guide_rear_right_lower",
    "qwg_guide_rear_right_foot",
]

LEG_PREFIXES = {
    "fl": ("front_left", "qwg_guide_front_left_upper", "qwg_guide_front_left_lower", "qwg_guide_front_left_foot"),
    "fr": ("front_right", "qwg_guide_front_right_upper", "qwg_guide_front_right_lower", "qwg_guide_front_right_foot"),
    "rl": ("rear_left", "qwg_guide_rear_left_upper", "qwg_guide_rear_left_lower", "qwg_guide_rear_left_foot"),
    "rr": ("rear_right", "qwg_guide_rear_right_upper", "qwg_guide_rear_right_lower", "qwg_guide_rear_right_foot"),
}


def validate_guide_bones(guide_bones: dict) -> dict[str, dict[str, list[float]]]:
    """Validate and normalize a full canonical guide_bones mapping."""
    if not isinstance(guide_bones, dict):
        raise ValueError("guide_bones must be an object.")
    cleaned: dict[str, dict[str, list[float]]] = {}
    missing = []
    for name in GUIDE_BONE_NAMES:
        endpoints = guide_bones.get(name)
        if not isinstance(endpoints, dict):
            missing.append(name)
            continue
        bone: dict[str, list[float]] = {}
        for endpoint in ("head", "tail"):
            values = endpoints.get(endpoint)
            if not isinstance(values, (list, tuple)) or len(values) < 3:
                raise ValueError(f"Guide bone {name} {endpoint} must be a 3-number array.")
            point = []
            for value in values[:3]:
                number = float(value)
                if number != number or number in (float("inf"), float("-inf")):
                    raise ValueError(f"Guide bone {name} {endpoint} has a non-finite coordinate.")
                point.append(round(number, 6))
            bone[endpoint] = point
        cleaned[name] = bone
    if missing:
        raise ValueError(f"Guide is missing required bones: {', '.join(missing)}")
    return cleaned


def landmarks_from_guide_bones(guide_bones: dict[str, dict[str, list[float]]]) -> dict[str, list[float]]:
    landmarks = {
        "pelvis": guide_bones["qwg_guide_pelvis"]["head"],
        "spine": guide_bones["qwg_guide_spine"]["tail"],
        "chest": guide_bones["qwg_guide_chest"]["tail"],
        "neck": guide_bones["qwg_guide_neck"]["tail"],
        "head": guide_bones["qwg_guide_head"]["tail"],
        "tail": guide_bones["qwg_guide_tail"]["tail"],
    }
    for _, (prefix, upper, lower, foot) in LEG_PREFIXES.items():
        landmarks[f"{prefix}_upper"] = guide_bones[upper]["head"]
        landmarks[f"{prefix}_mid"] = guide_bones[upper]["tail"]
        landmarks[f"{prefix}_lower"] = guide_bones[lower]["tail"]
        landmarks[f"{prefix}_foot"] = guide_bones[foot]["tail"]
    return landmarks


def build_label_metadata(
    *,
    sample_id: str,
    source: str,
    verified: bool,
    animal_type: str,
    morphology_type: str,
    guide_bones: dict[str, dict[str, list[float]]],
    split: str,
    parameters: dict,
) -> dict:
    return {
        "id": sample_id,
        "source": source,
        "verified_label": verified,
        "training_eligible": verified,
        "animal_type": animal_type,
        "morphology_type": morphology_type,
        "axes": {
            "forward": [0.0, 1.0, 0.0],
            "left": [1.0, 0.0, 0.0],
            "up": [0.0, 0.0, 1.0],
        },
        "guide_bones": guide_bones,
        "landmarks": landmarks_from_guide_bones(guide_bones),
        "parameters": parameters,
        "split": split,
        "mesh_file": f"{split}/{sample_id}.obj",
        "label_file": f"{split}/{sample_id}.json",
    }


def write_manifest_and_info(out_dir: Path, metadata: dict) -> None:
    """Upsert one exported label into the real dataset manifest and summary."""
    manifest_path = out_dir / "manifest.jsonl"
    records = []
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("id") != metadata["id"]:
                records.append(record)
    records.append(metadata)
    manifest_path.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )

    animal_types = []
    morphology_types = []
    animal_counts = {}
    split_counts = {}
    verified_count = 0
    for record in records:
        animal = record["animal_type"]
        morphology = record["morphology_type"]
        if animal not in animal_types:
            animal_types.append(animal)
        if morphology not in morphology_types:
            morphology_types.append(morphology)
        animal_counts[animal] = animal_counts.get(animal, 0) + 1
        split_counts[record["split"]] = split_counts.get(record["split"], 0) + 1
        verified_count += 1 if record.get("verified_label", False) else 0

    dataset_info = {
        "source": "real_qwalk_labels",
        "count": len(records),
        "verified_count": verified_count,
        "animal_counts": animal_counts,
        "split_counts": split_counts,
        "label_schema": {
            "animal_type": animal_types,
            "morphology_type": morphology_types,
            "guide_bones": "QWalk guide bone head/tail coordinates in mesh space",
            "landmarks": "Simplified joint/centerline landmarks derived from guide_bones",
            "axes": "forward, left, and up vectors in mesh space",
        },
    }
    (out_dir / "dataset_info.json").write_text(json.dumps(dataset_info, indent=2) + "\n", encoding="utf-8")
