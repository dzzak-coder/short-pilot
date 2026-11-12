"""Contrôle de propreté du texte source — aucun réseau, aucun modèle, aucune image.

Objectif : vérifier que le texte extrait depuis Wikipédia ne contient plus de mobilier
d'interface, et que la narration n'a pas été amputée au passage.

Deux modes.

1. Hors ligne, sur un texte déjà extrait :

       python tools\\check_source_text.py --file texte.txt

   Lit le fichier et signale les lignes d'interface résiduelles.

2. Source testée en direct (réseau et écritures de cache, sans modèle) :

       python tools\\check_source_text.py --live --topic "pyramide de Kheops" --lang fr

   Appelle `sources.fetch_bundle` : ses collecteurs peuvent écrire dans
   `data/sources_cache.json` et `data/wiki_cache.json`. Usage manuel seulement.
   Aucun Ollama, aucun ComfyUI, aucune image.

`--file` ne fait ni réseau ni écriture. `--json-out` en mode `--live` écrit le
rapport demandé. Ce script ne planifie et ne génère aucune image.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Vocabulaire d'interface Wikimedia. Aucun mot du domaine narratif.
UI_TOKENS = {
    "modifier", "wikidata", "wikimedia", "commons", "discussion", "historique",
    "contributions", "rediriger", "renommer", "portail", "catégorie", "catégories",
    "notes", "références", "annexes", "sommaire", "accueil",
}
LEAD_TOKENS = {"modifier", "portail", "catégorie", "catégories", "notes",
               "sommaire", "accueil", "wikidata", "wikimedia"}
_WORD_RX = re.compile(r"[\wÀ-ÖØ-öø-ÿ']+", re.UNICODE)


def ui_noise_score(line: str) -> float:
    words = [w.casefold() for w in _WORD_RX.findall(line or "")]
    if not words:
        return 0.0
    # Le prefixe d'interface est concluant quelle que soit la longueur : une ligne
    # "modifier le code ..." peut compter 32 mots et rester du mobilier de site.
    if words[0] in LEAD_TOKENS:
        return 1.0
    if len(words) > 12:
        return 0.0
    hits = sum(1 for w in words if w in UI_TOKENS)
    return hits / len(words)


def find_noise(lines: list[str]) -> list[tuple[int, str]]:
    return [(i, line) for i, line in enumerate(lines) if ui_noise_score(line) >= 0.5]


def report(lines: list[str], label: str) -> int:
    noise = find_noise(lines)
    print(f"--- {label} ---")
    print(f"lignes            : {len(lines)}")
    print(f"mots              : {sum(len(l.split()) for l in lines)}")
    print(f"lignes d'interface: {len(noise)}")
    for index, line in noise:
        print(f"    L{index + 1} : {line[:110]}")
    if noise:
        print("RÉSULTAT : mobilier d'interface encore présent — le filtre ne couvre pas ce cas.")
        return 1
    print("RÉSULTAT : aucun mobilier d'interface détecté.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Propreté du texte source (sans modèle)")
    parser.add_argument("--file", help="Fichier texte déjà extrait")
    parser.add_argument("--live", action="store_true", help="Extraire depuis Wikipédia (réseau)")
    parser.add_argument("--topic", default="", help="Sujet à extraire en mode --live")
    parser.add_argument("--lang", default="fr", choices=["fr", "en"])
    parser.add_argument("--source", default="jour",
                        choices=["actu", "jour", "science", "mythes", "perso"])
    parser.add_argument("--json-out", help="Écrire le détail à ce chemin")
    args = parser.parse_args(argv)

    if args.file:
        path = Path(args.file)
        if not path.exists():
            raise SystemExit(f"Fichier introuvable : {path}")
        lines = [l.strip() for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        return report(lines, f"fichier {path.name}")

    if not args.live:
        raise SystemExit("Choisir --file ou --live.")

    repo_root = Path(__file__).resolve().parent.parent
    for candidate in (repo_root, Path.cwd()):
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))

    try:
        from core import sources
    except ImportError as exc:
        raise SystemExit(f"Impossible d'importer core.sources : {exc}")

    bundle = sources.fetch_bundle(args.source, topic=args.topic, lang=args.lang,
                                  niche="sujet", avoid_repeat=False, log=print)
    items = bundle.get("items") or []
    text = " ".join(str(item.get("text") or "") for item in items)
    title = str(bundle.get("title") or "")

    print(f"titre   : {title}")
    print(f"articles: {len(items)}")
    print(f"mots    : {len(text.split())}")

    lines = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    status = report(lines, f"source {args.source} — {args.topic or '(sujet libre)'}")

    title_status = report([title], "titre") if title else 0

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "topic": args.topic, "lang": args.lang, "source": args.source,
            "title": title, "item_count": len(items), "line_count": len(lines),
            "noise_lines": find_noise(lines),
            "noise_in_title": bool(title) and ui_noise_score(title) >= 0.5,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON écrit : {out}")

    return 1 if (status or title_status) else 0


if __name__ == "__main__":
    sys.exit(main())
