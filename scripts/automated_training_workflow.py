"""Resumable workflow for generating and gold-labeling quadruped training assets.

The workflow generates multi-view OpenAI reference art, sends those references
to Tripo3D, downloads generated model artifacts, and prepares Blender files for
the repo-local qwalk-gold-labeler review loop.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
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
DEFAULT_PROMPT_CATALOG = REPO_ROOT / "prompts" / "quadruped_reference_prompts.json"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_IMAGE_MODEL = "gpt-image-2"
DEFAULT_TRIPO_BASE_URL = "https://api.tripo3d.ai/v2/openapi"
DEFAULT_BLENDER = r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"
DEFAULT_TRIPO_MESH_FORWARD_AXIS = "POS_X"
MODEL_EXTENSIONS = (".glb", ".gltf", ".obj", ".fbx", ".zip")
REFERENCE_VIEWS = ("front", "left", "right", "back")
REFERENCE_STRATEGIES = ("sequential", "independent")
SEQUENTIAL_REFERENCE_VIEWS = ("left", "right", "front", "back")
TRIPO_VIEW_ORDER = ("front", "left", "back", "right")
LEGACY_BODY_PLAN_ALIASES = {
    "canid": "medium_quadruped",
    "feline": "medium_quadruped",
    "amphibian": "hind_leg_dominant",
    "ungulate": "long_legged_ungulate",
    "lagomorph": "hind_leg_dominant",
    "reptile_shell": "shell_reptile",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automate Tripo3D generation and QWalk gold-label setup.")
    parser.add_argument("--work-root", default=str(DEFAULT_WORK_ROOT), help="Root directory for generated samples.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init-sample", help="Create a resumable workflow state for one sample.")
    init.add_argument("--sample-id", required=True)
    init.add_argument("--prompt", required=True)
    init.add_argument("--animal-type", required=True)
    init.add_argument("--morphology-type", required=True)
    init.add_argument(
        "--mesh-forward-axis",
        default=DEFAULT_TRIPO_MESH_FORWARD_AXIS,
        choices=("POS_X", "NEG_X", "POS_Y", "NEG_Y"),
    )

    init_batch = subparsers.add_parser("init-batch", help="Create N sample states from the prompt catalog.")
    init_batch.add_argument("--count", type=int, required=True)
    init_batch.add_argument("--catalog", default=str(DEFAULT_PROMPT_CATALOG))
    init_batch.add_argument("--sample-prefix", default="auto")
    init_batch.add_argument("--animal-type", default="", help="Optional catalog animal_type filter.")
    init_batch.add_argument("--armor-state", default="", choices=("", "armored", "unarmored"))
    init_batch.add_argument("--seed", type=int, default=0, help="Random seed. Defaults to current time.")
    init_batch.add_argument("--mesh-forward-axis", default="", choices=("", "POS_X", "NEG_X", "POS_Y", "NEG_Y"))

    run_batch = subparsers.add_parser(
        "run-batch",
        help="Create N catalog samples and run them through reference art, Tripo, and optional Blender prep.",
    )
    run_batch.add_argument("--count", type=int, required=True)
    run_batch.add_argument("--catalog", default=str(DEFAULT_PROMPT_CATALOG))
    run_batch.add_argument("--sample-prefix", default="auto")
    run_batch.add_argument("--animal-type", default="", help="Optional catalog animal_type filter.")
    run_batch.add_argument("--armor-state", default="", choices=("", "armored", "unarmored"))
    run_batch.add_argument("--seed", type=int, default=0, help="Random seed. Defaults to current time.")
    run_batch.add_argument("--mesh-forward-axis", default="", choices=("", "POS_X", "NEG_X", "POS_Y", "NEG_Y"))
    run_batch.add_argument("--openai-api-key", default="", help="OpenAI API key. Defaults to OPENAI_API_KEY.")
    run_batch.add_argument("--openai-base-url", default=DEFAULT_OPENAI_BASE_URL)
    run_batch.add_argument("--openai-model", default="", help=f"Defaults to catalog or {DEFAULT_OPENAI_IMAGE_MODEL}.")
    run_batch.add_argument("--image-size", default="", help="Defaults to catalog image_size or 1024x1024.")
    run_batch.add_argument("--image-quality", default="", help="Defaults to catalog image_quality or medium.")
    run_batch.add_argument("--background", default="", choices=("", "opaque", "transparent", "auto"))
    run_batch.add_argument("--output-format", default="", choices=("", "png", "jpeg", "webp"))
    run_batch.add_argument("--reference-views", default="all")
    run_batch.add_argument(
        "--reference-strategy",
        default="",
        choices=("", *REFERENCE_STRATEGIES),
        help="Defaults to catalog reference_strategy or sequential.",
    )
    run_batch.add_argument("--overwrite-reference", action="store_true")
    run_batch.add_argument("--tripo-api-key", default="", help="Tripo3D API key. Defaults to TRIPO_API_KEY.")
    run_batch.add_argument("--tripo-base-url", default=DEFAULT_TRIPO_BASE_URL)
    run_batch.add_argument("--model-version", default="v3.1-20260211")
    run_batch.add_argument("--texture", action=argparse.BooleanOptionalAction, default=True)
    run_batch.add_argument("--pbr", action=argparse.BooleanOptionalAction, default=True)
    run_batch.add_argument("--quad", action=argparse.BooleanOptionalAction, default=False)
    run_batch.add_argument("--geometry-quality", default="", choices=("", "standard", "detailed"))
    run_batch.add_argument("--texture-alignment", default="", choices=("", "original_image", "geometry"))
    run_batch.add_argument("--face-limit-min", type=int, default=3000)
    run_batch.add_argument("--face-limit-max", type=int, default=8000)
    run_batch.add_argument("--poll-interval", type=float, default=15.0)
    run_batch.add_argument("--poll-timeout", type=float, default=1800.0)
    run_batch.add_argument("--no-poll", action="store_true")
    run_batch.add_argument("--no-download", action="store_true")
    run_batch.add_argument("--prepare-label-work", action="store_true")
    run_batch.add_argument("--blender", default=os.environ.get("BLENDER_EXE", DEFAULT_BLENDER))
    run_batch.add_argument("--profile", default="", choices=("", "AUTO", "MEDIUM", "STOCKY", "HORSE"))
    run_batch.add_argument("--resolution", type=int, default=1200)
    run_batch.add_argument("--no-join-meshes", action="store_true")
    run_batch.add_argument("--continue-on-error", action="store_true")
    run_batch.add_argument("--dry-run", action="store_true", help="Create local sample state and print the plan only.")

    reference_generate = subparsers.add_parser("generate-reference", help="Generate OpenAI reference art for one sample.")
    reference_generate.add_argument("--sample-id", required=True)
    reference_generate.add_argument("--api-key", default="", help="OpenAI API key. Defaults to OPENAI_API_KEY.")
    reference_generate.add_argument("--base-url", default=DEFAULT_OPENAI_BASE_URL)
    reference_generate.add_argument("--model", default="", help=f"Defaults to catalog or {DEFAULT_OPENAI_IMAGE_MODEL}.")
    reference_generate.add_argument("--size", default="", help="Defaults to catalog image_size or 1024x1024.")
    reference_generate.add_argument("--quality", default="", help="Defaults to catalog image_quality or medium.")
    reference_generate.add_argument("--background", default="", choices=("", "opaque", "transparent", "auto"))
    reference_generate.add_argument("--output-format", default="", choices=("", "png", "jpeg", "webp"))
    reference_generate.add_argument(
        "--views",
        default="all",
        help="Comma-separated subset of front,left,right,back, or all.",
    )
    reference_generate.add_argument(
        "--reference-strategy",
        default="",
        choices=("", *REFERENCE_STRATEGIES),
        help="Use sequential image edits for consistent views, or independent generations.",
    )
    reference_generate.add_argument("--overwrite", action="store_true")

    submit = subparsers.add_parser("submit-tripo", help="Submit a multiview-to-model task to Tripo3D.")
    submit.add_argument("--sample-id", required=True)
    submit.add_argument("--api-key", default="", help="Tripo3D API key. Defaults to TRIPO_API_KEY.")
    submit.add_argument("--base-url", default=DEFAULT_TRIPO_BASE_URL)
    submit.add_argument(
        "--view-image-dir",
        default="",
        help="Directory containing front/left/right/back images. Defaults to generated OpenAI views in state.",
    )
    submit.add_argument("--model-version", default="v3.1-20260211")
    submit.add_argument("--texture", action=argparse.BooleanOptionalAction, default=True)
    submit.add_argument("--pbr", action=argparse.BooleanOptionalAction, default=True)
    submit.add_argument("--quad", action=argparse.BooleanOptionalAction, default=False)
    submit.add_argument("--geometry-quality", default="", choices=("", "standard", "detailed"))
    submit.add_argument(
        "--face-limit",
        type=int,
        default=5000,
        help="Target output face count for Tripo3D. Use 0 to omit the API parameter.",
    )
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


def openai_api_key(value: str) -> str:
    load_local_env(REPO_ROOT / ".env.local")
    load_local_env(REPO_ROOT / ".env")
    key = value or os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("Set OPENAI_API_KEY or pass --api-key.")
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


def load_prompt_catalog(path: str | Path) -> dict[str, Any]:
    catalog_path = Path(path).expanduser().resolve()
    if not catalog_path.exists():
        raise FileNotFoundError(f"Prompt catalog not found: {catalog_path}")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    specs = catalog.get("specs")
    if not isinstance(specs, list) or not specs:
        raise RuntimeError(f"Prompt catalog must contain at least one spec: {catalog_path}")
    return catalog


def skeleton_schema_id_for_body_plan(catalog: dict[str, Any], body_plan: str) -> str:
    label_schema = catalog.get("label_schema")
    if not isinstance(label_schema, dict):
        return ""
    mapping = label_schema.get("body_plan_skeleton_schema")
    if not isinstance(mapping, dict):
        return ""
    normalized_body_plan = LEGACY_BODY_PLAN_ALIASES.get(str(body_plan or "").strip(), str(body_plan or "").strip())
    return str(mapping.get(normalized_body_plan, "") or "").strip()


def select_prompt_spec(
    catalog: dict[str, Any],
    rng: random.Random,
    *,
    animal_type: str = "",
    armor_state: str = "",
) -> dict[str, Any]:
    specs = catalog["specs"]
    candidates = [
        spec
        for spec in specs
        if (not animal_type or spec.get("animal_type") == animal_type)
        and (not armor_state or spec.get("armor_state") == armor_state)
    ]
    if not candidates:
        filters = ", ".join(value for value in (animal_type, armor_state) if value) or "none"
        raise RuntimeError(f"No prompt specs matched filters: {filters}")
    selected = rng.choice(candidates)
    if not isinstance(selected, dict):
        raise RuntimeError(f"Invalid prompt spec in catalog: {selected}")
    return selected


def build_view_prompts(catalog: dict[str, Any], spec: dict[str, Any]) -> dict[str, str]:
    defaults = catalog.get("defaults", {})
    template = catalog.get("prompt_template") or defaults.get("prompt_template")
    if not isinstance(template, str) or not template:
        raise RuntimeError("Prompt catalog needs a prompt_template string.")
    views = catalog.get("views", {})
    if not isinstance(views, dict):
        raise RuntimeError("Prompt catalog views must be an object.")

    prompts: dict[str, str] = {}
    values = {
        "animal_type": spec.get("animal_type", ""),
        "morphology_type": spec.get("morphology_type", ""),
        "animal_description": spec.get("animal_description", ""),
        "equipment_description": spec.get("equipment_description", ""),
        "style_notes": spec.get("style_notes", defaults.get("style_notes", "")),
        "negative_notes": spec.get("negative_notes", defaults.get("negative_notes", "")),
    }
    for view in REFERENCE_VIEWS:
        view_instruction = views.get(view)
        if not isinstance(view_instruction, str) or not view_instruction:
            raise RuntimeError(f"Prompt catalog is missing view instruction: {view}")
        prompts[view] = template.format(**values, view=view, view_instruction=view_instruction)
    return prompts


def fallback_view_prompts(prompt: str) -> dict[str, str]:
    base = (
        "Create clean orthographic reference art for a symmetrical four-legged animal 3D character. "
        "Use a Dragon Quest XI-ish bright cel-shaded JRPG creature design: rounded expressive monster proportions, "
        "clean anime-inspired silhouettes, saturated heroic-fantasy colors, simple readable materials, and soft "
        "toy-like sculptural forms. "
        "Single animal only, centered, neutral standing pose, animation-ready proportions, full body visible, "
        "plain white background, no text, no labels, no split panels, no gritty realism, no horror design. "
        f"Character brief: {prompt}"
    )
    view_instructions = {
        "front": "front view, animal facing the camera",
        "left": "left side profile view, animal facing toward the viewer's left",
        "right": "right side profile view, animal facing toward the viewer's right",
        "back": "back view, animal facing away from the camera",
    }
    return {view: f"{base}. Render the {instruction}." for view, instruction in view_instructions.items()}


def parse_reference_views(value: str) -> list[str]:
    if value.strip().lower() == "all":
        return list(REFERENCE_VIEWS)
    views = [part.strip().lower() for part in value.split(",") if part.strip()]
    invalid = [view for view in views if view not in REFERENCE_VIEWS]
    if invalid:
        raise RuntimeError(f"Unknown reference views: {', '.join(invalid)}")
    if not views:
        raise RuntimeError("At least one reference view is required.")
    return views


def parse_reference_strategy(value: str) -> str:
    strategy = value.strip().lower()
    if not strategy:
        return "sequential"
    if strategy not in REFERENCE_STRATEGIES:
        raise RuntimeError(f"Unknown reference strategy: {value}")
    return strategy


def reference_generation_order(views: list[str], strategy: str) -> list[str]:
    if strategy == "sequential":
        return [view for view in SEQUENTIAL_REFERENCE_VIEWS if view in views]
    return views


def prior_reference_views(view: str, images: dict[str, str], strategy: str) -> list[str]:
    if strategy != "sequential":
        return []
    if view not in SEQUENTIAL_REFERENCE_VIEWS:
        return []
    view_index = SEQUENTIAL_REFERENCE_VIEWS.index(view)
    prior_views = SEQUENTIAL_REFERENCE_VIEWS[:view_index]
    return [prior_view for prior_view in prior_views if images.get(prior_view)]


def tail_constraint_for_state(state: dict[str, Any]) -> str:
    tags = state.get("variant_tags")
    tag_set = {str(tag).strip().lower() for tag in tags} if isinstance(tags, list) else set()
    body_plan = str(state.get("morphology_type") or state.get("body_plan") or "").strip().lower()
    animal_type = str(state.get("animal_type") or "").strip().lower()
    prompt = str(state.get("prompt") or "").strip().lower()

    if "long_tail" in tag_set or "long tail" in prompt:
        return "The animal has a clearly visible long tail; preserve the same tail length, attachment point, and silhouette in every view."
    if "short_tail" in tag_set or "short tail" in prompt:
        return "The animal has only a short tail or tail stub; do not turn it into a long tail in later views."
    if body_plan in {"hind_leg_dominant", "shell_reptile"} or animal_type in {"frog", "turtle"}:
        return "Do not add a visible mammal-like tail; use no tail or only a tiny anatomy-appropriate tail stub."
    return "Do not add, remove, lengthen, or shorten the tail between views; keep appendages exactly consistent with the prompt."


def effective_reference_prompt(
    *,
    base_prompt: str,
    view: str,
    prior_views: list[str],
    strategy: str,
    state: dict[str, Any],
) -> str:
    tail_rule = tail_constraint_for_state(state)
    consistency_rules = [
        tail_rule,
        "Use the same creature identity, body proportions, equipment, markings, material colors, and silhouette across all views.",
        "Keep the pose neutral and orthographic for clean Tripo3D reconstruction.",
        "Do not invent new horns, ears, paws, armor plates, tails, accessories, or secondary animals in later views.",
    ]
    if strategy != "sequential":
        return f"{base_prompt} Consistency constraints: {' '.join(consistency_rules)}"

    if not prior_views:
        lead_in = (
            "This is the canonical first model-sheet view. Establish the final creature design clearly, "
            "because later views will use this image as identity reference."
        )
    else:
        prior_text = ", ".join(prior_views)
        lead_in = (
            f"Use the attached {prior_text} reference image(s) as the source of truth for this {view} view. "
            "Match the exact same creature rather than redesigning it."
        )
    if view == "right":
        lead_in += " This should read as the opposite side of the left profile, with mirrored proportions and no new anatomy."
    elif view == "front":
        lead_in += " Reconcile the left and right profiles into a centered front view with matching width and limb placement."
    elif view == "back":
        lead_in += " Reconcile all previous views into a centered rear view with matching width, tail treatment, and equipment."

    return f"{base_prompt} Sequential consistency instructions: {lead_in} {' '.join(consistency_rules)}"


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


def mime_type_for_path(path: Path) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(path.suffix.lower(), "application/octet-stream")


def multipart_openai_image_edit(
    *,
    base_url: str,
    key: str,
    fields: dict[str, Any],
    image_paths: list[Path],
    image_field_name: str = "image[]",
) -> dict[str, Any]:
    boundary = f"----nito{uuid.uuid4().hex}"
    parts: list[bytes] = []

    for name, value in fields.items():
        if value is None or value == "":
            continue
        parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )

    for image_path in image_paths:
        resolved = image_path.expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"OpenAI reference image does not exist: {resolved}")
        parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{image_field_name}"; '
                    f'filename="{resolved.name}"\r\nContent-Type: {mime_type_for_path(resolved)}\r\n\r\n'
                ).encode("utf-8"),
                resolved.read_bytes(),
                b"\r\n",
            ]
        )

    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/images/edits",
        data=b"".join(parts),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600.0) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI image edit failed with HTTP {error.code}: {detail}") from error


def image_extension_for_format(output_format: str) -> str:
    return ".jpg" if output_format == "jpeg" else f".{output_format}"


def save_openai_image_item(item: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    b64_json = item.get("b64_json")
    if isinstance(b64_json, str) and b64_json:
        output.write_bytes(base64.b64decode(b64_json))
        return output

    url = item.get("url")
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        return download_named_url(url, output)

    raise RuntimeError(f"OpenAI image response did not include b64_json or url: {item}")


def redacted_openai_response(response: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(json.dumps(response))
    for item in redacted.get("data", []):
        if isinstance(item, dict) and "b64_json" in item:
            item["b64_json"] = "<redacted>"
    return redacted


def generate_openai_image(
    *,
    base_url: str,
    key: str,
    model: str,
    prompt: str,
    size: str,
    quality: str,
    output_format: str,
    background: str,
    reference_images: list[Path] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "quality": quality,
        "output_format": output_format,
    }
    if background:
        payload["background"] = background
    if reference_images:
        try:
            return multipart_openai_image_edit(
                base_url=base_url,
                key=key,
                fields=payload,
                image_paths=reference_images,
            )
        except RuntimeError as error:
            if "HTTP 400" not in str(error):
                raise
            return multipart_openai_image_edit(
                base_url=base_url,
                key=key,
                fields=payload,
                image_paths=reference_images,
                image_field_name="image",
            )
    return request_json(
        "POST",
        f"{base_url.rstrip('/')}/images/generations",
        key=key,
        payload=payload,
        timeout=600.0,
    )


def upload_file(base_url: str, key: str, path: Path) -> dict[str, Any]:
    boundary = f"----qwalk{uuid.uuid4().hex}"
    data = path.read_bytes()
    content_type = mime_type_for_path(path)
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
    return download_named_url(url, output)


def download_named_url(url: str, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(url, timeout=600.0) as response:
                output.write_bytes(response.read())
            return output
        except urllib.error.URLError as error:
            last_error = error
            if attempt == 3:
                break
            time.sleep(float(attempt))
    if last_error is not None:
        raise last_error
    return output


def reference_images_from_dir(directory: Path) -> dict[str, str]:
    images: dict[str, str] = {}
    for view in REFERENCE_VIEWS:
        matches = [
            candidate
            for extension in (".png", ".jpg", ".jpeg", ".webp")
            for candidate in [directory / f"{view}{extension}"]
            if candidate.exists()
        ]
        if matches:
            images[view] = str(matches[0])
    missing = [view for view in REFERENCE_VIEWS if view not in images]
    if missing:
        raise FileNotFoundError(f"Missing reference view images in {directory}: {', '.join(missing)}")
    return images


def reference_images_for_submit(state: dict[str, Any], view_image_dir: str) -> dict[str, str]:
    if view_image_dir:
        return reference_images_from_dir(Path(view_image_dir).expanduser().resolve())
    images = state.get("openai_reference_images")
    if not isinstance(images, dict):
        raise RuntimeError(
            "No OpenAI reference images found in state. Run generate-reference or pass --view-image-dir."
        )
    missing = [view for view in REFERENCE_VIEWS if not images.get(view)]
    if missing:
        raise RuntimeError(f"OpenAI reference images are incomplete: {', '.join(missing)}")
    return {view: str(Path(images[view]).expanduser().resolve()) for view in REFERENCE_VIEWS}


def tripo_file_payloads_from_reference_images(
    base_url: str,
    key: str,
    images: dict[str, str],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    files: list[dict[str, str]] = []
    uploads: dict[str, Any] = {}
    for view in TRIPO_VIEW_ORDER:
        image_path = Path(images[view]).expanduser().resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"Reference image for {view} does not exist: {image_path}")
        upload_response = upload_file(base_url, key, image_path)
        uploads[view] = {
            "image": str(image_path),
            "response": upload_response,
        }
        files.append({"type": "image", "file_token": extract_token(upload_response)})
    return files, uploads


def task_status(task_response: dict[str, Any]) -> str:
    data = response_data(task_response)
    status = data.get("status") or data.get("task_status") or data.get("state")
    return str(status or "").lower()


def wait_for_task(base_url: str, key: str, task_id: str, interval: float, timeout: float) -> dict[str, Any]:
    deadline = time.time() + timeout
    while True:
        response = request_json("GET", f"{base_url.rstrip('/')}/task/{task_id}", key=key)
        status = task_status(response)
        print(f"task {task_id}: {status or 'unknown'}")
        if status in {"success", "succeeded", "completed", "complete", "finished"}:
            return response
        if status in {"failed", "failure", "canceled", "cancelled", "error", "banned", "expired"}:
            raise RuntimeError(f"Tripo task failed: {json.dumps(response, indent=2)}")
        if time.time() >= deadline:
            raise TimeoutError(f"Timed out waiting for Tripo task {task_id}.")
        time.sleep(interval)


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


def require_created_file(path: Path, label: str) -> None:
    if not path.exists():
        raise RuntimeError(f"{label} was not created: {path}")


def create_batch_states(
    *,
    work_root: str | Path,
    count: int,
    catalog_path: str | Path,
    sample_prefix: str,
    animal_type: str,
    armor_state: str,
    seed: int,
    mesh_forward_axis: str,
) -> tuple[list[str], int]:
    if count <= 0:
        raise RuntimeError("--count must be greater than zero.")
    catalog = load_prompt_catalog(catalog_path)
    resolved_seed = seed or int(time.time())
    rng = random.Random(resolved_seed)
    created: list[str] = []
    timestamp = int(time.time())

    for index in range(count):
        spec = select_prompt_spec(
            catalog,
            rng,
            animal_type=animal_type,
            armor_state=armor_state,
        )
        sample_id = f"{sample_prefix}_{timestamp}_{index:04d}"
        view_prompts = build_view_prompts(catalog, spec)
        resolved_mesh_forward_axis = mesh_forward_axis or spec.get(
            "mesh_forward_axis", DEFAULT_TRIPO_MESH_FORWARD_AXIS
        )
        state = {
            "sample_id": sample_id,
            "prompt": spec.get("animal_description", ""),
            "animal_type": spec["animal_type"],
            "morphology_type": spec["morphology_type"],
            "body_plan": spec.get("body_plan", spec["morphology_type"]),
            "skeleton_schema_id": spec.get("skeleton_schema_id", "")
            or skeleton_schema_id_for_body_plan(catalog, spec.get("body_plan", spec["morphology_type"])),
            "variant_tags": spec.get("variant_tags", []),
            "armor_state": spec.get("armor_state", "unarmored"),
            "mesh_forward_axis": resolved_mesh_forward_axis,
            "label_profile": spec.get("label_profile", "AUTO"),
            "reference_prompt_catalog": str(Path(catalog_path).expanduser().resolve()),
            "reference_prompt_spec_id": spec.get("id", ""),
            "reference_prompt_spec": spec,
            "openai_reference_prompts": view_prompts,
            "openai_reference_defaults": catalog.get("defaults", {}),
            "batch_seed": resolved_seed,
            "status": "initialized",
            "created_at": int(time.time()),
        }
        save_state(work_root, sample_id, state)
        created.append(sample_id)

    return created, resolved_seed


def command_init_sample(args: argparse.Namespace) -> None:
    catalog = load_prompt_catalog(DEFAULT_PROMPT_CATALOG)
    state = {
        "sample_id": args.sample_id,
        "prompt": args.prompt,
        "animal_type": args.animal_type,
        "morphology_type": args.morphology_type,
        "body_plan": args.morphology_type,
        "skeleton_schema_id": skeleton_schema_id_for_body_plan(catalog, args.morphology_type),
        "variant_tags": [],
        "mesh_forward_axis": args.mesh_forward_axis,
        "status": "initialized",
        "created_at": int(time.time()),
    }
    save_state(args.work_root, args.sample_id, state)
    print(state_path(args.work_root, args.sample_id))


def command_init_batch(args: argparse.Namespace) -> None:
    created, seed = create_batch_states(
        work_root=args.work_root,
        count=args.count,
        catalog_path=args.catalog,
        sample_prefix=args.sample_prefix,
        animal_type=args.animal_type,
        armor_state=args.armor_state,
        seed=args.seed,
        mesh_forward_axis=args.mesh_forward_axis,
    )
    print(json.dumps({"created": created, "seed": seed}, indent=2))


def validate_face_limit_range(minimum: int, maximum: int) -> None:
    if minimum <= 0 or maximum <= 0:
        raise RuntimeError("--face-limit-min and --face-limit-max must be positive integers.")
    if maximum < minimum:
        raise RuntimeError("--face-limit-max must be greater than or equal to --face-limit-min.")


def save_batch_run_summary(work_root: str | Path, summary: dict[str, Any]) -> Path:
    run_id = summary["run_id"]
    output = Path(work_root).expanduser().resolve() / "batch_runs" / f"{run_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return output


def command_run_batch(args: argparse.Namespace) -> None:
    validate_face_limit_range(args.face_limit_min, args.face_limit_max)
    if args.prepare_label_work and (args.no_poll or args.no_download):
        raise RuntimeError("--prepare-label-work requires polling and model download.")

    created, seed = create_batch_states(
        work_root=args.work_root,
        count=args.count,
        catalog_path=args.catalog,
        sample_prefix=args.sample_prefix,
        animal_type=args.animal_type,
        armor_state=args.armor_state,
        seed=args.seed,
        mesh_forward_axis=args.mesh_forward_axis,
    )
    face_rng = random.Random(seed + 1009)
    run_id = f"run_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    summary: dict[str, Any] = {
        "run_id": run_id,
        "dry_run": bool(args.dry_run),
        "created": created,
        "seed": seed,
        "face_limit_range": [args.face_limit_min, args.face_limit_max],
        "started_at": int(time.time()),
        "samples": [],
    }

    for sample_id in created:
        face_limit = face_rng.randint(args.face_limit_min, args.face_limit_max)
        result: dict[str, Any] = {
            "sample_id": sample_id,
            "face_limit": face_limit,
            "status": "planned" if args.dry_run else "running",
        }
        state = load_state(args.work_root, sample_id)
        state["batch_runner"] = {
            "run_id": run_id,
            "face_limit": face_limit,
            "face_limit_range": [args.face_limit_min, args.face_limit_max],
            "dry_run": bool(args.dry_run),
            "planned_at": int(time.time()),
        }
        state["status"] = "runner_planned" if args.dry_run else "runner_running"
        save_state(args.work_root, sample_id, state)

        if args.dry_run:
            summary["samples"].append(result)
            continue

        try:
            command_generate_reference(
                argparse.Namespace(
                    work_root=args.work_root,
                    sample_id=sample_id,
                    api_key=args.openai_api_key,
                    base_url=args.openai_base_url,
                    model=args.openai_model,
                    size=args.image_size,
                    quality=args.image_quality,
                    background=args.background,
                    output_format=args.output_format,
                    views=args.reference_views,
                    reference_strategy=args.reference_strategy,
                    overwrite=args.overwrite_reference,
                )
            )
            command_submit_tripo(
                argparse.Namespace(
                    work_root=args.work_root,
                    sample_id=sample_id,
                    api_key=args.tripo_api_key,
                    base_url=args.tripo_base_url,
                    view_image_dir="",
                    model_version=args.model_version,
                    texture=args.texture,
                    pbr=args.pbr,
                    quad=args.quad,
                    geometry_quality=args.geometry_quality,
                    face_limit=face_limit,
                    texture_alignment=args.texture_alignment,
                )
            )
            result["status"] = "submitted"

            if not args.no_poll:
                command_poll_tripo(
                    argparse.Namespace(
                        work_root=args.work_root,
                        sample_id=sample_id,
                        api_key=args.tripo_api_key,
                        base_url=args.tripo_base_url,
                        interval=args.poll_interval,
                        timeout=args.poll_timeout,
                        no_download=args.no_download,
                    )
                )
                result["status"] = "model_polled" if args.no_download else "model_downloaded"

            if args.prepare_label_work:
                latest_state = load_state(args.work_root, sample_id)
                profile = args.profile or latest_state.get("label_profile", "AUTO")
                command_prepare_label_work(
                    argparse.Namespace(
                        work_root=args.work_root,
                        sample_id=sample_id,
                        blender=args.blender,
                        model_file="",
                        profile=profile,
                        mesh_forward_axis="",
                        resolution=args.resolution,
                        no_join_meshes=args.no_join_meshes,
                    )
                )
                result["status"] = "label_work_prepared"

            latest_state = load_state(args.work_root, sample_id)
            latest_state["batch_runner"]["completed_at"] = int(time.time())
            latest_state["batch_runner"]["result_status"] = result["status"]
            save_state(args.work_root, sample_id, latest_state)
        except Exception as error:
            result["status"] = "failed"
            result["error"] = str(error)
            try:
                failed_state = load_state(args.work_root, sample_id)
                failed_state["status"] = "runner_failed"
                failed_state["batch_runner"] = failed_state.get("batch_runner", {})
                failed_state["batch_runner"]["failed_at"] = int(time.time())
                failed_state["batch_runner"]["error"] = str(error)
                save_state(args.work_root, sample_id, failed_state)
            except Exception:
                pass
            summary["samples"].append(result)
            summary["finished_at"] = int(time.time())
            save_batch_run_summary(args.work_root, summary)
            if not args.continue_on_error:
                raise
            print(f"Sample {sample_id} failed: {error}", file=sys.stderr)
            continue

        summary["samples"].append(result)
        save_batch_run_summary(args.work_root, summary)

    summary["finished_at"] = int(time.time())
    summary_path = save_batch_run_summary(args.work_root, summary)
    summary["summary_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


def command_generate_reference(args: argparse.Namespace) -> None:
    state = load_state(args.work_root, args.sample_id)
    key = openai_api_key(args.api_key)
    defaults = state.get("openai_reference_defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}

    model = args.model or defaults.get("image_model") or DEFAULT_OPENAI_IMAGE_MODEL
    size = args.size or defaults.get("image_size") or "1024x1024"
    quality = args.quality or defaults.get("image_quality") or "medium"
    output_format = args.output_format or defaults.get("output_format") or "png"
    background = args.background or defaults.get("background") or "opaque"
    views = parse_reference_views(args.views)
    strategy_arg = getattr(args, "reference_strategy", "")
    strategy = parse_reference_strategy(strategy_arg or str(defaults.get("reference_strategy") or ""))
    generation_order = reference_generation_order(views, strategy)

    base_prompts = state.get("openai_reference_base_prompts")
    if not isinstance(base_prompts, dict):
        base_prompts = state.get("openai_reference_prompts")
    if not isinstance(base_prompts, dict):
        base_prompts = fallback_view_prompts(state["prompt"])
    state["openai_reference_base_prompts"] = base_prompts
    effective_prompts = dict(base_prompts)

    reference_dir = sample_dir(args.work_root, args.sample_id) / "reference"
    images = dict(state.get("openai_reference_images", {})) if isinstance(state.get("openai_reference_images"), dict) else {}
    responses = (
        dict(state.get("openai_reference_responses", {}))
        if isinstance(state.get("openai_reference_responses"), dict)
        else {}
    )

    for view in generation_order:
        output = reference_dir / f"{view}{image_extension_for_format(output_format)}"
        prompt = base_prompts.get(view)
        if not isinstance(prompt, str) or not prompt:
            raise RuntimeError(f"No OpenAI prompt available for view: {view}")

        prior_views = prior_reference_views(view, images, strategy)
        prior_images = [Path(images[prior_view]).expanduser().resolve() for prior_view in prior_views]
        effective_prompt = effective_reference_prompt(
            base_prompt=prompt,
            view=view,
            prior_views=prior_views,
            strategy=strategy,
            state=state,
        )
        effective_prompts[view] = effective_prompt
        if output.exists() and not args.overwrite:
            images[view] = str(output)
            print(f"Skipping existing {view} reference: {output}")
            continue

        response = generate_openai_image(
            base_url=args.base_url,
            key=key,
            model=str(model),
            prompt=effective_prompt,
            size=str(size),
            quality=str(quality),
            output_format=str(output_format),
            background=str(background),
            reference_images=prior_images,
        )
        data = response.get("data")
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            raise RuntimeError(f"Unexpected OpenAI image response: {response}")
        save_openai_image_item(data[0], output)
        images[view] = str(output)
        responses[view] = {
            "strategy": strategy,
            "reference_inputs": [str(path) for path in prior_images],
            "response": redacted_openai_response(response),
        }
        if prior_images:
            print(f"Generated {view} reference from {len(prior_images)} prior image(s): {output}")
        else:
            print(f"Generated {view} reference: {output}")

    state["openai_reference_images"] = images
    state["openai_reference_responses"] = responses
    state["openai_reference_prompts"] = effective_prompts
    state["openai_reference_generation"] = {
        "model": model,
        "size": size,
        "quality": quality,
        "output_format": output_format,
        "background": background,
        "views": views,
        "generation_order": generation_order,
        "reference_strategy": strategy,
        "created_at": int(time.time()),
    }
    state["reference_status"] = "openai_generated"
    state["status"] = "openai_reference_generated"
    save_state(args.work_root, args.sample_id, state)


def command_submit_tripo(args: argparse.Namespace) -> None:
    state = load_state(args.work_root, args.sample_id)
    key = api_key(args.api_key)
    base_url = args.base_url.rstrip("/")

    payload: dict[str, Any] = {
        "type": "multiview_to_model",
        "model_version": args.model_version,
        "texture": args.texture,
        "pbr": args.pbr,
        "quad": args.quad,
    }
    reference_images = reference_images_for_submit(state, args.view_image_dir)
    files, uploads = tripo_file_payloads_from_reference_images(base_url, key, reference_images)
    payload["files"] = files
    state["tripo_model_source"] = "openai_reference_views"
    state["tripo_model_reference_images"] = reference_images
    state["tripo_model_reference_uploads"] = uploads
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
    state["status"] = "tripo_model_submitted"
    save_state(args.work_root, args.sample_id, state)
    print(f"Submitted Tripo multiview-to-model task: {task_id}")


def command_poll_tripo(args: argparse.Namespace) -> None:
    state = load_state(args.work_root, args.sample_id)
    task_id = state.get("tripo_task_id")
    if not task_id:
        raise RuntimeError("No tripo_task_id in state. Run submit-tripo first.")
    key = api_key(args.api_key)
    base_url = args.base_url.rstrip("/")
    response = wait_for_task(base_url, key, str(task_id), args.interval, args.timeout)

    state["tripo_result_response"] = response
    state["status"] = "tripo_completed"
    save_state(args.work_root, args.sample_id, state)
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
    source_axis = args.mesh_forward_axis or state.get("mesh_forward_axis", DEFAULT_TRIPO_MESH_FORWARD_AXIS)
    canonical_axis = "POS_Y"

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
            "--source-forward-axis",
            source_axis,
            "--target-forward-axis",
            canonical_axis,
            *(["--no-join-meshes"] if args.no_join_meshes else []),
        ]
    )
    require_created_file(source_blend, "Imported Blender file")
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
            canonical_axis,
        ]
    )
    require_created_file(label_blend, "Label-work Blender file")
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
            canonical_axis,
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
            "source_mesh_forward_axis": source_axis,
            "mesh_forward_axis": canonical_axis,
            "mesh_orientation_standardized": True,
            "label_profile": args.profile,
            "review_dir": str(review_dir),
            "status": "candidate_review_rendered",
            "updated_at": int(time.time()),
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
    export_dir = REPO_ROOT / "data" / "real_quadrupeds" / args.split
    label_file = export_dir / f"{args.sample_id}.json"
    mesh_file = export_dir / f"{args.sample_id}.obj"
    require_created_file(label_file, "Exported label JSON")
    require_created_file(mesh_file, "Exported label mesh")
    state["status"] = "verified_exported" if args.verified else "candidate_exported"
    state["export_verified"] = bool(args.verified)
    state["training_eligible"] = bool(args.verified)
    state["export_split"] = args.split
    state["export_label"] = str(label_file)
    state["export_mesh"] = str(mesh_file)
    save_state(args.work_root, args.sample_id, state)


def command_status(args: argparse.Namespace) -> None:
    print(json.dumps(load_state(args.work_root, args.sample_id), indent=2))


def main() -> None:
    args = parse_args()
    handlers = {
        "init-sample": command_init_sample,
        "init-batch": command_init_batch,
        "run-batch": command_run_batch,
        "generate-reference": command_generate_reference,
        "submit-tripo": command_submit_tripo,
        "poll-tripo": command_poll_tripo,
        "prepare-label-work": command_prepare_label_work,
        "export-verified": command_export_verified,
        "status": command_status,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
