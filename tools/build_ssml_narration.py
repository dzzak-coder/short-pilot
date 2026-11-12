"""Construit une narration SSML unique pour Hortense, au lieu de 19 WAV recollés.

PROBLÈME RÉSOLU
---------------
L'assemblage actuel synthétise chaque scène séparément puis colle les fichiers avec
0,55 s de silence. Chaque clip démarre et finit à plat : aucune continuité d'intonation
entre les phrases. Résultat : une voix hachée, perçue comme plus robotique qu'elle ne
l'est réellement.

SOLUTION
--------
Une seule synthèse de tout le texte, avec :
  - <break time="..."/> aux frontières de scènes (pause naturelle, pas un silence collé) ;
  - <mark mark="scene_N"/> avant chaque scène, pour récupérer les temps exacts via
    l'évènement BookmarkReached de System.Speech — donc pas de perte de synchronisation ;
  - <prosody rate="..."> réglable pour ajuster le débit À LA SOURCE.

DIFFÉRENCE IMPORTANTE avec atempo
---------------------------------
`atempo` étire l'audio déjà synthétisé : ça dégrade le signal et accentue l'effet
métallique. C'est pour ça que la règle « atempo >= 1,0 » existe.
`<prosody rate>` demande au moteur de parler plus ou moins vite NATIVEMENT : aucune
dégradation. Les deux leviers ne sont pas interchangeables.

CE MODULE NE SYNTHÉTISE RIEN. Il produit le document SSML et le manifeste. La synthèse
est faite par tools/synthesize_ssml_hortense.ps1 (System.Speech, hors ligne).
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Iterable

# Voix imposée. Aucune voix réseau, jamais.
VOICE_NAME = "Microsoft Hortense Desktop"
VOICE_LANG = "fr-FR"

# Débits à essayer à l'écoute, du plus rapide au plus lent.
# Valeur relative System.Speech : "-10%" est 10 % plus lent que le débit par défaut.
RATE_OPTIONS = ["+0%", "-5%", "-10%", "-15%"]

DEFAULT_RATE = "+0%"

# Pause entre deux scènes. La marge actuelle de l'assemblage est 0,55 s : on la conserve
# pour ne pas casser le budget de durée, mais elle est désormais prononcée par le moteur.
DEFAULT_SCENE_BREAK_MS = 550

# Pause plus longue après une phrase qui termine une section (question, CTA).
LONG_BREAK_MS = 900


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def _detect_break(scene: dict[str, Any], default_ms: int) -> int:
    """Pause après la scène : plus longue si la scène se termine par une question."""
    text = (scene.get("text_tts") or scene.get("narration") or "").strip()
    if text.endswith("?"):
        return LONG_BREAK_MS
    return int(scene.get("break_ms", default_ms))


def build_ssml(
    scenes: Iterable[dict[str, Any]],
    *,
    rate: str = DEFAULT_RATE,
    scene_break_ms: int = DEFAULT_SCENE_BREAK_MS,
    voice: str = VOICE_NAME,
) -> dict[str, Any]:
    """Renvoie {ssml, scene_count, rate, voice, total_chars, marks}.

    `scenes` : itérable de dicts avec `scene_index` et `text_tts` (déjà normalisé par
    tools/prepare_narration.py — on ne renormalise pas ici).
    """
    scenes = list(scenes)
    if not scenes:
        raise ValueError("aucune scène à synthétiser")

    parts: list[str] = [
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang="{VOICE_LANG}">',
        f'<voice name="{_escape(voice)}">',
        f'<prosody rate="{rate}">',
    ]
    marks: list[str] = []
    total_chars = 0

    for position, scene in enumerate(scenes, start=1):
        index = scene.get("scene_index", position)
        text = scene.get("text_tts") or scene.get("narration") or ""
        if not text.strip():
            raise ValueError(f"scène {index} : texte vide")
        total_chars += len(text)

        mark = f"scene_{index:02d}"
        marks.append(mark)
        parts.append(f'<mark mark="{mark}"/>')
        parts.append(_escape(text.strip()))

        # Pause après chaque scène, sauf la dernière.
        if position < len(scenes):
            parts.append(f'<break time="{_detect_break(scene, scene_break_ms)}ms"/>')

    parts += ["</prosody>", "</voice>", "</speak>"]
    ssml = "".join(parts)

    return {
        "ssml": ssml,
        "scene_count": len(scenes),
        "rate": rate,
        "voice": voice,
        "lang": VOICE_LANG,
        "total_chars": total_chars,
        "marks": marks,
    }


def write_ssml(doc: dict[str, Any], path: str | Path) -> Path:
    out = Path(path)
    out.write_text(doc["ssml"], encoding="utf-8")
    return out


def write_manifest(doc: dict[str, Any], path: str | Path) -> Path:
    out = Path(path)
    meta = {k: v for k, v in doc.items() if k != "ssml"}
    out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    demo = [
        {"scene_index": 1, "text_tts":
            "La pyramide de Kéops s'élève à 239 mètres au-dessus du plateau de Guizè."},
        {"scene_index": 2, "text_tts":
            "Elle occupe un volume de deux millions et demi de mètres cubes."},
        {"scene_index": 3, "text_tts": "Abonne-toi pour ne rien manquer."},
    ]
    doc = build_ssml(demo)
    print(doc["ssml"].replace("><", ">\n<"))
    print(f"\n{len(doc['ssml'])} caractères SSML, {doc['scene_count']} scènes, "
          f"{len(doc['marks'])} marques")
