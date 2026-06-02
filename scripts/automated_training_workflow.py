"""Resumable workflow for generating and gold-labeling quadruped training assets.

The OpenAI image generation step is intentionally a placeholder for now. The
Tripo3D and Blender handoff steps are implemented so generated model artifacts
can be downloaded, imported into Blender, and prepared for the repo-local
qwalk-gold-labeler review loop.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORK_ROOT = REPO_ROOT / "data" / "automated_training"
DEFAULT_TRIPO_BASE_URL = "https://api.tripo3d.ai/v2/openapi"
DEFAULT_BLENDER = r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"
MODEL_EXTENSIONS = (".glb", ".gltf", ".obj", ".fbx", ".zip")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automate Tripo3D generation and QWalk gold-label setup.")
    parser.add_argument("--work-root", default=str(DEFAULT_WORK_ROOT), help="Root directory for generated samples.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init-sample", help="Create a resumable workflow state for one sample.")
    init.add_argument("--sample-id", required=True)
    init.add_argument("--prompt", required=True)
    init.add_argument("--animal-type", required=True)
    init.add_argument("--morphology-type", required=True)
    init.add_argument("--mesh-forward-axis", default="POS_Y", choices=("POS_X", "NEG_X", "POS_Y", "NEG_Y"))

    reference = subparsers.add_parser("reference-placeholder", help="Record the future reference-image step.")
    reference.add_argument("--sample-id", required=True)
    reference.add_argument("--reference-image", default="", help="Optional existing local reference image path.")
    reference.add_argument("--reference-image-url", default="", help="Optional existing public reference image URL.")

    submit = subparsers.add_parser("submit-tripo", help="Submit an image-to-model task to Tripo3D.")
    submit.add_argument("--sample-id", required=True)
    submit.add_argument("--api-key", default="", help="Tripo3D API key. Defaults to TRIPO_API_KEY.")
    submit.add_argument("--base-url", default=DEFAULT_TRIPO_BASE_URL)
    submit.add_argument("--image-url", default="", help="Public image URL. Overrides state reference URL.")
    submit.add_argument("--image-file", default="", help="Local image file. Uploaded before task submission.")
    submit.add_argument("--model-version", default="v3.1-20260211")
    submit.add_argument("--texture", action=argparse.BooleanOptionalAction, default=True)
    submit.add_argument("--pbr", action=argparse.BooleanOptionalAction, default=True)
    submit.add_argument("--quad", action=argparse.BooleanOptionalAction, default=False)
    submit.add_argument("--geometry-quality", default="", choices=("", "standard", "detailed"))
    submit.add_argument("--face-limit", type=int, default=0)
    submit.add_argument("--texture-alignment", default="", choices=("", "original_image", "geometry"))

    poll = subparsers.add_parser("poll-tripo", help="Poll Tripo3D task and download model artifacts on success.")
    poll.add_argument("--sample-id", required=True)
    poll.add_argument("--api-key", default="", help="Tripo3D API key. Defaults to TRIPO_API_KEY.")
    poll.add_argument("--base-url", default=DEFAULT_TRIPO_BASE_URL)
    poll.add_argument("--interval", type=float, default=15.0)
    poll.add_argument("--timeout", type=float, default=1800.0)
    poll.add_argument("--no-download", action="store_true")

    prepare = subparsers.add_parser("prepare-label-work", help="Import downloaded model, create candidate guides, and render review views.")
    prepare.add_argument("--sample-id", required=True)
    prepare.add_argument("--blender", default=os.environ.get("BLENDER_EXE", DEFAULT_BLENDER))
    prepare.add_argument("--model-file", default="", help="Override downloaded model file.")
    prepare.add_argument("--profile", default="AUTO", choices=("AUTO", "MEDIUM", "STOCKY", "HORSE"))
    prepare.add_argument("--mesh-forward-axis", default="", choices=("", "POS_X", "NEG_X", "POS_Y", "NEG_Y"))
    prepare.add_argument("--resolution", type=int, default=1200)
    prepare.add_argument("--no-join-meshes", action="store_true")

    export = subparsers.add_parser("export-verified", help="Export a manually reviewed guide as a verified real label.")
    export.add_argument("--sample-id", required=True)
    export.add_argument("--blender", default=os.environ.get("BLENDER_EXE", DEFAULT_BLENDER))
    export.add_argument("--label-blend", default="", help="Blend file containing the corrected guide.")
    export.add_argument("--verified", action=argparse.BooleanOptionalAction, default=False)
    export.add_argument("--split", default="train", choices=("train", "val", "test"))

    status = subparsers.add_parser("status", help="Print state for one sample.")
    status.add_argument("--sample-id", required=True)
    return parser.parse_args()


def sample_dir(work_root: str | Path, sample_id: str) -> Path:
    return Path(work_root).expanduser().resolve() / sample_id


def state_path(work_root: str | Path, sample_id: str) -> Path:
    return sample_dir(work_root, sample_id) / "workflow_state.json"


def load_state(work_root: str | Path, sample_id: str) -> dict[str, Any]:
    path = state_path(work_root, sample_id)
    if not path.exists():
        raise FileNotFoundError(f"Workflow state not found for {sample_id}: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(work_root: str | Path, sample_id: str, state: dict[str, Any]) -> None:
    directory = sample_dir(work_root, sample_id)
    directory.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = int(time.time())
    state_path(work_root, sample_id).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def api_key(value: str) -> str:
    load_local_env(REPO_ROOT / ".env.local")
    load_local_env(REPO_ROOT / ".env")
    key = value or os.environ.get("TRIPO_API_KEY", "")
    if not key:
        raise RuntimeError("Set TRIPO_API_KEY or pass --api-key.")
    return key


def load_local_env(path: Path) -> None:
    """Load simple KEY=VALUE pairs without overwriting existing environment variables."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def request_json(
    method: str,
    url: str,
    *,
    key: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Authorization": f"Bearer {key}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {error.code}: {detail}") from error
    return json.loads(text)


def upload_file(base_url: str, key: str, path: Path) -> dict[str, Any]:
    boundary = f"----qwalk{uuid.uuid4().hex}"
    data = path.read_bytes()
    content_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        (
            'Content-Disposition: form-data; name="file"; '
            f'filename="{path.name}"\r\nContent-Type: {content_type}\r\n\r\n'
        ).encode("utf-8"),
        data,
        f"\r\n--{boundary}--\r\n".encode("utf-8"),
    ]
    body = b"".join(parts)
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/upload",
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180.0) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Upload failed with HTTP {error.code}: {detail}") from error


def response_data(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data", response)
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected API response shape: {response}")
    return data


def extract_token(upload_response: dict[str, Any]) -> str:
    data = response_data(upload_response)
    for key in ("image_token", "file_token", "token"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    if isinstance(data.get("file"), dict):
        for key in ("image_token", "file_token", "token"):
            value = data["file"].get(key)
            if isinstance(value, str) and value:
                return value
    raise RuntimeError(f"Upload response did not include a usable token: {upload_response}")


def model_url_candidates(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            urls.extend(model_url_candidates(item))
    elif isinstance(value, list):
        for item in value:
            urls.extend(model_url_candidates(item))
    elif isinstance(value, str) and value.startswith(("http://", "https://")):
        parsed_path = urllib.parse.urlparse(value).path.lower()
        if any(parsed_path.endswith(ext) for ext in MODEL_EXTENSIONS):
            urls.append(value)
    return urls


def preferred_model_url(task_response: dict[str, Any]) -> str:
    urls = model_url_candidates(task_response)
    if not urls:
        raise RuntimeError(f"No downloadable model URL found in task response: {task_response}")
    for extension in (".glb", ".gltf", ".obj", ".fbx", ".zip"):
        for url in urls:
            if urllib.parse.urlparse(url).path.lower().endswith(extension):
                return url
    return urls[0]


def download_url(url: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    name = Path(urllib.parse.urlparse(url).path).name or "tripo_model.glb"
    output = out_dir / name
    with urllib.request.urlopen(url, timeout=600.0) as response:
        output.write_bytes(response.read())
    return output


def task_status(task_response: dict[str, Any]) -> str:
    data = response_data(task_response)
    status = data.get("status") or data.get("task_status") or data.get("state")
    return str(status or "").lower()


def run(command: list[str], cwd: Path = REPO_ROOT) -> None:
    print("+ " + " ".join(command))
    subprocess.run(command, cwd=str(cwd), check=True)


def blender_exe(path: str) -> str:
    blender = Path(path)
    if not blender.exists():
        raise FileNotFoundError(f"Blender executable not found: {path}")
    return str(blender)


def require_model_file(state: dict[str, Any], override: str = "") -> Path:
    model_file = Path(override).expanduser().resolve() if override else Path(state.get("downloaded_model", ""))
    if not model_file.exists():
        raise FileNotFoundError(f"Model file not found. Run poll-tripo first or pass --model-file. Got: {model_file}")
    return model_file


def command_init_sample(args: argparse.Namespace) -> None:
    state = {
        "sample_id": args.sample_id,
        "prompt": args.prompt,
        "animal_type": args.animal_type,
        "morphology_type": args.morphology_type,
        "mesh_forward_axis": args.mesh_forward_axis,
        "status": "initialized",
        "created_at": int(time.time()),
    }
    save_state(args.work_root, args.sample_id, state)
    print(state_path(args.work_root, args.sample_id))


def command_reference_placeholder(args: argparse.Namespace) -> None:
    state = load_state(args.work_root, args.sample_id)
    directory = sample_dir(args.work_root, args.sample_id)
    (directory / "reference_prompt.txt").write_text(state["prompt"] + "\n", encoding="utf-8")
    if args.reference_image:
        state["reference_image"] = str(Path(args.reference_image).expanduser().resolve())
    if args.reference_image_url:
        state["reference_image_url"] = args.reference_image_url
    state["reference_status"] = "placeholder"
    state["status"] = "reference_placeholder_recorded"
    save_state(args.work_root, args.sample_id, state)
    print("Recorded placeholder reference step. OpenAI image generation is intentionally not wired yet.")


def command_submit_tripo(args: argparse.Namespace) -> None:
    state = load_state(args.work_root, args.sample_id)
    key = api_key(args.api_key)
    base_url = args.base_url.rstrip("/")
    image_url = args.image_url or state.get("reference_image_url", "")
    file_token = ""
    image_file = args.image_file or state.get("reference_image", "")
    if not image_url and image_file:
        upload_response = upload_file(base_url, key, Path(image_file).expanduser().resolve())
        state["tripo_upload_response"] = upload_response
        file_token = extract_token(upload_response)
        state["tripo_file_token"] = file_token
    if not image_url and not file_token:
        raise RuntimeError("submit-tripo needs --image-url, --image-file, or a state reference image/url.")

    payload: dict[str, Any] = {
        "type": "image_to_model",
        "model_version": args.model_version,
        "texture": args.texture,
        "pbr": args.pbr,
        "quad": args.quad,
    }
    if image_url:
        payload["file"] = {"type": "image", "url": image_url}
    else:
        payload["file"] = {"type": "image", "file_token": file_token}
    if args.geometry_quality:
        payload["geometry_quality"] = args.geometry_quality
    if args.face_limit > 0:
        payload["face_limit"] = args.face_limit
    if args.texture_alignment:
        payload["texture_alignment"] = args.texture_alignment

    response = request_json("POST", f"{base_url}/task", key=key, payload=payload)
    data = response_data(response)
    task_id = data.get("task_id") or data.get("id")
    if not task_id:
        raise RuntimeError(f"Task creation response did not include task_id: {response}")
    state["tripo_task_payload"] = payload
    state["tripo_task_response"] = response
    state["tripo_task_id"] = task_id
    state["status"] = "tripo_submitted"
    save_state(args.work_root, args.sample_id, state)
    print(f"Submitted Tripo task: {task_id}")


def command_poll_tripo(args: argparse.Namespace) -> None:
    state = load_state(args.work_root, args.sample_id)
    task_id = state.get("tripo_task_id")
    if not task_id:
        raise RuntimeError("No tripo_task_id in state. Run submit-tripo first.")
    key = api_key(args.api_key)
    base_url = args.base_url.rstrip("/")
    deadline = time.time() + args.timeout
    response: dict[str, Any] = {}
    while True:
        response = request_json("GET", f"{base_url}/task/{task_id}", key=key)
        status = task_status(response)
        print(f"task {task_id}: {status or 'unknown'}")
        if status in {"success", "succeeded", "completed", "complete", "finished"}:
            break
        if status in {"failed", "failure", "canceled", "cancelled", "error"}:
            raise RuntimeError(f"Tripo task failed: {json.dumps(response, indent=2)}")
        if time.time() >= deadline:
            raise TimeoutError(f"Timed out waiting for Tripo task {task_id}.")
        time.sleep(args.interval)

    state["tripo_result_response"] = response
    state["status"] = "tripo_completed"
    if not args.no_download:
        url = preferred_model_url(response)
        output = download_url(url, sample_dir(args.work_root, args.sample_id) / "model")
        state["downloaded_model_url"] = url
        state["downloaded_model"] = str(output)
        state["status"] = "model_downloaded"
        print(f"Downloaded model: {output}")
    save_state(args.work_root, args.sample_id, state)


def command_prepare_label_work(args: argparse.Namespace) -> None:
    state = load_state(args.work_root, args.sample_id)
    directory = sample_dir(args.work_root, args.sample_id)
    blender = blender_exe(args.blender)
    model_file = require_model_file(state, args.model_file)
    mesh_name = f"{args.sample_id}_Mesh"
    source_blend = directory / f"{args.sample_id}_imported.blend"
    label_blend = directory / f"{args.sample_id}_label_work.blend"
    review_dir = directory / "review_candidate"
    axis = args.mesh_forward_axis or state.get("mesh_forward_axis", "POS_Y")

    run(
        [
            blender,
            "--background",
            "--python",
            str(REPO_ROOT / "scripts" / "import_model_for_qwalk_label.py"),
            "--",
            str(model_file),
            "--output",
            str(source_blend),
            "--mesh-name",
            mesh_name,
            *(["--no-join-meshes"] if args.no_join_meshes else []),
        ]
    )
    run(
        [
            blender,
            "--background",
            str(source_blend),
            "--python",
            str(REPO_ROOT / "scripts" / "apply_qwalk_geometric_to_blend.py"),
            "--",
            "--mesh",
            mesh_name,
            "--output",
            str(label_blend),
            "--guides-only",
            "--profile",
            args.profile,
            "--mesh-forward-axis",
            axis,
        ]
    )
    guide_name = f"{mesh_name}_QWalk_Geometric_Guides"
    run(
        [
            blender,
            "--background",
            str(label_blend),
            "--python",
            str(REPO_ROOT / "scripts" / "render_qwalk_label_review.py"),
            "--",
            "--mesh",
            mesh_name,
            "--guide",
            guide_name,
            "--out-dir",
            str(review_dir),
            "--resolution",
            str(args.resolution),
            "--mesh-forward-axis",
            axis,
        ]
    )
    manifest_path = review_dir / "review_manifest.json"
    expected_views = [review_dir / f"{name}.png" for name in ("left", "right", "front", "rear", "top", "quarter")]
    missing = [path for path in [manifest_path, *expected_views] if not path.exists()]
    if missing:
        missing_list = ", ".join(str(path) for path in missing)
        raise RuntimeError(f"Review rendering did not produce expected outputs: {missing_list}")
    state.update(
        {
            "imported_blend": str(source_blend),
            "label_work_blend": str(label_blend),
            "label_mesh": mesh_name,
            "label_guide": guide_name,
            "mesh_forward_axis": axis,
            "label_profile": args.profile,
            "review_dir": str(review_dir),
            "status": "candidate_review_rendered",
        }
    )
    save_state(args.work_root, args.sample_id, state)
    print(f"Review candidate: {review_dir}")


def command_export_verified(args: argparse.Namespace) -> None:
    state = load_state(args.work_root, args.sample_id)
    blender = blender_exe(args.blender)
    label_blend = Path(args.label_blend).expanduser().resolve() if args.label_blend else Path(state["label_work_blend"])
    mesh = state["label_mesh"]
    guide = state["label_guide"]
    axis = state.get("mesh_forward_axis", "POS_Y")
    command = [
        blender,
        "--background",
        str(label_blend),
        "--python",
        str(REPO_ROOT / "scripts" / "export_qwalk_guide_label.py"),
        "--",
        "--mesh",
        mesh,
        "--guide",
        guide,
        "--out-dir",
        str(REPO_ROOT / "data" / "real_quadrupeds"),
        "--id",
        args.sample_id,
        "--split",
        args.split,
        "--animal-type",
        state["animal_type"],
        "--morphology-type",
        state["morphology_type"],
        "--source",
        "real_qwalk_label_gold_automated",
        "--mesh-forward-axis",
        axis,
    ]
    if args.verified:
        command.append("--verified")
    run(command)
    state["status"] = "verified_exported" if args.verified else "candidate_exported"
    state["export_verified"] = bool(args.verified)
    save_state(args.work_root, args.sample_id, state)


def command_status(args: argparse.Namespace) -> None:
    print(json.dumps(load_state(args.work_root, args.sample_id), indent=2))


def main() -> None:
    args = parse_args()
    handlers = {
        "init-sample": command_init_sample,
        "reference-placeholder": command_reference_placeholder,
        "submit-tripo": command_submit_tripo,
        "poll-tripo": command_poll_tripo,
        "prepare-label-work": command_prepare_label_work,
        "export-verified": command_export_verified,
        "status": command_status,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
