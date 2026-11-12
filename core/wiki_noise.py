"""Remove Wikipedia interface text before it becomes narration or metadata."""

import re


_WORDS = re.compile(r"\b[\wÀ-ÖØ-öø-ÿ]+(?:['’][\wÀ-ÖØ-öø-ÿ]+)?\b", re.UNICODE)
_UI_WORDS = {
    "modifier", "code", "wikidata", "wikimedia", "commons", "discussion",
    "historique", "contributions", "créer", "rediriger", "renommer",
    "portail", "catégorie", "catégories", "notes", "références", "annexes",
}
_UI_START = {"modifier", "portail", "catégorie", "catégories", "notes", "références"}
_EDIT_PREFIX = re.compile(
    r"^\s*(?:(?:\[\s*)?modifier(?:\s+le\s+code|\s+wikidata)?"
    r"(?:\s*\])?\s*(?:[-–—|·]\s*)?)+",
    re.IGNORECASE,
)


def is_wiki_ui_noise(line: str) -> bool:
    """Identify a short standalone interface line, without domain vocabulary."""
    words = [word.casefold() for word in _WORDS.findall(line or "")]
    if not words:
        return False
    if words[0] in _UI_START:
        return True
    if len(words) > 12:
        return False
    hits = sum(word in _UI_WORDS for word in words)
    return hits >= 2 and hits / len(words) >= 0.5


def clean_wiki_ui_line(line: str) -> str:
    """Keep article prose following an edit toolbar when both share a paragraph."""
    line = str(line or "").strip()
    if not line:
        return ""
    match = _EDIT_PREFIX.match(line)
    if match:
        remainder = line[match.end():].strip(" -–—|·[]")
        if len(_WORDS.findall(remainder)) >= 6 and not is_wiki_ui_noise(remainder):
            return remainder
    return "" if is_wiki_ui_noise(line) else line
