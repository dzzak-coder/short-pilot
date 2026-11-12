"""Offline visual-density measurement from source text.

The extractor deliberately returns only phrases that occur verbatim in the
corpus.  It does not turn abstract narration into objects and does not depend
on whether the source came from a file or the Web.
"""
from __future__ import annotations

import math
import re
import unicodedata


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")
_SPACE = re.compile(r"\s+")
_COMPARISON_SPANS = (
    re.compile(r"\bplus\s+(?:haut|haute|grand|grande|petit|petite|long|longue)\w*\s+que\s+([^,;.]+)", re.I),
    re.compile(r"\b(?:contrairement\s+à|comparé(?:e)?\s+à|à\s+la\s+différence\s+de)\s+([^,;.]+)", re.I),
    re.compile(r"\brecord\b[^.;]*?\bjusqu['’]?en\b[^.;]*?\b(?:érection|construction)\s+de\s+([^,;.]+)", re.I),
    re.compile(r"\b(?:higher|larger|greater|taller)\s+than\s+([^,;.]+)", re.I),
    re.compile(r"\b(?:unlike|compared\s+with|compared\s+to|in\s+contrast\s+to)\s+([^,;.]+)", re.I),
)
_CONTEXT_MARKER = re.compile(
    r"\b(?:selon\s+(?:lequel|laquelle|lesquels|lesquelles)|d['’]après|"
    r"according\s+to|as\s+reported\s+by)\b", re.I)

# The patterns describe concrete, renderable subject classes.  Captured
# modifiers are retained in the canonical key, so a king's chamber and an
# underground chamber are distinct while repeated mentions are collapsed.
_CONCRETE_PATTERNS = (
    ("structure", re.compile(
        r"\b(?:pyramide(?:\s+de\s+(?!son\b|sa\b|ses\b|la\b|le\b|l['’])"
        r"[A-ZÀ-ÖØ-Þ][\w'’.-]+)?|complexe\s+funéraire|"
        r"temple|basilique|cathédrale|église|mosquée|palais|château|forteresse|"
        r"tour|pont|barrage|monument|édifice|building|pyramid|temple|palace|"
        r"castle|fortress|tower|bridge|dam)\b", re.I)),
    ("room", re.compile(
        r"\b(?:chambre(?:\s+(?:du\s+roi|de\s+la\s+reine|de\s+décharge|"
        r"souterraine|sépulcrale|funéraire))|appartements?\s+funéraires?|antichambre|"
        r"room(?:\s+of\s+the\s+[\w'’-]+)?|chamber(?:\s+of\s+the\s+[\w'’-]+)?)\b", re.I)),
    ("passage", re.compile(
        r"\b(?:grande\s+galerie|galerie|couloir(?:\s+(?:ascendant|descendant|horizontal))?|"
        r"corridor|tunnel|boyau|descenderie|passage|great\s+gallery|gallery|"
        r"corridor|tunnel|passage)\b", re.I)),
    ("opening", re.compile(
        r"\b(?:entrée|ouverture|porte|fenêtre|escalier|niche|puits|grotte|"
        r"entry|entrance|opening|door|window|staircase|niche|shaft|cave)\b", re.I)),
    ("construction_part", re.compile(
        r"\b(?:socle\s+rocheux|assises?\s+(?:de\s+la\s+pyramide|de\s+pierres?)?|"
        r"parement|revêtement(?:\s+de\s+calcaire)?|enceinte(?:\s+à\s+redans)?|"
        r"voûte(?:\s+en\s+[\w'’-]+)?|linteaux?|mur|plafond|paroi|toit|colonne|"
        r"fondation|façade|masonry|casing|enclosure|vault|lintel|wall|ceiling|"
        r"roof|column|foundation|facade)\b", re.I)),
    ("material", re.compile(
        r"\b(?:blocs?\s+(?:de|du|en)\s+(?:pierres?\s+)?(?:calcaire|granit(?:e)?(?:\s+rose)?|"
        r"pierre)|pierres?\s+calcaires?(?:\s+blanches?)?|granit(?:e)?(?:\s+rose)?|"
        r"calcaire|briques?|bois|acier|bronze|marbre|stone\s+blocks?|limestone|"
        r"granite|bricks?|wood|steel|bronze|marble)\b", re.I)),
    ("artifact", re.compile(
        r"\b(?:sarcophage|momie|cartouche|statue|statuette|sculpture|peinture|"
        r"inscriptions?|papyrus|tablette|outil|levier|traîneau|rampe|barque|"
        r"sarcophagus|mummy|cartouche|statue|sculpture|painting|inscriptions?|"
        r"papyrus|tablet|tool|lever|sled|ramp|boat)\b", re.I)),
    ("mechanism", re.compile(
        r"\b(?:blocs?\s+bouchons?|pierre\s+mobile|herses?\s+de\s+fermeture|"
        r"conduits?\s+(?:dits?\s+de\s+)?[«\"]?ventilation|système\s+de\s+décharge|"
        r"plug\s+blocks?|movable\s+stone|portcullis|ventilation\s+shafts?|"
        r"relieving\s+system)\b", re.I)),
    ("site", re.compile(
        r"\b(?:plateau\s+de\s+Gizeh|carrière(?:\s+de\s+[A-ZÀ-ÖØ-Þ][\w'’.-]+)?|"
        r"roche\s+naturelle|île|canal|port|quai|atelier|chantier|"
        r"Giza\s+plateau|quarry|natural\s+rock|island|canal|harbour|harbor|"
        r"dock|workshop|construction\s+site)\b", re.I)),
    ("vehicle_machine", re.compile(
        r"\b(?:machine|moteur|char|chariot|voiture|train|navire|avion|fusée|satellite|"
        r"ordinateur|téléphone|machine|engine|cart|automobile|train|ship|aircraft|rocket|"
        r"satellite|computer|phone)\b", re.I)),
)


def _canonical(text: str) -> str:
    value = "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                    if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _identity(category: str, label: str, source_title: str) -> str:
    """Collapse lexical aliases without merging genuinely different objects."""
    value = _canonical(label)
    title = _canonical(source_title)
    if category == "structure":
        if value in {"monument", "edifice", "pyramide"}:
            return f"main:{title or value}"
        if ("pyramide de kheops" in title
                and value in {"pyramide de kheops", "pyramide de gizeh"}):
            return f"main:{title}"
    if category == "construction_part":
        if value.startswith("revetement") or value == "parement":
            return "casing"
        if value.startswith("assise"):
            return "stone_courses"
    if category == "material":
        if "granit" in value:
            return "granite_blocks"
        if "calcaire" in value:
            return "limestone_blocks"
    if category == "artifact" and value in {"inscription", "inscriptions"}:
        return "inscriptions"
    return value


def _inside_comparison_object(sentence: str, start: int, end: int) -> bool:
    """True only for the compared object, not every object in that sentence."""
    for pattern in _COMPARISON_SPANS:
        for marker in pattern.finditer(sentence):
            object_start, object_end = marker.span(1)
            if start < object_end and end > object_start:
                return True
    return False


def _scope_for_occurrence(sentence: str, start: int) -> tuple[str, str | None]:
    marker = _CONTEXT_MARKER.search(sentence)
    if marker and start >= marker.end():
        return "contextual", "Objet rapporté par une source ou hypothèse historique"
    return "principal", None


def extract_visual_anchors(corpus_sources) -> list[dict]:
    """Return distinct concrete anchors with source-verbatim evidence."""
    anchors: list[dict] = []
    by_key: dict[tuple[str, str], dict] = {}
    for source_index, raw_source in enumerate(corpus_sources or []):
        source = raw_source if isinstance(raw_source, dict) else {"text": str(raw_source)}
        text = _SPACE.sub(" ", str(source.get("text") or "")).strip()
        if not text:
            continue
        for sentence_index, sentence in enumerate(_SENTENCE_SPLIT.split(text)):
            for category, pattern in _CONCRETE_PATTERNS:
                for match in pattern.finditer(sentence):
                    label = _SPACE.sub(" ", match.group(0)).strip(" ,.;:()[]")
                    if _inside_comparison_object(sentence, match.start(), match.end()):
                        continue
                    key = (category, _identity(category, label, str(source.get("title") or "")))
                    if not key[1]:
                        continue
                    scope, scope_reason = _scope_for_occurrence(sentence, match.start())
                    existing = by_key.get(key)
                    if existing:
                        if sentence.strip() not in existing["evidence_sentences"]:
                            existing["evidence_sentences"].append(sentence.strip())
                        if existing["scope"] == "contextual" and scope == "principal":
                            existing["scope"] = "principal"
                            existing["scope_reason"] = None
                        continue
                    anchor = {
                        "id": f"{category}:{key[1].replace(' ', '_')}",
                        "label": label,
                        "category": category,
                        "scope": scope,
                        "scope_reason": scope_reason,
                        "source_index": source_index,
                        "source_title": str(source.get("title") or ""),
                        "sentence_index": sentence_index,
                        "evidence": sentence.strip(),
                        "evidence_sentences": [sentence.strip()],
                    }
                    by_key[key] = anchor
                    anchors.append(anchor)
    return anchors


_STOPWORDS = {
    "avec", "avoir", "cette", "comme", "dans", "depuis", "elle", "elles", "entre",
    "faire", "furent", "mais", "meme", "memes", "plus", "pour", "reste", "sans",
    "sont", "sous", "tandis", "toutes", "tout", "tous", "vers", "ainsi", "alors",
    "ancien", "ancienne", "autre", "consideree", "donne", "durant", "fait", "grande",
    "grand", "haute", "humaine", "jusqu", "monde", "premiere", "record", "second",
    "seule", "tres", "about", "after", "before", "from", "have", "into", "same", "than", "that",
    "their", "these", "they", "this", "through", "were", "with", "which",
}
_TOKEN_ALIASES = {
    "chantier": "construction",
    "method": "construction",
    "methode": "construction",
    "architectural": "construction",
    "architecturale": "construction",
    "edifiee": "construction",
    "pyramid": "pyramide",
}
_VISUAL_BRIDGE_TERMS = {
    "base", "carree", "construction", "egypte", "funeraire", "gizeh", "tombeau",
}


def _tokens(text: str) -> set[str]:
    normalized = _canonical(text)
    tokens = set()
    for token in normalized.split():
        if len(token) < 4 or token in _STOPWORDS:
            continue
        for suffix in ("ements", "ement", "ations", "ation", "iques", "ique", "es", "s"):
            if token.endswith(suffix) and len(token) - len(suffix) >= 4:
                token = token[:-len(suffix)]
                break
        token = _TOKEN_ALIASES.get(token, token)
        if token not in _STOPWORDS:
            tokens.add(token)
    return tokens


_BASE_SUBJECT_IDS = {
    "construction_part:stone_courses",
    "construction_part:socle_rocheux",
    "site:roche_naturelle",
    "site:plateau_de_gizeh",
}
_CASING_SUBJECT_IDS = {
    "construction_part:casing",
    "material:limestone_blocks",
}


def _visual_subject_id(anchor: dict) -> str:
    """Collapse labels that would produce the same recognisable shot."""
    anchor_id = str(anchor.get("id") or "")
    if anchor_id in _BASE_SUBJECT_IDS:
        return "visual_subject:site_base"
    if anchor_id in _CASING_SUBJECT_IDS:
        return "visual_subject:outer_casing"
    return f"visual_subject:{anchor_id}"


def distribute_visual_anchors(scenes, anchors, *, visual_briefs=None,
                              generic_terms=None, max_implicit_scenes=3) -> dict:
    """Measure lexical source support per narration scene, without inventing links."""
    briefs = visual_briefs or []
    principal = [anchor for anchor in anchors if anchor.get("scope") == "principal"]
    title_tokens = set()
    for anchor in principal:
        title_tokens |= _tokens(anchor.get("source_title", ""))
    scene_list = list(scenes or [])
    scene_queries = []
    for index, scene in enumerate(scene_list):
        proposition = ""
        if index < len(briefs) and isinstance(briefs[index], dict):
            proposition = briefs[index].get("visual_proposition") or ""
        scene_queries.append(_tokens(f"{scene} {proposition}"))
    token_scene_counts = {
        token: sum(token in query for query in scene_queries)
        for token in set().union(*scene_queries) if scene_queries
    }
    computed_generic_terms = {
        token for token, count in token_scene_counts.items()
        if count / len(scene_queries) > .30
    } if scene_queries else set()
    generic_terms_fixed = generic_terms is not None
    generic_terms = (set(generic_terms) if generic_terms_fixed
                     else computed_generic_terms)

    rows = []
    anchor_by_id = {anchor["id"]: anchor for anchor in principal}
    for index, scene in enumerate(scene_list):
        query_tokens = scene_queries[index]
        meaningful_query = query_tokens - title_tokens
        matches = []
        for anchor in principal:
            label_tokens = _tokens(anchor.get("label", ""))
            evidence_tokens = set()
            for evidence in anchor.get("evidence_sentences") or [anchor.get("evidence", "")]:
                evidence_tokens |= _tokens(evidence)
            label_overlap = meaningful_query & (label_tokens - title_tokens)
            evidence_overlap = meaningful_query & (evidence_tokens - title_tokens)
            matched_terms = label_overlap | evidence_overlap
            specific_terms = matched_terms - generic_terms
            main_subject_match = bool(
                query_tokens & title_tokens and anchor["id"].startswith("structure:main:"))
            evidence_match = (len(evidence_overlap) >= 2
                              or bool(evidence_overlap & _VISUAL_BRIDGE_TERMS))
            if not (main_subject_match or label_overlap or evidence_match):
                continue
            score = 3 * len(label_overlap) + len(evidence_overlap)
            # A frequent scene-wide word (for example "construction") cannot
            # create an assignment by itself.  Weak matches survive only when
            # their one signal is specific rather than the article subject.
            if not specific_terms and score < 2:
                continue
            if label_overlap:
                match_reason = "direct_label"
            elif main_subject_match:
                match_reason = "explicit_main_subject"
            else:
                match_reason = "indirect_evidence"
            matches.append({"anchor_id": anchor["id"], "label": anchor["label"],
                            "visual_subject_id": _visual_subject_id(anchor),
                            "score": score,
                            "match_reason": match_reason,
                            "matched_terms": sorted(matched_terms),
                            "specific_terms": sorted(specific_terms)})
        matches.sort(key=lambda item: (-item["score"], item["label"].casefold()))
        rows.append({"scene_index": index + 1, "narration": str(scene),
                     "anchors_available": len(matches), "anchors": matches})

    # Evidence-sentence overlap is useful but can otherwise leak one object
    # through an entire section.  Keep every explicit label/main-subject match;
    # retain at most three indirect occurrences in total after those explicit
    # assignments, choosing the strongest evidence deterministically.
    occurrences: dict[str, list[tuple[int, dict]]] = {}
    for row_index, row in enumerate(rows):
        for match in row["anchors"]:
            occurrences.setdefault(match["anchor_id"], []).append((row_index, match))
    keep_occurrences: set[tuple[int, str]] = set()
    capped_anchors = []
    for anchor_id, items in occurrences.items():
        explicit = [(row_index, match) for row_index, match in items
                    if match["match_reason"] != "indirect_evidence"]
        indirect = [(row_index, match) for row_index, match in items
                    if match["match_reason"] == "indirect_evidence"]
        for row_index, _ in explicit:
            keep_occurrences.add((row_index, anchor_id))
        allowance = max(0, int(max_implicit_scenes) - len(explicit))
        ranked_indirect = sorted(
            indirect,
            key=lambda item: (-item[1]["score"], -len(item[1]["specific_terms"]), item[0]))
        for row_index, _ in ranked_indirect[:allowance]:
            keep_occurrences.add((row_index, anchor_id))
        if len(indirect) > allowance:
            capped_anchors.append({
                "anchor_id": anchor_id,
                "implicit_matches_before": len(indirect),
                "implicit_matches_retained": allowance,
                "explicit_matches_retained": len(explicit),
            })
    usage: dict[str, dict] = {}
    for row_index, row in enumerate(rows):
        row["anchors"] = [match for match in row["anchors"]
                          if (row_index, match["anchor_id"]) in keep_occurrences]
        row["anchors_available"] = len(row["anchors"])
        for match in row["anchors"]:
            item = usage.setdefault(match["anchor_id"], {
                "anchor_id": match["anchor_id"], "label": match["label"],
                "scene_indices": [],
            })
            item["scene_indices"].append(row_index + 1)
    zero = [row["scene_index"] for row in rows if row["anchors_available"] == 0]
    one = [row["scene_index"] for row in rows if row["anchors_available"] == 1]
    multiple = [row["scene_index"] for row in rows if row["anchors_available"] >= 2]
    reuse = []
    for item in sorted(usage.values(), key=lambda value: value["label"].casefold()):
        scene_count = len(item["scene_indices"])
        reuse.append({**item, "scene_count": scene_count,
                      "reuse_count": max(0, scene_count - 1),
                      "scene_share_rate": round(scene_count / len(rows), 4) if rows else 0.0})
    subject_usage: dict[str, dict] = {}
    for anchor_id, item in usage.items():
        subject_id = _visual_subject_id(anchor_by_id[anchor_id])
        subject = subject_usage.setdefault(subject_id, {
            "visual_subject_id": subject_id, "anchor_ids": [], "labels": [],
            "scene_indices": set(),
        })
        subject["anchor_ids"].append(anchor_id)
        subject["labels"].append(item["label"])
        subject["scene_indices"].update(item["scene_indices"])
    visual_subjects = []
    for subject in sorted(subject_usage.values(), key=lambda value: value["visual_subject_id"]):
        scene_indices = sorted(subject["scene_indices"])
        visual_subjects.append({
            **subject,
            "anchor_ids": sorted(subject["anchor_ids"]),
            "labels": sorted(set(subject["labels"]), key=str.casefold),
            "scene_indices": scene_indices,
            "scene_count": len(scene_indices),
            "scene_share_rate": round(len(scene_indices) / len(rows), 4) if rows else 0.0,
        })
    scene_count = len(rows)
    orphan_rate = round(len(zero) / scene_count, 4) if scene_count else 0.0
    return {
        "primary_decision_metric": {
            "name": "scenes_without_anchor_rate",
            "value": orphan_rate,
        },
        "scene_count": scene_count,
        "scenes_without_anchor": len(zero),
        "scenes_without_anchor_rate": orphan_rate,
        "coverage_rate": round(1.0 - orphan_rate, 4) if scene_count else 0.0,
        "scenes_with_0_anchors": len(zero),
        "scenes_with_1_anchor": len(one),
        "scenes_with_2plus_anchors": len(multiple),
        "orphan_scene_indices": zero,
        "orphan_scenes": [rows[index - 1]["narration"] for index in zero],
        "generic_terms_excluded_as_sole_signal": sorted(generic_terms),
        "generic_terms_fixed_for_comparison": generic_terms_fixed,
        "implicit_match_scene_cap": int(max_implicit_scenes),
        "anchors_with_implicit_matches_capped": sorted(
            capped_anchors, key=lambda item: item["anchor_id"]),
        "distinct_anchors_used": len(usage),
        "visually_distinct_subjects": len(visual_subjects),
        "visual_subjects": visual_subjects,
        "anchor_reuse": reuse,
        "scenes": rows,
    }


def visual_budget(duration_seconds, anchors_available, *, seconds_per_image=4.0,
                  corpus_word_count=0, anchors_before=None, scene_count=None,
                  scenes_without_anchor=None, visually_distinct_subjects=None) -> dict:
    """Measure source density against the requested duration, not its origin."""
    seconds_per_image = float(seconds_per_image)
    if not 3.0 <= seconds_per_image <= 5.0:
        raise ValueError("seconds_per_image doit être compris entre 3 et 5")
    duration_seconds = max(0.0, float(duration_seconds or 0))
    available = max(0, int(anchors_available or 0))
    images_planned = (int(math.floor(duration_seconds / seconds_per_image + .5))
                      if duration_seconds else 0)
    images_needed = images_planned
    required_min = int(math.ceil(images_needed * .50))
    required_max = int(math.ceil(images_needed * .60))
    total_scenes = max(0, int(scene_count or 0))
    orphan_scenes = max(0, min(total_scenes, int(scenes_without_anchor or 0)))
    orphan_rate = orphan_scenes / total_scenes if total_scenes else None
    coverage_rate = 1.0 - orphan_rate if orphan_rate is not None else None
    if orphan_rate is not None and orphan_rate <= .20:
        verdict = "sufficient"
    elif orphan_rate is not None and orphan_rate <= .30:
        verdict = "thin"
    elif orphan_rate is not None:
        verdict = "insufficient"
    elif available >= required_max:
        verdict = "sufficient"
    elif available >= required_min:
        verdict = "thin"
    else:
        verdict = "insufficient"
    sustainable_duration = (duration_seconds if verdict == "sufficient" else
                            duration_seconds * coverage_rate
                            if coverage_rate is not None else duration_seconds)
    report = {
        "duration_seconds": duration_seconds,
        "seconds_per_image": seconds_per_image,
        "max_seconds_per_image": 7.0,
        "images_planned": images_planned,
        "images_needed": images_needed,
        "images_needed_range": {
            "at_5_seconds": int(math.ceil(duration_seconds / 5.0)) if duration_seconds else 0,
            "at_3_seconds": int(math.ceil(duration_seconds / 3.0)) if duration_seconds else 0,
        },
        "anchors_available": available,
        "visually_distinct_subjects": max(
            0, int(visually_distinct_subjects if visually_distinct_subjects is not None else available)),
        "anchors_required": {"minimum_50_percent": required_min,
                             "target_60_percent": required_max},
        "verdict": verdict,
        "corpus_word_count": int(corpus_word_count or 0),
        "anchor_density_per_1000_words": (
            round(available * 1000 / corpus_word_count, 2) if corpus_word_count else 0.0),
        "scene_coverage": {
            "total_scenes": total_scenes,
            "scenes_without_anchor": orphan_scenes,
            "scenes_without_anchor_rate": round(orphan_rate, 4) if orphan_rate is not None else None,
            "coverage_rate": round(coverage_rate, 4) if coverage_rate is not None else None,
            "thin_threshold_max_orphan_rate": .30,
        },
        "sustainable_duration_seconds": round(sustainable_duration, 1),
    }
    if anchors_before is not None:
        report["anchors_available_before_corpus"] = max(0, int(anchors_before))
        report["anchors_gain"] = available - report["anchors_available_before_corpus"]
    return report


def _allocate_bounded_duration(weights, image_counts, total_duration):
    minimums = [3.0 * count for count in image_counts]
    maximums = [4.0 * count for count in image_counts]
    if not sum(minimums) <= total_duration <= sum(maximums):
        raise ValueError("La durée cible est incompatible avec la plage de 3 à 4 s par image")
    values = list(minimums)
    remaining = total_duration - sum(values)
    active = {index for index in range(len(values)) if maximums[index] > values[index]}
    while remaining > 1e-9 and active:
        weight_sum = sum(max(.01, weights[index]) for index in active)
        consumed = 0.0
        for index in list(active):
            share = remaining * max(.01, weights[index]) / weight_sum
            addition = min(share, maximums[index] - values[index])
            values[index] += addition
            consumed += addition
            if maximums[index] - values[index] <= 1e-9:
                active.remove(index)
        if consumed <= 1e-9:
            break
        remaining -= consumed
    values[-1] += total_duration - sum(values)
    return values


def plan_image_schedule(scenes, distribution, *, duration_seconds,
                        seconds_per_image=4.0, max_seconds_per_image=7.0,
                        max_anchor_scene_reuse=3, max_reframe_rate=.25,
                        corpus_anchors=None):
    """Create an ordered, offline image schedule from validated assignments."""
    scene_list = [str(scene) for scene in (scenes or [])]
    rows = distribution.get("scenes") or []
    if len(rows) != len(scene_list) or not scene_list:
        raise ValueError("La distribution doit contenir exactement une ligne par scène")
    target_images = int(math.floor(float(duration_seconds) / float(seconds_per_image) + .5))
    if target_images < len(scene_list):
        raise ValueError("La durée cible ne permet pas une image par scène")
    image_counts = [1] * len(scene_list)
    extra = target_images - len(scene_list)
    candidates = sorted(
        range(len(scene_list)),
        key=lambda index: (
            -(rows[index].get("anchors_available") or 0),
            -len(_tokens(scene_list[index])),
            index,
        ),
    )
    cursor = 0
    while extra:
        if not candidates:
            raise ValueError("Aucune scène ne peut recevoir les images supplémentaires")
        index = candidates[cursor % len(candidates)]
        if rows[index].get("anchors_available", 0) >= image_counts[index] + 1:
            image_counts[index] += 1
            extra -= 1
        cursor += 1
        if cursor > len(candidates) * (target_images + 1):
            raise ValueError("Ancrages distincts insuffisants pour la durée demandée")

    weights = [max(1, len(_tokens(scene))) for scene in scene_list]
    scene_durations = _allocate_bounded_duration(weights, image_counts, float(duration_seconds))
    anchor_scene_usage: dict[str, set[int]] = {}
    anchor_image_usage: dict[str, int] = {}
    schedule = []
    max_reframed_images = int(math.floor(target_images * max_reframe_rate))
    reframed_images = 0
    principal_corpus = [anchor for anchor in (corpus_anchors or [])
                        if anchor.get("scope") == "principal"]

    def eligible(anchor_id, scene_index, used_here):
        if anchor_id in used_here:
            return False
        used_scenes = anchor_scene_usage.get(anchor_id, set())
        if not (scene_index in used_scenes or len(used_scenes) < max_anchor_scene_reuse):
            return False
        return not (anchor_image_usage.get(anchor_id, 0) > 0
                    and reframed_images >= max_reframed_images)

    for row_index, (row, count, scene_duration) in enumerate(
            zip(rows, image_counts, scene_durations)):
        scene_index = row_index + 1
        direct = list(row.get("anchors") or [])
        used_here = set()
        for image_offset in range(count):
            direct_candidates = [item for item in direct
                                 if eligible(item["anchor_id"], scene_index, used_here)]
            reason = "direct"
            pool = direct_candidates
            if not pool:
                neighbor_pool = []
                for distance in range(1, len(rows)):
                    for neighbor in (row_index - distance, row_index + distance):
                        if not 0 <= neighbor < len(rows):
                            continue
                        neighbor_pool.extend([
                            item for item in rows[neighbor].get("anchors") or []
                            if eligible(item["anchor_id"], scene_index, used_here)
                        ])
                    if neighbor_pool:
                        break
                pool = neighbor_pool
                reason = "continuity"
            if not pool and principal_corpus:
                scene_tokens = _tokens(scene_list[row_index])
                coherent = []
                for anchor in principal_corpus:
                    if not eligible(anchor["id"], scene_index, used_here):
                        continue
                    anchor_tokens = _tokens(anchor.get("label", ""))
                    for evidence in anchor.get("evidence_sentences") or [anchor.get("evidence", "")]:
                        anchor_tokens |= _tokens(evidence)
                    overlap = scene_tokens & anchor_tokens
                    if overlap:
                        coherent.append({"anchor_id": anchor["id"], "score": len(overlap)})
                pool = coherent
                reason = "corpus_coherent"
            if not pool:
                raise ValueError(
                    f"Scène {scene_index}: aucun ancrage distinct disponible; réduire la durée")
            chosen = min(
                pool,
                key=lambda item: (
                    anchor_image_usage.get(item["anchor_id"], 0) > 0,
                    anchor_image_usage.get(item["anchor_id"], 0),
                    -item.get("score", 0),
                    item["anchor_id"],
                ),
            )
            anchor_id = chosen["anchor_id"]
            reused = anchor_image_usage.get(anchor_id, 0) > 0
            if reused:
                reframed_images += 1
            used_here.add(anchor_id)
            anchor_scene_usage.setdefault(anchor_id, set()).add(scene_index)
            anchor_image_usage[anchor_id] = anchor_image_usage.get(anchor_id, 0) + 1
            schedule.append({
                "scene_index": scene_index,
                "image_index": len(schedule) + 1,
                "anchor_id": anchor_id,
                "duration_seconds": round(scene_duration / count, 3),
                "assignment_reason": reason,
                "reframed_reuse": reused,
            })
    duration_error = float(duration_seconds) - sum(item["duration_seconds"] for item in schedule)
    schedule[-1]["duration_seconds"] = round(
        schedule[-1]["duration_seconds"] + duration_error, 3)
    reframed = sum(bool(item["reframed_reuse"]) for item in schedule)
    reframe_rate = reframed / len(schedule) if schedule else 0.0
    max_duration = max(item["duration_seconds"] for item in schedule)
    min_duration = min(item["duration_seconds"] for item in schedule)
    max_reuse = max((len(indices) for indices in anchor_scene_usage.values()), default=0)
    accepted = (max_duration <= max_seconds_per_image and min_duration >= 3.0
                and reframe_rate <= max_reframe_rate
                and max_reuse <= max_anchor_scene_reuse)
    return {
        "selection_accepted": accepted,
        "images_planned": target_images,
        "seconds_per_image": float(seconds_per_image),
        "min_seconds_per_image": 3.0,
        "max_seconds_per_image": float(max_seconds_per_image),
        "minimum_image_duration_seconds": round(min_duration, 3),
        "maximum_image_duration_seconds": round(max_duration, 3),
        "reframed_images": reframed,
        "reframe_rate": round(reframe_rate, 4),
        "max_reframe_rate": float(max_reframe_rate),
        "maximum_anchor_scene_reuse": max_reuse,
        "max_anchor_scene_reuse": int(max_anchor_scene_reuse),
        "images": schedule,
    }
