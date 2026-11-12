r"""Diagnostic de planification visuelle — sans rendu, sans image.

Objectif : comprendre, ligne par ligne, ce que le planificateur decide AVANT tout rendu.
Toujours vrai : aucun POST /prompt, aucune image produite, aucun fichier du projet ecrit
(seul le chemin passe a --out est ecrit, et uniquement si --out est fourni).

ATTENTION — EN EXECUTION NORMALE, CET OUTIL N'EST PAS NEUTRE :
  - il entre dans `text_phase`, qui envoie POST /free a ComfyUI s'il tourne (liberation
    memoire) ;
  - il charge reellement qwen3.8:27b dans Ollama, puis le decharge a la fin ;
  - si un rendu ComfyUI est en cours, le precontrole de phase texte echoue au lieu de
    l'interrompre : c'est voulu, pas un bug.

Seul `--dry-run` ne contacte aucun service : il resout les modules et affiche cet
avertissement, sans entrer dans `text_phase`.

Usage (Windows, a la racine du depot) :

    .venv\Scripts\python.exe tools\diagnose_line_planning.py --dry-run
    .venv\Scripts\python.exe tools\diagnose_line_planning.py scripts\mon_script.json
    .venv\Scripts\python.exe tools\diagnose_line_planning.py scripts\mon_script.json --out rapports\diag.json

Le fichier d'entree accepte :
  - un script complet : {"title": "...", "niche": "...", "language": "fr", "scenes": ["...", "..."]}
  - une simple liste de lignes : ["ligne 1", "ligne 2"]

Le script s'execute sous `text_phase`, donc :
  - ComfyUI est libere avant l'appel Ollama s'il tourne ;
  - Ollama est decharge a la fin, meme en cas d'erreur ;
  - aucune phase rendu n'est ouverte.

Il produit :
  - un rapport lisible sur stdout ;
  - un JSON structure pour analyse ulterieure.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PLANNER_MODEL = "qwen3.8:27b"

# Mots qui, s'ils n'apparaissent nulle part, rendent une personne suspecte.
_PERSON_WORDS = re.compile(
    r"\b(?:personne|personnes|homme|femme|enfant|enfants|gar[çc]on|fille|mains?|"
    r"person|people|man|woman|child|hands?|someone)\b",
    re.I,
)


_MODULE_ROOTS = ("core", "shortpilot.core", "shortpilot")


def _load_modules():
    """Trouve `content` et `local_resources` quel que soit le point d'entrée.

    Le dépôt expose les modules sous `core/` lorsque le script est lancé depuis la
    racine du projet, et sous `shortpilot.core` si le paquet est importé depuis le
    dossier parent. On essaie les deux plutôt d'imposer une arborescence.
    """
    # Permet l'exécution depuis tools/ : la racine du dépôt est le parent du dossier
    # du script, ce qui rend `core` importable même si le cwd est ailleurs.
    repo_root = Path(__file__).resolve().parent.parent
    for candidate in (repo_root, Path.cwd()):
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    errors = []
    for root in _MODULE_ROOTS:
        try:
            content = __import__(f"{root}.content", fromlist=["content"])
            local_resources = __import__(f"{root}.local_resources", fromlist=["local_resources"])
        except ImportError as exc:
            errors.append(f"{root} : {exc}")
            continue
        missing = [name for name, mod, attr in (
            ("visual_plan_bundle", content, "visual_plan_bundle"),
            ("text_phase", local_resources, "text_phase"),
        ) if not callable(getattr(mod, attr, None))]
        if missing:
            errors.append(f"{root} : attribut(s) manquant(s) {', '.join(missing)}")
            continue
        return content, local_resources
    raise SystemExit(
        "Modules de planification introuvables. Lancez le script depuis la racine du "
        "projet (dossier contenant `core/`), avec l'environnement virtuel activé.\n"
        "Tentatives :\n  " + "\n  ".join(errors)
    )


SIDE_EFFECTS = """
ATTENTION — EFFETS DE BORD DE CETTE COMMANDE
  - POST /free sur ComfyUI s'il tourne : libère sa mémoire (le rendu en cours, s'il y
    en a un, fait échouer le précontrôle au lieu d'être interrompu).
  - Appel réel à Ollama avec qwen3.8:27b : charge puis DÉCHARGE le modèle à la fin.
  - Aucune image, aucun POST /prompt.
  - Aucun fichier du projet modifié. Seul le chemin passé à --out serait écrit (JSON
    de diagnostic), et uniquement si --out est fourni.
Relancer avec --dry-run pour vérifier le câblage sans contacter aucun service.
"""

def _load_script(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return {"title": "", "niche": "", "language": "fr",
                "scenes": [str(s) for s in raw]}
    if not isinstance(raw, dict):
        raise SystemExit("Format d'entrée non reconnu : attendu un objet ou une liste.")
    scenes = raw.get("scenes") or raw.get("lines") or []
    if not isinstance(scenes, list) or not scenes:
        raise SystemExit("Aucune scène trouvée : clé 'scenes' ou 'lines' requise.")
    return {
        "title": str(raw.get("title") or ""),
        "niche": str(raw.get("niche") or ""),
        "language": str(raw.get("language") or "fr"),
        "scenes": [str(s).strip() for s in scenes],
    }


def _norm(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _anchors(scenes: list[str], controls: list[dict]) -> list[dict]:
    """Extrait, par ligne, l'objet d'ancrage tel qu'il sera envoyé au rendu."""
    rows = []
    for index, (scene, control) in enumerate(zip(scenes, controls)):
        control = control or {}
        facts = control.get("source_facts") or []
        subjects = [f for f in facts if f.get("category") == "subject"]
        secondary = [f for f in facts if f.get("category") == "secondary"]
        anchor = subjects[0].get("entity") if subjects else ""
        rows.append({
            "index": index,
            "line": scene,
            "anchor": anchor,
            "anchor_english": subjects[0].get("english") if subjects else "",
            "secondary": [f.get("entity") for f in secondary],
            "kind": control.get("kind"),
            "subject_type": control.get("subject_type"),
            "human_mode": control.get("human_mode"),
            "still_life": control.get("still_life"),
            "fact_count": len(facts),
            "categories": sorted({f.get("category") for f in facts if f.get("category")}),
            "planning_error": control.get("planning_error"),
            "reason": control.get("reason"),
            "facts": facts,
        })
    return rows


def _analysis(script: dict, rows: list[dict], plans: list[str]) -> dict:
    scenes = script["scenes"]
    full_script = _norm(" ".join(scenes) + " " + script["title"])
    person_requested = bool(_PERSON_WORDS.search(full_script))

    # 1. Sujet d'ancrage : répétitions et diversité.
    anchors = [r["anchor"] for r in rows if r["anchor"]]
    anchor_counts = Counter(a.casefold() for a in anchors)
    duplicated_anchors = {a: c for a, c in anchor_counts.items() if c > 1}

    # 2. Prompts compilés strictement identiques (aucune image comparee ici).
    normalized_plans = [_norm(p) for p in plans]
    identical_groups = defaultdict(list)
    for i, p in enumerate(normalized_plans):
        if p:
            identical_groups[p].append(i)
    identical = [g for g in identical_groups.values() if len(g) > 1]

    # 3. Personnes non demandées.
    person_rows = []
    if not person_requested:
        for r in rows:
            if r["subject_type"] in ("person", "hands") or r["human_mode"] in ("required", "hands_only"):
                person_rows.append(r["index"])

    # 4. Objets récurrents décrits différemment (rupture de continuité).
    appearances = defaultdict(list)
    for r in rows:
        for fact in r["facts"]:
            if fact.get("category") in ("subject", "secondary"):
                appearances[str(fact.get("entity") or "").casefold()].append(
                    (r["index"], str(fact.get("english") or "")))
    inconsistent = {}
    for entity, items in appearances.items():
        if not entity or len(items) < 2:
            continue
        variants = {e for _, e in items}
        if len(variants) > 1:
            inconsistent[entity] = items

    # 5. Erreurs de planification.
    errors = [{"index": r["index"], "error": r["planning_error"]}
              for r in rows if r["planning_error"]]

    # 6. Lignes longues (risque d'écrasement en un seul sujet).
    long_lines = [{"index": r["index"], "words": len(r["line"].split()),
                   "facts": r["fact_count"]}
                  for r in rows if len(r["line"].split()) >= 20]

    return {
        "scene_count": len(scenes),
        "person_requested_in_script": person_requested,
        "person_rows_suspect": person_rows,
        "duplicated_anchors": duplicated_anchors,
        "identical_prompt_groups": identical,
        "inconsistent_recurring_objects": inconsistent,
        "planning_errors": errors,
        "long_lines": long_lines,
        "distinct_anchors": len({a.casefold() for a in anchors}),
        "anchor_distribution": dict(anchor_counts),
    }


def _report(script: dict, rows: list[dict], plans: list[str], analysis: dict) -> str:
    out = []
    add = out.append
    add("=" * 78)
    add("DIAGNOSTIC DE PLANIFICATION VISUELLE — aucun rendu, aucune image")
    add("=" * 78)
    add(f"Titre   : {script['title'] or '(aucun)'}")
    add(f"Niche   : {script['niche'] or '(aucune)'}")
    add(f"Langue  : {script['language']}")
    add(f"Lignes  : {len(script['scenes'])}")
    add("")

    for r in rows:
        add("-" * 78)
        add(f"LIGNE {r['index'] + 1}")
        add(f"  Texte      : {r['line']}")
        if r["planning_error"]:
            add(f"  ERREUR     : {r['planning_error']}")
        add(f"  Type       : kind={r['kind']} sujet={r['subject_type']} humain={r['human_mode']}"
            f" still_life={r['still_life']}")
        add(f"  Ancrage    : {r['anchor'] or '(aucun)'}   [secondaires : "
            f"{', '.join(r['secondary']) or 'aucun'}]")
        add(f"  Faits      : {r['fact_count']} ({', '.join(r['categories']) or '-'})")
        for fact in r["facts"]:
            cat = fact.get("category")
            add(f"      - {cat:<10} {fact.get('entity') or '':<18} "
                f"{fact.get('source_span') or '':<28} -> {fact.get('english') or ''}")
        add(f"  Prompt     : {plans[r['index']] if r['index'] < len(plans) else '(vide)'}")
        if r["reason"]:
            add(f"  Raison     : {r['reason']}")
    add("-" * 78)
    add("")

    add("=" * 78)
    add("SYNTHÈSE")
    add("=" * 78)
    a = analysis
    add(f"Ancrages distincts      : {a['distinct_anchors']} / {a['scene_count']} lignes")
    if a["duplicated_anchors"]:
        add("Ancrages répétés        : " + ", ".join(
            f"{k} ({v}x)" for k, v in a["duplicated_anchors"].items()))
    else:
        add("Ancrages répétés        : aucun")
    if a["identical_prompt_groups"]:
        for group in a["identical_prompt_groups"]:
            add("PROMPTS COMPILÉS IDENTIQUES : lignes " + ", ".join(str(i + 1) for i in group))
    else:
        add("Prompts compilés identiques : aucun")
    if a["person_rows_suspect"]:
        add("PERSONNES NON DEMANDÉES : lignes " +
            ", ".join(str(i + 1) for i in a["person_rows_suspect"]))
    else:
        add("Personnes               : cohérent "
            f"(personne demandée dans le script : {a['person_requested_in_script']})")
    if a["inconsistent_recurring_objects"]:
        add("CONTINUITÉ ROMPUE       :")
        for entity, items in a["inconsistent_recurring_objects"].items():
            variants = sorted({e for _, e in items})
            lines = sorted({i + 1 for i, _ in items})
            add(f"    {entity} — lignes {lines} — {len(variants)} description(s) : {variants}")
    else:
        add("Continuité des objets   : aucune divergence détectée")
    if a["long_lines"]:
        add("Lignes longues (>=20 mots) : " + ", ".join(
            f"L{item['index'] + 1} ({item['words']} mots, {item['facts']} faits)"
            for item in a["long_lines"]))
    if a["planning_errors"]:
        add("ERREURS DE PLANIFICATION :")
        for item in a["planning_errors"]:
            add(f"    ligne {item['index'] + 1} : {item['error']}")
    else:
        add("Erreurs de planification: aucune")
    add("")
    add("Rappel : ce diagnostic ne prouve RIEN sur l'image. Il montre seulement ce")
    add("qui est demandé au rendu. Aucun POST /prompt n'a été émis.")
    return "\n".join(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Diagnostic de planification (sans image)")
    parser.add_argument("script", nargs="?", help="Fichier JSON du script (facultatif en --dry-run)")
    parser.add_argument("--out", help="Écrire le JSON du diagnostic à ce chemin")
    parser.add_argument("--json-only", action="store_true", help="N'afficher que le JSON")
    parser.add_argument("--dry-run", action="store_true",
                        help="Valider le câblage sans contacter Ollama ni ComfyUI")
    args = parser.parse_args(argv)

    if not args.script:
        if not args.dry_run:
            raise SystemExit("Fichier de script requis (sauf en --dry-run).")
        content, local_resources = _load_modules()
        print(SIDE_EFFECTS.strip())
        print("\nDRY-RUN (sans fichier) : modules charges, aucun service contacte.")
        print(f"  content        : {content.__name__}")
        print(f"  local_resources: {local_resources.__name__}")
        print(f"  modele prevu   : {PLANNER_MODEL}")
        return 0

    path = Path(args.script)
    if not path.exists():
        raise SystemExit(f"Script introuvable : {path}")
    script = _load_script(path)

    content, local_resources = _load_modules()

    if args.dry_run:
        print(SIDE_EFFECTS.strip())
        print("\nDRY-RUN : modules charges, aucun service contacte.")
        print(f"  content        : {content.__name__}")
        print(f"  local_resources: {local_resources.__name__}")
        print(f"  lignes         : {len(script['scenes'])}")
        print(f"  modele prevu   : {PLANNER_MODEL}")
        return 0

    payload = {}
    with local_resources.text_phase(model=PLANNER_MODEL):
        bundle = content.visual_plan_bundle(
            script["scenes"], title=script["title"],
            niche=script["niche"], language=script["language"],
        )
        payload = {
            "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "planner_model": PLANNER_MODEL,
            "fingerprint": bundle.get("visual_plan_fingerprint"),
            "script": script,
            "plans": bundle.get("visual_plans") or [],
            "controls": bundle.get("visual_controls") or [],
        }

    plans = payload["plans"]
    rows = _anchors(script["scenes"], payload["controls"])
    analysis = _analysis(script, rows, plans)
    payload["analysis"] = analysis

    report = _report(script, rows, plans, analysis)
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json_only else report)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON écrit : {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
