"""Traduction des ancrages français vers un anglais visuellement non ambigu.

Cause du bug constaté sur la campagne Khéops : les étiquettes d'ancrage françaises
étaient injectées telles quelles dans un prompt anglais. Qwen-Image les interprète
avec leur sens anglais ou ignore le contexte égyptien.

Exemples réels :
  "an entrée"              -> un plat (entrée = starter en anglais culinaire)
  "an inscriptions"        -> stèle à calligraphie chinoise (biais natif du modèle)
  "a système de décharge"  -> machine d'évacuation industrielle
  "a corridor"             -> couloir moderne, pas un couloir de pyramide

Deux règles :
  1. aucun substantif français ne doit apparaître dans le prompt final ;
  2. chaque prompt porte un contexte égyptien explicite.
"""
from __future__ import annotations

# Contexte ajouté en tête de chaque prompt. Court, factuel, non ambigu.
CONTEXT = "Ancient Egypt, Giza, inside or around the Great Pyramid of Khufu"

# Traductions des ancrages rencontrés dans la campagne Khéops.
# La clé doit rester identique à l'étiquette produite par visual_corpus.
ANCHOR_EN = {
    # structures
    "pyramide de Khéops": "the Great Pyramid of Khufu, a massive stepped stone pyramid",
    "pyramide de khéops": "the Great Pyramid of Khufu, a massive stepped stone pyramid",
    "pyramide de kheops": "the Great Pyramid of Khufu, a massive stepped stone pyramid",
    "khéops": "the Great Pyramid of Khufu",
    "pyramide de Khéphren": "the pyramid of Khafre, seen in the distance",
    "complexe funéraire": "the ancient funerary complex around the pyramid",
    "plateau de Gizeh": "the Giza plateau, sandy desert with pyramids in the background",
    "plateau de gizeh": "the Giza plateau, sandy desert with pyramids in the background",
    "basilique": "a distant European basilica on the horizon",       # comparateur : à exclure
    "cathédrale": "a distant European cathedral",                     # comparateur : à exclure

    # parties de construction
    "assises de la pyramide": "the large horizontal courses of limestone masonry of the pyramid",
    "socle rocheux": "the bedrock foundation the pyramid was built on",
    "revêtement": "the smooth white limestone casing of the pyramid",
    "enceinte à redans": "a low niched stone enclosure wall",
    "linteaux": "heavy granite lintel blocks above a passage",
    "voûte": "a corbelled stone vault ceiling",
    "mur": "a rough stone wall inside the pyramid",
    "paroi": "a stone wall face inside a narrow passage",
    "toit": "the sloping stone ceiling of a gallery",
    "plafond": "the flat stone ceiling of a burial chamber",

    # roches et matériaux
    "roche naturelle": "the natural limestone bedrock outcrop",
    "blocs de pierre": "huge rough-cut limestone blocks",
    "blocs de granit rose": "polished rose granite blocks",
    "pierres calcaires blanches": "smooth white limestone casing stones",

    # espaces
    "chambre funéraire": "the granite burial chamber",
    "chambre du roi": "the King's Chamber with granite walls",
    "chambre de la reine": "the Queen's Chamber",
    "chambre de décharge": "a relieving chamber above the King's Chamber",
    "chambre souterraine": "a rough-cut underground chamber",
    "chambre sépulcrale": "the burial chamber with its granite sarcophagus",
    "antichambre": "a small antechamber in a stone passage",
    "appartements funéraires": "the burial apartments inside the pyramid",
    "grande galerie": "the Grand Gallery, a tall corbelled stone corridor",
    "galerie": "a narrow stone gallery inside the pyramid",
    "couloir": "a narrow ascending stone corridor",
    "couloir ascendant": "the ascending stone corridor",
    "couloir descendant": "the descending stone corridor",
    "couloir horizontal": "a horizontal stone corridor",
    "corridor": "a narrow stone corridor cut through limestone masonry",
    "passage": "a low stone passage",
    "boyau": "a tight rough-hewn tunnel",
    "descenderie": "a steep descending tunnel",
    "puits": "a vertical shaft cut down through bedrock",
    "grotte": "a small natural cave hollow in the bedrock",

    # ouvertures et mécanismes
    "entrée": "the original stone entrance passage of the pyramid",
    "ouverture": "a narrow forced tunnel opening cut through masonry",
    "niche": "a carved stone niche in a chamber wall",
    "voûte en encorbellement": "a corbelled vault above a niche",
    "herses de fermeture": "heavy granite portcullis slabs blocking a passage",
    "blocs bouchons": "large granite blocking plugs in a passage",
    "pierre mobile": "a movable stone slab used as a door",
    "système de décharge": "the relieving chambers built above the King's Chamber",
    "corridor (décharge)": "a narrow relieving chamber ceiling space",

    # artefacts
    "sarcophage": "the empty granite sarcophagus in the burial chamber",
    "momie": "an ancient Egyptian mummy",  # ancrage contextuel, à exclure si non attribué
    "inscriptions": "red ochre quarry marks painted on stone blocks",  # PAS "inscriptions"
    "cartouche": "a painted royal name cartouche on stone",
    "île": "a small island in a river",   # contexte historique (Hérodote) : à exclure
    "canal": "an ancient canal of water",  # contexte historique (Hérodote) : à exclure
}

# Ancrages à exclure : comparaisons et contexte historique extérieur au sujet.
EXCLUDED = {"basilique", "cathédrale", "île", "canal", "momie"}


def translate_anchor(label: str) -> str | None:
    """Renvoie l'anglais visuel, ou None si l'ancrage doit être exclu.

    Si l'étiquette est inconnue, on ne devine pas : on renvoie None et le
    appelant doit journaliser l'ancrage non traduit plutôt que l'injecter brut.
    """
    key = (label or "").strip().casefold()
    if key in EXCLUDED:
        return None
    return ANCHOR_EN.get(key)


def build_prompt(label: str, extra: str = "") -> str:
    """Prompt complet : contexte égyptien + objet anglais. Lève si non traduit."""
    english = translate_anchor(label)
    if english is None:
        raise ValueError(f"ancrage exclu ou non traduit : {label!r}")
    prompt = (
        f"A realistic documentary photograph in a vertical 9:16 composition of {english}, "
        f"{CONTEXT}. Photographic, natural light, no text, no people."
    )
    if extra:
        prompt += f" {extra}"
    return prompt


if __name__ == "__main__":
    for label in ("entrée", "inscriptions", "corridor", "système de décharge",
                  "pyramide de Khéops", "basilique"):
        try:
            print(f"{label:<24} -> {build_prompt(label)[:120]}...")
        except ValueError as exc:
            print(f"{label:<24} -> EXCLU ({exc})")


# --------------------------------------------------------------------------- cadrage
# Le cadrage depend de l'ANCRAGE, pas de la scene. Objectif : varier les echelles de plan
# et interdire deux prompts strictement identiques.
FRAMING_BY_CATEGORY = {
    "structure": "wide establishing shot",
    "site": "wide establishing shot",
    "construction_part": "medium shot, low angle",
    "material": "medium shot, shallow depth of field",
    "passage": "medium shot, leading lines into darkness",
    "room": "medium close shot, symmetrical framing",
    "opening": "medium shot, seen from outside toward the opening",
    "mechanism": "close-up detail shot",
    "artifact": "close-up detail shot",
}

# Alternance de secours quand un ancrage revient : jamais deux fois le meme cadrage.
FRAMING_ALTERNATES = [
    "wide establishing shot",
    "medium shot, low angle",
    "close-up detail shot",
    "medium shot, from behind",
    "close-up, shallow depth of field",
    "wide shot, framed by stone",
]


def category_from_id(anchor_id: str) -> str:
    """'construction_part:stone_courses' -> 'construction_part'."""
    return (anchor_id or "").split(":")[0]


def framing_for(anchor_id: str, occurrence: int = 0) -> str:
    """Cadrage deterministe. `occurrence` = combien de fois cet ancrage a deja servi."""
    base = FRAMING_BY_CATEGORY.get(category_from_id(anchor_id), "medium documentary shot")
    if occurrence <= 0:
        return base
    alt = FRAMING_ALTERNATES[occurrence % len(FRAMING_ALTERNATES)]
    return alt if alt != base else FRAMING_ALTERNATES[(occurrence + 1) % len(FRAMING_ALTERNATES)]


def build_image_prompts(assignments):
    """Construit les prompts d'une campagne et garantit l'unicite.

    `assignments` : liste de dicts {image_index, anchor_id, label}.
    Renvoie une liste de prompts dont AUCUN n'est strictement identique.
    Leve ValueError si l'unicite ne peut pas etre obtenue.
    """
    seen_counts = {}
    used_prompts = set()
    out = []
    for item in assignments:
        anchor_id = item.get("anchor_id", "")
        label = item.get("label", "")
        occurrence = seen_counts.get(anchor_id, 0)
        seen_counts[anchor_id] = occurrence + 1

        prompt = None
        for attempt in range(len(FRAMING_ALTERNATES) + 1):
            framing = framing_for(anchor_id, occurrence + attempt)
            candidate = build_prompt(label) + f" Camera framing: {framing}."
            if candidate not in used_prompts:
                prompt = candidate
                break
        if prompt is None:
            raise ValueError(
                f"impossible de rendre unique le prompt de l'image {item.get('image_index')} "
                f"(ancrage {anchor_id!r}) : trop de repetitions sur le meme ancrage")
        used_prompts.add(prompt)
        out.append({"image_index": item.get("image_index"), "anchor_id": anchor_id,
                    "label": label, "prompt": prompt})
    return out
