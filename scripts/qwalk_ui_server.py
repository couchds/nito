#!/usr/bin/env python3
"""Local web UI for the Nito training-asset workflow."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import random
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "web"
DEFAULT_WORK_ROOT = REPO_ROOT / "data" / "automated_training"
DEFAULT_CATALOG = REPO_ROOT / "prompts" / "quadruped_reference_prompts.json"
WORKFLOW_SCRIPT = REPO_ROOT / "scripts" / "automated_training_workflow.py"
UI_DB_NAME = "qwalk_ui.sqlite3"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MODEL_EXTENSIONS = {".glb", ".gltf"}
REFERENCE_ORDER = ("front", "left", "right", "back")
REVIEW_ORDER = ("front", "left", "right", "rear", "top", "quarter")
STALE_JOB_SECONDS = 15 * 60
DEFAULT_COMMAND_TIMEOUT_SECONDS = 30 * 60
COMMAND_TIMEOUT_SECONDS = {
    "generate-reference": 10 * 60,
    "submit-tripo": 10 * 60,
    "poll-tripo": 20 * 60,
    "prepare-label-work": 15 * 60,
    "run-batch": 60 * 60,
}
RUNNING_SAMPLE_STATUS_SUFFIXES = ("running", "polling")
SAMPLE_ACTION_STATUS = {
    "generate-reference": "reference_running",
    "submit-tripo": "tripo_submission_running",
    "poll-tripo": "tripo_polling",
    "prepare-label-work": "label_work_running",
    "run-pipeline": "pipeline_running",
}
DEFAULT_VIEW_INSTRUCTIONS = {
    "front": "front orthographic view, animal facing directly toward the camera",
    "left": "left side orthographic profile, animal facing toward the viewer's left",
    "right": "right side orthographic profile, animal facing toward the viewer's right",
    "back": "back orthographic view, animal facing directly away from the camera",
}
LEGACY_BODY_PLAN_ALIASES = {
    "canid": "medium_quadruped",
    "feline": "medium_quadruped",
    "amphibian": "hind_leg_dominant",
    "ungulate": "long_legged_ungulate",
    "lagomorph": "hind_leg_dominant",
    "reptile_shell": "shell_reptile",
}


def workflow_python_executable() -> str:
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        candidate = executable.with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    return str(executable)


WORKFLOW_PYTHON = workflow_python_executable()


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


def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = value.split(",")
    else:
        return []
    cleaned: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def body_plan_value(state: dict[str, Any]) -> str:
    raw = str(state.get("body_plan") or state.get("morphology_type") or "").strip()
    return LEGACY_BODY_PLAN_ALIASES.get(raw, raw)


class JobDatabase:
    def __init__(self, path: Path, legacy_job_root: Path) -> None:
        self.path = path
        self.legacy_job_root = legacy_job_root
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()
        self.import_legacy_jobs()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ui_jobs (
                    job_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL DEFAULT '',
                    sample_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    started_at INTEGER NOT NULL,
                    finished_at INTEGER NOT NULL DEFAULT 0,
                    returncode INTEGER,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    command_json TEXT NOT NULL DEFAULT '[]',
                    log_path TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ui_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_ui_jobs_sample_id ON ui_jobs(sample_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_ui_jobs_status ON ui_jobs(status)")

    def import_legacy_jobs(self) -> None:
        if self.meta_value("legacy_jobs_imported") == "1":
            return
        if not self.legacy_job_root.exists():
            self.set_meta_value("legacy_jobs_imported", "1")
            return
        for job_path in sorted(self.legacy_job_root.glob("*.json")):
            job = read_json(job_path, {})
            if not isinstance(job, dict) or not job.get("job_id"):
                continue
            self.insert_job(job, self.legacy_job_root / f"{job['job_id']}.log", ignore_existing=True)
        self.set_meta_value("legacy_jobs_imported", "1")

    def meta_value(self, key: str) -> str:
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM ui_meta WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else ""

    def set_meta_value(self, key: str, value: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO ui_meta (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

    def insert_job(self, job: dict[str, Any], log_path: Path, ignore_existing: bool = False) -> None:
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        commands = job.get("commands") if isinstance(job.get("commands"), list) else [job.get("command", [])]
        command_json = json.dumps(commands)
        payload_json = json.dumps(payload)
        action = str(payload.get("action") or ("run-batch" if payload.get("count") else ""))
        sample_id = str(payload.get("sampleId") or payload.get("sample_id") or "")
        now = int(time.time())
        verb = "INSERT OR IGNORE" if ignore_existing else "INSERT"
        with self.connect() as connection:
            connection.execute(
                f"""
                {verb} INTO ui_jobs (
                    job_id,
                    action,
                    sample_id,
                    status,
                    started_at,
                    finished_at,
                    returncode,
                    payload_json,
                    command_json,
                    log_path,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(job["job_id"]),
                    action,
                    sample_id,
                    str(job.get("status") or "running"),
                    int(job.get("started_at") or now),
                    int(job.get("finished_at") or 0),
                    job.get("returncode"),
                    payload_json,
                    command_json,
                    str(log_path),
                    int(job.get("started_at") or now),
                    now,
                ),
            )

    def update_job(self, job_id: str, status: str, finished_at: int, returncode: int | None) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE ui_jobs
                SET status = ?, finished_at = ?, returncode = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (status, finished_at, returncode, int(time.time()), job_id),
            )

    def acknowledge_stale_job(self, job_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE ui_jobs
                SET status = 'stale_acknowledged', updated_at = ?
                WHERE job_id = ? AND status = 'stale'
                """,
                (int(time.time()), job_id),
            )

    def mark_stale_jobs(self, active_job_ids: set[str], stale_seconds: int) -> list[dict[str, Any]]:
        now = int(time.time())
        cutoff = now - stale_seconds
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM ui_jobs
                WHERE status = 'running'
                  AND started_at <= ?
                ORDER BY started_at DESC
                """,
                (cutoff,),
            ).fetchall()
            stale_rows = [row for row in rows if str(row["job_id"]) not in active_job_ids]
            for row in stale_rows:
                connection.execute(
                    """
                    UPDATE ui_jobs
                    SET status = 'stale', finished_at = ?, updated_at = ?
                    WHERE job_id = ? AND status = 'running'
                    """,
                    (now, now, row["job_id"]),
                )
        return [
            {
                **self.job_from_row(row, now=now),
                "status": "stale",
                "finished_at": now,
            }
            for row in stale_rows
        ]

    def jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        now = int(time.time())
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM ui_jobs
                ORDER BY started_at DESC, job_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self.job_from_row(row, now=now) for row in rows]

    def job(self, job_id: str) -> dict[str, Any] | None:
        now = int(time.time())
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM ui_jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self.job_from_row(row, now=now) if row is not None else None

    def job_from_row(self, row: sqlite3.Row, now: int) -> dict[str, Any]:
        payload = json.loads(row["payload_json"] or "{}")
        commands = json.loads(row["command_json"] or "[]")
        started_at = int(row["started_at"] or now)
        finished_at = int(row["finished_at"] or 0)
        status = str(row["status"] or "unknown")
        end_at = finished_at or now
        job = {
            "job_id": row["job_id"],
            "status": status,
            "started_at": started_at,
            "finished_at": finished_at,
            "elapsed_seconds": max(0, end_at - started_at),
            "command": commands[0] if len(commands) == 1 else commands,
            "commands": commands,
            "payload": payload,
            "returncode": row["returncode"],
            "log_path": row["log_path"],
        }
        if row["action"]:
            job["action"] = row["action"]
        if row["sample_id"]:
            job["sample_id"] = row["sample_id"]
        return job


class WorkflowStore:
    def __init__(self, work_root: Path, catalog_path: Path) -> None:
        self.work_root = work_root.expanduser().resolve()
        self.catalog_path = catalog_path.expanduser().resolve()
        self.job_root = self.work_root / "ui_jobs"
        self.job_root.mkdir(parents=True, exist_ok=True)
        self.active_job_ids: set[str] = set()
        self.job_db = JobDatabase(self.work_root / UI_DB_NAME, self.job_root)
        self.refresh_stale_jobs()

    def catalog(self) -> dict[str, Any]:
        catalog = read_json(self.catalog_path, {})
        specs = catalog.get("specs", [])
        label_schema = catalog.get("label_schema", {})
        animals = sorted(
            {
                *string_list(label_schema.get("animal_type") if isinstance(label_schema, dict) else []),
                *[spec.get("animal_type", "") for spec in specs if spec.get("animal_type")],
            }
        )
        body_plans = sorted(
            {
                *string_list(label_schema.get("body_plan") if isinstance(label_schema, dict) else []),
                *[spec.get("body_plan") or spec.get("morphology_type", "") for spec in specs if spec.get("body_plan") or spec.get("morphology_type")],
            }
        )
        variant_tags = sorted(
            {
                *string_list(label_schema.get("variant_tags") if isinstance(label_schema, dict) else []),
                *[
                    tag
                    for spec in specs
                    for tag in string_list(spec.get("variant_tags"))
                ],
            }
        )
        return {
            "path": str(self.catalog_path),
            "defaults": catalog.get("defaults", {}),
            "label_schema": label_schema if isinstance(label_schema, dict) else {},
            "animals": animals,
            "body_plans": body_plans,
            "variant_tags": variant_tags,
            "specs": specs,
        }

    def sample_states(self) -> list[dict[str, Any]]:
        self.refresh_stale_jobs()
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
            remote_model_url = state.get("downloaded_model_url", "") or self.tripo_output_url(state, "pbr_model")
            remote_preview_url = self.tripo_output_url(state, "rendered_image")
            remote_model_proxy_url = self.tripo_proxy_url(sample_id, "model") if remote_model_url else ""
            remote_preview_proxy_url = self.tripo_proxy_url(sample_id, "preview") if remote_preview_url else ""
            ui_job = self.sample_ui_job(state)
            status = state.get("status", "")
            if self.sample_status_is_running(status) and ui_job.get("status") == "stale":
                status = "ui_job_stale"
            samples.append(
                {
                    "sample_id": sample_id,
                    "prompt": state.get("prompt", ""),
                    "prompt_spec_id": state.get("reference_prompt_spec_id", ""),
                    "openai_reference_prompts": state.get("openai_reference_prompts", {}),
                    "animal_type": state.get("animal_type", ""),
                    "morphology_type": state.get("morphology_type", ""),
                    "body_plan": body_plan_value(state),
                    "variant_tags": string_list(state.get("variant_tags")),
                    "armor_state": state.get("armor_state", ""),
                    "status": status,
                    "ui_job": ui_job,
                    "created_at": state.get("created_at", 0),
                    "updated_at": state.get("updated_at", state.get("created_at", 0)),
                    "face_limit": (state.get("batch_runner") or {}).get("face_limit")
                    or (state.get("tripo_task_payload") or {}).get("face_limit"),
                    "tripo_task_id": state.get("tripo_task_id", ""),
                    "tripo_multiview_task_id": state.get("tripo_multiview_task_id", ""),
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
                        "remote_url": remote_model_url,
                        "viewer_url": remote_model_proxy_url,
                        "preview_url": remote_preview_url,
                        "preview_proxy_url": remote_preview_proxy_url,
                        "source": "local" if model_url else "tripo" if remote_model_url else "",
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
        self.refresh_stale_jobs()
        return self.job_db.jobs(limit=50)

    def job(self, job_id: str) -> dict[str, Any] | None:
        self.refresh_stale_jobs()
        job = self.job_db.job(job_id)
        if job is None:
            return None
        log_path = Path(str(job.get("log_path") or ""))
        if log_path.exists():
            text = log_path.read_text(encoding="utf-8", errors="replace")
            job["log"] = text[-12000:]
        else:
            job["log"] = ""
        return job

    def sample_ui_job(self, state: dict[str, Any]) -> dict[str, Any]:
        ui_job = state.get("ui_job") if isinstance(state.get("ui_job"), dict) else {}
        job_id = str(ui_job.get("job_id") or "")
        if not job_id:
            return ui_job
        job = self.job_db.job(job_id)
        if job is None:
            return {}
        return {
            **ui_job,
            "status": job.get("status", ui_job.get("status", "")),
            "started_at": job.get("started_at", ui_job.get("started_at", 0)),
            "finished_at": job.get("finished_at", ui_job.get("finished_at", 0)),
            "elapsed_seconds": job.get("elapsed_seconds", 0),
            "returncode": job.get("returncode"),
        }

    def refresh_stale_jobs(self) -> None:
        stale_jobs = self.job_db.mark_stale_jobs(self.active_job_ids, STALE_JOB_SECONDS)
        for job in stale_jobs:
            self.finish_sample_job(job)

    def sample_status_is_running(self, status: Any) -> bool:
        return str(status or "").endswith(RUNNING_SAMPLE_STATUS_SUFFIXES)

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

    def tripo_output_url(self, state: dict[str, Any], key: str) -> str:
        response = state.get("tripo_result_response")
        if not isinstance(response, dict):
            return ""
        data = response.get("data")
        containers: list[Any] = []
        if isinstance(data, dict):
            containers.extend([data.get("output"), data.get("result")])
        containers.extend([response.get("output"), response.get("result")])
        for container in containers:
            value = self.url_value(container, key)
            if value:
                return value
        return ""

    def url_value(self, container: Any, key: str) -> str:
        if not isinstance(container, dict):
            return ""
        value = container.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            return value
        if isinstance(value, dict):
            nested = value.get("url")
            if isinstance(nested, str) and nested.startswith(("http://", "https://")):
                return nested
        return ""

    def tripo_proxy_url(self, sample_id: str, kind: str) -> str:
        return f"/tripo-output?sample_id={quote(sample_id)}&kind={quote(kind)}"

    def tripo_remote_output(self, sample_id_value: str, kind: str) -> tuple[str, str]:
        sample_id = safe_token(sample_id_value, "")
        if not sample_id or sample_id != sample_id_value:
            raise ValueError("Invalid sample id.")
        state = read_json(self.work_root / sample_id / "workflow_state.json", {})
        if not state:
            raise FileNotFoundError(f"Sample not found: {sample_id}")
        if kind == "preview":
            url = self.tripo_output_url(state, "rendered_image")
        elif kind == "model":
            url = state.get("downloaded_model_url", "") or self.tripo_output_url(state, "pbr_model")
        else:
            raise ValueError(f"Unsupported Tripo output kind: {kind}")
        if not url:
            raise FileNotFoundError(f"Tripo {kind} output not found for {sample_id}")
        return url, self.remote_mime_type(url, kind)

    def remote_mime_type(self, url: str, kind: str) -> str:
        extension = Path(urlparse(url).path).suffix.lower()
        if extension == ".glb":
            return "model/gltf-binary"
        if extension == ".gltf":
            return "model/gltf+json"
        if extension == ".webp":
            return "image/webp"
        return mimetypes.guess_type(urlparse(url).path)[0] or (
            "application/octet-stream" if kind == "model" else "image/webp"
        )

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
        count = bounded_int(payload.get("count"), 1, 1, 100)
        seed = bounded_int(payload.get("seed"), 0, 0, 999999999)
        face_min = bounded_int(payload.get("faceLimitMin"), 3000, 1, 100000)
        face_max = bounded_int(payload.get("faceLimitMax"), 8000, 1, 100000)
        if face_max < face_min:
            face_min, face_max = face_max, face_min

        command = [
            WORKFLOW_PYTHON,
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

        job_payload = dict(payload)
        job_payload["action"] = "run-batch"
        return self.start_job(job_payload, [command])

    def workflow_command(self, *parts: str) -> list[str]:
        return [WORKFLOW_PYTHON, str(WORKFLOW_SCRIPT), "--work-root", str(self.work_root), *parts]

    def start_sample_action(self, sample_id_value: str, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        sample_id = safe_token(sample_id_value, "")
        if not sample_id or sample_id != sample_id_value:
            raise ValueError("Invalid sample id.")
        if not (self.work_root / sample_id / "workflow_state.json").exists():
            raise ValueError(f"Sample not found: {sample_id}")

        commands: list[list[str]]
        job_payload = dict(payload)
        job_payload.update({"action": action, "sampleId": sample_id})
        if action == "generate-reference":
            command = self.workflow_command("generate-reference", "--sample-id", sample_id)
            if payload.get("overwrite"):
                command.append("--overwrite")
            commands = [command]
        elif action == "submit-tripo":
            face_limit = self.face_limit_for_payload(payload)
            job_payload["faceLimit"] = face_limit
            commands = [
                self.workflow_command("submit-tripo", "--sample-id", sample_id, "--face-limit", str(face_limit))
            ]
        elif action == "poll-tripo":
            commands = [self.workflow_command("poll-tripo", "--sample-id", sample_id)]
        elif action == "prepare-label-work":
            commands = [self.workflow_command("prepare-label-work", "--sample-id", sample_id)]
        elif action == "run-pipeline":
            face_limit = self.face_limit_for_payload(payload)
            job_payload["faceLimit"] = face_limit
            commands = [
                self.workflow_command("generate-reference", "--sample-id", sample_id),
                self.workflow_command("submit-tripo", "--sample-id", sample_id, "--face-limit", str(face_limit)),
                self.workflow_command("poll-tripo", "--sample-id", sample_id),
            ]
            if payload.get("prepareLabelWork"):
                commands.append(self.workflow_command("prepare-label-work", "--sample-id", sample_id))
        else:
            raise ValueError(f"Unknown sample action: {action}")

        return self.start_job(
            job_payload,
            commands,
            sample_id=sample_id,
            sample_status=SAMPLE_ACTION_STATUS.get(action, "ui_job_running"),
        )

    def face_limit_for_payload(self, payload: dict[str, Any]) -> int:
        default = random.randint(3000, 8000)
        return bounded_int(payload.get("faceLimit"), default, 1, 100000)

    def start_job(
        self,
        payload: dict[str, Any],
        commands: list[list[str]],
        sample_id: str = "",
        sample_status: str = "",
    ) -> dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        now = int(time.time())
        job = {
            "job_id": job_id,
            "status": "running",
            "started_at": now,
            "finished_at": 0,
            "command": commands[0] if len(commands) == 1 else commands,
            "commands": commands,
            "payload": payload,
            "returncode": None,
        }
        log_path = self.job_root / f"{job_id}.log"
        self.job_db.insert_job(job, log_path)
        if sample_id and sample_status:
            self.mark_sample_job(sample_id, job_id, payload.get("action", ""), sample_status, now)

        self.active_job_ids.add(job_id)
        thread = threading.Thread(target=self._run_job, args=(job_id, commands), daemon=True)
        thread.start()
        return job

    def mark_sample_job(self, sample_id: str, job_id: str, action: str, status: str, started_at: int) -> None:
        path = self.work_root / sample_id / "workflow_state.json"
        state = read_json(path, {})
        if not state:
            return
        state["status"] = status
        state["ui_job"] = {
            "job_id": job_id,
            "action": action,
            "status": "running",
            "started_at": started_at,
        }
        write_json(path, state)

    def inferred_sample_status(self, state: dict[str, Any]) -> str:
        reference_images = state.get("openai_reference_images")
        if state.get("label_work_blend"):
            return "label_work_prepared"
        if state.get("downloaded_model"):
            return "model_downloaded"
        if state.get("tripo_task_id"):
            return "tripo_multiview_model_submitted"
        if isinstance(reference_images, dict) and all(reference_images.get(view) for view in REFERENCE_ORDER):
            return "openai_reference_generated"
        return "initialized"

    def reset_stale_sample_job(self, sample_id_value: str) -> dict[str, Any]:
        sample_id = safe_token(sample_id_value, "")
        if not sample_id or sample_id != sample_id_value:
            raise ValueError("Invalid sample id.")
        path = self.work_root / sample_id / "workflow_state.json"
        state = read_json(path, {})
        if not state:
            raise ValueError(f"Sample not found: {sample_id}")
        ui_job = state.get("ui_job") if isinstance(state.get("ui_job"), dict) else {}
        if state.get("status") != "ui_job_stale" and ui_job.get("status") != "stale":
            raise ValueError("Sample does not have a stale UI job.")

        now = int(time.time())
        stale_jobs = state.get("stale_ui_jobs") if isinstance(state.get("stale_ui_jobs"), list) else []
        stale_jobs.append({**ui_job, "reset_at": now})
        state["stale_ui_jobs"] = stale_jobs[-10:]
        job_id = str(ui_job.get("job_id") or "")
        if job_id:
            self.job_db.acknowledge_stale_job(job_id)
        state["ui_job"] = {**ui_job, "status": "stale_acknowledged", "reset_at": now}
        state["status"] = self.inferred_sample_status(state)
        state["updated_at"] = now
        write_json(path, state)
        return {"sample_id": sample_id, "status": state["status"], "ui_job": state["ui_job"]}

    def command_timeout_seconds(self, command: list[str]) -> int:
        for part in command:
            if part in COMMAND_TIMEOUT_SECONDS:
                return COMMAND_TIMEOUT_SECONDS[part]
        return DEFAULT_COMMAND_TIMEOUT_SECONDS

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
        morphology_type = str(payload.get("morphologyType") or "").strip()
        if not morphology_type or morphology_type == "unknown":
            raise ValueError("Body plan is required.")
        armor_state = str(payload.get("armorState") or "").strip()
        variant_tags = string_list(payload.get("variantTags"))
        if armor_state and armor_state not in variant_tags:
            variant_tags.insert(0, armor_state)
        label_profile = str(payload.get("labelProfile") or "AUTO").strip() or "AUTO"
        mesh_forward_axis = str(payload.get("meshForwardAxis") or "POS_Y").strip() or "POS_Y"
        now = int(time.time())
        state = {
            "sample_id": sample_id,
            "prompt": prompt,
            "animal_type": animal_type,
            "morphology_type": morphology_type,
            "body_plan": morphology_type,
            "variant_tags": variant_tags,
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
                    f"generation. Animal brief: {prompt}. View: {instruction}. Use a Dragon Quest XI-ish bright "
                    "cel-shaded JRPG creature design with rounded expressive monster proportions, clean "
                    "anime-inspired silhouettes, saturated heroic-fantasy colors, simple readable materials, and "
                    "soft toy-like sculptural forms. Use a neutral standing pose, plain white background, full body "
                    "visible, animation-ready proportions, and no text."
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

    def _run_job(self, job_id: str, commands: list[list[str]]) -> None:
        log_path = self.job_root / f"{job_id}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        returncode = 0
        status = "completed"
        try:
            with log_path.open("w", encoding="utf-8") as log:
                for index, command in enumerate(commands, start=1):
                    prefix = f"[{index}/{len(commands)}] " if len(commands) > 1 else ""
                    timeout = self.command_timeout_seconds(command)
                    log.write(f"\n{prefix}{' '.join(command)}\n")
                    log.write(f"Timeout: {timeout}s\n")
                    log.flush()
                    try:
                        result = subprocess.run(
                            command,
                            cwd=str(REPO_ROOT),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            env=os.environ.copy(),
                            timeout=timeout,
                            check=False,
                        )
                        if result.stdout:
                            log.write(result.stdout)
                            log.flush()
                        returncode = result.returncode
                    except subprocess.TimeoutExpired as error:
                        status = "failed"
                        returncode = 124
                        if error.stdout:
                            log.write(str(error.stdout))
                        log.write(f"\nCommand timed out after {timeout}s.\n")
                        log.flush()
                        break
                    if returncode != 0:
                        status = "failed"
                        break
        except Exception as error:
            status = "failed"
            returncode = 1
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"\nUI job runner failed: {error}\n")
        finally:
            self.active_job_ids.discard(job_id)
        finished_at = int(time.time())
        self.job_db.update_job(job_id, status, finished_at, returncode)
        job = self.job_db.job(job_id) or {
            "job_id": job_id,
            "status": status,
            "finished_at": finished_at,
            "returncode": returncode,
        }
        self.finish_sample_job(job)

    def finish_sample_job(self, job: dict[str, Any]) -> None:
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        sample_id = str(payload.get("sampleId") or "")
        if not sample_id:
            return
        path = self.work_root / sample_id / "workflow_state.json"
        state = read_json(path, {})
        if not state:
            return
        ui_job = state.get("ui_job") if isinstance(state.get("ui_job"), dict) else {}
        if ui_job.get("job_id") != job.get("job_id"):
            return
        ui_job["status"] = job.get("status", "")
        ui_job["finished_at"] = job.get("finished_at", 0)
        ui_job["returncode"] = job.get("returncode")
        state["ui_job"] = ui_job
        if self.sample_status_is_running(state.get("status")):
            if job.get("status") == "failed":
                state["status"] = "ui_job_failed"
            elif job.get("status") == "stale":
                state["status"] = "ui_job_stale"
        write_json(path, state)


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
        elif parsed.path == "/tripo-output":
            params = parse_qs(parsed.query)
            sample_id = params.get("sample_id", [""])[0]
            kind = params.get("kind", ["model"])[0]
            try:
                self.send_tripo_output(sample_id, kind)
            except FileNotFoundError:
                self.send_error(404, "Tripo output not found")
            except (OSError, ValueError, urllib.error.URLError):
                self.send_error(502, "Could not fetch Tripo output")
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
            elif parsed.path.startswith("/api/samples/") and parsed.path.endswith("/reset-stale"):
                parts = parsed.path.strip("/").split("/")
                if len(parts) != 4 or parts[0] != "api" or parts[1] != "samples" or parts[3] != "reset-stale":
                    self.send_error(404, "Not found")
                    return
                sample_id = unquote(parts[2])
                result = self.store.reset_stale_sample_job(sample_id)
                self.send_json(result)
            elif parsed.path.startswith("/api/samples/") and "/actions/" in parsed.path:
                parts = parsed.path.strip("/").split("/")
                if len(parts) != 5 or parts[0] != "api" or parts[1] != "samples" or parts[3] != "actions":
                    self.send_error(404, "Not found")
                    return
                sample_id = unquote(parts[2])
                action = unquote(parts[4])
                job = self.store.start_sample_action(sample_id, action, payload)
                self.send_json(job, status=202)
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

    def send_tripo_output(self, sample_id: str, kind: str) -> None:
        url, mime_type = self.store.tripo_remote_output(sample_id, kind)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Nito/0.1 local-preview",
                "Accept": "*/*",
            },
        )
        with urllib.request.urlopen(request, timeout=120.0) as response:
            body = response.read()
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
    parser = argparse.ArgumentParser(description="Run the local Nito workflow UI.")
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
        try:
            print(f"Nito running at {url}")
        except OSError:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
