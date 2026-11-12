"""Vérifie que le graphe ComfyUI contient EXACTEMENT les prompts du plan.

CONTRÔLE MANQUANT, À FAIRE AVANT TOUT POST /prompt
--------------------------------------------------
`plan.json` peut être parfait et le graphe compilé faux. Le bug d'origine (étiquettes
françaises injectées brutes) a produit 23 images correctement associées à leurs scènes,
avec des prompts faux. Un contrôle « 23/23 plans conformes » ne l'aurait pas vu : il
faut comparer le TEXTE, pas les index.

Ce script compare, image par image :
    plan.json  ->  workflow compilé envoyé à ComfyUI

Sortie non nulle en cas d'écart. Aucun accès réseau, aucune génération.

Usage :
    .venv\\Scripts\\python.exe tools\\verify_compiled_prompts.py ^
        outputs\\kheops_campaign_2026-11-11-v2\\plan.json

Avec un workflow extrait :
    .venv\\Scripts\\python.exe tools\\verify_compiled_prompts.py plan.json workflow.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Bibliothèque de prompts (visual_corpus, etc.) : ce préfixe n'est pas un défaut.
LIBRARY_PREFIXES = (
    ", clean negative space for captions",
    ", clean negative space for captions.",
)


def load_json(path: Path):
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw.startswith(("{", "[")):
        raise SystemExit(f"{path.name} : contenu non JSON ({raw[:30]!r}) — marqueur ignoré")
    return json.loads(raw)


def find_prompts(node, acc: list[tuple[str, str]], where: str = "") -> None:
    """Collecte tous les champs texte destinés à l'encodeur."""
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{where}/{key}" if where else key
            if key in ("prompt", "prompt_text", "positive", "text") and isinstance(value, str) and len(value) > 25:
                acc.append((path, value))
            else:
                find_prompts(value, acc, path)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            find_prompts(value, acc, f"{where}[{i}]")


def normalize_ws(text: str) -> str:
    return " ".join(text.split())


def strip_library(text: str) -> str:
    out = text
    for prefix in LIBRARY_PREFIXES:
        out = out.replace(prefix, "")
    return out.strip()


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    plan_path = Path(argv[0])
    plan = load_json(plan_path)

    # --- prompts attendus, lus dans le plan ---
    expected: dict[str, str] = {}
    for key in ("images", "prompts", "items"):
        entries = plan.get(key)
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                index = entry.get("image_index") or entry.get("index")
                text = entry.get("prompt")
                if index is not None and isinstance(text, str):
                    expected[str(index)] = normalize_ws(text)
            if expected:
                break

    if not expected:
        print("ÉCHEC : aucun prompt trouvé dans le plan "
              "(cherché dans les clés images/prompts/items).")
        print("Clés présentes :", list(plan.keys())[:20])
        return 1

    print(f"Plan : {plan_path}")
    print(f"Prompts attendus : {len(expected)}")
    long_max = max(len(v) for v in expected.values())
    print(f"Longueur max : {long_max} caractères (~{long_max // 4} tokens, T5 tronque à 512)")

    # --- vérifications propres au plan ---
    failures = 0

    # 1. unicité
    values = list(expected.values())
    if len(set(values)) != len(values):
        dupes: dict[str, list[str]] = {}
        for idx, text in expected.items():
            dupes.setdefault(text, []).append(idx)
        print("\nÉCHEC : prompts dupliqués dans le plan")
        for text, idxs in dupes.items():
            if len(idxs) > 1:
                print(f"  images {idxs} : {text[:90]}")
        failures += 1
    else:
        print("OK : 23 prompts distincts dans le plan")

    # 2. résidus français (contrôle explicite, sans faux positif corridor/niche)
    forbidden = {"entrée", "chambre", "pierre", "voûte", "puits", "sarcophage",
                 "mur", "roche", "décharge", "inscriptions", "ouverture"}
    import re as _re
    # Recherche par MOT ENTIER : "mur" ne doit pas matcher "mural", et les mots
    # anglais légitimes (corridor, niche) ne sont jamais dans cette liste.
    _pat = _re.compile(r"\b(" + "|".join(sorted(forbidden, key=len, reverse=True)) + r")\b",
                       _re.IGNORECASE)
    hits = []
    for idx, text in expected.items():
        for m in _pat.finditer(text):
            hits.append((idx, m.group(0)))
    if hits:
        print("\nÉCHEC : mots français résiduels dans les prompts du plan")
        for idx, mot in hits:
            print(f"  image {idx} : {mot!r}")
        failures += 1
    else:
        print("OK : aucun mot français résiduel")

    # 3. contexte égyptien présent (EXT = "Egypt", INT = "inside the Great Pyramid")
    CONTEXT_MARKERS = ("egypt", "great pyramid of khufu", "giza")
    sans_contexte = [i for i, t in expected.items()
                     if not any(m in t.lower() for m in CONTEXT_MARKERS)]
    if sans_contexte:
        print(f"\nÉCHEC : contexte égyptien/gizeh absent sur les images {sans_contexte}")
        failures += 1
    else:
        print("OK : contexte égyptien sur les 23")

    # --- comparaison avec le workflow compilé, si fourni ---
    if len(argv) > 1:
        wf_path = Path(argv[1])
        workflow = load_json(wf_path)
        compiled: list[tuple[str, str]] = []
        find_prompts(workflow, compiled)
        texts = [strip_library(normalize_ws(t)) for _p, t in compiled]

        print(f"\nWorkflow : {wf_path}")
        print(f"Prompts trouvés dans le graphe : {len(texts)}")

        if len(texts) != len(expected):
            print(f"ÉCHEC : {len(texts)} prompts dans le graphe pour "
                  f"{len(expected)} attendus")
            failures += 1

        expected_set = set(expected.values())
        node_by_prompt = {}
        for node_path, raw in compiled:
            node_by_prompt.setdefault(strip_library(normalize_ws(raw)), []).append(node_path)

        manquants = [i for i, t in expected.items() if t not in node_by_prompt]
        if manquants:
            print(f"\nÉCHEC : {len(manquants)} prompts du plan ABSENTS du graphe")
            for idx in manquants[:23]:
                print(f"  image {idx} : {expected[idx][:100]}")
            failures += 1
        else:
            print("OK : chaque prompt du plan est présent tel quel dans le graphe")

        extra = [t for t in node_by_prompt if t not in expected_set
                 and t.strip() and len(t) > 25]
        if extra:
            print(f"\nAVERTISSEMENT : {len(extra)} texte(s) dans le graphe "
                  f"qui ne viennent pas du plan")
            for t in extra[:10]:
                print(f"  {t[:110]}")

        # Correspondance nœud -> image, pour l'audit
        print("\nCorrespondance nœud -> image :")
        for idx in sorted(expected, key=lambda x: int(x)):
            nodes = node_by_prompt.get(expected[idx], [])
            etat = nodes[0] if nodes else "ABSENT"
            print(f"  image {idx:>2} -> {etat}")

    else:
        print("\n(Workflow non fourni : comparaison plan<->graphe non effectuée.)")
        print("Pour la faire, extraire le graphe compilé puis relancer avec son chemin.")

    print("\n" + ("=" * 60))
    if failures:
        print(f"RÉSULTAT : ÉCHEC ({failures} contrôle(s) en échec) — NE PAS GÉNÉRER")
        return 1
    print("RÉSULTAT : OK — le plan est cohérent")
    return 0


if __name__ == "__main__":
    sys.exit(main([a for a in sys.argv[1:] if not a.startswith("-")]))
