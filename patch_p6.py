import os, shutil, subprocess, sys, pathlib

path = pathlib.Path("core/sources.py")
raw = path.read_bytes().decode("utf-8")
crlf = "\r\n" in raw
s = raw.replace("\r\n", "\n")

def swap(text, old, new, label):
    n = text.count(old)
    if n != 1:
        sys.exit(f"« {label} » trouvé {n} fois (attendu 1). Rien n'est modifié.")
    return text.replace(old, new)

# 1. Actualité : articles liés seulement si l'article principal est court
s = swap(s, "    for other in related[:4]:\n",
         "    for other in (related[:2] if _word_count(sources[0][\"text\"]) < 120 else []):\n", "articles liés")

# 2. Science : écarter les articles pratiques
s = swap(s, "def _pick_news(feeds, topic, max_age_days, avoid_repeat, log):",
         "def _pick_news(feeds, topic, max_age_days, avoid_repeat, log, exclude=None):", "signature _pick_news")
s = swap(s, "    items, errors = _load_feeds(feeds, max_age_days)\n    if not items:",
'''    items, errors = _load_feeds(feeds, max_age_days)
    if exclude is not None:
        kept_items = [i for i in items if not exclude.search(i["title"] + " " + i["summary"])]
        if len(kept_items) >= 3:
            items = kept_items
    if not items:''', "filtre exclude")
s = swap(s, "    items, key = _pick_news(feeds, topic, 45, avoid_repeat, log)",
         "    items, key = _pick_news(feeds, topic, 45, avoid_repeat, log, exclude=_PRACTICAL_RX)", "appel science")
s = swap(s, "def fetch_science(", '''_PRACTICAL_RX = re.compile(
    r"forfaits?|op[ée]rateurs?|esim|smartphones?|iphone|android|box internet|bon plan|promo|soldes|"
    r"guide d.achat|comparatif|meilleurs?\\b|comment (?:choisir|bien|installer|activer|r[ée]soudre|profiter)|"
    r"\\b5g\\b|wi-?fi|abonnements?|black friday", re.I)


def fetch_science(''', "regex pratique")

# 3. prompt : titre sans date inventée, récit continu
s = swap(s, "Première phrase = accroche forte. Termine par un appel à l'action court. \"",
 "Première phrase = accroche forte. Termine par un appel à l'action court. \"\n"
 "           \"Le titre ne contient aucune date ni jour précis, sauf si un fait fourni la donne. \"\n"
 "           \"Les phrases s'enchaînent comme un récit continu sur UN seul sujet. \"", "prompt fr")

# 4. contrôle des dates du titre
s = swap(s, "_TAGS = {\n", '''_DATE_RX = re.compile(
    r"\\b(?:du\\s+|le\\s+)?\\d{1,2}(?:er)?\\s+(?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|"
    r"septembre|octobre|novembre|d[ée]cembre)(?:\\s+\\d{4})?", re.I)


def _title_without_invented_dates(title, bundle):
    # retire du titre toute date absente de la matière source
    blob = _norm(" ".join((i.get("text") or "") + " " + (i.get("title") or "") for i in bundle["items"]))
    cleaned = _DATE_RX.sub(lambda m: m.group(0) if _norm(m.group(0)) in blob else "", title or "")
    cleaned = re.sub(r"\\s{2,}", " ", cleaned).strip(" :,-–—")
    return cleaned or title


_TAGS = {
''', "bloc dates")
s = swap(s, '    title = (written.get("title") or scenes[0]).strip()\n',
         '    title = _title_without_invented_dates((written.get("title") or scenes[0]).strip(), bundle)\n', "titre")

# 5. relance si < 90 % de la cible
s = swap(s, "if len(kept) >= 4 and total >= goal * .8:", "if len(kept) >= 4 and total >= goal * .9:", "seuil relance")

compile(s, "sources.py", "exec")
shutil.copy(path, "core/sources.py.bak_p6")
path.write_bytes((s.replace("\n", "\r\n") if crlf else s).encode("utf-8"))
print("OK : sources.py modifié (sauvegarde : core/sources.py.bak_p6)")

env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
chk = ("from core import sources as s; b={'items':[{'text':'Une manifestation a eu lieu.','title':'X'}]}; "
       "print(s._title_without_invented_dates('Manifestations du 17 Octobre : Réactions', b)); "
       "print(bool(s._PRACTICAL_RX.search('Quel forfait 5G choisir ?')), bool(s._PRACTICAL_RX.search('Une étoile découverte')))")
r = subprocess.run([sys.executable, "-c", chk], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=env)
print(r.stdout or r.stderr)
r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
print((r.stderr or r.stdout)[-300:])
