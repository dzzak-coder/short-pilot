"""Prevalidate and execute the 23-image Khéops campaign in one ComfyUI POST."""
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


FOLDER = ROOT / "outputs" / "kheops_campaign_2026-11-10"
DENSITY_REPORT = ROOT / "outputs" / "text_diagnostics" / "kheops_visual_density_2026-11-10.json"
PROMPT_REPORT = ROOT / "outputs" / "text_diagnostics" / "kheops_image_plans_2026-11-10.json"
LEGACY_MARKER = ROOT / "outputs" / "qwen_turbo_visual_validation" / "generation_once.json"
LEGACY_MARKER_SHA256 = "bd5651e3f501fc42702945ced55d26605a8cbefa8a1b2253e46c0757c555ab1b"
SERVER = "http://127.0.0.1:8188"
SEEDS = tuple(range(72001, 72024))


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


def save(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def build_workflow(image_plans: list[dict], seeds=SEEDS) -> dict:
    if len(image_plans) != len(seeds) or 70001 in seeds:
        raise ValueError("Un plan par seed et aucune seed 70001 sont requis")
    workflow = {
        "4": {"class_type": "UNETLoader", "inputs": {"unet_name": aiimg.QWEN_TURBO_UNET, "weight_dtype": "default"}},
        "5": {"class_type": "CLIPLoader", "inputs": {"clip_name": aiimg.QWEN_TURBO_CLIP, "type": "qwen_image", "device": "default"}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": aiimg.QWEN_TURBO_VAE}},
    }
    for branch, (item, seed) in enumerate(zip(image_plans, seeds), 1):
        base = 100 + branch * 10
        encoder, latent, sampler, decode, output = map(str, range(base, base + 5))
        workflow[encoder] = {"class_type": "TextEncodeQwenImage21", "inputs": {
            "prompt": item["prompt"], "negative_prompt": "", "resolution": 1280, "clip": ["5", 0]}}
        workflow[latent] = {"class_type": "EmptyLatentImage", "inputs": {
            "width": 720, "height": 1280, "batch_size": 1}}
        workflow[sampler] = {"class_type": "KSampler", "inputs": {
            "seed": seed, "steps": 8, "cfg": 1.0, "sampler_name": "euler",
            "scheduler": "simple", "denoise": 1.0, "model": ["4", 0],
            "positive": [encoder, 0], "negative": [encoder, 1], "latent_image": [latent, 0]}}
        workflow[decode] = {"class_type": "VAEDecode", "inputs": {
            "samples": [sampler, 0], "vae": ["6", 0]}}
        workflow[output] = {"class_type": "SaveImage", "inputs": {
            "filename_prefix": f"shortpilot_kheops_campaign_{branch:02d}", "images": [decode, 0]}}
    return workflow


def prepare():
    if FOLDER.exists():
        raise RuntimeError(f"Le dossier de campagne doit être neuf : {FOLDER}")
    if sha256(LEGACY_MARKER) != LEGACY_MARKER_SHA256:
        raise RuntimeError("Le marqueur historique seed 70001 a changé")
    prompts = json.loads(PROMPT_REPORT.read_text(encoding="utf-8"))
    density = json.loads(DENSITY_REPORT.read_text(encoding="utf-8"))
    if not prompts.get("accepted") or not density["image_schedule"]["selection_accepted"]:
        raise RuntimeError("Les phases 1 et 2 ne sont pas acceptées")
    image_plans = prompts["image_plans"]
    for item in image_plans:
        visual_planner.validate_required_terms(item["prompt"], item["control"])
    workflow = build_workflow(image_plans)
    FOLDER.mkdir(parents=True)
    plan = {
        "report_kind": "kheops_campaign_preflight",
        "code_hash": code_hash(),
        "density_report_sha256": sha256(DENSITY_REPORT),
        "prompt_report_sha256": sha256(PROMPT_REPORT),
        "legacy_marker_sha256_before": sha256(LEGACY_MARKER),
        "seeds": list(SEEDS),
        "expected_images": 23,
        "visual_plan_fingerprint": hashlib.sha256(json.dumps(
            [item["prompt"] for item in image_plans], ensure_ascii=False).encode("utf-8")).hexdigest(),
        "workflow": workflow,
        "graph_sha256": oneshot.graph_hash(workflow),
        "visual_acceptance": {"accepted": None, "review": "Images non inspectées"},
    }
    save(FOLDER / "plan.json", plan)
    print(json.dumps({"folder": str(FOLDER), "expected_images": 23,
                      "graph_sha256": plan["graph_sha256"]}, indent=2))


def test():
    plan = json.loads((FOLDER / "plan.json").read_text(encoding="utf-8"))
    before = code_hash()
    if before != plan["code_hash"]:
        raise RuntimeError("Le code a changé depuis la prévalidation")
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            encoding="utf-8", errors="replace")
    (FOLDER / "final_tests.log").write_text(result.stdout, encoding="utf-8")
    stamp = {"returncode": result.returncode, "code_hash": code_hash(),
             "unchanged_during_tests": before == code_hash(),
             "legacy_marker_sha256_after_tests": sha256(LEGACY_MARKER)}
    save(FOLDER / "final_tests.json", stamp)
    print(result.stdout)
    if result.returncode or not stamp["unchanged_during_tests"]:
        raise SystemExit(result.returncode or 1)


def generate():
    import requests
    from PIL import Image

    plan = json.loads((FOLDER / "plan.json").read_text(encoding="utf-8"))
    tests = json.loads((FOLDER / "final_tests.json").read_text(encoding="utf-8"))
    current_hash = code_hash()
    if (plan["code_hash"] != current_hash or tests["code_hash"] != current_hash
            or tests["returncode"] != 0 or not tests["unchanged_during_tests"]
            or plan["density_report_sha256"] != sha256(DENSITY_REPORT)
            or plan["prompt_report_sha256"] != sha256(PROMPT_REPORT)
            or sha256(LEGACY_MARKER) != LEGACY_MARKER_SHA256):
        raise RuntimeError("Prévalidation obsolète : aucun marqueur ni POST autorisé")
    workflow = plan["workflow"]
    post_count = 0

    def preflight_check():
        if code_hash() != current_hash or sha256(LEGACY_MARKER) != LEGACY_MARKER_SHA256:
            raise RuntimeError("Intégrité modifiée avant réservation")
        info = requests.get(SERVER + "/object_info", timeout=30)
        info.raise_for_status()
        data = info.json()
        required = {"UNETLoader": ("unet_name", aiimg.QWEN_TURBO_UNET),
                    "CLIPLoader": ("clip_name", aiimg.QWEN_TURBO_CLIP),
                    "VAELoader": ("vae_name", aiimg.QWEN_TURBO_VAE)}
        for node, (field, expected) in required.items():
            if expected not in data[node]["input"]["required"][field][0]:
                raise RuntimeError("Composant Qwen manquant : " + expected)
        queue = requests.get(SERVER + "/queue", timeout=5)
        queue.raise_for_status()
        state = queue.json()
        if state.get("queue_running") or state.get("queue_pending"):
            raise RuntimeError("Conflit ComfyUI externe détecté")

    def submit(payload, client_id):
        nonlocal post_count
        post_count += 1
        if post_count != 1:
            raise RuntimeError("Plus d’un POST /prompt interdit")
        return requests.post(SERVER + "/prompt", json={"prompt": payload, "client_id": client_id}, timeout=30)

    def history(prompt_id):
        response = requests.get(SERVER + "/history/" + prompt_id, timeout=30)
        response.raise_for_status()
        return response.json()

    def download(image):
        response = requests.get(SERVER + "/view", params=image, timeout=30)
        response.raise_for_status()
        return response.content

    def validate_execution(executed):
        if executed != workflow:
            raise ValueError("Le graphe exécuté diffère du graphe prévalidé")
        samplers = [node for node in executed.values() if node.get("class_type") == "KSampler"]
        if sorted(node["inputs"]["seed"] for node in samplers) != list(SEEDS):
            raise ValueError("Seeds exécutées non conformes")

    execution = oneshot.run(
        FOLDER, seed=SEEDS[0],
        preflight={"mode": "comfy_23_branches_one_post", "code_hash": current_hash,
                   "visual_plan_fingerprint": plan["visual_plan_fingerprint"],
                   "legacy_marker_sha256": LEGACY_MARKER_SHA256,
                   "expected_images": 23, "max_prompt_posts": 1,
                   "final_tests": tests},
        workflow=workflow, preflight_check=preflight_check, submit=submit,
        history=history, download=download, max_polls=900, poll_interval=2,
        image_size=lambda path: list(Image.open(path).size),
        expected_image_size=(720, 1280), validate_execution=validate_execution,
        render_phase=local_resources.render_phase(
            comfy_url=SERVER,
            required_components=(aiimg.QWEN_TURBO_UNET, aiimg.QWEN_TURBO_CLIP, aiimg.QWEN_TURBO_VAE)),
    )
    postconditions = {"prompt_post_count": post_count,
                      "legacy_marker_sha256_after": sha256(LEGACY_MARKER),
                      "legacy_marker_unchanged": sha256(LEGACY_MARKER) == LEGACY_MARKER_SHA256,
                      "accepted": None}
    save(FOLDER / "postconditions.json", postconditions)
    print(json.dumps({"execution_status": execution.get("execution_status"),
                      "prompt_id": execution.get("prompt_id"),
                      "image_count": execution.get("image_count"), **postconditions}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--test", action="store_true")
    group.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.test:
        test()
    else:
        generate()


if __name__ == "__main__":
    main()
