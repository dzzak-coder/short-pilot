"""One-shot fast regression: text plan, complete tests, then ONE fixed-seed image.

Run --plan, review plan.json, run --test, then --generate. No architecture,
checkpoint, seed or sampler options. Historical attempt folders stay untouched.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import aiimg, content, render, visual_planner

SOURCE = "Un minuteur rouge sur un bureau en bois, à côté d’un planning fermé, lumière du matin"
# The French source is the sole evidence for all scene attributes.
TITLE = ""
# This is an acceptance assertion for this one French-source regression, not a
# production vocabulary rule: the rendered subject must stay recognisable.
EXPECTED = ("red timer", "wooden desk", "closed planner", "morning light")
FOLDER = ROOT / "outputs" / "qwen_turbo_visual_validation"
SEED = 70001
CHECKPOINT = aiimg.QWEN_TURBO_UNET


def code_hash():
    files = [ROOT / "app.py", *sorted((ROOT / "core").glob("*.py")),
             *sorted((ROOT / "tests").glob("*.py")), *sorted((ROOT / "tools").glob("*.py")),
             *sorted((ROOT / "templates").glob("*.html")), *sorted((ROOT / "workflows").glob("*.json"))]
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def planner_compiler_hash():
    digest = hashlib.sha256()
    for path in (ROOT / "core" / "visual_planner.py", ROOT / "core" / "visual_constraints.py"):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", action="store_true", help="Text planning only; no image requests")
    group.add_argument("--test", action="store_true", help="Run the complete unittest suite on final code")
    group.add_argument("--generate", action="store_true", help="One image only, after successful final tests")
    args = parser.parse_args()
    FOLDER.mkdir(parents=True, exist_ok=True)
    if args.plan:
        if (FOLDER / "generation_once.json").exists():
            raise RuntimeError("Cette preuve a déjà été exécutée ; conserver ses résultats")
        bundle = content.visual_plan_bundle([SOURCE], title=TITLE, niche="sujet", language="fr")
        control, plan = bundle["visual_controls"][0], bundle["visual_plans"][0]
        try:
            render._local_comfy_prompt("", "", "", "", plan, control)
            for detail in EXPECTED:
                if detail not in plan:
                    raise ValueError("Regression textuelle non satisfaite : " + detail)
            review = visual_planner.semantic_review(SOURCE, TITLE, control, plan)
            if not review["passed"]:
                # One text-only repair is allowed; unlike image sampling, it
                # is deterministic, bounded, and retains the rejection reason.
                raw = visual_planner._request_plans((SOURCE,), TITLE, "sujet", "fr",
                    feedback=("Revue sémantique rejetée : " + review["reason"] +
                              " Correct the rejected fact rather than repeating it. For every colour or material, "
                              "bind the attribute to the local source noun in the same phrase; never attach it "
                              "to a distant object. Keep each requested physical object as its own fact."))
                bundle = visual_planner._validate_result(raw, [SOURCE], TITLE)
                bundle["visual_plan_fingerprint"] = content.visual_plan_fingerprint(
                    [SOURCE], title=TITLE, niche="sujet", language="fr")
                control, plan = bundle["visual_controls"][0], bundle["visual_plans"][0]
                render._local_comfy_prompt("", "", "", "", plan, control)
                for detail in EXPECTED:
                    if detail not in plan:
                        raise ValueError("Réparation textuelle non satisfaite : " + detail)
                review = visual_planner.semantic_review(SOURCE, TITLE, control, plan)
                if not review["passed"]:
                    raise ValueError("Revue sémantique rejetée : " + review["reason"])
        except Exception as exc:
            save(FOLDER / "plan.json", {"source": SOURCE, "title": TITLE, "code_hash": code_hash(),
                 "planner_compiler_sha256": planner_compiler_hash(), "planner_model": visual_planner.PLANNER_MODEL,
                 "image_backend": "Qwen-Image-2.1 Turbo",
                 "semantic_review": {"passed": False, "reason": str(exc)}, **bundle})
            raise
        save(FOLDER / "plan.json", {"source": SOURCE, "title": TITLE, "code_hash": code_hash(),
              "planner_compiler_sha256": planner_compiler_hash(), "planner_model": visual_planner.PLANNER_MODEL,
              "image_backend": "Qwen-Image-2.1 Turbo",
              "semantic_review": review,
              **bundle})
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        return
    if args.test:
        before = code_hash()
        started = time.monotonic()
        command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                encoding="utf-8", errors="replace", env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
        (FOLDER / "final_tests.log").write_text(result.stdout, encoding="utf-8")
        after = code_hash()
        stamp = {"command": command, "returncode": result.returncode, "code_hash": after,
                 "unchanged_during_tests": before == after, "duration_seconds": round(time.monotonic() - started, 2),
                 "planner_version": content.VISUAL_PLANNER_VERSION,
                 "planner_compiler_sha256": planner_compiler_hash(),
                 "log": str(FOLDER / "final_tests.log")}
        save(FOLDER / "final_tests.json", stamp)
        print(result.stdout)
        if result.returncode or before != after:
            raise SystemExit(result.returncode or 1)
        return
    stamp = json.loads((FOLDER / "final_tests.json").read_text(encoding="utf-8"))
    planned = json.loads((FOLDER / "plan.json").read_text(encoding="utf-8"))
    if planned.get("semantic_review", {}).get("passed") is not True:
        raise RuntimeError("Le plan textuel doit réussir la revue sémantique avant toute image")
    if (stamp["returncode"] != 0 or not stamp["unchanged_during_tests"] or
            stamp["code_hash"] != code_hash() or planned["code_hash"] != code_hash() or
            stamp.get("planner_compiler_sha256") != planner_compiler_hash() or
            planned.get("planner_compiler_sha256") != planner_compiler_hash()):
        raise RuntimeError("Le plan et la suite complète doivent correspondre au code final inchangé")
    plan, control = planned["visual_plans"][0], planned["visual_controls"][0]
    prompt, negative = render._local_comfy_prompt("", "", "", "", plan, control)
    for detail in EXPECTED:
        if detail not in prompt:
            raise ValueError("Regression textuelle non satisfaite : " + detail)
    workflow = aiimg.build_comfy_payload(prompt, negative, CHECKPOINT, 720, 1280, SEED, visual_control=control)
    sampler = workflow["3"]["inputs"]
    if (set(workflow) != {"3", "4", "5", "6", "7", "8", "9", "10"} or
            workflow["7"]["inputs"]["prompt"] != plan or workflow["7"]["class_type"] != "TextEncodeQwenImage21" or
            (sampler["steps"], sampler["cfg"], sampler["sampler_name"], sampler["scheduler"]) != (8, 1.0, "euler", "simple")):
        raise RuntimeError("Le workflow rapide doit rester minimal et textuellement identique au plan")
    # Historical proof folders are immutable: do not even create a derived
    # report when their one-shot reservation already exists.
    if (FOLDER / "generation_once.json").exists():
        raise RuntimeError("Cette preuve a déjà été réservée ; aucune reprise automatique n'est autorisée")
    from core import local_resources, oneshot
    import requests
    from PIL import Image

    def preflight_check():
        queue = requests.get("http://127.0.0.1:8188/queue", timeout=5)
        queue.raise_for_status()
        state = queue.json()
        if state.get("queue_running") or state.get("queue_pending"):
            raise RuntimeError("Conflit ComfyUI externe détecté dans /queue")

    def submit(payload, client_id):
        return requests.post("http://127.0.0.1:8188/prompt",
                             json={"prompt": payload, "client_id": client_id}, timeout=20)

    def history(prompt_id):
        response = requests.get("http://127.0.0.1:8188/history/" + prompt_id, timeout=20)
        response.raise_for_status()
        return response.json()

    def download(image):
        response = requests.get("http://127.0.0.1:8188/view", params=image, timeout=20)
        response.raise_for_status()
        return response.content

    def validate_execution(executed):
        """Reject a technically completed job whose executed Qwen graph drifted."""
        try:
            qwen_nodes = (executed["4"]["inputs"]["unet_name"],
                          executed["5"]["inputs"]["clip_name"],
                          executed["6"]["inputs"]["vae_name"])
            executed_sampler = executed["3"]["inputs"]
            executed_size = (executed["8"]["inputs"]["width"], executed["8"]["inputs"]["height"])
            executed_prompt = executed["7"]["inputs"]["prompt"]
        except (KeyError, TypeError) as exc:
            raise ValueError("Graphe Qwen exécuté incomplet") from exc
        if (qwen_nodes != (aiimg.QWEN_TURBO_UNET, aiimg.QWEN_TURBO_CLIP, aiimg.QWEN_TURBO_VAE) or
                executed_prompt != plan or executed_sampler.get("seed") != SEED or
                (executed_sampler.get("steps"), executed_sampler.get("cfg"),
                 executed_sampler.get("sampler_name"), executed_sampler.get("scheduler")) != (8, 1.0, "euler", "simple") or
                executed_size != (720, 1280)):
            raise ValueError("Le graphe Qwen exécuté ne respecte pas le contrat one-shot")

    report = oneshot.run(
        FOLDER, seed=SEED,
        preflight={"mode": "comfy", "source": SOURCE, "title": TITLE,
                   "code_hash": code_hash(), "planner_compiler_sha256": planner_compiler_hash(),
                   "planner_version": content.VISUAL_PLANNER_VERSION,
                   "visual_plan_fingerprint": planned["visual_plan_fingerprint"], "final_tests": stamp},
        workflow=workflow, preflight_check=preflight_check, submit=submit, history=history, download=download,
        image_size=lambda path: list(Image.open(path).size),
        expected_image_size=(720, 1280), validate_execution=validate_execution,
        render_phase=local_resources.render_phase(
            comfy_url="http://127.0.0.1:8188",
            required_components=(aiimg.QWEN_TURBO_UNET, aiimg.QWEN_TURBO_CLIP, aiimg.QWEN_TURBO_VAE),
        ),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
