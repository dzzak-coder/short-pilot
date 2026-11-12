"""Constructeur de prompts visuels — version 2.

Corrige trois défauts constatés sur les 23 prompts de la campagne Khéops :

1. CONTEXTE UNIQUE. "inside or around the Great Pyramid" était ajouté partout,
   y compris aux plans larges du plateau (contradiction) et aux plans intérieurs
   (aucune indication de lumière). On distingue désormais EXTÉRIEUR et INTÉRIEUR,
   avec la lumière qui va avec.

2. CATÉGORIE "mechanism" TROP LARGE. "système de décharge" (une chambre) était
   rendu en close-up. Une chambre de décharge est un volume, pas un détail.
   Les mécanismes sont désormais séparés : objets (close-up) vs espaces (plan large).

3. RÉPÉTITION DU SUJET. "the Great Pyramid of Khufu" apparaissait dans le sujet
   ET dans le contexte. Le contexte ne le répète plus quand il est déjà le sujet.

Le style photographique est aussi explicité : sans lui, 23 générations
indépendantes produisent 23 étalonnages différents et le short ne tient pas
visuellement ensemble.
"""
from __future__ import annotations

# Ce module est VOLONTAIREMENT autonome : aucune dépendance à anchor_translations.py,
# afin d'éviter deux implémentations divergentes dans le dépôt.

EXCLUDED = {"basilique", "cathédrale", "île", "canal", "momie"}


def category_from_id(anchor_id: str) -> str:
    """'construction_part:stone_courses' -> 'construction_part'."""
    return (anchor_id or "").split(":")[0]

# --------------------------------------------------------------------------- contextes

CONTEXT_EXTERIOR = (
    "Ancient Egypt, near Cairo, open desert under harsh dry sunlight, "
    "pale limestone and sand tones")
CONTEXT_INTERIOR = (
    "deep inside the Great Pyramid of Khufu, ancient limestone and granite masonry, "
    "dim ambient light, dust in the air")

# Ancrages qui se voient de l'extérieur.
EXTERIOR_ANCHORS = {
    "site:plateau_de_gizeh",
    "site:roche_naturelle",
    "structure:main:pyramide_de_kheops",
    "structure:pyramide_de_khephren",
    "construction_part:stone_courses",
    "construction_part:socle_rocheux",
    "construction_part:revetement",
    "construction_part:enceinte_a_redans",
    "material:blocs_de_pierre",
    "material:granite_blocks",
    "material:pierres_calcaires_blanches",
    "opening:entree",          # l'entrée se voit de l'extérieur, face à la maçonnerie
}

# Sujets anglais, indexés par IDENTIFIANT d'ancrage (et non par label français :
# certains labels sont ambigus, "corridor" existe aussi en anglais).
SUBJECT_BY_ANCHOR = {
    "site:plateau_de_gizeh": "the Giza plateau, sandy desert with pyramids in the background",
    "site:roche_naturelle": "the natural limestone bedrock outcrop",
    "structure:main:pyramide_de_kheops": "a massive stepped stone pyramid, the largest of the three",
    "structure:pyramide_de_khephren": "the second pyramid, slightly smaller, seen at distance",
    "construction_part:stone_courses": "the large horizontal courses of limestone masonry",
    "construction_part:socle_rocheux": "the bedrock foundation the pyramid was built on",
    "construction_part:revetement": "the smooth white limestone casing of the pyramid",
    "construction_part:enceinte_a_redans": "a low niched stone enclosure wall",
    "construction_part:voute": "a corbelled stone vault ceiling",
    "construction_part:mur": "a rough stone wall inside the pyramid",
    "construction_part:paroi": "a stone wall face inside a narrow passage",
    "construction_part:plafond": "the flat stone ceiling of a burial chamber",
    "construction_part:linteaux": "heavy granite lintel blocks above a passage",
    "material:blocs_de_pierre": "huge rough-cut limestone blocks",
    "material:granite_blocks": "polished rose granite blocks",
    "material:pierres_calcaires_blanches": "smooth white limestone casing stones",
    "passage:corridor": "a narrow stone passageway cut through limestone masonry",
    "passage:couloir_ascendant": "a narrow ascending stone passageway",
    "passage:couloir_descendant": "a narrow descending stone passageway",
    "passage:galerie": "a narrow stone gallery inside the pyramid",
    "passage:grande_galerie": "the Grand Gallery, a tall corbelled stone passageway",
    "passage:boyau": "a tight rough-hewn tunnel",
    "room:chambre_funeraire": "the granite burial chamber",
    "room:chambre_de_decharge": "a relieving chamber above the King's Chamber",
    "room:chambre_du_roi": "the King's Chamber with granite walls",
    "room:chambre_de_la_reine": "the Queen's Chamber",
    "room:antichambre": "a small stone antechamber",
    "mechanism:systeme_de_decharge": "the relieving chambers built above the King's Chamber",
    "mechanism:herses_de_fermeture": "heavy granite portcullis slabs blocking a passage",
    "mechanism:blocs_bouchons": "large granite blocking plugs in a passage",
    "mechanism:pierre_mobile": "a movable stone slab used as a door",
    "opening:entree": "the original stone entrance passage of the pyramid",
    "opening:ouverture": "a narrow forced tunnel opening cut through masonry",
    "opening:niche": "a carved stone niche in a chamber wall",
    "opening:puits": "a vertical shaft cut down through bedrock",
    "artifact:sarcophage": "the empty granite sarcophagus in the burial chamber",
    "artifact:inscriptions": "red ochre quarry marks painted on stone blocks",
}

# Sujets qui sont déjà nommés dans le contexte : ne pas les répéter.
SUBJECT_IN_CONTEXT = {"structure:main:pyramide_de_kheops"}


def is_exterior(anchor_id: str) -> bool:
    return anchor_id in EXTERIOR_ANCHORS


def context_for(anchor_id: str) -> str:
    return CONTEXT_EXTERIOR if is_exterior(anchor_id) else CONTEXT_INTERIOR


# --------------------------------------------------------------------------- cadrages
# Cadrage déterminé par l'ancrage. Les ancrages "espace" ne reçoivent jamais de close-up.

FRAMING_BY_ANCHOR = {
    # vues d'ensemble
    "site:plateau_de_gizeh": "wide establishing shot",
    "structure:main:pyramide_de_kheops": "wide establishing shot",
    "structure:pyramide_de_khephren": "wide establishing shot, distant",

    # maçonnerie, matière
    "construction_part:stone_courses": "medium shot, low angle, raking light",
    "construction_part:socle_rocheux": "medium shot, low angle",
    "construction_part:revetement": "medium shot, grazing light",
    "construction_part:enceinte_a_redans": "medium wide shot",
    "construction_part:voute": "medium shot, looking up at the corbelled vault",
    "construction_part:mur": "medium shot, low angle, raking light",
    "construction_part:paroi": "medium shot, grazing light along the wall",
    "construction_part:plafond": "medium shot, looking up at flat ceiling slabs",
    "construction_part:linteaux": "medium shot, low angle on massive lintels",
    "material:blocs_de_pierre": "medium shot, shallow depth of field",
    "material:granite_blocks": "close-up, shallow depth of field",
    "material:pierres_calcaires_blanches": "medium shot, shallow depth of field",

    # circulations : le sujet est la profondeur
    "passage:corridor": "medium shot, leading lines into darkness",
    "passage:couloir_ascendant": "medium shot, looking up the slope",
    "passage:couloir_descendant": "medium shot, looking down the slope",
    "passage:galerie": "medium shot, leading lines",
    "passage:grande_galerie": "wide shot, looking up at the corbelled vault",
    "passage:boyau": "medium shot, confined framing",

    # volumes : jamais de close-up
    "room:chambre_funeraire": "medium wide shot, symmetrical framing",
    "room:chambre_de_decharge": "medium wide shot, low ceiling pressing down",
    "room:chambre_du_roi": "medium wide shot, symmetrical framing",
    "room:chambre_de_la_reine": "medium wide shot",
    "room:antichambre": "medium shot, confined framing",
    "mechanism:systeme_de_decharge": "wide shot, confined space, ceiling of stacked granite",
    "mechanism:herses_de_fermeture": "close-up detail shot, low angle",
    "mechanism:blocs_bouchons": "close-up detail shot",
    "mechanism:pierre_mobile": "close-up detail shot",

    # ouvertures
    "opening:entree": "medium shot, from outside toward the opening",
    "opening:ouverture": "medium shot, looking into a rough forced tunnel",
    "opening:niche": "medium shot, facing the niche squarely",
    "opening:puits": "medium shot, looking down into the shaft",

    # objets
    "artifact:sarcophage": "close-up detail shot, slightly above",
    "artifact:inscriptions": "close-up detail shot, raking light on painted marks",
}

DEFAULT_FRAMING = "medium shot"


def framing_for_v2(anchor_id: str) -> str:
    if anchor_id in FRAMING_BY_ANCHOR:
        return FRAMING_BY_ANCHOR[anchor_id]
    return FRAMING_BY_ANCHOR.get("*" + category_from_id(anchor_id), DEFAULT_FRAMING)


# Variantes utilisées seulement pour désambiguïser un ancrage répété.
VARIANT = {
    "wide establishing shot": [
        "wide establishing shot",
        "wide establishing shot, elevated three-quarter view",
        "wide establishing shot, low horizon, pyramid off-centre",
    ],
    "medium shot, facing the niche squarely": [
        "medium shot, facing the niche squarely",
        "medium close shot, side angle revealing the niche depth",
    ],
    "medium wide shot, symmetrical framing": [
        "medium wide shot, symmetrical framing",
        "medium wide shot, off-axis from a corner",
    ],
    "medium wide shot, low ceiling pressing down": [
        "medium wide shot, low ceiling pressing down",
        "medium shot, from the far corner",
    ],
    "close-up detail shot, slightly above": [
        "close-up detail shot, slightly above",
        "close-up, end of the sarcophagus in frame",
    ],
}


def _variant(prompt: str, base: str, occurrence: int, taken: set[str]) -> str:
    """Renvoie un prompt inédit en changeant le cadrage, sans jamais dupliquer."""
    options = VARIANT.get(base)
    if options:
        for shift in range(len(options)):
            candidate = options[(occurrence + shift) % len(options)]
            new = prompt.replace(f"Camera framing: {base}.", f"Camera framing: {candidate}.")
            if new not in taken:
                return new
    # Repli : ajout d'un qualificatif distinct pour chaque occurrence.
    extra = ["", ", centered on the main subject", ", wide angle",
             ", tight framing", ", from a lower position"][occurrence % 5]
    if extra:
        return prompt.replace(f"Camera framing: {base}.",
                              f"Camera framing: {base}{extra}.")
    # Dernier recours : suffixe explicite (n'altère pas l'objet, garantit l'unicité).
    return prompt.replace("Camera framing:", f"Variation {occurrence}. Camera framing:")


STYLE = "Documentary photograph, 35mm, natural colour, fine grain, no text, no people."


def english_subject(anchor_id: str) -> str:
    """Traduit via l'ancrage (jamais via le label seul, qui peut être ambigu).

    "corridor" seul n'est pas dans la table (le mot anglais existe aussi) ; c'est
    l'identifiant `passage:corridor` qui porte l'information. Aucun mot français
    ne doit subsister dans le prompt final.
    """
    by_id = SUBJECT_BY_ANCHOR.get(anchor_id)
    if by_id:
        return by_id
    raise ValueError(f"aucun sujet anglais défini pour l'ancrage {anchor_id!r} "
                     f"— ajouter une entrée à SUBJECT_BY_ANCHOR")


def build_prompt_v2(anchor_id: str, label: str) -> str:
    """Prompt complet : sujet traduit + contexte adapté + style + cadrage."""
    subject = english_subject(anchor_id)

    context = context_for(anchor_id)
    if anchor_id in SUBJECT_IN_CONTEXT:
        # Le sujet est déjà nommé dans le contexte : ne pas le répéter.
        prompt = (f"A realistic documentary photograph in a vertical 9:16 composition, "
                  f"{subject}, {context}.")
    else:
        prompt = (f"A realistic documentary photograph in a vertical 9:16 composition of "
                  f"{subject}, {context}.")

    framing = framing_for_v2(anchor_id)
    return f"{prompt} {STYLE} Camera framing: {framing}."


def build_image_prompts_v2(assignments, log=None) -> list[dict]:
    """Construit les 23 prompts, garantit l'unicité et journalise exclusions/doublons."""
    taken: set[str] = set()
    counts: dict[str, int] = {}
    out = []

    for item in assignments:
        anchor_id = item.get("anchor_id", "")
        label = item.get("label", "")
        if label.strip().casefold() in EXCLUDED:
            if log:
                log(f"image {item.get('image_index')} : ancrage exclu {label!r}")
            continue

        prompt = build_prompt_v2(anchor_id, label)
        occurrence = counts.get(anchor_id, 0)
        counts[anchor_id] = occurrence + 1

        if prompt in taken:
            base = framing_for_v2(anchor_id)
            prompt = _variant(prompt, base, occurrence, taken)
        if prompt in taken:
            raise ValueError(
                f"impossible de rendre unique l'image {item.get('image_index')} "
                f"(ancrage {anchor_id!r})")

        taken.add(prompt)
        out.append({"image_index": item.get("image_index"), "anchor_id": anchor_id,
                    "label": label, "prompt": prompt,
                    "scene": item.get("scene"), "exterior": is_exterior(anchor_id)})
    return out
