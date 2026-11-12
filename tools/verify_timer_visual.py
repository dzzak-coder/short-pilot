"""Real local semantic regression; never enqueues rendering or publishing jobs."""
import json
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import aiimg, content, render


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=70001)
    args = parser.parse_args()
    source = "Un minuteur rouge sur un bureau en bois, à côté d’un planning fermé, lumière du matin"
    output = Path(__file__).resolve().parents[1] / "outputs" / "timer_universal_validation"
    output.mkdir(exist_ok=True)
    script = content.generate_script(niche="sujet", lang="fr", topic=source, source="local")
    control = script["visual_controls"][0]
    plan = script["visual_plans"][0]
    prompt, negative = render._local_comfy_prompt(source, source, "sujet", "auto", plan, control)
    for detail in ("red kitchen timer", "wooden desk", "closed planner", "morning sunlight"):
        assert detail in prompt, detail
    report = {"index": 1, "narration": source, "visual_plan": plan, "visual_control": control}
    image = aiimg.image_for_scene_ai(
        prompt, str(output), seed=args.seed, server="http://127.0.0.1:8188",
        ckpt=aiimg.QWEN_TURBO_UNET, human_mode=control["human_mode"],
        visual_control=control, negative_prompt=negative, report=report, log=print)
    if not image:
        raise RuntimeError("La génération réelle ou la vérification du prompt exécuté a échoué")
    assert report["executed_positive_prompt"] == plan == report["positive_prompt"]
    for detail in ("red kitchen timer", "wooden desk", "closed planner", "morning sunlight"):
        assert detail in plan
    payload = {"mode": "comfy", "seed_policy": "70000 + scene index", "script": script,
               "scenes": [report], "visual_acceptance": "requires image inspection"}
    path = output / f"timer_{args.seed}_corrected.visual.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(path))
    print(str(image))


if __name__ == "__main__":
    main()
