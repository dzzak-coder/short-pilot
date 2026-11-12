"""Validate every campaign gate and write one final non-destructive report."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "outputs" / "kheops_campaign_2026-11-10"
DENSITY_PATH = ROOT / "outputs" / "text_diagnostics" / "kheops_visual_density_2026-11-10.json"
PLANS_PATH = ROOT / "outputs" / "text_diagnostics" / "kheops_image_plans_2026-11-10.json"
GENERALITY_PATH = FOLDER / "generality_report.json"
ASSEMBLY_PATH = FOLDER / "assembly_report.json"
LEGACY_MARKER = ROOT / "outputs" / "qwen_turbo_visual_validation" / "generation_once.json"
LEGACY_SHA = "bd5651e3f501fc42702945ced55d26605a8cbefa8a1b2253e46c0757c555ab1b"
OUT = FOLDER / "campaign_final_report.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    density, plans = load(DENSITY_PATH), load(PLANS_PATH)
    generality, assembly = load(GENERALITY_PATH), load(ASSEMBLY_PATH)
    execution_path = next(FOLDER.glob("execution_report.*.json"))
    execution, postconditions = load(execution_path), load(FOLDER / "postconditions.json")
    budget, schedule = density["visual_budget"], density["image_schedule"]
    phase0 = {
        "accepted": (budget["verdict"] == "sufficient"
                     and budget["scene_coverage"]["scenes_without_anchor_rate"] == .1053
                     and all(key in budget for key in (
                         "selection_accepted", "seconds_per_image", "max_seconds_per_image",
                         "scene_count_final", "images_planned"))),
        "criterion": "Verdict unique après sélection et clés de décision présentes",
        "verdict": budget["verdict"],
    }
    phase1 = {
        "accepted": (schedule["selection_accepted"] and schedule["images_planned"] == 23
                     and schedule["maximum_image_duration_seconds"] <= 7
                     and schedule["reframe_rate"] <= .25
                     and schedule["maximum_anchor_scene_reuse"] <= 3
                     and len(schedule["images"]) == 23),
        "criterion": "23 images, 3–7 s, recadrage ≤25 %, ancrage ≤3 scènes",
        "images_planned": schedule["images_planned"],
        "reframe_rate": schedule["reframe_rate"],
    }
    phase2 = {
        "accepted": (plans["accepted"] and plans["plans_count"] == 23
                     and plans["nonempty_plans"] == 23 and plans["distinct_prompt_rate"] >= .60
                     and all(item.get("anchor_id") for item in plans["image_plans"])),
        "criterion": "23 plans non vides, ≥60 % distincts, anchor_id présent",
        "distinct_prompt_rate": plans["distinct_prompt_rate"],
    }
    phase3 = {
        "accepted": (execution["execution_status"] == "succeeded"
                     and execution["prompt_post_count"] == 1 and execution["image_count"] == 23
                     and execution["visual_acceptance"]["accepted"] is None
                     and all(item.get("image_sha256") for item in execution["images"])
                     and postconditions["legacy_marker_unchanged"]
                     and sha(LEGACY_MARKER) == LEGACY_SHA),
        "criterion": "1 POST, 23 SHA-256, accepted null, marqueur historique intact",
        "prompt_id": execution["prompt_id"],
        "prompt_post_count": execution["prompt_post_count"],
    }
    phase4 = {
        "accepted": bool(assembly["accepted"]),
        "criterion": "MP4 720×1280 H.264/AAC, ±5 %, images 3–7 s, audio synchronisé",
        "duration_seconds": assembly["duration_seconds"],
        "video_sha256": assembly["video_sha256"],
    }
    phase5 = {
        "accepted": bool(generality["accepted"]),
        "criterion": "Durées multiples cohérentes et source abstraite refusée",
        "five_minute_sustainable_duration_seconds":
            generality["same_source_durations"][3]["sustainable_duration_seconds"],
    }
    phases = {"phase_0": phase0, "phase_1": phase1, "phase_2": phase2,
              "phase_3": phase3, "phase_4": phase4, "phase_5": phase5}
    final_video = FOLDER / assembly["video"]
    phase6 = {
        "accepted": (all(item["accepted"] for item in phases.values())
                     and final_video.is_file()
                     and assembly["duration_seconds"] == budget["sustainable_duration_seconds"]),
        "criterion": "Un short réel à la durée maximale soutenable annoncée, sans publication",
        "source": "Pyramide de Khéops",
        "duration_seconds": assembly["duration_seconds"],
        "sustainable_duration_seconds": budget["sustainable_duration_seconds"],
        "video": str(final_video.relative_to(ROOT)),
        "publication": None,
    }
    phases["phase_6"] = phase6
    report = {
        "report_kind": "shortpilot_campaign_final",
        "accepted": all(item["accepted"] for item in phases.values()),
        "phases": phases,
        "deliverables": {
            "video": str(final_video.relative_to(ROOT)),
            "video_sha256": sha(final_video),
            "density_report": str(DENSITY_PATH.relative_to(ROOT)),
            "prompt_report": str(PLANS_PATH.relative_to(ROOT)),
            "execution_report": str(execution_path.relative_to(ROOT)),
            "assembly_report": str(ASSEMBLY_PATH.relative_to(ROOT)),
            "generality_report": str(GENERALITY_PATH.relative_to(ROOT)),
        },
        "safety": {"published": False, "artifacts_deleted": False,
                   "legacy_seed_70001_marker_sha256": sha(LEGACY_MARKER),
                   "legacy_marker_unchanged": sha(LEGACY_MARKER) == LEGACY_SHA},
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
