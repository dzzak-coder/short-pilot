"""Sonde de planification bornée — quelques scènes, aucun rendu.

La sonde n'autorise que les POST ``/api/chat``. Tout POST ``/prompt`` est
bloqué et compté avant envoi. Les résultats valides sont conservés dans le
rapport afin qu'une relance ne repaie pas les scènes déjà réussies.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import sys
import time
from pathlib import Path

CONTINUITY_SUFFIX = ", clean negative space for captions"


def _visual_subject_key(plan: str) -> str:
    """Normalize continuity copies to the visual subject of their anchor."""
    normalized = " ".join(str(plan or "").split())
    suffix = " ".join(CONTINUITY_SUFFIX.split())
    while normalized.endswith(suffix):
        normalized = normalized[:-len(suffix)].rstrip()
    return normalized


def _resolve_modules():
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from core import content, local_resources
    return content, local_resources


def _install_post_guard(requests_module):
    """Autorise uniquement /api/chat et interdit /prompt avant tout envoi."""
    original = requests_module.post
    calls = {"text": 0, "prompt_blocked": 0, "other_blocked": 0}

    def guarded(url, *args, **kwargs):
        target = str(url).rstrip("/")
        if target.endswith("/prompt"):
            calls["prompt_blocked"] += 1
            raise AssertionError("POST /prompt interdit par la sonde")
        if not target.endswith("/api/chat"):
            calls["other_blocked"] += 1
            raise AssertionError(f"POST non textuel interdit par la sonde : {target}")
        calls["text"] += 1
        return original(url, *args, **kwargs)

    requests_module.post = guarded
    return calls


def _install_chat_only_phase(resources):
    """Garde le verrou ShortPilot sans POST /free ni /api/generate.

    Le planificateur envoie ``keep_alive: 0`` à /api/chat, donc le modèle est
    déchargé par Ollama après chaque réponse sans requête POST de nettoyage.
    """
    original = resources.text_phase

    @contextmanager
    def chat_only_phase(*, model=None, comfy_url=None, ollama_url=None, timeout=30.0):
        del model, comfy_url, ollama_url
        with resources.resource_lock("text", timeout=timeout):
            yield

    resources.text_phase = chat_only_phase
    return original


def _load_report(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Rapport introuvable : {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _scene_signature(scene: str) -> str:
    normalized = " ".join(str(scene).split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Sonde de planification bornée")
    parser.add_argument("--report", required=True, help="JSON contenant les scènes")
    parser.add_argument("--indices", default="1,2,3",
                        help="Indices de scènes, numérotés à partir de 1")
    parser.add_argument("--title", default=None, help="Titre (défaut : celui du rapport)")
    parser.add_argument("--niche", default=None)
    parser.add_argument("--language", default=None)
    parser.add_argument("--model", default="qwen3.8:27b")
    parser.add_argument("--force", action="store_true", help="Replanifier même si déjà fait")
    args = parser.parse_args(argv)

    report_path = Path(args.report)
    report = _load_report(report_path)
    scenes = report.get("scenes") or []
    if not scenes:
        raise SystemExit("Le rapport ne contient aucune scène.")

    try:
        wanted = [int(value.strip()) - 1 for value in args.indices.split(",") if value.strip()]
    except ValueError as exc:
        raise SystemExit("--indices doit être une liste d'entiers, ex. 2,3,4") from exc
    if not wanted or any(index < 0 or index >= len(scenes) for index in wanted):
        raise SystemExit(f"Indices hors bornes (1..{len(scenes)})")

    content, resources = _resolve_modules()
    import requests
    calls = _install_post_guard(requests)
    original_text_phase = _install_chat_only_phase(resources)

    title = args.title if args.title is not None else report.get("title", "")
    niche = args.niche if args.niche is not None else report.get("niche", "sujet")
    language = args.language if args.language is not None else report.get("language", "fr")
    briefs = content.visual_briefs_for_scenes(scenes)
    report["visual_briefs"] = briefs
    probe = report.setdefault("probe", {})
    results = probe.setdefault("scenes", {})
    summary = {}
    pending_context = []
    started = time.time()

    try:
        with resources.text_phase(model=args.model):
            for index in wanted:
                scene = scenes[index]
                brief = briefs[index]
                visual_proposition = brief["visual_proposition"]
                key = str(index + 1)
                digest = _scene_signature(scene + "\0" + visual_proposition)
                previous = results.get(key) or {}
                if brief["needs_context"]:
                    results[key] = {
                        "scene": scene,
                        "visual_proposition": visual_proposition,
                        "antecedent": brief["antecedent"],
                        "needs_context": True,
                        "scene_sha": digest,
                        "plan": "",
                        "kind": "contextual",
                        "subject_type": None,
                        "human_mode": "auto",
                        "planning_error": None,
                        "facts": [],
                        "visual_control": {"kind": "contextual", "human_mode": "auto",
                                           "required_terms": [], "needs_context": True},
                        "seconds": 0.0,
                        "phase": "context_pending",
                    }
                    pending_context.append(index)
                    continue

                if (not args.force and previous.get("scene_sha") == digest
                        and previous.get("plan") and not previous.get("planning_error")
                        and isinstance(previous.get("visual_control"), dict)):
                    summary[index] = ("CACHE", previous["plan"])
                    continue

                scene_started = time.time()
                try:
                    bundle = content.visual_plan_bundle(
                        [visual_proposition], title=title, niche=niche, language=language)
                    plan = (bundle.get("visual_plans") or [""])[0]
                    control = (bundle.get("visual_controls") or [{}])[0]
                    error = control.get("planning_error")
                except Exception as exc:  # Le diagnostic doit conserver le motif exact.
                    plan, control = "", {}
                    error = f"{type(exc).__name__}: {exc}"

                results[key] = {
                    "scene": scene,
                    "visual_proposition": visual_proposition,
                    "antecedent": brief["antecedent"],
                    "needs_context": brief["needs_context"],
                    "scene_sha": digest,
                    "plan": plan,
                    "kind": control.get("kind"),
                    "subject_type": control.get("subject_type"),
                    "human_mode": control.get("human_mode"),
                    "planning_error": error,
                    "facts": control.get("source_facts") or [],
                    "visual_control": control,
                    "seconds": round(time.time() - scene_started, 1),
                    "phase": "probe",
                }
                status = "OK" if plan and not error else "ÉCHEC"
                summary[index] = (status, error or plan)
                # Persiste chaque scène : une interruption conserve les succès.
                report_path.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

            anchors = []
            for index in wanted:
                item = results.get(str(index + 1)) or {}
                expected = _scene_signature(
                    scenes[index] + "\0" + briefs[index]["visual_proposition"])
                if (item.get("scene_sha") == expected and item.get("plan")
                        and not item.get("planning_error") and not item.get("needs_context")):
                    anchors.append(index)
            for index in pending_context:
                item = results[str(index + 1)]
                if anchors:
                    anchor = min(anchors, key=lambda candidate: (
                        abs(candidate - index), candidate > index, candidate))
                    anchor_item = results[str(anchor + 1)]
                    context_control = {
                        **anchor_item["visual_control"],
                        "kind": "contextual",
                        "needs_context": True,
                        "context_scene_index": anchor + 1,
                        "reason": "Continuité depuis l’ancrage validé voisin",
                    }
                    item.update({
                        "plan": anchor_item["plan"] + CONTINUITY_SUFFIX,
                        "kind": "contextual",
                        "subject_type": anchor_item.get("subject_type"),
                        "human_mode": anchor_item.get("human_mode"),
                        "planning_error": None,
                        "facts": anchor_item.get("facts") or [],
                        "visual_control": context_control,
                        "phase": "context_reuse",
                        "context_scene_index": anchor + 1,
                    })
                    summary[index] = ("CONTEXTE", item["plan"])
                else:
                    item["planning_error"] = (
                        f"Scène {index + 1} : contexte visuel requis mais aucun ancrage validé")
                    summary[index] = ("ÉCHEC", item["planning_error"])
            report_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        resources.text_phase = original_text_phase

    elapsed = round(time.time() - started, 1)
    selected = [results.get(str(index + 1)) or {} for index in wanted]
    nonempty_plans = sum(bool(item.get("plan")) for item in selected)
    distinct_visual_subjects = len({_visual_subject_key(item.get("plan"))
                                    for item in selected if item.get("plan")})
    continuity_scenes = sum(
        bool(item.get("needs_context") and item.get("plan")) for item in selected)
    probe["last_run"] = {
        "indices": [index + 1 for index in wanted],
        "elapsed_seconds": elapsed,
        "text_posts": calls["text"],
        "prompt_posts_blocked": calls["prompt_blocked"],
        "other_posts_blocked": calls["other_blocked"],
        "nonempty_plans": nonempty_plans,
        "distinct_render_requests": distinct_visual_subjects,
        "distinct_visual_subjects": distinct_visual_subjects,
        "continuity_scenes": continuity_scenes,
        "model": args.model,
        "title": title,
        "niche": niche,
        "language": language,
    }
    report["visual_plans"] = [item.get("plan") or "" for item in selected]
    report["visual_controls"] = []
    for item in selected:
        control = dict(item.get("visual_control") or {})
        if item.get("planning_error"):
            control["planning_error"] = item["planning_error"]
        control.setdefault("needs_context", bool(item.get("needs_context")))
        report["visual_controls"].append(control)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 70)
    print(f"SONDE — {len(wanted)} scène(s), {calls['text']} POST texte, "
          f"{calls['prompt_blocked']} POST /prompt bloqué(s), {elapsed} s")
    print(f"PLANS — {nonempty_plans} non vide(s) / {distinct_visual_subjects} sujet(s) "
          f"visuel(s) distinct(s) / {continuity_scenes} scène(s) en continuité")
    print("=" * 70)
    for index in wanted:
        status, detail = summary[index]
        print(f"  scène {index + 1:>2} [{status}] {detail}")
    print(f"POST non-/api/chat bloqués : {calls['other_blocked']}")
    print("Rapport :", args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
