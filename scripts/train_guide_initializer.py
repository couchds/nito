#!/usr/bin/env python3
"""Train a point-cloud QWalk guide initializer from verified Nito labels."""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, Dataset
except ImportError as error:  # pragma: no cover - exercised by users without torch installed.
    raise SystemExit(
        "PyTorch is required for training. Install it in a local venv, for example:\n"
        "  python -m venv .venv\n"
        "  .\\.venv\\Scripts\\python.exe -m pip install torch numpy\n"
    ) from error


TARGET_POINT_SPECS = [
    ("pelvis_head", "qwg_guide_pelvis", "head"),
    ("pelvis_tail", "qwg_guide_pelvis", "tail"),
    ("spine_tail", "qwg_guide_spine", "tail"),
    ("chest_tail", "qwg_guide_chest", "tail"),
    ("neck_tail", "qwg_guide_neck", "tail"),
    ("head_tail", "qwg_guide_head", "tail"),
    ("tail_tail", "qwg_guide_tail", "tail"),
    ("front_left_upper", "qwg_guide_front_left_upper", "head"),
    ("front_left_mid", "qwg_guide_front_left_upper", "tail"),
    ("front_left_lower", "qwg_guide_front_left_lower", "tail"),
    ("front_left_foot", "qwg_guide_front_left_foot", "tail"),
    ("front_right_upper", "qwg_guide_front_right_upper", "head"),
    ("front_right_mid", "qwg_guide_front_right_upper", "tail"),
    ("front_right_lower", "qwg_guide_front_right_lower", "tail"),
    ("front_right_foot", "qwg_guide_front_right_foot", "tail"),
    ("rear_left_upper", "qwg_guide_rear_left_upper", "head"),
    ("rear_left_mid", "qwg_guide_rear_left_upper", "tail"),
    ("rear_left_lower", "qwg_guide_rear_left_lower", "tail"),
    ("rear_left_foot", "qwg_guide_rear_left_foot", "tail"),
    ("rear_right_upper", "qwg_guide_rear_right_upper", "head"),
    ("rear_right_mid", "qwg_guide_rear_right_upper", "tail"),
    ("rear_right_lower", "qwg_guide_rear_right_lower", "tail"),
    ("rear_right_foot", "qwg_guide_rear_right_foot", "tail"),
]
TARGET_POINT_NAMES = [name for name, _, _ in TARGET_POINT_SPECS]

GUIDE_BONE_CHAIN = {
    "qwg_guide_pelvis": ("pelvis_head", "pelvis_tail"),
    "qwg_guide_spine": ("pelvis_tail", "spine_tail"),
    "qwg_guide_chest": ("spine_tail", "chest_tail"),
    "qwg_guide_neck": ("chest_tail", "neck_tail"),
    "qwg_guide_head": ("neck_tail", "head_tail"),
    "qwg_guide_tail": ("pelvis_head", "tail_tail"),
    "qwg_guide_front_left_upper": ("front_left_upper", "front_left_mid"),
    "qwg_guide_front_left_lower": ("front_left_mid", "front_left_lower"),
    "qwg_guide_front_left_foot": ("front_left_lower", "front_left_foot"),
    "qwg_guide_front_right_upper": ("front_right_upper", "front_right_mid"),
    "qwg_guide_front_right_lower": ("front_right_mid", "front_right_lower"),
    "qwg_guide_front_right_foot": ("front_right_lower", "front_right_foot"),
    "qwg_guide_rear_left_upper": ("rear_left_upper", "rear_left_mid"),
    "qwg_guide_rear_left_lower": ("rear_left_mid", "rear_left_lower"),
    "qwg_guide_rear_left_foot": ("rear_left_lower", "rear_left_foot"),
    "qwg_guide_rear_right_upper": ("rear_right_upper", "rear_right_mid"),
    "qwg_guide_rear_right_lower": ("rear_right_mid", "rear_right_lower"),
    "qwg_guide_rear_right_foot": ("rear_right_lower", "rear_right_foot"),
}


@dataclass(frozen=True)
class Sample:
    sample_id: str
    mesh_file: Path
    animal_type: str
    morphology_type: str
    points: np.ndarray
    guide_points: np.ndarray
    center: np.ndarray
    scale: float


def read_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def read_obj_vertices(path: Path) -> np.ndarray:
    vertices = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("v "):
                _, x, y, z = line.split()[:4]
                vertices.append((float(x), float(y), float(z)))
    if not vertices:
        raise ValueError(f"{path} has no OBJ vertex lines.")
    return np.asarray(vertices, dtype=np.float32)


def normalize_points(points: np.ndarray, guide_points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    center = (mins + maxs) * 0.5
    scale = float(np.max(maxs - mins))
    if scale <= 1e-8:
        scale = 1.0
    return (points - center) / scale, (guide_points - center) / scale, center.astype(np.float32), scale


def extract_guide_points(record: dict) -> np.ndarray:
    return np.asarray(
        [record["guide_bones"][bone_name][endpoint] for _, bone_name, endpoint in TARGET_POINT_SPECS],
        dtype=np.float32,
    )


def load_samples(
    data_dir: Path,
    split: str,
    *,
    require_verified_labels: bool = False,
) -> tuple[list[Sample], list[str], list[str]]:
    info_path = data_dir / "dataset_info.json"
    manifest_path = data_dir / "manifest.jsonl"
    if not info_path.exists() or not manifest_path.exists():
        raise FileNotFoundError(f"{data_dir} must contain dataset_info.json and manifest.jsonl.")

    info = json.loads(info_path.read_text(encoding="utf-8"))
    animal_types = list(info["label_schema"]["animal_type"])
    morphology_types = list(info["label_schema"]["morphology_type"])
    samples = []
    for record in read_jsonl(manifest_path):
        if record["split"] != split:
            continue
        if require_verified_labels and not record.get("verified_label", False):
            continue
        mesh_file = data_dir / record["mesh_file"]
        vertices = read_obj_vertices(mesh_file)
        guide_points = extract_guide_points(record)
        points, norm_guide_points, center, scale = normalize_points(vertices, guide_points)
        samples.append(
            Sample(
                sample_id=record["id"],
                mesh_file=mesh_file,
                animal_type=record["animal_type"],
                morphology_type=record["morphology_type"],
                points=points.astype(np.float32),
                guide_points=norm_guide_points.astype(np.float32),
                center=center,
                scale=scale,
            )
        )
    if not samples:
        verified_note = " verified" if require_verified_labels else ""
        raise ValueError(f"No{verified_note} samples found for split '{split}' in {manifest_path}.")
    return samples, animal_types, morphology_types


class QuadrupedPointDataset(Dataset):
    def __init__(
        self,
        samples: list[Sample],
        animal_types: list[str],
        morphology_types: list[str],
        num_points: int,
        augment: bool,
    ) -> None:
        self.samples = samples
        self.animal_index = {name: index for index, name in enumerate(animal_types)}
        self.morphology_index = {name: index for index, name in enumerate(morphology_types)}
        self.num_points = num_points
        self.augment = augment

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor | str]:
        sample = self.samples[index]
        point_count = sample.points.shape[0]
        replace = point_count < self.num_points
        chosen = np.random.choice(point_count, self.num_points, replace=replace)
        points = sample.points[chosen].copy()

        if self.augment:
            points += np.random.normal(0.0, 0.003, size=points.shape).astype(np.float32)

        return {
            "id": sample.sample_id,
            "points": torch.from_numpy(points.T).float(),
            "guide_points": torch.from_numpy(sample.guide_points.reshape(-1)).float(),
            "animal": torch.tensor(self.animal_index[sample.animal_type], dtype=torch.long),
            "morphology": torch.tensor(self.morphology_index[sample.morphology_type], dtype=torch.long),
            "center": torch.from_numpy(sample.center).float(),
            "scale": torch.tensor(sample.scale, dtype=torch.float32),
        }


class PointNetGuideInitializer(nn.Module):
    def __init__(self, guide_point_count: int, animal_count: int, morphology_count: int) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv1d(3, 64, 1),
            nn.BatchNorm1d(64),
            nn.ReLU(inplace=True),
            nn.Conv1d(64, 128, 1),
            nn.BatchNorm1d(128),
            nn.ReLU(inplace=True),
            nn.Conv1d(128, 256, 1),
            nn.BatchNorm1d(256),
            nn.ReLU(inplace=True),
            nn.Conv1d(256, 512, 1),
            nn.BatchNorm1d(512),
            nn.ReLU(inplace=True),
        )
        self.shared = nn.Sequential(
            nn.Linear(512, 384),
            nn.ReLU(inplace=True),
            nn.Dropout(0.15),
            nn.Linear(384, 256),
            nn.ReLU(inplace=True),
        )
        self.guide_points = nn.Linear(256, guide_point_count * 3)
        self.animal = nn.Linear(256, animal_count)
        self.morphology = nn.Linear(256, morphology_count)

    def forward(self, points: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        features = self.encoder(points)
        pooled = torch.max(features, dim=2).values
        shared = self.shared(pooled)
        return self.guide_points(shared), self.animal(shared), self.morphology(shared)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def resolve_device(name: str) -> torch.device:
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(name)


def batch_loss(
    outputs: tuple[torch.Tensor, torch.Tensor, torch.Tensor],
    batch: dict[str, torch.Tensor],
    animal_weight: float,
    morphology_weight: float,
) -> tuple[torch.Tensor, dict[str, float]]:
    pred_guide_points, pred_animal, pred_morphology = outputs
    guide_point_loss = nn.functional.mse_loss(pred_guide_points, batch["guide_points"])
    animal_loss = nn.functional.cross_entropy(pred_animal, batch["animal"])
    morphology_loss = nn.functional.cross_entropy(pred_morphology, batch["morphology"])
    loss = guide_point_loss + animal_loss * animal_weight + morphology_loss * morphology_weight
    return loss, {
        "guide_point_loss": float(guide_point_loss.detach().cpu()),
        "animal_loss": float(animal_loss.detach().cpu()),
        "morphology_loss": float(morphology_loss.detach().cpu()),
    }


@torch.no_grad()
def evaluate(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
    animal_weight: float,
    morphology_weight: float,
) -> dict[str, float]:
    model.eval()
    total_loss = 0.0
    total_guide_point_error = 0.0
    total_animal_correct = 0
    total_morphology_correct = 0
    total_samples = 0
    total_batches = 0

    for batch in loader:
        tensor_batch = {
            key: value.to(device)
            for key, value in batch.items()
            if isinstance(value, torch.Tensor)
        }
        outputs = model(tensor_batch["points"])
        loss, _ = batch_loss(outputs, tensor_batch, animal_weight, morphology_weight)
        pred_guide_points, pred_animal, pred_morphology = outputs
        batch_size = tensor_batch["points"].shape[0]

        pred = pred_guide_points.reshape(batch_size, len(TARGET_POINT_NAMES), 3)
        truth = tensor_batch["guide_points"].reshape(batch_size, len(TARGET_POINT_NAMES), 3)
        scale = tensor_batch["scale"].reshape(batch_size, 1, 1)
        world_error = torch.linalg.norm((pred - truth) * scale, dim=2).mean(dim=1)

        total_loss += float(loss.detach().cpu())
        total_guide_point_error += float(world_error.sum().detach().cpu())
        total_animal_correct += int((pred_animal.argmax(dim=1) == tensor_batch["animal"]).sum().detach().cpu())
        total_morphology_correct += int((pred_morphology.argmax(dim=1) == tensor_batch["morphology"]).sum().detach().cpu())
        total_samples += batch_size
        total_batches += 1

    return {
        "loss": total_loss / max(1, total_batches),
        "mean_guide_point_error": total_guide_point_error / max(1, total_samples),
        "animal_accuracy": total_animal_correct / max(1, total_samples),
        "morphology_accuracy": total_morphology_correct / max(1, total_samples),
    }


@torch.no_grad()
def write_predictions(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
    output_path: Path,
    animal_types: list[str],
    morphology_types: list[str],
    limit: int,
) -> None:
    model.eval()
    written = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for batch in loader:
            tensor_batch = {
                key: value.to(device)
                for key, value in batch.items()
                if isinstance(value, torch.Tensor)
            }
            pred_guide_points, pred_animal, pred_morphology = model(tensor_batch["points"])
            batch_size = pred_guide_points.shape[0]
            pred = pred_guide_points.reshape(batch_size, len(TARGET_POINT_NAMES), 3).cpu().numpy()
            centers = tensor_batch["center"].cpu().numpy()
            scales = tensor_batch["scale"].cpu().numpy()
            animal_pred = pred_animal.argmax(dim=1).cpu().numpy()
            morph_pred = pred_morphology.argmax(dim=1).cpu().numpy()

            for row in range(batch_size):
                world = pred[row] * scales[row] + centers[row]
                record = {
                    "id": batch["id"][row],
                    "predicted_animal_type": animal_types[int(animal_pred[row])],
                    "predicted_morphology_type": morphology_types[int(morph_pred[row])],
                    "predicted_guide_points": {
                        name: [round(float(value), 6) for value in world[index]]
                        for index, name in enumerate(TARGET_POINT_NAMES)
                    },
                }
                record["predicted_guide_bones"] = guide_bones_from_points(record["predicted_guide_points"])
                handle.write(json.dumps(record, separators=(",", ":")) + "\n")
                written += 1
                if written >= limit:
                    return


def guide_bones_from_points(points_by_name: dict[str, list[float]]) -> dict[str, dict[str, list[float]]]:
    return {
        bone_name: {
            "head": points_by_name[head_name],
            "tail": points_by_name[tail_name],
        }
        for bone_name, (head_name, tail_name) in GUIDE_BONE_CHAIN.items()
    }


def train(args: argparse.Namespace) -> dict[str, float]:
    set_seed(args.seed)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    device = resolve_device(args.device)

    if not args.real_data:
        raise ValueError("--real-data is required.")
    real_dir = Path(args.real_data)
    train_samples, animal_types, morphology_types = load_samples(
        real_dir,
        "train",
        require_verified_labels=not args.allow_unverified_real,
    )
    try:
        val_samples, _, _ = load_samples(real_dir, "val", require_verified_labels=not args.allow_unverified_real)
    except ValueError:
        val_samples = train_samples
    try:
        test_samples, _, _ = load_samples(real_dir, "test", require_verified_labels=not args.allow_unverified_real)
    except ValueError:
        test_samples = val_samples

    train_dataset = QuadrupedPointDataset(train_samples, animal_types, morphology_types, args.num_points, augment=True)
    val_dataset = QuadrupedPointDataset(val_samples, animal_types, morphology_types, args.num_points, augment=False)
    test_dataset = QuadrupedPointDataset(test_samples, animal_types, morphology_types, args.num_points, augment=False)

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)

    model = PointNetGuideInitializer(len(TARGET_POINT_NAMES), len(animal_types), len(morphology_types)).to(device)
    if args.init_checkpoint:
        checkpoint = torch.load(args.init_checkpoint, map_location=device, weights_only=False)
        model.load_state_dict(checkpoint["model_state"])
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, args.epochs))

    best_val = math.inf
    best_metrics: dict[str, float] = {}
    best_path = out_dir / "qwalk_guide_initializer.pt"
    history = []

    print(f"Training only on {len(train_samples)} verified real sample(s).")
    if val_samples is train_samples or test_samples is val_samples:
        print("Validation/test splits were not present, so Nito is reusing available labeled samples for metrics.")
    print(f"Training on {len(train_samples)} samples, validating on {len(val_samples)}, testing on {len(test_samples)}.")
    print(f"Device: {device}; points/sample: {args.num_points}; guide points: {len(TARGET_POINT_NAMES)}.")

    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        running_guide_point = 0.0
        for batch in train_loader:
            tensor_batch = {
                key: value.to(device)
                for key, value in batch.items()
                if isinstance(value, torch.Tensor)
            }
            optimizer.zero_grad(set_to_none=True)
            outputs = model(tensor_batch["points"])
            loss, pieces = batch_loss(outputs, tensor_batch, args.animal_weight, args.morphology_weight)
            loss.backward()
            optimizer.step()
            running_loss += float(loss.detach().cpu())
            running_guide_point += pieces["guide_point_loss"]
        scheduler.step()

        val_metrics = evaluate(model, val_loader, device, args.animal_weight, args.morphology_weight)
        train_loss = running_loss / max(1, len(train_loader))
        train_guide_point = running_guide_point / max(1, len(train_loader))
        epoch_record = {
            "epoch": epoch,
            "train_loss": train_loss,
            "train_guide_point_loss": train_guide_point,
            **{f"val_{key}": value for key, value in val_metrics.items()},
        }
        history.append(epoch_record)

        print(
            "epoch {epoch:03d} train_loss={train_loss:.5f} val_loss={val_loss:.5f} "
            "val_guide_point_err={err:.4f} animal_acc={animal:.3f} morph_acc={morph:.3f}".format(
                epoch=epoch,
                train_loss=train_loss,
                val_loss=val_metrics["loss"],
                err=val_metrics["mean_guide_point_error"],
                animal=val_metrics["animal_accuracy"],
                morph=val_metrics["morphology_accuracy"],
            )
        )

        if val_metrics["mean_guide_point_error"] < best_val:
            best_val = val_metrics["mean_guide_point_error"]
            best_metrics = val_metrics
            torch.save(
                {
                    "model_state": model.state_dict(),
                    "target_point_names": TARGET_POINT_NAMES,
                    "target_point_specs": TARGET_POINT_SPECS,
                    "guide_bone_chain": GUIDE_BONE_CHAIN,
                    "animal_types": animal_types,
                    "morphology_types": morphology_types,
                    "num_points": args.num_points,
                    "normalization": "bbox_center_and_max_extent",
                    "epoch": epoch,
                    "val_metrics": val_metrics,
                    "args": vars(args),
                    "real_sample_count": len(train_samples),
                },
                best_path,
            )

    checkpoint = torch.load(best_path, map_location=device, weights_only=False)
    model.load_state_dict(checkpoint["model_state"])
    test_metrics = evaluate(model, test_loader, device, args.animal_weight, args.morphology_weight)
    metrics = {
        "best_val_epoch": checkpoint["epoch"],
        **{f"best_val_{key}": value for key, value in best_metrics.items()},
        **{f"test_{key}": value for key, value in test_metrics.items()},
    }

    with (out_dir / "metrics.json").open("w", encoding="utf-8") as handle:
        json.dump({"metrics": metrics, "history": history}, handle, indent=2)
        handle.write("\n")

    write_predictions(
        model,
        test_loader,
        device,
        out_dir / "test_predictions_preview.jsonl",
        animal_types,
        morphology_types,
        args.prediction_preview,
    )
    print(f"Saved checkpoint to {best_path}")
    print(json.dumps(metrics, indent=2))
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a Nito guide initializer from verified labels.")
    parser.add_argument("--real-data", required=True, help="Verified real labeled dataset directory.")
    parser.add_argument("--real-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--allow-unverified-real",
        action="store_true",
        help="Allow real labels without verified_label=true. Intended only for debugging, not training.",
    )
    parser.add_argument("--init-checkpoint", default="", help="Optional checkpoint to initialize/fine-tune from.")
    parser.add_argument("--out", default="models/qwalk_guide_initializer", help="Output directory for model artifacts.")
    parser.add_argument("--epochs", type=int, default=40, help="Training epochs.")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size.")
    parser.add_argument("--num-points", type=int, default=1024, help="Point samples per mesh.")
    parser.add_argument("--lr", type=float, default=1e-3, help="Learning rate.")
    parser.add_argument("--weight-decay", type=float, default=1e-4, help="AdamW weight decay.")
    parser.add_argument("--animal-weight", type=float, default=0.08, help="Auxiliary animal classification loss weight.")
    parser.add_argument("--morphology-weight", type=float, default=0.08, help="Auxiliary morphology classification loss weight.")
    parser.add_argument("--device", default="auto", help="auto, cpu, cuda, or a torch device string.")
    parser.add_argument("--seed", type=int, default=20260531, help="Training RNG seed.")
    parser.add_argument("--prediction-preview", type=int, default=20, help="Number of test predictions to export as JSONL.")
    args = parser.parse_args()
    if args.epochs <= 0:
        parser.error("--epochs must be positive.")
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive.")
    if args.num_points <= 0:
        parser.error("--num-points must be positive.")
    return args


def main() -> None:
    train(parse_args())


if __name__ == "__main__":
    main()
