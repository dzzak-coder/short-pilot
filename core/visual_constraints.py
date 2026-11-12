"""Pure textual scene contracts. No model loading, geometry or image operations."""
import re


CATEGORIES = {"subject", "color", "count", "secondary", "state", "action", "setting", "lighting", "relation"}
STYLE = "realistic documentary photography, vertical 9:16 composition"


def unique_terms(terms):
    """Deduplicate comma-separated CLIP exclusions across all entry points."""
    result, seen = [], set()
    for value in terms:
        if not isinstance(value, str):
            raise ValueError("Les contraintes textuelles doivent être des chaînes")
        for part in value.split(","):
            part = " ".join(part.split())
            key = part.casefold()
            if key and key not in seen:
                seen.add(key)
                result.append(part)
    return result


def compile_atoms(facts, *, still_life=False, subject_type="object", human_mode="forbidden"):
    """Bind states and counterexamples to their owners, never ban all open objects."""
    positives, negatives = [], []
    for atom in facts:
        category, entity = atom.get("category"), str(atom.get("entity") or "").strip()
        term = str(atom.get("english") or "").strip()
        if category not in CATEGORIES or not term or len(term) > 230:
            raise ValueError("Contrainte atomique invalide ou trop longue")
        if category != "lighting" and not entity:
            raise ValueError("Une contrainte atomique doit nommer son sujet")
        if entity and not re.search(r"(?<!\w)" + re.escape(entity.casefold()) + r"(?!\w)", term.casefold()):
            if category in {"color", "count"}:
                term = f"{term} {entity}"
            elif category in {"action", "setting", "relation"}:
                term = f"{entity} {term}"
            elif category != "lighting":
                raise ValueError("Le fait anglais doit inclure son propriétaire anglais : " + entity)
        positives.append(term)
        exclusions = atom.get("negative_terms", [])
        if not isinstance(exclusions, list) or any(not isinstance(t, str) for t in exclusions):
            raise ValueError("negative_terms atomiques invalides")
        # Preserve functional numerals, labels and graduations on real objects.
        for negative in unique_terms(exclusions):
            if negative.casefold() in {"text", "words", "letters", "numbers", "digits", "markings", "labels"}:
                raise ValueError("Exclusion trop large : cibler overlay text/captions/watermark")
            if any(re.fullmatch(re.escape(negative.casefold()), p.casefold()) for p in positives):
                raise ValueError("Une exclusion contredit un fait demandé")
            negatives.append(negative)
        if category == "state":
            state, form = atom.get("state"), atom.get("form")
            if state not in {"open", "closed"} or form not in {"bound_volume", "container", "door", "other"}:
                raise ValueError("État ouvert/fermé ou forme physique manquant")
            if form == "bound_volume":
                if state == "closed":
                    positives.append(f"{entity} with opaque outer cover facing the camera and covers pressed together")
                    negatives.extend([f"open {entity}", f"{entity} with exposed interior pages"])
                else:
                    positives.append(f"{entity} open with interior pages visible")
                    negatives.append(f"closed {entity}")
            elif form == "container":
                if state == "closed":
                    positives.append(f"{entity} shut with exterior visible and opening fully covered")
                    negatives.append(f"open {entity}")
                else:
                    positives.append(f"{entity} with its opening visible")
                    negatives.append(f"closed {entity}")
            elif form == "door":
                positives.append(f"{entity} " + ("shut flush in its frame" if state == "closed" else "open clear of its frame"))
                negatives.append(f"{'open' if state == 'closed' else 'closed'} {entity}")
            else:
                negatives.append(f"{'open' if state == 'closed' else 'closed'} {entity}")
    # A landscape, animal in habitat, or human scene must retain its surroundings.
    restricted = still_life is True and subject_type == "object" and human_mode == "forbidden"
    if restricted:
        positives.append("uncluttered still life showing only the described objects")
        negatives.extend(["duplicate objects", "additional foreground objects", "unrequested accessories"])
    positives = list(dict.fromkeys(positives))
    negatives = unique_terms(negatives)
    # Check all atoms, including ones appearing after the exclusion was supplied.
    if any(re.search(r"(?<!\w)" + re.escape(n.casefold()) + r"(?!\w)", p.casefold())
           for p in positives for n in negatives):
        raise ValueError("Exclusion incompatible avec un fait visuel demandé")
    # Qwen's native encoder exposes a negative socket, but this Turbo workflow
    # uses CFG 1 and an empty negative prompt.  Mandatory scene limits must
    # therefore be stated positively in the natural-language prompt.
    if restricted:
        positives.append("no people are present")
    return {"positive_terms": list(dict.fromkeys(positives)), "negative_terms": negatives, "still_life": restricted}


def _without_owner(term, owner):
    """Remove a leading canonical owner without changing the remaining fact."""
    return re.sub(r"^\s*(?:a|an|the)?\s*" + re.escape(owner) + r"\s*", "", term,
                  count=1, flags=re.IGNORECASE).strip()


def _article(term):
    term = term.strip()
    if re.match(r"^(?:a|an|the)\b", term, re.IGNORECASE):
        return term
    return ("an " if term[:1].lower() in "aeiou" else "a ") + term


def compile_final_prompt(facts, *, still_life=False, human_mode="forbidden"):
    """Compile source-grounded facts into a coherent, owner-bound image brief."""
    if not facts:
        raise ValueError("Aucune contrainte positive à compiler")
    by_category = {}
    indexed_facts = []
    for index, original_fact in enumerate(facts):
        fact = {**original_fact, "_index": index}
        indexed_facts.append(fact)
        by_category.setdefault(fact["category"], []).append(fact)
    subjects = by_category.get("subject", [])
    if not subjects:
        raise ValueError("Sujet principal manquant")
    subject = subjects[0]
    used = {subject["_index"]}
    owner = subject["entity"].strip()
    colors = [fact["english"].strip() for fact in by_category.get("color", [])
              if fact.get("entity", "").strip().casefold() == owner.casefold()]
    # A colour fact that already includes the canonical entity is the most
    # natural subject phrase and proves the attribute remains correctly bound.
    subject_color = next((fact for fact in by_category.get("color", [])
                          if fact.get("entity", "").strip().casefold() == owner.casefold()), None)
    if subject_color:
        used.add(subject_color["_index"])
    subject_phrase = next((term for term in colors if re.search(r"(?<!\w)" + re.escape(owner) + r"(?!\w)", term, re.I)),
                          subject["english"].strip())
    settings = [fact["english"].strip() for fact in by_category.get("setting", [])
                if fact.get("entity", "").strip().casefold() == owner.casefold()]
    subject_setting = next((fact for fact in by_category.get("setting", [])
                            if fact.get("entity", "").strip().casefold() == owner.casefold()), None)
    if subject_setting:
        used.add(subject_setting["_index"])
    setting = _without_owner(subject_setting["english"], owner) if subject_setting else ""
    secondary = by_category.get("secondary", [])
    states = {fact.get("entity", "").strip().casefold(): fact for fact in by_category.get("state", [])}
    secondary_phrases = []
    state_sentences = []
    for fact in secondary:
        used.add(fact["_index"])
        secondary_owner = fact["entity"].strip()
        state = states.get(secondary_owner.casefold())
        phrase = fact["english"].strip()
        if state:
            used.add(state["_index"])
            state_term = state["english"].strip()
            phrase = state_term if re.search(r"(?<!\w)" + re.escape(secondary_owner) + r"(?!\w)", state_term, re.I) else phrase
            if state.get("form") == "bound_volume" and state.get("state") == "closed":
                state_sentences.append(
                    f"The {secondary_owner} has its opaque outer cover facing the camera with its covers pressed together, and no interior pages are visible"
                )
        secondary_phrases.append(_article(phrase))
    relations = [fact["english"].strip() for fact in by_category.get("relation", [])
                 if fact.get("entity", "").strip().casefold() == owner.casefold()]
    subject_relation = next((fact for fact in by_category.get("relation", [])
                             if fact.get("entity", "").strip().casefold() == owner.casefold()), None)
    relation = _without_owner(subject_relation["english"], owner) if subject_relation else ""
    if relation and secondary_phrases:
        # Replace a bare secondary canonical noun with its state-aware phrase.
        related_owner = secondary[0]["entity"].strip()
        relation = re.sub(r"\b" + re.escape(related_owner) + r"\b", secondary_phrases[0], relation,
                          flags=re.IGNORECASE)
    elif secondary_phrases:
        relation = "beside " + secondary_phrases[0]
    clauses = [_article(subject_phrase)]
    if setting:
        clauses.append(setting)
    if relation:
        clauses.append(relation)
    description = " ".join(clauses)
    lighting_fact = by_category.get("lighting", [None])[0]
    lighting = [lighting_fact["english"].strip()] if lighting_fact else []
    if lighting_fact:
        used.add(lighting_fact["_index"])
    description_sentence = f"A realistic documentary photograph in a vertical 9:16 composition of {description}"
    sentences = [description_sentence + "."]
    sentences.extend(sentence + "." for sentence in state_sentences)
    required_terms = [description_sentence]
    required_terms.extend(state_sentences)
    if lighting:
        lighting_sentence = f"The scene is illuminated by {lighting[0]}"
        sentences.append(lighting_sentence + ".")
        required_terms.append(lighting_sentence)
    if still_life and human_mode == "forbidden":
        still_life_sentence = "The uncluttered still life showing only the described objects contains no people"
        sentences.append(still_life_sentence + ".")
        required_terms.append(still_life_sentence)
    # Never trade source fidelity for a smoother sentence.  Facts not safely
    # fused above remain explicit, source-grounded clauses in the final prompt.
    for fact in indexed_facts:
        if fact["_index"] in used:
            continue
        detail = f"The scene visibly includes {fact['english'].strip()}"
        sentences.append(detail + ".")
        required_terms.append(detail)
    return " ".join(sentences), required_terms
