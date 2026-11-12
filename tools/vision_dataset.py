"""Read-only image inventory and human annotation / evaluation sealing.

No detector, network call, image transformation, or source-image write lives here.
Annotations are edited as JSON by a human; `seal` validates and hashes them.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "outputs"
DATASET = ROOT / "data" / "vision_chantier3"
EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
FACT_TYPES = {"object", "state", "attribute", "relation"}
STATUSES = {"present", "absent", "indeterminate"}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def linked_plan(path):
    for report in sorted(path.parent.glob("*.visual.json")):
        data = json.loads(report.read_text(encoding="utf-8"))
        for scene in data.get("scenes", []):
            if Path(scene.get("image") or "").name == path.name:
                return scene.get("narration"), (scene.get("visual_control") or {}).get("source_facts") or [], str(report.relative_to(ROOT))
    plan = path.parent / "plan.json"
    if plan.is_file() and path.name.startswith("comfy_"):
        data = json.loads(plan.read_text(encoding="utf-8"))
        return data.get("source"), (data.get("visual_controls") or [{}])[0].get("source_facts") or [], str(plan.relative_to(ROOT))
    return None, [], None


def inventory():
    rows = []
    for path in sorted(p for p in IMAGES.rglob("*") if p.suffix.lower() in EXTENSIONS):
        source, facts, plan = linked_plan(path)
        rows.append({"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(path),
                     "source": source, "source_group": hashlib.sha256(source.encode("utf-8")).hexdigest() if source else None,
                     "plan": plan, "facts": facts})
    return rows


def fact_type(fact):
    category = fact.get("category")
    return ("object" if category in {"subject", "secondary"} else
            "state" if category == "state" else "relation" if category == "relation" else "attribute")


def make_template(row):
    return {"schema_version": 1, "image": row["path"], "image_sha256": row["sha256"],
            "source": row["source"], "source_group": row["source_group"], "plan": row["plan"],
            "split": "unassigned", "annotator": "", "annotated_at": "", "signature": "",
            "facts": [{"id": f"f{i + 1}", "type": fact_type(f), "category": f.get("category"),
                       "entity": f.get("entity", ""), "source_span": f.get("source_span", ""),
                       "requested": f.get("english", ""), "required": False,
                       "required_reviewed": False, "status": "indeterminate", "bbox_xyxy": None,
                       "quality": "unassessed", "reason": "", "evidence": ""}
                      for i, f in enumerate(row["facts"])]}


def initialize(rows):
    target = DATASET / "annotations"
    target.mkdir(parents=True, exist_ok=True)
    for row in rows:
        path = target / (row["sha256"] + ".json")
        if not path.exists():
            path.write_text(json.dumps(make_template(row), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Annotation templates: {len(list(target.glob('*.json')))}; existing files preserved")


def seal():
    target = DATASET / "evaluation.seal.json"
    if target.exists():
        raise ValueError("Evaluation already sealed; never overwrite its manifest")
    files = sorted((DATASET / "annotations").glob("*.json"))
    if not files:
        raise ValueError("No annotations")
    entries, groups = [], defaultdict(set)
    for file in files:
        item = json.loads(file.read_text(encoding="utf-8"))
        split = item.get("split")
        if split not in {"tuning", "evaluation", "unassigned"}:
            raise ValueError(f"Invalid split: {file}")
        if split == "unassigned":
            continue
        image = (ROOT / item["image"]).resolve()
        if not image.is_relative_to(IMAGES.resolve()) or sha256(image) != item["image_sha256"]:
            raise ValueError(f"Image path or hash mismatch: {file}")
        group = item.get("source_group")
        if not group:
            raise ValueError(f"Source group missing: {file}")
        groups[group].add(split)
        if split == "evaluation":
            if not all(isinstance(item.get(k), str) and item[k] for k in ("annotator", "annotated_at", "signature")):
                raise ValueError(f"Human annotation not signed: {file}")
            if not item.get("facts"):
                raise ValueError(f"No facts: {file}")
            for fact in item["facts"]:
                if (fact.get("type") not in FACT_TYPES or fact.get("status") not in STATUSES or
                        type(fact.get("required")) is not bool or fact.get("required_reviewed") is not True or
                        not fact.get("reason") or fact.get("quality") == "unassessed"):
                    raise ValueError(f"Incomplete fact: {file} / {fact.get('id')}")
                if fact["status"] == "absent" and not fact.get("evidence"):
                    raise ValueError(f"Contradiction requires positive evidence: {file}")
            entries.append({"image": item["image"], "image_sha256": item["image_sha256"],
                            "annotation": str(file.relative_to(ROOT)).replace("\\", "/"),
                            "annotation_sha256": sha256(file), "source_group": group})
    if not entries or not any("tuning" in splits for splits in groups.values()):
        raise ValueError("Both tuning and fully annotated evaluation images are required")
    if any(len(splits) > 1 for splits in groups.values()):
        raise ValueError("A source family cannot cross the tuning/evaluation boundary")
    tuning_hashes = {json.loads(p.read_text(encoding="utf-8"))["image_sha256"] for p in files
                     if json.loads(p.read_text(encoding="utf-8")).get("split") == "tuning"}
    if any(entry["image_sha256"] in tuning_hashes for entry in entries):
        raise ValueError("Duplicate image across splits")
    manifest = {"schema_version": 1, "entries": entries, "evaluation_count": len(entries),
                "annotation_rule": "Human signed; never inspect evaluation during detector development"}
    with target.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    print(f"Sealed {len(entries)} evaluation images: {target}; SHA-256 {sha256(target)}")


def verify_seal():
    target = DATASET / "evaluation.seal.json"
    manifest = json.loads(target.read_text(encoding="utf-8"))
    for entry in manifest["entries"]:
        if sha256(ROOT / entry["image"]) != entry["image_sha256"]:
            raise ValueError(f"Sealed image changed: {entry['image']}")
        if sha256(ROOT / entry["annotation"]) != entry["annotation_sha256"]:
            raise ValueError(f"Sealed annotation changed: {entry['annotation']}")
    print(f"Seal verified: {len(manifest['entries'])} images; manifest SHA-256 {sha256(target)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inventory", "init", "seal", "verify-seal"))
    action = parser.parse_args().action
    if action == "seal":
        seal()
        return
    if action == "verify-seal":
        verify_seal()
        return
    rows = inventory()
    distinct = {row["sha256"]: row for row in rows}
    render = [row for row in distinct.values() if row["path"].endswith(".png") and Path(row["path"]).name.startswith("comfy_")]
    counts = Counter(fact_type(f) for row in render for f in row["facts"])
    print(json.dumps({"files": len(rows), "distinct_sha256": len(distinct),
                      "linked_render_images": len(render), "structured_facts": dict(counts),
                      "render_source_groups": len({row["source_group"] for row in render})}, ensure_ascii=False))
    if action == "init":
        initialize(list(distinct.values()))


if __name__ == "__main__":
    main()
