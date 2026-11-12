"""Plan one validated prompt per scheduled image. No ComfyUI request."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core import content


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--density-report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    density_path = Path(args.density_report)
    density = json.loads(density_path.read_text(encoding="utf-8"))
    source_path = Path(density["source_report"])
    if not source_path.is_absolute():
        source_path = REPO / source_path
    source = json.loads(source_path.read_text(encoding="utf-8"))
    scenes = density["coverage_guided_selection"]["scenes"]
    assignments = density["image_schedule"]["images"]
    bundle = content.visual_plan_bundle(
        scenes,
        title=source.get("title", ""), niche=source.get("niche", ""),
        language=source.get("language", ""),
        image_assignments=assignments,
        visual_anchors=density.get("visual_anchors") or [],
    )
    prompts = bundle["visual_plans"]
    distinct_count = len(set(prompts))
    report = {
        "report_kind": "image_prompt_plan",
        "density_report": str(density_path),
        "images_planned": len(assignments),
        "plans_count": len(prompts),
        "nonempty_plans": sum(bool(prompt.strip()) for prompt in prompts),
        "distinct_prompts": distinct_count,
        "distinct_prompt_rate": round(distinct_count / len(prompts), 4) if prompts else 0.0,
        "accepted": (
            len(prompts) == len(assignments)
            and all(prompt.strip() for prompt in prompts)
            and distinct_count / len(prompts) >= .60
        ) if prompts else False,
        "image_plans": bundle["image_plans"],
        "verification": {
            "image_requests": 0,
            "prompt_posts": 0,
            "images_generated": 0,
        },
    }
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "plans_count", "nonempty_plans", "distinct_prompts",
        "distinct_prompt_rate", "accepted")}, ensure_ascii=False, indent=2))
    return 0 if report["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
