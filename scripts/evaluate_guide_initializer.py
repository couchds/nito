#!/usr/bin/env python3
"""Evaluate a trained QWalk guide initializer checkpoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from train_guide_initializer import (
    PointNetGuideInitializer,
    QuadrupedPointDataset,
    evaluate,
    load_samples,
    resolve_device,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a trained QWalk guide initializer.")
    parser.add_argument("--data", default="data/synthetic_quadrupeds", help="Synthetic dataset directory.")
    parser.add_argument("--checkpoint", default="models/qwalk_guide_initializer/qwalk_guide_initializer.pt")
    parser.add_argument("--split", default="test", choices=("train", "val", "test"))
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--out", default="", help="Optional JSON metrics output path.")
    parser.add_argument("--animal-weight", type=float, default=0.08)
    parser.add_argument("--morphology-weight", type=float, default=0.08)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    device = resolve_device(args.device)
    checkpoint_path = Path(args.checkpoint)
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    samples, animal_types, morphology_types = load_samples(Path(args.data), args.split)
    dataset = QuadrupedPointDataset(
        samples,
        animal_types,
        morphology_types,
        int(checkpoint.get("num_points", 1024)),
        augment=False,
    )
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)
    model = PointNetGuideInitializer(
        len(checkpoint["target_point_names"]),
        len(checkpoint["animal_types"]),
        len(checkpoint["morphology_types"]),
    ).to(device)
    model.load_state_dict(checkpoint["model_state"])
    metrics = evaluate(model, loader, device, args.animal_weight, args.morphology_weight)
    result = {
        "checkpoint": str(checkpoint_path),
        "checkpoint_epoch": checkpoint.get("epoch"),
        "split": args.split,
        "sample_count": len(samples),
        "metrics": metrics,
    }
    print(json.dumps(result, indent=2))
    if args.out:
        output_path = Path(args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
