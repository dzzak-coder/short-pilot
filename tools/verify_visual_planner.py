"""Text-only live Ollama checks; does not request a ComfyUI image."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import content


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    scenes = [
        "Un minuteur rouge sur un bureau en bois, à côté d’un planning fermé, lumière du matin",
        "Un paysage de fjord norvégien enneigé au crépuscule, sans humain",
        "Un axolotl rose nage entre les rochers dans une rivière",
        "Deux mains pétrissent une pâte sur une table en marbre",
        "Une astronome rousse observe Saturne depuis un observatoire la nuit",
        "La procrastination coûte du temps.",
        "Abonne-toi pour la suite.",
    ]
    cases = []
    for scene in scenes[:-1]:
        bundle = content.visual_plan_bundle([scene], title=scene, language="fr", niche="sujet")
        cases.append({"scenes": [scene], **bundle})
    cases.append({"scenes": [scenes[0], scenes[-1]], **content.visual_plan_bundle(
        [scenes[0], scenes[-1]], title=scenes[0], language="fr", niche="sujet")})
    folder = Path(__file__).resolve().parents[1] / "outputs" / "timer_universal_validation"
    folder.mkdir(exist_ok=True)
    path = folder / "live_planner_cases.json"
    path.write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    for i, case in enumerate(cases, 1):
        for plan, control in zip(case["visual_plans"], case["visual_controls"]):
            print(i, control.get("human_mode"), plan or control.get("planning_error"))
    print(path)
    if not all(plan for case in cases for plan in case["visual_plans"]):
        raise RuntimeError("Au moins un plan doit être révisé; aucune image demandée")


if __name__ == "__main__":
    main()
