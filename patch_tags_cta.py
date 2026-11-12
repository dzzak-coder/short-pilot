import shutil, subprocess, sys, pathlib

p = pathlib.Path("core/sources.py")
raw = p.read_bytes().decode("utf-8")
crlf = "\r\n" in raw
src = raw.replace("\r\n", "\n")

BLOCK = '''_TAGS = {
    "actu": {"fr": ["actu", "actualite", "info", "news"],
             "en": ["news", "breakingnews", "worldnews", "currentevents"]},
    "jour": {"fr": ["histoire", "cejourla", "culturegenerale"],
             "en": ["history", "onthisday", "historyfacts"]},
    "science": {"fr": ["science", "sciences", "decouverte", "savoir"],
                "en": ["science", "discovery", "sciencefacts"]},
    "mythes": {"fr": ["ideesrecues", "mythes", "verite", "saviezvous"],
               "en": ["myths", "mythsdebunked", "factcheck", "didyouknow"]},
}

_CTAS = {
    "actu": {
        "fr": ["Abonne-toi pour suivre l'actualité de près.",
               "Abonne-toi pour ne rien rater des prochaines infos.",
               "Abonne-toi pour connaître la suite de l'histoire.",
               "Abonne-toi pour suivre l'évolution de la situation."],
        "en": ["Subscribe to follow the story as it unfolds.",
               "Subscribe so you don't miss the next update.",
               "Subscribe to find out what happens next."]},
    "jour": {
        "fr": ["Abonne-toi pour revivre l'histoire jour après jour.",
               "Abonne-toi pour découvrir les prochains événements.",
               "Abonne-toi pour connaître la suite de l'histoire.",
               "Abonne-toi pour suivre l'aventure."],
        "en": ["Subscribe to relive history day by day.",
               "Subscribe to discover the next event.",
               "Subscribe to follow the adventure."]},
    "science": {
        "fr": ["Abonne-toi pour découvrir les prochaines découvertes.",
               "Abonne-toi pour suivre l'aventure scientifique.",
               "Abonne-toi pour ne rien rater des prochaines vidéos.",
               "Abonne-toi pour en savoir plus sur le monde qui nous entoure."],
        "en": ["Subscribe for the next discovery.",
               "Subscribe to follow the scientific adventure.",
               "Subscribe so you don't miss the next videos."]},
    "mythes": {
        "fr": ["Abonne-toi pour démonter les prochaines idées reçues.",
               "Abonne-toi pour découvrir la vérité sur le prochain mythe.",
               "Abonne-toi pour ne rien rater des prochaines vidéos.",
               "Abonne-toi pour suivre l'aventure."],
        "en": ["Subscribe to bust the next myth.",
               "Subscribe to learn the truth about the next one.",
               "Subscribe so you don't miss the next videos."]},
}

_SKIP_TAG_WORDS = {"mythes", "vérités", "verites", "réalité", "realite", "histoire",
                   "science", "sciences", "actualité", "actualite", "découverte"}


def _tags_for(source_id, lang, title):
    """Hashtags propres à la rubrique (vide si rubrique inconnue)."""
    import re as _re
    if source_id not in _TAGS:
        return ""
    base = list(_TAGS[source_id].get(lang) or [])
    words = [w for w in _re.findall(r"[a-zà-ÿ]{6,}", (title or "").lower())
             if w not in _SKIP_TAG_WORDS]
    tags = list(dict.fromkeys(base + words[:2] + ["shorts", "reels"]))[:8]
    return " ".join("#" + t for t in tags)


def _pick_cta(source_id, lang, title=""):
    """Fin de vidéo tirée de la banque de la rubrique (vide si rubrique inconnue)."""
    bank = (_CTAS.get(source_id) or {}).get(lang) or []
    return random.choice(bank) if bank else ""


'''

def once(text, needle, label):
    n = text.count(needle)
    if n != 1:
        sys.exit(f"Point d'insertion « {label} » trouvé {n} fois (attendu 1). Rien n'est modifié.")

A1 = 'def generate(source_id, niche="sujet"'
A2 = '    cta = (written.get("cta") or "").strip() or webcontent._cta_for(niche, lang)'
A3 = 'names, urls[0] if urls else "")'
for needle, label in ((A1, "def generate"), (A2, "ligne cta"), (A3, "appel _caption")):
    once(src, needle, label)

src = src.replace(A1, BLOCK + A1)
src = src.replace(A2, '    cta = _pick_cta(source_id, lang, title) or (written.get("cta") or "").strip() or webcontent._cta_for(niche, lang)')
src = src.replace(A3, A3 + '\n    _tg = _tags_for(source_id, lang, title)\n    if _tg and hashtags:\n        caption = caption.replace(hashtags, _tg)\n        hashtags = _tg')

compile(src, "sources.py", "exec")
shutil.copy(p, "core/sources.py.bak_tags")
p.write_bytes((src.replace("\n", "\r\n") if crlf else src).encode("utf-8"))
print("core/sources.py modifié (sauvegarde : core/sources.py.bak_tags)")

chk = ("from core import sources as s; "
       "print(s._tags_for('mythes','fr','Les Mythes et Vérités sur les Requins')); "
       "print(s._tags_for('jour','fr','Le Parlement d Angleterre')); "
       "print(s._pick_cta('actu','fr')); print(s._pick_cta('science','en'))")
r = subprocess.run([sys.executable, "-c", chk], capture_output=True, text=True, encoding="utf-8")
print(r.stdout or r.stderr)
r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"],
                   capture_output=True, text=True, encoding="utf-8")
print((r.stderr or r.stdout)[-300:])
