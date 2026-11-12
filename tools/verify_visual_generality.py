"""Offline phase-5 verification across durations and source densities."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import content, visual_corpus


DENSITY = ROOT / "outputs" / "text_diagnostics" / "kheops_visual_density_2026-11-10.json"
OUT = ROOT / "outputs" / "kheops_campaign_2026-11-10" / "generality_report.json"


def select_from_corpus(title, text, duration, *, generic_terms=None):
    corpus = [{"title": title, "text": text}]
    anchors = visual_corpus.extract_visual_anchors(corpus)
    hook = f"{title} : les éléments concrets"
    cta = f"Retenez les éléments concrets de {title}."
    wanted = content.target_words(duration, "fr")
    groups = content.short_scenes(
        [text], max_words=max(7, min(20, wanted // 6)), grouped=True)
    groups = content._coverage_guided_groups(
        groups, anchors, base_words=content.word_count(hook) + content.word_count(cta),
        wanted=wanted, generic_terms=generic_terms,
        minimum_groups=max(0, math.ceil(duration / 7.0) - 2),
        maximum_groups=max(0, int(math.floor(duration / 4.0 + .5)) - 2))
    body, words = [], content.word_count(hook) + content.word_count(cta)
    for group in groups:
        count = sum(content.word_count(part) for part in group)
        if words + count > wanted * 1.15:
            continue
        body.extend(group)
        words += count
        if words >= wanted * .97 and len(body) + 2 >= math.ceil(duration / 7.0):
            break
    scenes = [hook, *body, cta]
    if generic_terms is None:
        initial = visual_corpus.distribute_visual_anchors(scenes, anchors)
        generic_terms = initial["generic_terms_excluded_as_sole_signal"]
    distribution = visual_corpus.distribute_visual_anchors(
        scenes, anchors, visual_briefs=content.visual_briefs_for_scenes(scenes),
        generic_terms=generic_terms)
    budget = visual_corpus.visual_budget(
        duration, distribution["distinct_anchors_used"], scene_count=len(scenes),
        scenes_without_anchor=distribution["scenes_without_anchor"],
        visually_distinct_subjects=distribution["visually_distinct_subjects"])
    schedule = None
    error = None
    try:
        schedule = visual_corpus.plan_image_schedule(
            scenes, distribution, duration_seconds=duration,
            corpus_anchors=anchors)
    except ValueError as exc:
        error = str(exc)
    effective_verdict = budget["verdict"] if schedule and schedule["selection_accepted"] else "insufficient"
    if schedule and schedule["selection_accepted"]:
        sustainable = budget["sustainable_duration_seconds"]
    else:
        unique_capacity = len([anchor for anchor in anchors if anchor.get("scope") == "principal"])
        theoretical = min(float(duration), math.floor(unique_capacity / .75) * 4.0)
        supported = [value for value in content.DURATION_OPTIONS if value and value <= theoretical]
        sustainable = float(max(supported)) if supported else 0.0
    return {
        "duration_seconds": duration,
        "scene_count": len(scenes),
        "images_planned": budget["images_planned"],
        "verdict": effective_verdict,
        "scenes_without_anchor_rate": distribution["scenes_without_anchor_rate"],
        "sustainable_duration_seconds": sustainable,
        "schedule_accepted": bool(schedule and schedule["selection_accepted"]),
        "schedule_error": error,
        "minimum_image_duration_seconds": schedule.get("minimum_image_duration_seconds") if schedule else None,
        "maximum_image_duration_seconds": schedule.get("maximum_image_duration_seconds") if schedule else None,
        "reframe_rate": schedule.get("reframe_rate") if schedule else None,
        "maximum_anchor_scene_reuse": schedule.get("maximum_anchor_scene_reuse") if schedule else None,
    }


def measured_case(name, source_kind, scenes, corpus, duration):
    anchors = visual_corpus.extract_visual_anchors(corpus)
    distribution = visual_corpus.distribute_visual_anchors(scenes, anchors)
    budget = visual_corpus.visual_budget(
        duration, distribution["distinct_anchors_used"], scene_count=len(scenes),
        scenes_without_anchor=distribution["scenes_without_anchor"],
        visually_distinct_subjects=distribution["visually_distinct_subjects"])
    refused = not anchors or distribution["scenes_without_anchor_rate"] > .30
    return {
        "name": name, "source_kind": source_kind,
        "scene_count": len(scenes), "images_planned": budget["images_planned"],
        "verdict": budget["verdict"],
        "scenes_without_anchor_rate": distribution["scenes_without_anchor_rate"],
        "sustainable_duration_seconds": budget["sustainable_duration_seconds"],
        "refused": refused,
    }


def main():
    density = json.loads(DENSITY.read_text(encoding="utf-8"))
    source = density["visual_corpus"][0]
    fixed = density["coverage_guided_selection"]["generic_terms_used_for_both"]
    durations = [select_from_corpus(source["title"], source["text"], duration,
                                    generic_terms=fixed)
                 for duration in (30, 90, 180, 300)]
    medium = measured_case(
        "local_medium_density", "local",
        ["Une statue se dresse devant le temple.", "Le pont franchit la vallée.",
         "La théorie reste discutée.", "Cette période change tout.",
         "Le débat demeure ouvert.", "Retenez cette histoire."],
        [{"title": "Site local", "text": "Une statue se dresse devant le temple. Le pont franchit la vallée."}],
        45)
    short_web = measured_case(
        "short_concrete_web", "web",
        ["La statue garde l'entrée du temple.", "Le sarcophage repose dans la chambre funéraire.",
         "La grande galerie mène au couloir ascendant."],
        [{"title": "Fouille", "text": ("La statue garde l'entrée du temple. "
          "Le sarcophage repose dans la chambre funéraire. "
          "La grande galerie mène au couloir ascendant.")}], 30)
    abstract = measured_case(
        "abstract_source", "local",
        ["Cette idée bouleverse notre manière de penser.",
         "Les théories restent incertaines et controversées."],
        [{"title": "Idées", "text": ("Cette idée bouleverse notre manière de penser. "
          "Les théories restent incertaines et controversées.")}], 30)
    accepted = (
        [item["images_planned"] for item in durations] == [8, 23, 45, 75]
        and all(item["schedule_accepted"] for item in durations[:3])
        and durations[3]["verdict"] == "insufficient"
        and durations[3]["sustainable_duration_seconds"] < 300
        and medium["verdict"] in {"thin", "insufficient"}
        and medium["sustainable_duration_seconds"] < 45
        and short_web["verdict"] == "sufficient"
        and abstract["refused"] and abstract["verdict"] == "insufficient"
    )
    report = {"report_kind": "visual_generality", "same_source_durations": durations,
              "local_medium": medium, "short_concrete_web": short_web,
              "abstract": abstract, "accepted": accepted,
              "verification": {"image_requests": 0, "prompt_posts": 0, "images_generated": 0}}
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
