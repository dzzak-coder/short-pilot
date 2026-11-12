import json, os, re, shutil, subprocess, sys, pathlib

def load(p):
    raw = pathlib.Path(p).read_bytes().decode("utf-8")
    return ("\r\n" in raw), raw.replace("\r\n", "\n")

def swap(text, old, new, label):
    n = text.count(old)
    if n != 1:
        sys.exit(f"« {label} » trouvé {n} fois (attendu 1). Rien n'est modifié.")
    return text.replace(old, new)

crlf_s, s = load("core/sources.py")
crlf_c, c = load("core/content.py")
if "_PRACTICAL_RX" not in s:
    sys.exit("Le correctif 6 n'est pas dans sources.py. Rien n'est modifié.")

# 1. regex promo / direct, définies avant _norm
s = swap(s, "def _norm(text):", r'''_PROMO_RX = re.compile(
    r"double live|plus de passion|suivez|revivez|notre live|notre direct|en direct sur|abonnez", re.I)
_LIVE_RX = re.compile(
    r"en direct|\blive\b|suivez|revivez|minute par minute|compositions? (?:probables?|officielles?)|"
    r"\bdirect\s*[:\-–—]", re.I)


def _norm(text):''', "def _norm")

# 2. phrases : promos et listes de noms
s = swap(s, "        if not (min_words <= words <= max_words) or _NOISE_RX.search(sentence):",
 '        if (not (min_words <= words <= max_words) or _NOISE_RX.search(sentence)\n'
 '                or _PROMO_RX.search(sentence) or sentence.count(",") >= 5):', "filtre phrases")

# 3. Actualité : écarter les directs
s = swap(s, "    items, key = _pick_news(feeds, topic, 10, avoid_repeat, log)\n",
         "    items, key = _pick_news(feeds, topic, 10, avoid_repeat, log, exclude=_LIVE_RX)\n", "appel actu")

# 4. prompt : titre, pas de comparaison inventée, pas de points de suspension
old = '''Les phrases s'enchaînent comme un récit continu sur UN seul sujet. "'''
new = old + '''\n           "Titre : majuscule seulement au début et aux noms propres, jamais à chaque mot ; ne promets jamais une résolution ou une révélation que les faits ne donnent pas. "\n           "Aucune comparaison, aucun exemple ni aucun détail absents des faits fournis. Pas de points de suspension. "'''
s = swap(s, old, new, "prompt fr")

# 5. angle mythe : structure idée reçue / réalité
myth = ("Le titre énonce une idée reçue. Alterne « On croit que » (idée répandue, formulée de façon générale) "
        "puis « En réalité » (le fait qui la corrige, tiré des faits numérotés), au moins trois fois. "
        "N'ajoute aucune croyance précise, aucun chiffre ni aucune comparaison que les faits ne soutiennent pas.")
s, n = re.subn(r'\("Structure en « idée répandue.*?soutiennent pas\."\)',
               lambda m: "(" + json.dumps(myth, ensure_ascii=False) + ")", s, count=1, flags=re.S)
if n != 1:
    sys.exit("Angle « mythe » introuvable. Rien n'est modifié.")

# 6. Mythes : sujets précis
topics = ["le cerveau", "le sommeil", "les requins", "le Moyen Âge", "l'alimentation",
 "le corps humain", "les dinosaures", "les pyramides d'Égypte", "les vikings", "le café",
 "les vaccins", "la Lune", "les chauves-souris", "les araignées", "les serpents",
 "le chocolat", "le sucre", "l'eau", "le rhume", "les cheveux", "les yeux", "les rêves",
 "la mémoire", "l'espace", "les châteaux forts", "les trous noirs", "la Grande Muraille de Chine",
 "Napoléon", "les gladiateurs", "les volcans", "la sorcellerie", "Christophe Colomb",
 "la foudre", "les caméléons", "les poissons rouges", "les tremblements de terre", "les éclipses",
 "les océans", "l'Antarctique", "le désert"]
block = "_MYTH_TOPICS = [" + ",\n                ".join(json.dumps(t, ensure_ascii=False) for t in topics) + "]"
s, n = re.subn(r"_MYTH_TOPICS = \[.*?\]", lambda m: block, s, count=1, flags=re.S)
if n != 1:
    sys.exit("Liste _MYTH_TOPICS introuvable. Rien n'est modifié.")

# 7. Mythes : écarter les pages de fiction
s = swap(s, "def _wiki_articles(topic, lang, queries, limit=3):", r'''_FICTION_RX = re.compile(
    r"\best (?:un|une) (?:s[ée]rie|film|manga|anime|album|jeu vid[ée]o|roman|bande dessin[ée]e|chanson|personnage)|"
    r"\best un (?:long[- ]m[ée]trage|dessin anim[ée])|"
    r"\bis an? (?:\w+ )?(?:series|film|manga|album|video game|novel)", re.I)


def _wiki_articles(topic, lang, queries, limit=3):''', "def _wiki_articles")
s = swap(s, '            if title in seen or re.search(r"homonymie|disambiguation", title, re.I):\n',
 '            if title in seen or re.search(r"homonymie|disambiguation", title, re.I) \\\n'
 '                    or _FICTION_RX.search((intro.get("text") or "")[:300]):\n', "fiction")

# 8. Mythes : tenter d'abord la page « idées reçues »
s = swap(s, '[subject, subject + " idées reçues", subject + " mythes et légendes"]',
         '[subject + " idées reçues", subject, subject + " mythes et légendes"]', "requêtes fr")
s = swap(s, '[subject, subject + " misconceptions", subject + " myths"]',
         '[subject + " misconceptions", subject, subject + " myths"]', "requêtes en")

# 9. hashtags : mots communs seulement + titre en minuscules sauf noms propres
func = r'''def _sentence_case_title(title, bundle):
    """Une majuscule n'est gardée que pour les noms propres présents dans les sources."""
    blob = " ".join((i.get("text") or "") + " " + (i.get("title") or "") for i in bundle["items"])

    def fix(m):
        w = m.group(0)
        if m.start() == 0:
            return w
        cap = re.search(r"(?<![\w])" + re.escape(w) + r"(?![\w])", blob)
        low = re.search(r"(?<![\w])" + re.escape(w.lower()) + r"(?![\w])", blob)
        return w if (cap and not low) else w.lower()

    return re.sub(r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+", fix, title or "")


def _tags_for(source_id, lang, title, bundle=None):
    """Hashtags de la rubrique + mots communs du titre (jamais de noms propres)."""
    if source_id not in _TAGS:
        return ""
    base = list(_TAGS[source_id].get(lang) or [])
    blob = " ".join((i.get("text") or "") for i in (bundle or {}).get("items", []))
    words = []
    for w in re.findall(r"[a-zà-ÿ]{6,}", (title or "").lower()):
        if w in _SKIP_TAG_WORDS or _norm(w) in words:
            continue
        if re.search(r"(?<![\w])" + re.escape(w) + r"(?![\w])", blob):
            words.append(_norm(w))
    tags = list(dict.fromkeys(base + words[:2] + ["shorts", "reels"]))[:8]
    return " ".join("#" + t for t in tags)


'''
s, n = re.subn(r"def _tags_for\(.*?(?=def _pick_cta\()", lambda m: func, s, count=1, flags=re.S)
if n != 1:
    sys.exit("Fonction _tags_for introuvable. Rien n'est modifié.")
s = swap(s, "    _tg = _tags_for(source_id, lang, title)\n", "    _tg = _tags_for(source_id, lang, title, bundle)\n", "appel _tags_for")
s = swap(s, '    title = _title_without_invented_dates((written.get("title") or scenes[0]).strip(), bundle)\n',
 '    title = _title_without_invented_dates((written.get("title") or scenes[0]).strip(), bundle)\n'
 '    title = _sentence_case_title(title, bundle)\n', "titre")
s = swap(s, '    if written.get("caption"):\n',
 '    if written.get("caption"):\n        written["caption"] = re.sub(r"\\s*#\\w+", "", written["caption"])\n', "légende")

# 10. phrases : ne plus couper après « … » quand la suite est en minuscule
c = swap(c, "def short_scenes(lines, max_words=22, grouped=False):", r'''_SCENE_SPLIT = re.compile(
    r"(?<=[.!?])(?<!\.\.)(?<!…)\s+|(?<=\.\.)\s+(?=[A-ZÀ-ÖØ-Þ«\"“0-9])|(?<=…)\s+(?=[A-ZÀ-ÖØ-Þ«\"“0-9])|\n+")


def short_scenes(lines, max_words=22, grouped=False):''', "short_scenes")
c = swap(c, '        for sentence in re.split(r"(?<=[.!?…])\\s+|\\n+", str(line or "")):',
         '        for sentence in _SCENE_SPLIT.split(str(line or "")):', "split")

compile(s, "sources.py", "exec"); compile(c, "content.py", "exec")
shutil.copy("core/sources.py", "core/sources.py.bak_p7")
shutil.copy("core/content.py", "core/content.py.bak_p7")
pathlib.Path("core/sources.py").write_bytes((s.replace("\n", "\r\n") if crlf_s else s).encode("utf-8"))
pathlib.Path("core/content.py").write_bytes((c.replace("\n", "\r\n") if crlf_c else c).encode("utf-8"))
print("OK : sources.py et content.py modifiés (sauvegardes .bak_p7)")

env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
chk = (
 "from core import sources as s, content as c\n"
 "b={'items':[{'title':'','text':'Désiré Doué marque. Les atouts du match sont clairs. Amelia Earhart a disparu. Un désert est sec.'}]}\n"
 "print(s._tags_for('actu','fr','Désiré Doué et Maghnes Akliouche : les atouts du PSG face à Villarreal', b))\n"
 "print(s._sentence_case_title('Les Mythes Des Déserts', b))\n"
 "print(s._sentence_case_title('L\\'Énigme Amelia Earhart Résolue ?', b))\n"
 "print(s._clean_sentences('Le XI de Lille : Ozer, Nagu, Niangou, Gasser, Verdonk, Kjaergaard, André, Balota, Mukau. Un but a été marqué par le joueur ce soir là.'))\n"
 "print(bool(s._PROMO_RX.search('C\\'est double live pour plus de passion !')), bool(s._LIVE_RX.search('Ligue des champions en direct : PSG')))\n"
 "print(bool(s._FICTION_RX.search('Saint Seiya est un manga de Masami Kurumada')), bool(s._FICTION_RX.search('Les requins sont des poissons')))\n"
 "print(c.short_scenes(['Le désert peut faire des averses… mais elles sont folles. Nouvelle phrase ici.']))\n")
r = subprocess.run([sys.executable, "-c", chk], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=env)
print(r.stdout or r.stderr)
r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
print((r.stderr or r.stdout)[-400:])
