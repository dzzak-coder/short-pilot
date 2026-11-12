"""Prépare la narration avant synthèse Hortense : normalisation + empreintes.

À appeler dans l'assemblage, juste AVANT la boucle de synthèse :

    from tts.tools.prepare_narration import prepare_scenes
    prepared = prepare_scenes(scenes_from_plan, language="fr")
    for scene in prepared["scenes"]:
        synth(scene["text_tts"])        # JAMAIS scene["text_original"]

Le rapport produit (`report`) contient :
  - le texte original et le texte normalisé de chaque scène ;
  - les scènes qui ont changé et comment ;
  - le sha256 du texte GLOBAL envoyé (concaténation ordonnée) ;
  - le sha256 par scène, pour recouper avec les fichiers voice_XX.wav.

Le sha256 global change par rapport aux assemblages précédents : c'est attendu,
puisque c'est désormais le texte normalisé qui est envoyé. Le nouveau hash doit être
journalisé dans assembly_report.json sous `sha256_texte_envoye`.
"""
from __future__ import annotations

import hashlib
import difflib
import json
from pathlib import Path
from typing import Any, Iterable

try:
    from .normalize_tts_text import normalize
except ImportError:  # exécution directe depuis tools/
    from normalize_tts_text import normalize

# Caractères par seconde de Hortense, mesure réelle (voir core/content.py).
# Sert uniquement à signaler un dépassement de durée, pas à réécrire le texte.
CPS_HORTENSE = 14.43


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prepare_scenes(
    scenes: Iterable[dict[str, Any]],
    *,
    language: str = "fr",
    spell_all_numbers: bool = False,
    ssml: bool = False,
) -> dict[str, Any]:
    """Normalise chaque scène et renvoie texte + empreintes + rapport de différences.

    `scenes` : itérable de dicts contenant au moins une clé texte parmi
    ("narration", "text", "texte", "narration_text") et de préférence "scene_index".
    """
    if not language.lower().startswith("fr"):
        # La table PRONUNCIATION est calibrée pour le français : ne pas l'appliquer ailleurs.
        raise ValueError(
            f"normalisation TTS prévue pour le français, reçu {language!r}")

    prepared: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    total_chars = 0

    for position, scene in enumerate(scenes, start=1):
        index = scene.get("scene_index", position)
        original = None
        for key in ("narration", "text", "texte", "narration_text"):
            value = scene.get(key)
            if isinstance(value, str) and value.strip():
                original = value
                break
        if original is None:
            raise ValueError(f"scène {index} : aucun texte de narration trouvé")

        tts_text = normalize(original, spell_all_numbers=spell_all_numbers, ssml=ssml)
        total_chars += len(tts_text)

        entry = {
            "scene_index": index,
            "text_original": original,
            "text_tts": tts_text,
            "sha256_original": _sha256(original),
            "sha256_tts": _sha256(tts_text),
            "chars": len(tts_text),
            "seconds_estimated": round(len(tts_text) / CPS_HORTENSE, 2),
        }
        prepared.append(entry)

        if tts_text != original:
            changed.append({
                "scene_index": index,
                "diff": list(difflib.unified_diff(
                    [original], [tts_text], fromfile="original", tofile="normalisé",
                    lineterm="", n=0)),
            })

    # Le texte global envoyé : scènes dans l'ordre, séparées par un saut de ligne.
    global_text = "\n".join(entry["text_tts"] for entry in prepared)
    report = {
        "language": language,
        "scenes_count": len(prepared),
        "scenes_changed": len(changed),
        "chars_total": total_chars,
        "seconds_estimated_total": round(total_chars / CPS_HORTENSE, 2),
        "sha256_texte_envoye": _sha256(global_text),
        "changes": changed,
    }
    return {"scenes": prepared, "global_text": global_text, "report": report}


def write_report(result: dict[str, Any], path: str | Path) -> Path:
    """Écrit le rapport JSON à côté de l'assemblage, pour l'audit."""
    out = Path(path)
    out.write_text(
        json.dumps(result["report"], ensure_ascii=False, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    demo = [
        {"scene_index": 1, "narration":
            "La pyramide de Khéops s'élève à 239 m au-dessus du plateau de Gizeh."},
        {"scene_index": 2, "narration":
            "Elle occupe un volume de 2 583 283 m3, incliné de 26° 26′."},
        {"scene_index": 3, "narration":
            "Hérodote rapporte que le couloir de seize mètres mène à la chambre."},
    ]
    res = prepare_scenes(demo)
    print(json.dumps(res["report"], ensure_ascii=False, indent=2))
    print("\n--- Texte réellement envoyé à Hortense ---")
    print(res["global_text"])
