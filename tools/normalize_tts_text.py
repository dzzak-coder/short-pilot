"""Normalisation du texte avant synthèse vocale — déterministe, hors ligne, sans IA.

Corrige les deux défauts constatés avec Hortense :
  1. les nombres et unités lus littéralement ("239 m" -> "239 monsieur") ;
  2. les noms propres prononcés phonétiquement de travers ("Khéops" -> "ki-up").

Deux approches sont combinées :

  - RÉÉCRITURE ORTHOGRAPHIQUE (par défaut, sûre) : "239 m" devient "239 mètres",
    "Khéops" devient "Kéops". Fonctionne avec n'importe quel moteur TTS.
  - SSML PHONÉTIQUE (optionnel) : produit un balisage <phoneme alphabet="ipa">
    pour les moteurs qui l'acceptent (System.Speech.SpeakSsml). À utiliser seulement
    si la réécriture orthographique ne suffit pas.

Aucun appel réseau. Aucune dépendance externe.

Usage en ligne de commande :

    python tools\\normalize_tts_text.py --file scenes.txt
    python tools\\normalize_tts_text.py --file scenes.txt --ssml --out scenes_tts.txt
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------- nombres

_UNITS = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf",
          "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize"]
_TENS = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante",
         60: "soixante", 80: "quatre-vingt"}


def number_to_french(value: int) -> str:
    """Écrit un entier en français. Couvre 0 à 999 999 999."""
    if value < 0:
        return "moins " + number_to_french(-value)
    if value < 17:
        return _UNITS[value]
    if value < 20:
        return "dix-" + _UNITS[value - 10]
    if value < 100:
        tens, unit = divmod(value, 10)
        if tens == 7:                           # 70-79 : soixante + 10..19
            return "soixante-" + _UNITS[value - 60]
        if tens == 9:                           # 90-99 : quatre-vingt + 10..19
            return "quatre-vingt-" + _UNITS[value - 80]
        word = _TENS[tens * 10]
        if unit == 1 and tens not in (8,):
            return word + "-et-un"
        return word if unit == 0 else f"{word}-{_UNITS[unit]}"
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        head = "cent" if hundreds == 1 else f"{_UNITS[hundreds]}-cent"
        if rest and hundreds > 1:
            head += "s" if rest == 0 else ""
        return head if rest == 0 else f"{head}-{number_to_french(rest)}"
    if value < 1_000_000:
        thousands, rest = divmod(value, 1000)
        head = "mille" if thousands == 1 else f"{number_to_french(thousands)}-mille"
        return head if rest == 0 else f"{head}-{number_to_french(rest)}"
    millions, rest = divmod(value, 1_000_000)
    head = "un-million" if millions == 1 else f"{number_to_french(millions)}-millions"
    return head if rest == 0 else f"{head}-{number_to_french(rest)}"


def _number_words(token: str) -> str:
    """Gère les entiers, les décimaux à la française et les séparateurs d'espace."""
    token = token.replace("\u202f", "").replace("\u00a0", "").replace(" ", "")
    if "," in token:
        whole, frac = token.split(",", 1)
        if whole.isdigit() and frac.isdigit():
            return f"{number_to_french(int(whole))} virgule " + " ".join(
                _UNITS[int(d)] for d in frac)
        return token
    if token.isdigit():
        return number_to_french(int(token))
    return token


# --------------------------------------------------------------------------- unités

# Unité -> forme parlée. L'ordre compte : les plus longues d'abord.
UNITS = [
    ("km/h", "kilomètres heure"),
    ("km²", "kilomètres carrés"),
    ("km2", "kilomètres carrés"),
    ("km3", "kilomètres cubes"),
    ("m²", "mètres carrés"),
    ("m³", "mètres cubes"),
    ("m2", "mètres carrés"),
    ("m3", "mètres cubes"),
    ("cm", "centimètres"),
    ("mm", "millimètres"),
    ("km", "kilomètres"),
    ("kg", "kilogrammes"),
    ("t", "tonnes"),
    ("°C", "degrés"),
    ("°", "degrés"),
    ("%", "pour cent"),
    ("m", "mètres"),
    ("g", "grammes"),
    ("L", "litres"),
    ("l", "litres"),
]

_NUMBER_UNIT = re.compile(
    r"(?<![\w])(\d+(?:[ \u00a0\u202f]\d{3})*(?:,\d+)?)\s*("
    + "|".join(re.escape(u) for u, _ in UNITS)
    + r")(?![\w])"
)
_PLAIN_NUMBER = re.compile(r"(?<![\w])(\d+(?:[ \u00a0\u202f]\d{3})*(?:,\d+)?)(?![\w])")

_UNIT_MAP = {u: spoken for u, spoken in UNITS}


def expand_primes(text: str) -> str:
    """« 26° 26′ 46″ » -> degrés / minutes / secondes d'arc, lisibles."""
    text = re.sub(r"(\d)\s*°\s*(\d+)\s*[′']",
                  lambda m: f"{m.group(1)} degrés {m.group(2)} minutes", text)
    text = re.sub(r"(\d)\s*[″\"]",
                  lambda m: f"{m.group(1)} secondes", text)
    return text


_ERAS = [
    (re.compile(r"av(?:ant)?\.?\s*J\.?-?\s*C\.?", re.I), "ans avant Jésus-Christ"),
    (re.compile(r"apr(?:ès)?\.?\s*J\.?-?\s*C\.?", re.I), "ans après Jésus-Christ"),
]


def expand_eras(text: str) -> str:
    """« 2 500 av. J.-C. » -> « 2 500 ans avant Jésus-Christ »."""
    for pattern, replacement in _ERAS:
        text = pattern.sub(replacement, text)
    return text


def expand_units(text: str) -> str:
    """« 239 m » -> « 239 mètres ». Le nombre reste en chiffres, le TTS sait le lire."""
    def repl(match):
        number, unit = match.group(1), match.group(2)
        return f"{number} {_UNIT_MAP[unit]}"
    return _NUMBER_UNIT.sub(repl, text)


def spell_numbers(text: str) -> str:
    """Écrit tous les nombres restants en toutes lettres (option plus sûre)."""
    return _PLAIN_NUMBER.sub(lambda m: _number_words(m.group(1)), text)


# --------------------------------------------------------------------------- noms propres
# Réécriture orthographique : on choisit une graphie que le TTS français prononce juste.
# À ajuster après écoute ; les valeurs ci-dessous sont un point de départ documenté.

PRONUNCIATION = {
    "Khéops": "Kéops",
    "Khéphren": "Kéfren",
    "Khafrê": "Kafré",
    "Gizeh": "Guizè",
    "Hérodote": "Érodote",
    "Héliopolis": "Éliopolis",
    "Saqqarah": "Sakara",
    "Saqqara": "Sakara",
    "Djoser": "Djozer",
    "Snéfrou": "Snéfrou",
    "Ouahibre": "Ouahibré",
    "Abousir": "Abousir",
    "Meïdoum": "Médoum",
    "Dahchour": "Dachour",
}

# Variantes IPA pour le mode SSML (facultatif).
IPA = {
    "Khéops": "ke.ɔps",
    "Gizeh": "ɡi.zɛ",
    "Khéphren": "ke.fʁɛn",
    "Hérodote": "e.ʁɔ.dɔt",
}

_PROPER = re.compile(r"\b(" + "|".join(re.escape(k) for k in PRONUNCIATION) + r")\b")


def rewrite_proper_nouns(text: str) -> str:
    """Remplace par une graphie que la voix prononce correctement."""
    return _PROPER.sub(lambda m: PRONUNCIATION[m.group(1)], text)


def ssml_proper_nouns(text: str) -> str:
    """Balisage IPA pour les moteurs qui acceptent SpeakSsml (System.Speech)."""
    def repl(match):
        word = match.group(1)
        phoneme = IPA.get(word)
        if not phoneme:
            return PRONUNCIATION[word]
        return f'<phoneme alphabet="ipa" ph="{phoneme}">{PRONUNCIATION[word]}</phoneme>'
    return _PROPER.sub(repl, text)


# --------------------------------------------------------------------------- pipeline

def normalize(text: str, *, spell_all_numbers: bool = False, ssml: bool = False) -> str:
    """Applique la chaîne complète. Idempotent sur un texte déjà normalisé."""
    out = expand_units(expand_eras(expand_primes(text)))
    if spell_all_numbers:
        out = spell_numbers(out)
    out = ssml_proper_nouns(out) if ssml else rewrite_proper_nouns(out)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Normalisation du texte pour TTS")
    parser.add_argument("--file", help="Fichier texte (une scène par ligne) ou JSON avec 'scenes'")
    parser.add_argument("--ssml", action="store_true", help="Émettre un balisage <phoneme> IPA")
    parser.add_argument("--spell-numbers", action="store_true",
                        help="Écrire tous les nombres en toutes lettres")
    parser.add_argument("--out", help="Écrire le résultat ici")
    parser.add_argument("--json", action="store_true", help="Sortie JSON avec les scènes normalisées")
    args = parser.parse_args(argv)

    if not args.file:
        raise SystemExit("--file requis")
    path = Path(args.file)
    if not path.exists():
        raise SystemExit(f"Fichier introuvable : {path}")

    raw = path.read_text(encoding="utf-8")
    lines = []
    if path.suffix.lower() == ".json":
        data = json.loads(raw)
        lines = [str(s) for s in (data.get("scenes") or [])]
    else:
        lines = [l.strip() for l in raw.splitlines() if l.strip()]

    normalized = [normalize(l, spell_all_numbers=args.spell_numbers, ssml=args.ssml)
                  for l in lines]

    if args.json:
        payload = json.dumps({"scenes": normalized}, ensure_ascii=False, indent=2)
    else:
        payload = "\n".join(normalized)

    print(payload)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"\nÉcrit : {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
