#!/usr/bin/env python3
"""Local web UI for the QWalk training-asset workflow."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "web"
DEFAULT_WORK_ROOT = REPO_ROOT / "data" / "automated_training"
DEFAULT_CATALOG = REPO_ROOT / "prompts" / "quadruped_reference_prompts.json"
WORKFLOW_SCRIPT = REPO_ROOT / "scripts" / "automated_training_workflow.py"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MODEL_EXTENSIONS = {".glb", ".gltf"}
REFERENCE_ORDER = ("front", "left", "right", "back")
REVIEW_ORDER = ("front", "left", "right", "rear", "top", "quarter")
DEFAULT_VIEW_INSTRUCTIONS = {
    "front": "front orthographic view, animal facing directly toward the camera",
    "left": "left side orthographic profile, animal facing toward the viewer's left",
    "right": "right side orthographic profile, animal facing toward the viewer's right",
    "back": "back orthographic view, animal facing directly away from the camera",
}


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def safe_token(value: Any, default: str) -> str:
    text = str(value or "").strip()
    if not text:
        return default
    allowed = []
    for character in text:
        if character.isalnum() or character in {"_", "-"}:
            allowed.append(character)
    return "".join(allowed)[:48] or default


class WorkflowStore:
    def __init__(self, work_root: Path, catalog_path: Path) -> None:
        self.work_root = work_root.expanduser().resolve()
        self.catalog_path = catalog_path.expanduser().resolve()
        self.job_root = self.work_root / "ui_jobs"

    def catalog(self) -> dict[str, Any]:
        catalog = read_json(self.catalog_path, {})
        specs = catalog.get("specs", [])
        animals = sorted({spec.get("animal_type", "") for spec in specs if spec.get("animal_type")})
        return {
            "path": str(self.catalog_path),
            "defaults": catalog.get("defaults", {}),
            "animals": animals,
            "specs": specs,
        }

    def sample_states(self) -> list[dict[str, Any]]:
        samples: list[dict[str, Any]] = []
        sample_batches = self.sample_membership()
        if not self.work_root.exists():
            return samples
        for state_path in sorted(self.work_root.glob("*/workflow_state.json")):
            state = read_json(state_path, {})
            if not state:
                continue
            sample_id = state.get("sample_id") or state_path.parent.name
            source_images = self.image_map(state.get("reference_image"), "reference")
            reference_images = self.image_map(state.get("openai_reference_images"), "reference")
            multiview_images = self.image_map(state.get("tripo_multiview_images"), "multiview")
            review_images = self.review_images(state.get("review_dir"))
            model_file = state.get("downloaded_model", "")
            model_url = self.artifact_url(model_file)
            samples.append(
                {
                    "sample_id": sample_id,
                    "prompt": state.get("prompt", ""),
                    "prompt_spec_id": state.get("reference_prompt_spec_id", ""),
                    "openai_reference_prompts": state.get("openai_reference_prompts", {}),
                    "animal_type": state.get("animal_type", ""),
                    "morphology_type": state.get("morphology_type", ""),
                    "armor_state": state.get("armor_state", ""),
                    "status": state.get("status", ""),
                    "created_at": state.get("created_at", 0),
                    "updated_at": state.get("updated_at", state.get("created_at", 0)),
                    "face_limit": (state.get("batch_runner") or {}).get("face_limit"),
                    "batches": sample_batches.get(sample_id, []),
                    "source_images": source_images,
                    "reference_images": reference_images,
                    "multiview_images": multiview_images,
                    "review_images": review_images,
                    "thumbnail_url": self.thumbnail_url(state, reference_images, multiview_images, review_images),
                    "model": {
                        "file": model_file,
                        "name": Path(model_file).name if model_file else "",
                        "type": Path(model_file).suffix.lower().removeprefix(".") if model_file else "",
                        "url": model_url,
                        "remote_url": state.get("downloaded_model_url", ""),
                    },
                    "model_file": model_file,
                    "model_url": model_url,
                    "review_dir": state.get("review_dir", ""),
                    "label_work_blend": state.get("label_work_blend", ""),
                }
            )
        samples.sort(key=lambda item: (item.get("updated_at") or 0, item["sample_id"]), reverse=True)
        return samples[:120]

    def batch_summaries(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for run_path in sorted((self.work_root / "batch_runs").glob("*.json")):
            run = read_json(run_path, {})
            if not run:
                continue
            run["summary_path"] = str(run_path)
            runs.append(run)
        runs.sort(key=lambda item: item.get("started_at") or 0, reverse=True)
        return runs

    def batch_sample_ids(self, run: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        for sample_id in run.get("created", []):
            if isinstance(sample_id, str) and sample_id:
                ids.append(sample_id)
        for sample in run.get("samples", []):
            if isinstance(sample, dict):
                sample_id = sample.get("sample_id")
                if isinstance(sample_id, str) and sample_id:
                    ids.append(sample_id)
        unique: list[str] = []
        seen: set[str] = set()
        for sample_id in ids:
            if sample_id not in seen:
                seen.add(sample_id)
                unique.append(sample_id)
        return unique

    def sample_membership(self) -> dict[str, list[str]]:
        membership: dict[str, list[str]] = {}
        for run in self.batch_summaries():
            run_id = str(run.get("run_id") or "")
            if not run_id:
                continue
            for sample_id in self.batch_sample_ids(run):
                membership.setdefault(sample_id, []).append(run_id)
        return membership

    def batch_runs(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for run in self.batch_summaries():
            sample_ids = self.batch_sample_ids(run)
            samples = run.get("samples", [])
            if not isinstance(samples, list):
                samples = []
            if not run:
                continue
            failures = [
                sample
                for sample in samples
                if isinstance(sample, dict) and sample.get("status") in {"failed", "reference_failed", "tripo_failed"}
            ]
            runs.append(
                {
                    "run_id": run.get("run_id", ""),
                    "dry_run": run.get("dry_run", False),
                    "started_at": run.get("started_at", 0),
                    "finished_at": run.get("finished_at", 0),
                    "count": len(sample_ids) or len(samples),
                    "sample_ids": sample_ids,
                    "samples": samples,
                    "created": run.get("created", []),
                    "seed": run.get("seed", 0),
                    "face_limit_range": run.get("face_limit_range", []),
                    "failed_count": len(failures),
                    "summary_path": run.get("summary_path", ""),
                }
            )
        return runs[:50]

    def jobs(self) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        for job_path in sorted(self.job_root.glob("*.json")):
            job = read_json(job_path, {})
            if job:
                jobs.append(job)
        jobs.sort(key=lambda item: item.get("started_at") or 0, reverse=True)
        return jobs[:50]

    def job(self, job_id: str) -> dict[str, Any] | None:
        path = self.job_root / f"{job_id}.json"
        if not path.exists():
            return None
        job = read_json(path, {})
        log_path = self.job_root / f"{job_id}.log"
        if log_path.exists():
            text = log_path.read_text(encoding="utf-8", errors="replace")
            job["log"] = text[-12000:]
        else:
            job["log"] = ""
        return job

    def image_map(self, value: Any, fallback_key: str) -> dict[str, str]:
        if isinstance(value, dict):
            images = {}
            for key, path_value in value.items():
                url = self.artifact_url(str(path_value))
                if url:
                    images[str(key)] = url
            return images
        if isinstance(value, str) and value:
            url = self.artifact_url(value)
            return {fallback_key: url} if url else {}
        return {}

    def review_images(self, review_dir_value: Any) -> dict[str, str]:
        if not isinstance(review_dir_value, str) or not review_dir_value:
            return {}
        directory = Path(review_dir_value).expanduser()
        if not directory.exists():
            return {}
        images: dict[str, str] = {}
        for name in REVIEW_ORDER:
            for extension in IMAGE_EXTENSIONS:
                candidate = directory / f"{name}{extension}"
                if candidate.exists():
                    images[name] = self.artifact_url(str(candidate))
                    break
        for candidate in sorted(directory.iterdir()):
            if candidate.suffix.lower() in IMAGE_EXTENSIONS and candidate.stem not in images:
                images[candidate.stem] = self.artifact_url(str(candidate))
        return images

    def thumbnail_url(
        self,
        state: dict[str, Any],
        reference_images: dict[str, str],
        multiview_images: dict[str, str],
        review_images: dict[str, str],
    ) -> str:
        for images in (review_images, multiview_images, reference_images):
            for key in ("quarter", "front", "reference"):
                if images.get(key):
                    return images[key]
        result = state.get("tripo_result_response", {}).get("data", {})
        for key in ("thumbnail",):
            value = result.get(key)
            if isinstance(value, str):
                return value
        output = result.get("output", {})
        rendered = output.get("rendered_image") if isinstance(output, dict) else ""
        return rendered if isinstance(rendered, str) else ""

    def artifact_url(self, path_value: str) -> str:
        if not path_value:
            return ""
        if path_value.startswith(("http://", "https://")):
            return path_value
        try:
            path = Path(path_value).expanduser().resolve()
            try:
                relative = path.relative_to(self.work_root)
                return f"/artifact?root=work&path={relative.as_posix()}"
            except ValueError:
                relative = path.relative_to(REPO_ROOT)
                return f"/artifact?root=repo&path={relative.as_posix()}"
        except (OSError, ValueError):
            return ""

    def artifact_path(self, root_value: str, relative_value: str) -> Path:
        root = REPO_ROOT if root_value == "repo" else self.work_root
        relative = Path(unquote(relative_value))
        path = (root / relative).resolve()
        path.relative_to(root)
        return path

    def start_run_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        count = bounded_int(payload.get("count"), 1, 1, 100)
        seed = bounded_int(payload.get("seed"), 0, 0, 999999999)
        face_min = bounded_int(payload.get("faceLimitMin"), 3000, 1, 100000)
        face_max = bounded_int(payload.get("faceLimitMax"), 8000, 1, 100000)
        if face_max < face_min:
            face_min, face_max = face_max, face_min

        command = [
            sys.executable,
            str(WORKFLOW_SCRIPT),
            "--work-root",
            str(self.work_root),
            "run-batch",
            "--count",
            str(count),
            "--catalog",
            str(self.catalog_path),
            "--sample-prefix",
            safe_token(payload.get("samplePrefix"), "ui"),
            "--face-limit-min",
            str(face_min),
            "--face-limit-max",
            str(face_max),
        ]
        if seed:
            command.extend(["--seed", str(seed)])
        animal_type = str(payload.get("animalType") or "").strip()
        if animal_type and animal_type != "all":
            command.extend(["--animal-type", animal_type])
        armor_state = str(payload.get("armorState") or "").strip()
        if armor_state and armor_state != "all":
            command.extend(["--armor-state", armor_state])
        if payload.get("dryRun", True):
            command.append("--dry-run")
        if payload.get("prepareLabelWork"):
            command.append("--prepare-label-work")
        if payload.get("continueOnError", True):
            command.append("--continue-on-error")

        now = int(time.time())
        job = {
            "job_id": job_id,
            "status": "running",
            "started_at": now,
            "finished_at": 0,
            "command": command,
            "payload": payload,
            "returncode": None,
        }
        write_json(self.job_root / f"{job_id}.json", job)

        thread = threading.Thread(target=self._run_job, args=(job_id, command), daemon=True)
        thread.start()
        return job

    def create_sample(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("Prompt is required.")
        prefix = safe_token(payload.get("samplePrefix"), "sample")
        sample_id = safe_token(payload.get("sampleId"), "")
        if not sample_id:
            sample_id = f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        path = self.work_root / sample_id / "workflow_state.json"
        if path.exists():
            raise ValueError(f"Sample already exists: {sample_id}")

        animal_type = str(payload.get("animalType") or "unknown").strip() or "unknown"
        morphology_type = str(payload.get("morphologyType") or animal_type).strip() or animal_type
        armor_state = str(payload.get("armorState") or "").strip()
        label_profile = str(payload.get("labelProfile") or "AUTO").strip() or "AUTO"
        mesh_forward_axis = str(payload.get("meshForwardAxis") or "POS_Y").strip() or "POS_Y"
        now = int(time.time())
        state = {
            "sample_id": sample_id,
            "prompt": prompt,
            "animal_type": animal_type,
            "morphology_type": morphology_type,
            "armor_state": armor_state,
            "mesh_forward_axis": mesh_forward_axis,
            "label_profile": label_profile,
            "openai_reference_prompts": self.custom_view_prompts(prompt),
            "openai_reference_defaults": self.catalog().get("defaults", {}),
            "status": "initialized",
            "created_at": now,
            "updated_at": now,
            "created_by": "qwalk_ui",
        }
        write_json(path, state)
        return {"sample_id": sample_id, "state_path": str(path), "sample": state}

    def custom_view_prompts(self, prompt: str) -> dict[str, str]:
        catalog = self.catalog()
        defaults = catalog.get("defaults", {})
        if not isinstance(defaults, dict):
            defaults = {}
        template = catalog.get("prompt_template")
        views = catalog.get("views")
        if not isinstance(views, dict):
            views = DEFAULT_VIEW_INSTRUCTIONS
        if not isinstance(template, str) or not template:
            return {
                view: (
                    "Create reference art for one symmetrical four-legged animal intended for Tripo3D mesh "
                    f"generation. Animal brief: {prompt}. View: {instruction}. Use a neutral standing pose, "
                    "plain white background, full body visible, animation-ready proportions, and no text."
                )
                for view, instruction in DEFAULT_VIEW_INSTRUCTIONS.items()
            }
        prompts: dict[str, str] = {}
        values = {
            "animal_description": prompt,
            "equipment_description": "as described in the user prompt",
            "style_notes": defaults.get("style_notes", ""),
            "negative_notes": defaults.get("negative_notes", ""),
        }
        for view in REFERENCE_ORDER:
            prompts[view] = template.format(
                **values,
                view=view,
                view_instruction=views.get(view, DEFAULT_VIEW_INSTRUCTIONS[view]),
            )
        return prompts

    def _run_job(self, job_id: str, command: list[str]) -> None:
        log_path = self.job_root / f"{job_id}.log"
        job_path = self.job_root / f"{job_id}.json"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                command,
                cwd=str(REPO_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=os.environ.copy(),
            )
            assert process.stdout is not None
            for line in process.stdout:
                log.write(line)
                log.flush()
            returncode = process.wait()
        job = read_json(job_path, {})
        job["status"] = "completed" if returncode == 0 else "failed"
        job["finished_at"] = int(time.time())
        job["returncode"] = returncode
        write_json(job_path, job)


class QWalkUIHandler(BaseHTTPRequestHandler):
    store: WorkflowStore

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_file(WEB_ROOT / "index.html")
        elif parsed.path.startswith("/static/"):
            try:
                self.send_static_file(parsed.path.removeprefix("/static/"))
            except (OSError, ValueError):
                self.send_error(404, "File not found")
        elif parsed.path == "/api/state":
            batches = self.store.batch_runs()
            self.send_json(
                {
                    "catalog": self.store.catalog(),
                    "samples": self.store.sample_states(),
                    "batches": batches,
                    "batch_runs": batches,
                    "jobs": self.store.jobs(),
                }
            )
        elif parsed.path == "/api/jobs":
            self.send_json({"jobs": self.store.jobs()})
        elif parsed.path.startswith("/api/jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            job = self.store.job(job_id)
            if job is None:
                self.send_error(404, "Job not found")
            else:
                self.send_json(job)
        elif parsed.path == "/artifact":
            root_value = parse_qs(parsed.query).get("root", ["work"])[0]
            path_value = parse_qs(parsed.query).get("path", [""])[0]
            try:
                self.send_file(self.store.artifact_path(root_value, path_value))
            except (OSError, ValueError):
                self.send_error(404, "Artifact not found")
        else:
            self.send_error(404, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self.read_json_body()
            if parsed.path == "/api/run-batch":
                job = self.store.start_run_batch(payload)
                self.send_json(job, status=202)
            elif parsed.path == "/api/samples":
                sample = self.store.create_sample(payload)
                self.send_json(sample, status=201)
            else:
                self.send_error(404, "Not found")
        except Exception as error:
            self.send_json({"error": str(error)}, status=400)

    def read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise ValueError("Expected a JSON object.")
        return parsed

    def send_json(self, value: Any, status: int = 200) -> None:
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path) -> None:
        resolved = path.resolve()
        if not resolved.exists() or not resolved.is_file():
            self.send_error(404, "File not found")
            return
        body = resolved.read_bytes()
        mime_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_static_file(self, relative_value: str) -> None:
        path = (WEB_ROOT / unquote(relative_value)).resolve()
        path.relative_to(WEB_ROOT.resolve())
        self.send_file(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local QWalk workflow UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--work-root", default=str(DEFAULT_WORK_ROOT))
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = WorkflowStore(Path(args.work_root), Path(args.catalog))
    QWalkUIHandler.store = store
    server = ThreadingHTTPServer((args.host, args.port), QWalkUIHandler)
    url = f"http://{args.host}:{args.port}"
    if sys.stdout is not None:
        print(f"QWalk UI running at {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
