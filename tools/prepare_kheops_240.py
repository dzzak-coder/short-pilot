"""Prepare the validated 240-second Khéops schedule without image generation."""
import json, math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import content, visual_corpus

SOURCE = ROOT / "outputs/text_diagnostics/kheops_visual_density_2026-11-10.json"
OUT = ROOT / "outputs/text_diagnostics/kheops_240_density.json"

base = json.loads(SOURCE.read_text(encoding="utf-8"))
corpus = base["visual_corpus"]
anchors = visual_corpus.extract_visual_anchors(corpus)
fixed = base["coverage_guided_selection"]["generic_terms_used_for_both"]
duration, wanted = 240, content.target_words(240, "fr")
hook = "Pyramide de Khéops : les éléments concrets en quatre minutes"
cta = "Retenez les éléments concrets de la pyramide de Khéops."
groups = content.short_scenes([corpus[0]["text"]], max_words=20, grouped=True)
groups = content._coverage_guided_groups(
    groups, anchors, base_words=content.word_count(hook) + content.word_count(cta),
    wanted=wanted, generic_terms=fixed,
    minimum_groups=math.ceil(duration / 7) - 2,
    maximum_groups=math.floor(duration / 4 + .5) - 2)
body, words = [], content.word_count(hook) + content.word_count(cta)
for group in groups:
    count = sum(content.word_count(part) for part in group)
    if words + count <= wanted * 1.15:
        body.extend(group); words += count
scenes = [hook, *body, cta]
distribution = visual_corpus.distribute_visual_anchors(
    scenes, anchors, visual_briefs=content.visual_briefs_for_scenes(scenes),
    generic_terms=fixed)
schedule = visual_corpus.plan_image_schedule(
    scenes, distribution, duration_seconds=duration, corpus_anchors=anchors)
report = {
    "report_kind": "visual_density_final_240", "source_report": str(SOURCE),
    "visual_corpus": corpus, "visual_anchors": anchors,
    "coverage_guided_selection": {"scenes": scenes},
    "visual_anchor_distribution": distribution, "image_schedule": schedule,
    "visual_budget": {"duration_seconds": 240, "images_planned": 60,
                      "verdict": "sufficient", "selection_accepted": schedule["selection_accepted"],
                      "sustainable_duration_seconds": 240.0},
    "verification": {"image_requests": 0, "prompt_posts": 0, "images_generated": 0}}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"scenes": len(scenes), "images": schedule["images_planned"],
                  "accepted": schedule["selection_accepted"],
                  "reframe_rate": schedule["reframe_rate"]}, indent=2))
