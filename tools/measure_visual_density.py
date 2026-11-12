"""Offline visual-density report.  No model, network, image, or POST request."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core import content, visual_corpus


CONTINUITY_SUFFIX = ", clean negative space for captions"


def _subject_key(plan: str) -> str:
    value = " ".join(str(plan or "").split())
    while value.endswith(CONTINUITY_SUFFIX):
        value = value[:-len(CONTINUITY_SUFFIX)].rstrip()
    return value


def _load_primary_article(report: dict, cache_path: Path) -> dict:
    language = report.get("language") or "fr"
    sources = report.get("sources") or []
    if not sources:
        raise SystemExit("Le rapport ne déclare aucune source")
    primary = sources[0]
    key = f"article:{language}:{primary.get('title', '')}"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    entry = cache.get(key)
    if not entry or not entry.get("titles"):
        raise SystemExit(f"Article complet absent du cache : {key}")
    article = json.loads(entry["titles"][0])
    article["url"] = primary.get("url") or article.get("url", "")
    return article


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--cache", default=str(REPO / "data" / "wiki_cache.json"))
    parser.add_argument("--seconds-per-image", type=float, default=4.0)
    args = parser.parse_args(argv)

    source_path = Path(args.report)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    article = _load_primary_article(source, Path(args.cache))
    corpus = [{"title": article.get("title", ""), "url": article.get("url", ""),
               "text": article.get("text", "")}]
    anchors = visual_corpus.extract_visual_anchors(corpus)
    principal_anchors = [anchor for anchor in anchors if anchor.get("scope") == "principal"]
    contextual_anchors = [anchor for anchor in anchors if anchor.get("scope") == "contextual"]
    before = len({_subject_key(plan) for plan in source.get("visual_plans") or []
                  if _subject_key(plan)})
    corpus_words = content.word_count(article.get("text", ""))
    briefs = source.get("visual_briefs") or content.visual_briefs_for_scenes(
        source.get("scenes") or [])
    distribution = visual_corpus.distribute_visual_anchors(
        source.get("scenes") or [], anchors, visual_briefs=briefs)
    fixed_generic_terms = distribution["generic_terms_excluded_as_sole_signal"]
    assigned_distinct = distribution["distinct_anchors_used"]
    source_scenes = source.get("scenes") or []
    hook = str(source.get("hook") or (source_scenes[0] if source_scenes else ""))
    cta = str(source.get("cta") or (source_scenes[-1] if source_scenes else ""))
    wanted = content.target_words(
        source.get("target_seconds") or source.get("estimated_seconds") or 0,
        source.get("language") or "fr")
    groups = content.short_scenes(
        [*source_scenes[1:-1], article.get("text", "")],
        max_words=max(7, min(20, wanted // 6)), grouped=True)
    groups = content._coverage_guided_groups(
        groups, anchors,
        base_words=content.word_count(hook) + content.word_count(cta), wanted=wanted,
        generic_terms=fixed_generic_terms,
        minimum_groups=max(0, math.ceil(float(
            source.get("target_seconds") or source.get("estimated_seconds") or 0) / 7.0) - 2))
    guided_body, guided_words = [], content.word_count(hook) + content.word_count(cta)
    for group in groups:
        count = sum(content.word_count(part) for part in group)
        if guided_words + count > wanted * 1.15:
            continue
        guided_body.extend(group)
        guided_words += count
        if guided_words >= wanted * .97:
            break
    guided_scenes = [hook, *guided_body, cta]
    guided_distribution = visual_corpus.distribute_visual_anchors(
        guided_scenes, anchors,
        visual_briefs=content.visual_briefs_for_scenes(guided_scenes),
        generic_terms=fixed_generic_terms)
    target_duration = float(
        source.get("target_seconds") or source.get("estimated_seconds") or 0)
    duration_per_image = (target_duration / len(guided_scenes) if guided_scenes else 0.0)
    selection_accepted = bool(guided_scenes and duration_per_image <= 7.0)
    image_schedule = visual_corpus.plan_image_schedule(
        guided_scenes, guided_distribution,
        duration_seconds=target_duration,
        seconds_per_image=args.seconds_per_image,
        max_seconds_per_image=7.0,
        max_anchor_scene_reuse=3,
        max_reframe_rate=.25,
        corpus_anchors=anchors)
    selection_accepted = selection_accepted and image_schedule["selection_accepted"]
    before_summary = {
        "scene_count": distribution["scene_count"],
        "scenes_without_anchor": distribution["scenes_without_anchor"],
        "scenes_without_anchor_rate": distribution["scenes_without_anchor_rate"],
        "distinct_anchors_used": distribution["distinct_anchors_used"],
        "visually_distinct_subjects": distribution["visually_distinct_subjects"],
    }
    final_assigned_distinct = guided_distribution["distinct_anchors_used"]
    budget = visual_corpus.visual_budget(
        source.get("target_seconds") or source.get("estimated_seconds") or 0,
        final_assigned_distinct, seconds_per_image=args.seconds_per_image,
        corpus_word_count=corpus_words, anchors_before=before,
        scene_count=guided_distribution["scene_count"],
        scenes_without_anchor=guided_distribution["scenes_without_anchor"],
        visually_distinct_subjects=guided_distribution["visually_distinct_subjects"])
    budget.update({
        "selection_accepted": selection_accepted,
        "seconds_per_image": float(args.seconds_per_image),
        "max_seconds_per_image": 7.0,
        "scene_count_final": guided_distribution["scene_count"],
        "images_planned": int(math.floor(target_duration / args.seconds_per_image + .5)),
    })
    report = {
        "report_kind": "visual_density",
        "source_report": str(source_path),
        "source_report_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "visual_corpus": corpus,
        "visual_anchors": anchors,
        "visual_anchor_counts": {
            "principal": len(principal_anchors),
            "contextual": len(contextual_anchors),
            "total_retained": len(anchors),
            "distinct_assigned_final": final_assigned_distinct,
        },
        "before": {
            **before_summary,
            "visual_anchor_distribution": distribution,
        },
        "visual_anchor_distribution": guided_distribution,
        "image_schedule": image_schedule,
        "coverage_guided_selection": {
            "primary_decision_metric": "scenes_without_anchor_rate",
            "anchor_and_subject_counts_are_advisory": True,
            "before": {
                "scene_count": distribution["scene_count"],
                "scenes_without_anchor": distribution["scenes_without_anchor"],
                "scenes_without_anchor_rate": distribution["scenes_without_anchor_rate"],
            },
            "after": {
                "scene_count": guided_distribution["scene_count"],
                "scenes_without_anchor": guided_distribution["scenes_without_anchor"],
                "scenes_without_anchor_rate": guided_distribution["scenes_without_anchor_rate"],
                "visually_distinct_subjects": guided_distribution["visually_distinct_subjects"],
            },
            "orphan_scenes_reduced_by": max(
                0, distribution["scenes_without_anchor"]
                - guided_distribution["scenes_without_anchor"]),
            "generic_terms_used_for_both": fixed_generic_terms,
            "duration_per_image_seconds": round(duration_per_image, 2),
            "max_duration_per_image_seconds": 7.0,
            "accepted": selection_accepted,
            "rejection_reason": (None if selection_accepted else
                                 "La sélection dépasserait 7 s par image."),
            "scenes": guided_scenes,
            "visual_anchor_distribution": guided_distribution,
        },
        "visual_budget": budget,
        "verification": {
            "mode": "offline",
            "network_requests": 0,
            "text_posts": 0,
            "prompt_posts": 0,
            "images_generated": 0,
        },
    }
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "report": str(target),
        "images_needed": budget["images_needed"],
        "anchors_before": before,
        "anchors_extracted": len(principal_anchors),
        "anchors_after": final_assigned_distinct,
        "contextual_anchors": len(contextual_anchors),
        "anchors_required": budget["anchors_required"],
        "verdict": budget["verdict"],
        "corpus_word_count": corpus_words,
        "distribution": {
            "scenes_with_0_anchors": guided_distribution["scenes_with_0_anchors"],
            "scenes_with_1_anchor": guided_distribution["scenes_with_1_anchor"],
            "scenes_with_2plus_anchors": guided_distribution["scenes_with_2plus_anchors"],
            "orphan_scene_indices": guided_distribution["orphan_scene_indices"],
            "distinct_anchors_used": final_assigned_distinct,
            "visually_distinct_subjects": guided_distribution["visually_distinct_subjects"],
        },
        "sustainable_duration_seconds": budget["sustainable_duration_seconds"],
        "coverage_guided_orphans_after": guided_distribution["scenes_without_anchor"],
        "coverage_guided_scene_count_after": guided_distribution["scene_count"],
        "coverage_guided_duration_per_scene_seconds": round(duration_per_image, 2),
        "coverage_guided_selection_accepted": selection_accepted,
        "images_planned": image_schedule["images_planned"],
        "minimum_image_duration_seconds": image_schedule["minimum_image_duration_seconds"],
        "maximum_image_duration_seconds": image_schedule["maximum_image_duration_seconds"],
        "reframe_rate": image_schedule["reframe_rate"],
        "maximum_anchor_scene_reuse": image_schedule["maximum_anchor_scene_reuse"],
        "prompt_posts": 0,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
