"""Diagnostic du décalage ancrage <-> image dans une campagne.

Objectif : vérifier que chaque image a bien été générée depuis le prompt de SA scène,
et non depuis celui d'une autre. Aucun service, aucune génération.

Usage, depuis la racine du dépôt :

    .venv\\Scripts\\python.exe diagnose_campaign_mapping.py outputs\\kheops_campaign_2026-11-10
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


def load_jsons(folder: Path):
    """Charge tous les .json du dossier, en ignorant les marqueurs 'x'."""
    out = {}
    for path in sorted(folder.rglob("*.json")):
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        if not raw.startswith("{") and not raw.startswith("["):
            continue  # marqueur generation_once.json = "x"
        try:
            out[str(path.relative_to(folder))] = json.loads(raw)
        except ValueError:
            continue
    return out


def find_prompt_lists(data):
    """Repère les listes de prompts dans une structure JSON quelconque."""
    found = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list) and node:
            if all(isinstance(x, str) and len(x) > 25 for x in node):
                found.append((path, node))
            else:
                for i, item in enumerate(node):
                    walk(item, f"{path}[{i}]")

    walk(data)
    return found


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if not argv:
        raise SystemExit("Usage : diagnose_campaign_mapping.py <dossier_campagne>")
    folder = Path(argv[0])
    if not folder.exists():
        raise SystemExit(f"Dossier introuvable : {folder}")

    print("=" * 78)
    print("DIAGNOSTIC : correspondance ancrage -> prompt -> image")
    print("=" * 78)
    print(f"Dossier : {folder}\n")

    # 1. Images présentes
    pngs = sorted(folder.rglob("*.png"))
    print(f"Images PNG : {len(pngs)}")
    for p in pngs[:30]:
        print(f"  {p.name:<55} {sha256(p)[:16]}")

    # 2. Prompts trouvés dans les JSON
    print("\n--- Prompts trouvés dans les rapports ---")
    jsons = load_jsons(folder)
    print(f"Fichiers JSON exploitables : {len(jsons)}")
    for name, data in jsons.items():
        for path, prompts in find_prompt_lists(data):
            print(f"\n{name} :: {path}  ({len(prompts)} entrées)")
            for i, prompt in enumerate(prompts[:30]):
                print(f"  [{i + 1:>2}] {prompt[:110]}")

    # 3. Le point critique : chaque prompt parle-t-il du sujet attendu ?
    print("\n" + "=" * 78)
    print("CONTRÔLE DE COHÉRENCE")
    print("=" * 78)
    all_prompts = []
    for data in jsons.values():
        for _path, prompts in find_prompt_lists(data):
            all_prompts.extend(prompts)

    if not all_prompts:
        print("Aucun prompt trouvé : le rapport ne contient pas les prompts compilés.")
        print("C'est déjà un défaut : impossible de vérifier ce qui a été envoyé au rendu.")
        return 1

    # Vocabulaire attendu pour Khéops (générique : uniquement des indices de sujet)
    expected = re.compile(
        r"pyramid|kheops|kéops|giza|gizeh|egypt|égypt|stone|block|granite|limestone|"
        r"corridor|gallery|chamber|tomb|sarcophagus|desert|sand|ancient|monument",
        re.I)
    off_topic = [(i + 1, p) for i, p in enumerate(all_prompts) if not expected.search(p)]
    on_topic = len(all_prompts) - len(off_topic)

    print(f"Prompts contenant le vocabulaire du sujet : {on_topic}/{len(all_prompts)}")
    if off_topic:
        print("\nPrompts HORS SUJET (aucun terme du sujet) :")
        for index, prompt in off_topic[:20]:
            print(f"  [{index:>2}] {prompt[:120]}")

    # 4. Détection de décalage : un prompt qui décrit un objet d'une autre scène
    print("\n--- Recherche de décalage d'index ---")
    print("Un prompt est 'décalé' s'il correspond mieux au sujet d'une AUTRE scène.")
    print("(nécessite les scènes ; à croiser manuellement avec le script)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
