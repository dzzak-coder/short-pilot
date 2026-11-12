"""Prevalidate and render the two Khéops anchors in one ComfyUI prompt.

The proof is isolated from every historical seed-70001 artifact.  One workflow
contains two Qwen branches and therefore produces two anchor images through one
POST /prompt.  Eight deterministic crops are derived locally for continuity;
no video, voice, publication, or additional image request is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import aiimg, local_resources, oneshot, visual_planner


FOLDER = ROOT / "outputs" / "kheops_dominant_visual_validation_2026-11-10_v2"
SOURCE_REPORT = ROOT / "outputs" / "text_diagnostics" / "kheops_plan_2026-11-09.json"
LEGACY_MARKER = ROOT / "outputs" / "qwen_turbo_visual_validation" / "generation_once.json"
LEGACY_MARKER_SHA256 = "bd5651e3f501fc42702945ced55d26605a8cbefa8a1b2253e46c0757c555ab1b"
SEEDS = (71102, 71103)
SERVER = "http://127.0.0.1:8188"
CAMERA_DIRECTIVES = (
    "wide establishing view, eye-level camera, full subject visible, deep depth of field",
    "medium-long three-quarter view, low camera position, foreground-to-background depth, deep focus",
)
CROP_MODES = (
    ("push_in", (0.06, 0.06, 0.94, 0.94)),
    ("left_to_right", (0.08, 0.04, 1.00, 0.96)),
    ("pull_out", (0.00, 0.00, 1.00, 1.00)),
    ("right_to_left", (0.00, 0.04, 0.92, 0.96)),
    ("rise", (0.04, 0.00, 0.96, 0.90)),
    ("descend", (0.04, 0.10, 0.96, 1.00)),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code_hash() -> str:
    files = [ROOT / "app.py", *sorted((ROOT / "core").glob("*.py")),
             *sorted((ROOT / "tests").glob("*.py")), *sorted((ROOT / "tools").glob("*.py")),
             *sorted((ROOT / "templates").glob("*.html")), *sorted((ROOT / "workflows").glob("*.json"))]
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def planner_compiler_hash() -> str:
    digest = hashlib.sha256()
    for path in (ROOT / "core" / "visual_planner.py", ROOT / "core" / "visual_constraints.py"):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _legacy_intact() -> bool:
    return LEGACY_MARKER.is_file() and sha256(LEGACY_MARKER) == LEGACY_MARKER_SHA256


def _anchor_rows(report: dict) -> list[dict]:
    plans = report.get("visual_plans") or []
    controls = report.get("visual_controls") or []
    scenes = report.get("scenes") or []
    if not (len(plans) == len(controls) == len(scenes) == 12):
        raise ValueError("Le rapport Khéops doit contenir 12 scènes, plans et contrôles")
    rows = []
    for index, (scene, plan, control) in enumerate(zip(scenes, plans, controls), 1):
        if plan and isinstance(control, dict) and not control.get("needs_context") and not control.get("planning_error"):
            visual_planner.validate_required_terms(plan, control)
            rows.append({"scene_index": index, "narration": scene, "visual_plan": plan,
                         "visual_control": control})
    if [row["scene_index"] for row in rows] != [2, 3]:
        raise ValueError("Les seuls ancrages validés attendus sont les scènes 2 et 3")
    return rows


def _continuity_schedule(report: dict, anchor_rows: list[dict]) -> list[dict]:
    anchor_scenes = {row["scene_index"] for row in anchor_rows}
    schedule = []
    for index, control in enumerate(report["visual_controls"], 1):
        if not isinstance(control, dict) or not control.get("needs_context"):
            continue
        anchor = int(control.get("context_scene_index") or 0)
        if anchor not in anchor_scenes:
            raise ValueError(f"Scène {index} : ancrage de continuité invalide ({anchor})")
        name, crop = CROP_MODES[(index - 1) % len(CROP_MODES)]
        schedule.append({"scene_index": index, "anchor_scene_index": anchor,
                         "camera_move": name, "crop_box_normalized": list(crop)})
    if len(schedule) != 8:
        raise ValueError(f"Huit scènes de continuité attendues, obtenu : {len(schedule)}")
    return schedule


def build_workflow(render_prompts: list[str]) -> dict:
    if len(render_prompts) != 2 or any(seed == 70001 for seed in SEEDS):
        raise ValueError("Deux prompts et deux nouvelles seeds non historiques sont requis")
    workflow = {
        "4": {"class_type": "UNETLoader", "inputs": {"unet_name": aiimg.QWEN_TURBO_UNET, "weight_dtype": "default"}},
        "5": {"class_type": "CLIPLoader", "inputs": {"clip_name": aiimg.QWEN_TURBO_CLIP, "type": "qwen_image", "device": "default"}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": aiimg.QWEN_TURBO_VAE}},
    }
    for branch, (prompt, seed) in enumerate(zip(render_prompts, SEEDS)):
        offset = branch * 10
        encoder, latent, sampler, decode, output = (str(7 + offset), str(8 + offset),
                                                     str(3 + offset), str(9 + offset), str(10 + offset))
        workflow[encoder] = {"class_type": "TextEncodeQwenImage21", "inputs": {
            "prompt": prompt, "negative_prompt": "", "resolution": 1280, "clip": ["5", 0]}}
        workflow[latent] = {"class_type": "EmptyLatentImage", "inputs": {
            "width": 720, "height": 1280, "batch_size": 1}}
        workflow[sampler] = {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": 8, "cfg": 1.0, "sampler_name": "euler",
            "scheduler": "simple", "denoise": 1.0, "model": ["4", 0],
            "positive": [encoder, 0], "negative": [encoder, 1], "latent_image": [latent, 0]}}
        workflow[decode] = {"class_type": "VAEDecode", "inputs": {
            "samples": [sampler, 0], "vae": ["6", 0]}}
        workflow[output] = {"class_type": "SaveImage", "inputs": {
            "filename_prefix": f"shortpilot_kheops_anchor_{branch + 1}", "images": [decode, 0]}}
    return workflow


def _prepare() -> None:
    if FOLDER.exists():
        raise RuntimeError(f"Le dossier de preuve doit être neuf : {FOLDER}")
    if not _legacy_intact():
        raise RuntimeError("Le marqueur historique seed 70001 ne correspond plus à son SHA-256")
    report = json.loads(SOURCE_REPORT.read_text(encoding="utf-8"))
    anchors = _anchor_rows(report)
    schedule = _continuity_schedule(report, anchors)
    render_prompts = []
    for row, directive in zip(anchors, CAMERA_DIRECTIVES):
        prompt = row["visual_plan"].rstrip(" ,") + ", " + directive
        if len(prompt) > 900:
            raise ValueError("Prompt cadré trop long")
        visual_planner.validate_required_terms(prompt, row["visual_control"])
        row["camera_directive"] = directive
        row["render_prompt"] = prompt
        render_prompts.append(prompt)
    workflow = build_workflow(render_prompts)
    FOLDER.mkdir(parents=True)
    plan = {
        "report_kind": "kheops_image_dominant_preflight",
        "source_report": str(SOURCE_REPORT.relative_to(ROOT)),
        "source_report_sha256": sha256(SOURCE_REPORT),
        "legacy_marker": str(LEGACY_MARKER.relative_to(ROOT)),
        "legacy_marker_sha256_before": sha256(LEGACY_MARKER),
        "code_hash": code_hash(),
        "planner_compiler_sha256": planner_compiler_hash(),
        "visual_plan_fingerprint": hashlib.sha256(
            json.dumps(render_prompts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest(),
        "seeds": list(SEEDS),
        "anchor_count": 2,
        "continuity_count": 8,
        "variation_contract": {
            "anchor_cameras": list(CAMERA_DIRECTIVES),
            "continuity": schedule,
            "scope": "Recadrage et distance apparente uniquement; aucun angle 3D ni profondeur nouvelle n'est inventé.",
        },
        "anchors": anchors,
        "workflow": workflow,
        "graph_sha256": oneshot.graph_hash(workflow),
        "visual_acceptance": {"accepted": None, "review": "Images non inspectées"},
    }
    save(FOLDER / "plan.json", plan)
    print(json.dumps({"folder": str(FOLDER), "code_hash": plan["code_hash"],
                      "graph_sha256": plan["graph_sha256"], "anchors": 2,
                      "continuities": 8}, ensure_ascii=False, indent=2))


def _test() -> None:
    plan = json.loads((FOLDER / "plan.json").read_text(encoding="utf-8"))
    before = code_hash()
    if before != plan["code_hash"] or not _legacy_intact():
        raise RuntimeError("Le code ou la preuve historique a changé depuis la prévalidation")
    started = time.monotonic()
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            encoding="utf-8", errors="replace",
                            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    (FOLDER / "final_tests.log").write_text(result.stdout, encoding="utf-8")
    after = code_hash()
    stamp = {"command": command, "returncode": result.returncode, "code_hash": after,
             "unchanged_during_tests": before == after,
             "duration_seconds": round(time.monotonic() - started, 2),
             "planner_compiler_sha256": planner_compiler_hash(),
             "legacy_marker_sha256_after_tests": sha256(LEGACY_MARKER)}
    save(FOLDER / "final_tests.json", stamp)
    print(result.stdout)
    if result.returncode or before != after or not _legacy_intact():
        raise SystemExit(result.returncode or 1)


def _crop_variants(plan: dict, execution: dict) -> dict:
    from PIL import Image
    images = execution.get("images") or []
    if len(images) != 2:
        raise RuntimeError("Deux images d'ancrage sont requises pour les continuités")
    anchor_files = {row["scene_index"]: FOLDER / evidence["image"]
                    for row, evidence in zip(plan["anchors"], images)}
    variants = []
    for item in plan["variation_contract"]["continuity"]:
        source = anchor_files[item["anchor_scene_index"]]
        with Image.open(source) as image:
            width, height = image.size
            left, top, right, bottom = item["crop_box_normalized"]
            box = (round(left * width), round(top * height), round(right * width), round(bottom * height))
            variant = image.crop(box).resize((width, height), Image.Resampling.LANCZOS)
            target = FOLDER / f"continuity_scene_{item['scene_index']:02d}_{item['camera_move']}.png"
            variant.save(target, format="PNG")
        variants.append({**item, "source_image": source.name, "image": target.name,
                         "image_sha256": sha256(target), "dimensions": [width, height]})
    return {"report_kind": "continuity_variants", "accepted": None,
            "review": "Images non inspectées", "variants": variants}


def _generate() -> None:
    marker = FOLDER / "generation_once.json"
    if marker.exists():
        raise RuntimeError("Cette nouvelle preuve possède déjà son marqueur one-shot")
    plan = json.loads((FOLDER / "plan.json").read_text(encoding="utf-8"))
    tests = json.loads((FOLDER / "final_tests.json").read_text(encoding="utf-8"))
    current_hash = code_hash()
    if (plan["code_hash"] != current_hash or tests["code_hash"] != current_hash
            or tests["returncode"] != 0 or not tests["unchanged_during_tests"]
            or plan["planner_compiler_sha256"] != planner_compiler_hash()
            or tests["planner_compiler_sha256"] != planner_compiler_hash()
            or plan["source_report_sha256"] != sha256(SOURCE_REPORT)
            or not _legacy_intact()):
        raise RuntimeError("Prévalidation obsolète : aucun marqueur ni POST autorisé")
    workflow = plan["workflow"]
    post_count = 0
    import requests
    from PIL import Image

    def preflight_check():
        if not _legacy_intact() or code_hash() != current_hash:
            raise RuntimeError("Intégrité modifiée avant réservation")
        stats = requests.get(SERVER + "/system_stats", timeout=5)
        stats.raise_for_status()
        info = requests.get(SERVER + "/object_info", timeout=20)
        info.raise_for_status()
        data = info.json()
        required = {"UNETLoader": ("unet_name", aiimg.QWEN_TURBO_UNET),
                    "CLIPLoader": ("clip_name", aiimg.QWEN_TURBO_CLIP),
                    "VAELoader": ("vae_name", aiimg.QWEN_TURBO_VAE)}
        for node, (field, expected) in required.items():
            values = data[node]["input"]["required"][field][0]
            if expected not in values:
                raise RuntimeError("Composant Qwen manquant : " + expected)
        queue = requests.get(SERVER + "/queue", timeout=5)
        queue.raise_for_status()
        state = queue.json()
        if state.get("queue_running") or state.get("queue_pending"):
            raise RuntimeError("Conflit ComfyUI externe détecté")
        for row in plan["anchors"]:
            visual_planner.validate_required_terms(row["render_prompt"], row["visual_control"])

    def submit(payload, client_id):
        nonlocal post_count
        post_count += 1
        if post_count != 1:
            raise RuntimeError("Plus d'un POST /prompt interdit")
        return requests.post(SERVER + "/prompt",
                             json={"prompt": payload, "client_id": client_id}, timeout=20)

    def history(prompt_id):
        response = requests.get(SERVER + "/history/" + prompt_id, timeout=20)
        response.raise_for_status()
        return response.json()

    def download(image):
        response = requests.get(SERVER + "/view", params=image, timeout=20)
        response.raise_for_status()
        return response.content

    def validate_execution(executed):
        if executed != workflow:
            raise ValueError("Le workflow exécuté diffère du workflow prévalidé")
        samplers = [node for node in executed.values() if node.get("class_type") == "KSampler"]
        encoders = [node for node in executed.values() if node.get("class_type") == "TextEncodeQwenImage21"]
        if ([node["inputs"]["seed"] for node in samplers] != list(SEEDS)
                or [node["inputs"]["prompt"] for node in encoders]
                != [row["render_prompt"] for row in plan["anchors"]]):
            raise ValueError("Seeds ou prompts exécutés non conformes")

    execution = oneshot.run(
        FOLDER, seed=SEEDS[0],
        preflight={"mode": "comfy_batch_two_anchors", "code_hash": current_hash,
                   "planner_compiler_sha256": planner_compiler_hash(),
                   "visual_plan_fingerprint": plan["visual_plan_fingerprint"],
                   "source_report_sha256": plan["source_report_sha256"],
                   "legacy_marker_sha256": LEGACY_MARKER_SHA256,
                   "expected_images": 2, "max_prompt_posts": 1,
                   "final_tests": tests},
        workflow=workflow, preflight_check=preflight_check, submit=submit,
        history=history, download=download, max_polls=180, poll_interval=2,
        image_size=lambda path: list(Image.open(path).size),
        expected_image_size=(720, 1280), validate_execution=validate_execution,
        render_phase=local_resources.render_phase(
            comfy_url=SERVER,
            required_components=(aiimg.QWEN_TURBO_UNET,
                                 aiimg.QWEN_TURBO_CLIP,
                                 aiimg.QWEN_TURBO_VAE)),
    )
    if execution.get("execution_status") == "succeeded":
        save(FOLDER / "continuity_variants.json", _crop_variants(plan, execution))
    postconditions = {"prompt_post_count": post_count,
                      "legacy_marker_sha256_after": sha256(LEGACY_MARKER),
                      "legacy_marker_unchanged": _legacy_intact(),
                      "accepted": None}
    save(FOLDER / "postconditions.json", postconditions)
    print(json.dumps({"execution_status": execution.get("execution_status"),
                      "prompt_id": execution.get("prompt_id"),
                      "image_count": execution.get("image_count"),
                      **postconditions}, ensure_ascii=False, indent=2))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--test", action="store_true")
    group.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        _prepare()
    elif args.test:
        _test()
    else:
        _generate()


if __name__ == "__main__":
    main()
