# -*- coding: utf-8 -*-
"""ShortPilot — contenu web infini pour l'onglet « Générer un script ».

La DURÉE CIBLE pilote la génération : le script est rempli jusqu'à ≈92 % du
temps demandé (puis le rendu cale la vidéo au centième près).
  • un short de 35 s → 1 article Wikipedia ;
  • 2 minutes → plusieurs articles enchaînés en « épisodes » ;
  • 5 minutes → jusqu'à 9 articles, tant que la matière reste fraîche ;
  • motivation / productivité → plusieurs citations enchaînées en chapitres.

Sources gratuites, sans clé :
  • Wikipedia — introductions complètes (MediaWiki extracts API), par catégorie
    de niche (avec exploration des sous-catégories), article aléatoire pour les
    faits insolites, recherche plein texte pour le « sujet libre » ;
  • ZenQuotes (citations) + traduction MyMemory — motivation / productivité ;
  • Useless Facts (EN) — faits insolites en anglais.

Garde-fous :
  • mémoire anti-répétition (signatures « web: » partagées, data/used.json) ;
  • quotas Wikipedia respectés : requêtes groupées (1 appel / 10 titres),
    listes en cache disque 20 h, backoff Retry-After sur 429 ;
  • phrases nettoyées pour la voix (parenthèses, espaces avant ponctuation) ;
  • chaque appel réseau a un timeout ; échec → None → repli banque locale ;
  • attribution : sources citées dans la légende (Wikipedia = CC BY-SA).
"""
import hashlib
import json
import math
import os
import random
import re
import time
import urllib.parse
import logging
import unicodedata
import threading
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser

import requests

from . import content as content_mod
from .wiki_noise import clean_wiki_ui_line

UA = {"User-Agent": "ShortPilot/1.4 (studio local de videos courtes; usage prive)"}
TIMEOUT = 12
MIN_TEXT = 150       # longueur minimale d'une introduction d'article
CACHE_TTL = 20 * 3600
MAX_ARTICLES = 9
BATCH = 10           # titres par requête groupée
_CACHE_LOCK = threading.RLock()
_NETWORK_STATE = threading.local()

# Niche → catégorie Wikipedia (FR / EN).
WIKI_CATS = {
    "psychologie": ("Catégorie:Psychologie", "Category:Psychology"),
    "argent": ("Catégorie:Finance", "Category:Personal finance"),
    "sante": ("Catégorie:Santé", "Category:Health"),
    "tech": ("Catégorie:Technologie", "Category:Technology"),
    "histoire": ("Catégorie:Histoire", "Category:History"),
}

# Accroches « web » — {T} = titre du sujet (initiale majuscule), {t} = minuscules.
WEB_HOOKS = {
    "fr": {
        "faits": ["{T} : le fait que personne ne connaît",
                  "Tu ne devineras jamais ça sur {t}",
                  "L'histoire incroyable de {t}"],
        "psychologie": ["{T} : ce que ça révèle de ton cerveau",
                        "Ton cerveau et {t} : la vérité",
                        "Ce que la science dit sur {t}"],
        "argent": ["{T} expliqué comme à un enfant de 10 ans",
                   "{T} : ce que les riches comprennent et pas toi",
                   "La vérité sur {t} que ta banque ne te dira pas"],
        "sante": ["{T} : ce que ton corps essaie de te dire",
                  "La science de {t} en quelques minutes",
                  "{T} : mythe ou réalité ?"],
        "tech": ["{T} : la techno qui va changer ta vie",
                 "{T} enfin expliqué simplement",
                 "Tu utilises {t} sans comprendre ça"],
        "histoire": ["{T} : l'histoire vraie en {D}",
                     "Le détail historique qui rend {t} fascinant",
                     "{T} : l'histoire derrière le nom"],
        "motivation": ["La phrase qui peut changer ta vie",
                       "À écouter chaque matin",
                       "Des mots qui débloquent tout"],
        "productivite": ["Le conseil qui double ta productivité",
                         "Pourquoi tu procrastines vraiment",
                         "La règle d'or des gens efficaces"],
        "sujet": ["{T} : l'essentiel en {D}",
                  "Le fait essentiel à connaître sur {t}",
                  "{T} : l'histoire derrière le sujet"],
    },
    "en": {
        "faits": ["{T}: the fact nobody knows",
                  "You'll never guess this about {t}",
                  "The unbelievable story of {t}"],
        "psychologie": ["{T}: what it says about your brain",
                        "Your brain vs {t}: the truth",
                        "What science really says about {t}"],
        "argent": ["{T} explained like you're 10",
                   "{T}: what rich people know and you don't",
                   "The truth about {t} your bank won't tell you"],
        "sante": ["{T}: what your body is trying to tell you",
                  "The science of {t} in a few minutes",
                  "{T}: myth or reality?"],
        "tech": ["{T}: the tech that will change your life",
                 "{T} finally explained simply",
                 "You use {t} daily without knowing this"],
        "histoire": ["{T}: the true story in {D}",
                     "The historical detail that makes {t} fascinating",
                     "{T}: the story behind the name"],
        "motivation": ["The one sentence that can change your life",
                       "Listen to this every morning",
                       "Words that unlock everything"],
        "productivite": ["The advice that doubles your productivity",
                         "Why you really procrastinate",
                         "The golden rule of efficient people"],
        "sujet": ["{T}: the essential in {D}",
                  "The key fact to know about {t}",
                  "{T}: the story behind the subject"],
    },
}

# A Wikipedia introduction is factual material, not yet a Short.  These beats
# create a clear spoken arc while leaving every factual assertion untouched.
STORY_BRIDGES = {
    "fr": [
        "Voilà le contexte de départ.",
        "Le point important arrive ensuite.",
        "C'est ce qui permet de comprendre la suite.",
        "Et cette conséquence explique son importance.",
    ],
    "en": [
        "That is the starting context.",
        "The important point comes next.",
        "This is what makes the next part understandable.",
        "And that consequence explains why it matters.",
    ],
}
STORY_PAYOFF = {
    "fr": "Voilà ce qu'il faut retenir sur {title}.",
    "en": "That is the key thing to remember about {title}.",
}

_SENT_RX = re.compile(r"(?<=[.!?…])\s+")
_WIKI_HEADING_RX = re.compile(r"={2,}\s*[^=\n]{1,120}\s*={2,}")
# Méta/contenu éditorial non racontable à voix haute
_bad_sent = re.compile(r"[\[\]{}|]|homonymie|redirection|Cet article|This article|"
                       r"est une commune|voir la page|may refer to|not to be confused", re.I)
# Titres « méta » sans intérêt narratif (années, listes, portails, notions-mères)
_META_RX = re.compile(r"^(Histoire$|Géographie$|Liste |Portail|Chronologie|Catégorie|Category:|"
                      r"Modèle|Wikipédia|Wikipedia:|Projet|Project:|Aide|Help:|Fichier|File:)", re.I)
_YEAR_RX = re.compile(r"^\d{1,4}( av\. J\.-C\.)?$")
_PAREN_RX = re.compile(r"\s*\([^)]*\)")
_STORY_SIGNAL_RX = re.compile(
    r"\b(mais|cependant|puis|ensuite|apres|avant|lorsque|alors|grace|cause|"
    r"permet|entraine|devient|construit|fonde|lance|attaque|guerre|bataille|"
    r"disparait|succede|premier|dernier|seul|record|retour|change|why|because|"
    r"after|before|then|became|built|founded|launched|war|battle|first|last)\b", re.I,
)
_BEAT_SPLIT_RX = re.compile(
    r"\s*(?:;|\s+[—–]\s+|,\s+(?=(?:puis|ensuite|mais|alors|lorsque|apres|après)\b))\s*",
    re.IGNORECASE,
)
_WEAK_STORY_TITLE_RX = re.compile(
    r"\b(?:historiographie|historiography|sociologie|sociology|cliométrie|"
    r"revue|journal|mémoire collective|collective memory|méthodologie|"
    r"théorie|concept|chronologie|liste|catégorie|category)\b", re.I,
)
_EVENT_WORD_RX = re.compile(
    r"\b(?:mission|vol|fusée|lancement|bataille|guerre|procès|explosion|"
    r"découverte|expédition|révolution|accord|crise|accident|attaque|"
    r"siège|conquête|débarquement|révolte|assassinat|disparition|sauvetage|"
    r"mission|flight|launch|battle|war|trial|discovery|expedition|"
    r"revolution|treaty|crash|attack|siege|landing)\b", re.I,
)
_NON_EVENT_TITLE_RX = re.compile(
    r"\b(?:film|roman|album|chanson|opéra|opera|pièce|piece|série|serie|jeu vidéo|"
    r"game|bande dessinée|bd|revue|journal)\b", re.I,
)
_NON_EVENT_LEAD_RX = re.compile(
    r"\b(?:revue|publication|journal|magazine|média|media|ouvrage|livre|film|roman|album|"
    r"chanson|série|jeu vidéo|bande dessinée|périodique|academic journal)\b", re.I,
)
# Queries return concrete historical material much more reliably than the
# enormous parent category "Histoire", whose members include journals,
# methodologies and philosophical periods.
HISTORY_STORY_QUERIES = {
    "fr": (
        "bataille historique", "expédition historique", "révolution historique",
        "mission spatiale historique", "catastrophe historique", "indépendance pays",
        "empire historique", "invention historique", "exploration historique",
        "citation historique attribuée",
    ),
    "en": (
        "historic battle", "historic expedition", "historical revolution",
        "historic space mission", "historical disaster", "national independence",
        "historical empire", "historic invention", "historic exploration",
        "attributed historical quote",
    ),
}
# One broad recovery search keeps the "Histoire" niche genuinely open-ended.
# It is deliberately a query, not a fixed catalogue of famous events: when a
# focused search only returns a journal or an unsuitable entry, we make one
# extra grouped Web request, rank its fresh results, and stay on the Web.
HISTORY_BROAD_RECOVERY_QUERY = {
    "fr": "histoire monde bataille révolution exploration empire indépendance invention catastrophe citation",
    "en": "world history battle revolution exploration empire independence invention disaster quote",
}

# Chapitres (motivation/productivité multi-citations)
CHAPTERS_FR = ["Première pépite.", "Deuxième phrase à retenir.", "Troisième vérité.",
               "Quatrième conseil en or.", "Cinquième dose de courage.",
               "Sixième rappel puissant.", "Septième clé.", "Huitième leçon de vie.",
               "Dernière phrase — la plus importante."]
CHAPTERS_EN = ["First gem.", "Second line to remember.", "Third truth.",
               "Fourth golden advice.", "Fifth dose of courage.",
               "Sixth powerful reminder.", "Seventh key.", "Eighth life lesson.",
               "Last line — the most important one."]
COMMENT_FR = ["Laisse-la résonner un instant.",
              "Ce n'est pas juste une phrase : c'est un mode de vie.",
              "Applique-la aujourd'hui et regarde ce qui change.",
              "Garde-la précieusement pour les jours difficiles.",
              "Répète-la demain matin, devant ton miroir."]
COMMENT_EN = ["Let that sink in for a second.",
              "It is not just a quote — it is a way of living.",
              "Apply it today and watch what shifts.",
              "Keep it close for the hard days."]


def _cache_path():
    return os.path.join(content_mod.DATA_DIR, "wiki_cache.json")


def _cache_get(key):
    try:
        with open(_cache_path(), "r", encoding="utf-8") as f:
            entry = (json.load(f) or {}).get(key) or {}
        if time.time() - entry.get("ts", 0) < CACHE_TTL and entry.get("titles"):
            return entry["titles"]
    except Exception:
        pass
    return None


def _cache_put(key, titles):
    # Les téléchargements groupés partagent le même fichier de cache.
    with _CACHE_LOCK:
        _cache_put_unlocked(key, titles)


def _cache_put_unlocked(key, titles):
    if not titles:
        return
    try:
        data = {}
        if os.path.exists(_cache_path()):
            with open(_cache_path(), "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        data[key] = {"ts": time.time(), "titles": titles[:400]}
        os.makedirs(os.path.dirname(_cache_path()), exist_ok=True)
        with open(_cache_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def _get(url, params=None):
    """GET poli : nouvelle tentative + respect du Retry-After (429 Wikipedia)."""
    for attempt in (1, 2, 3):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=TIMEOUT)
            if r.status_code == 200:
                return r
            if r.status_code == 429 and attempt < 3:
                wait = 2.5
                try:
                    wait = min(float(r.headers.get("Retry-After", wait)), 6.0)
                except (TypeError, ValueError):
                    pass
                time.sleep(wait)
                continue
            _NETWORK_STATE.reason = f"HTTP {r.status_code} ({url})"
            logging.getLogger(__name__).warning("Source web HTTP %s : %s", r.status_code, url)
            return None
        except Exception as exc:
            _NETWORK_STATE.reason = f"{type(exc).__name__}: {exc}"
            logging.getLogger(__name__).warning("Source web %s : %s", url, exc)
            if attempt == 3:
                return None
    return None


def _clean_title(t):
    t = clean_wiki_ui_line(t)
    t = re.sub(r"\s*\(.*?\)\s*", " ", t).strip()
    t = re.sub(r"\s{2,}", " ", t)
    if len(t) > 42:
        t = t[:42].rsplit(" ", 1)[0]
    return t.strip(" ,:;»«-–—") or (t or "")[:42].strip()


def _sentences(text, keep=6):
    """Phrases « racontables » d'un article ; parenthèses retirées pour la voix."""
    out = []
    # Wikipedia extracts can contain section headings such as ``== Structure ==``.
    # They are neither speech nor a visual action, so remove them before the
    # sentence split instead of leaking editorial markup into a Short.
    cleaned_text = _WIKI_HEADING_RX.sub(" ", (text or "").strip())
    seen = set()
    for s in _SENT_RX.split(cleaned_text):
        s = _PAREN_RX.sub(" ", clean_wiki_ui_line(s.strip()))
        s = re.sub(r"^\d+\s*", "", s.strip().strip("—-· ")).strip()
        s = re.sub(r"\s{2,}", " ", s)
        s = re.sub(r"\s+([,.;:!?»])", r"\1", s)
        s = re.sub(r"([«(])\s+", r"\1", s)
        if not (55 <= len(s) <= 240):
            continue
        if _bad_sent.search(s):
            continue
        signature = re.sub(r"[^\w]+", "", s.lower())
        if signature in seen:
            continue
        seen.add(signature)
        out.append(s)
        if len(out) >= keep:
            break
    return out


def _select_story_facts(sentences, keep=6):
    """Keep the factual spine, then favour concrete turning points.

    Wikipedia introductions normally open with a useful definition, then mix
    structural details and actual developments. A Short needs both, but the
    latter create a better story. This is only selection: source wording and
    chronology stay intact.
    """
    items = [s for s in sentences if s]
    if len(items) <= keep:
        return items
    scored = []
    for index, sentence in enumerate(items[1:], start=1):
        score = 0
        score += 3 * len(_STORY_SIGNAL_RX.findall(sentence))
        score += 1 if re.search(r"\d", sentence) else 0
        score += 1 if 75 <= len(sentence) <= 180 else 0
        score -= 2 if len(sentence) > 210 else 0
        scored.append((score, index))
    chosen = {0}
    for _, index in sorted(scored, key=lambda item: (-item[0], item[1]))[:max(0, keep - 1)]:
        chosen.add(index)
    return [sentence for index, sentence in enumerate(items) if index in chosen]


def _expand_story_beats(facts, limit=10):
    """Split only explicit chronological clauses into separate visual beats.

    It never rewrites a fact or cuts at ordinary commas.  The point is simply
    to stop one scene from asking a renderer to show two successive events at
    the same time, while retaining Wikipedia's wording and chronology.
    """
    beats = []
    for fact in facts:
        parts = [part.strip(" ,;—–") for part in _BEAT_SPLIT_RX.split(fact or "")]
        for part in parts:
            if len(part) >= 20:
                beats.append(part)
                if len(beats) >= limit:
                    return beats
    return beats


def _sig(kind, ident):
    return "web:" + hashlib.md5(f"{kind}|{ident}".encode("utf-8")).hexdigest()[:12]


def _keep_for(target=None):
    """Maximum source sentences retained for one coherent story.

    A longer video must deepen its chosen event, not stitch unrelated articles
    together.  Wikipedia extracts already contain enough source material for
    the normal ShortPilot durations; this cap simply grows with the requested
    narration time.
    """
    if not target:
        return 6
    return max(6, min(40, math.ceil(_need_secs(target) / 8)))


def _need_secs(target):
    """Secondes de parole visées ≈ 92 % de la cible (le rendu cale au reste)."""
    return float(target or 35) * 0.92


def _articles_budget(target):
    """Nombre d'articles à empiler pour la durée (≈60-70 s de parole/article)."""
    if not target:
        return 1
    return max(1, min(MAX_ARTICLES, math.ceil(_need_secs(target) / 62)))


# ---------------------------------------------------------------- Wikipedia ---
def _wiki_random_summary(lang):
    """Résumé d'un article totalement aléatoire (1 requête REST)."""
    r = _get("https://%s.wikipedia.org/api/rest_v1/page/random/summary" % lang)
    if not r:
        return None
    d = r.json() or {}
    if d.get("type") != "standard" or len(d.get("extract") or "") < MIN_TEXT:
        return None
    return {"title": d.get("title") or "", "text": d["extract"],
            "url": (d.get("content_urls", {}).get("desktop", {}) or {}).get("page", "")}


def _wiki_intros(lang, titles):
    """Début documenté de plusieurs articles, groupé en une requête.

    On lit les premiers caractères de l'article, pas seulement son introduction :
    certaines introductions Wikipédia ne contiennent qu'une définition et ne
    suffisent donc pas pour raconter un Short de 45 secondes.
    """
    if not titles:
        return {}
    r = _get("https://%s.wikipedia.org/w/api.php" % lang, params={
        "action": "query", "format": "json", "prop": "extracts|info",
        # MediaWiki only permits grouped extracts when exintro is enabled.
        # Asking for whole articles silently lowered exlimit to one page, so
        # ShortPilot often ranked one unrelated candidate and fell back to the
        # repetitive local outline. A 1,200-character introduction keeps all
        # candidates in the grouped response and supplies enough material for
        # the normal two-minute target.
        "inprop": "url", "explaintext": "1", "exintro": "1",
        "exchars": "1200", "exlimit": "max",
        "redirects": "1",
        "titles": "|".join(titles[:20])})
    if not r:
        return {}
    try:
        q = r.json().get("query", {})
        norm = {n.get("to"): n.get("from") for n in (q.get("normalized") or [])}
        redir = {d.get("to"): d.get("from") for d in (q.get("redirects") or [])}
        out = {}
        for p in (q.get("pages") or {}).values():
            if p.get("missing") is not None or p.get("ns", 0) != 0:
                continue
            text = (p.get("extract") or "").strip()
            if len(text) < MIN_TEXT:
                continue
            art = {"title": p.get("title") or "", "text": text,
                   "url": p.get("fullurl", "")}
            asked = norm.get(art["title"], art["title"])
            asked = redir.get(asked, asked)
            out.setdefault(asked, art)
            out.setdefault(art["title"], art)
        return out
    except Exception:
        return {}


class _WikiParagraphs(HTMLParser):
    """Extract readable article paragraphs from MediaWiki's parsed HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.skip_depth = 0
        self.edit_depth = 0
        self.current = []
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        if self.edit_depth:
            self.edit_depth += 1
            return
        if tag == "span" and "mw-editsection" in dict(attrs).get("class", "").split():
            self.edit_depth = 1
            return
        if tag == "p":
            self.depth += 1
            self.current = []
        elif self.depth and tag in ("sup", "style", "script"):
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if self.edit_depth:
            self.edit_depth -= 1
            return
        if tag in ("sup", "style", "script") and self.skip_depth:
            self.skip_depth -= 1
        elif tag == "p" and self.depth:
            text = clean_wiki_ui_line(re.sub(r"\s+", " ", "".join(self.current)).strip())
            if len(text) >= 35:
                self.paragraphs.append(text)
            self.current = []
            self.depth -= 1

    def handle_data(self, data):
        if self.depth and not self.skip_depth:
            self.current.append(data)


def _wiki_full_article(lang, title):
    """Fetch the readable paragraphs of one chosen article.

    The extracts API is capped at 1,200 characters. The parse endpoint lets a
    two-to-five-minute script deepen the same relevant article instead of
    switching subject or padding the narration with repeated template lines.
    """
    if not title:
        return None
    cached = _cache_get(f"article:{lang}:{title}")
    if cached:
        try:
            article = json.loads(cached[0])
            if isinstance(article, dict):
                # Old cache entries predate the Wikipedia interface filter.
                # Clean the returned copy without rewriting historical cache data.
                article["title"] = clean_wiki_ui_line(article.get("title", ""))
                article["text"] = clean_wiki_ui_line(article.get("text", ""))
                return article
        except (ValueError, TypeError):
            pass
    r = _get("https://%s.wikipedia.org/w/api.php" % lang, params={
        "action": "parse", "format": "json", "formatversion": "2",
        "prop": "text", "redirects": "1", "page": title,
    })
    if not r:
        return None
    try:
        parsed = (r.json() or {}).get("parse") or {}
        reader = _WikiParagraphs()
        reader.feed(parsed.get("text") or "")
        text = " ".join(reader.paragraphs)
        if len(text) >= MIN_TEXT:
            canonical = parsed.get("title") or title
            url = "https://%s.wikipedia.org/wiki/%s" % (
                lang, urllib.parse.quote(canonical.replace(" ", "_")),
            )
            article = {"title": canonical, "text": text[:18000], "url": url}
            _cache_put(f"article:{lang}:{title}", [json.dumps(article, ensure_ascii=False)])
            return article
    except Exception:
        pass
    return None


def _cat_members(cat, lang, cmtype="page", limit="300"):
    r = _get("https://%s.wikipedia.org/w/api.php" % lang, params={
        "action": "query", "format": "json", "list": "categorymembers",
        "cmtitle": cat, "cmtype": cmtype, "cmlimit": limit})
    if not r:
        return []
    try:
        want_ns = 0 if cmtype == "page" else 14
        return [m.get("title", "") for m in
                (r.json().get("query", {}).get("categorymembers") or [])
                if m.get("title") and m.get("ns") == want_ns]
    except Exception:
        return []


def _category_titles(cat, lang):
    """Articles d'une catégorie ; si la catégorie est surtout organisée en
    SOUS-catégories (les grosses n'ont que quelques pages directes), on en
    pioche quelques-unes au hasard (rotation par l'heure) et on agrège."""
    key = f"cat:{lang}:{cat}"
    cached = _cache_get(key)
    if cached:
        return cached
    titles = _cat_members(cat, lang, "page")
    if len(titles) < 30:
        subs = _cat_members(cat, lang, "subcat", limit="200")
        # rotation horaire : le pool change au fil de la journée, pas à chaque appel
        rng = random.Random(int(time.time() // 3600))
        rng.shuffle(subs)
        for sub in subs[:6]:
            titles += _cat_members(sub, lang, "page", limit="200")
        titles = list(dict.fromkeys(titles))
    if titles:
        _cache_put(key, titles)
    return titles


def _topic_titles(topic, lang):
    """Recherche plein texte Wikipedia pour le « sujet libre » (pertinence, cache)."""
    key = f"search:{lang}:{topic.lower()[:60]}"
    cached = _cache_get(key)
    if cached:
        return cached
    r = _get("https://%s.wikipedia.org/w/api.php" % lang, params={
        "action": "query", "format": "json", "list": "search",
        "srsearch": topic, "srlimit": "25", "srnamespace": "0"})
    if not r:
        return []
    try:
        titles = [m.get("title", "") for m in
                  (r.json().get("query", {}).get("search") or []) if m.get("title")]
    except Exception:
        titles = []
    if titles:
        _cache_put(key, titles)
    return titles


# ------------------------------------------------------------------ autres ----
def _zenquote():
    """Citation aléatoire {quote, author} (anglais) — ZenQuotes, sans clé."""
    r = _get("https://zenquotes.io/api/random")
    if not r:
        return None
    try:
        d = (r.json() or [{}])[0]
        q, a = (d.get("q") or "").strip(), (d.get("a") or "").strip()
        return {"quote": q, "author": a} if q else None
    except Exception:
        return None


def _zenquotes_many():
    """LOT de citations en 1 seule requête (~50, cache 20 h ; évite le quota
    « 5 requêtes / IP / 30 s » qui plafonnerait les longues durées)."""
    key = "zenquotes"
    cached = _cache_get(key)
    pool = []
    if cached:
        for line in cached:
            try:
                d = json.loads(line)
                if d.get("quote"):
                    pool.append(d)
            except Exception:
                pass
    if not pool:
        r = _get("https://zenquotes.io/api/quotes")
        if r:
            try:
                for d in (r.json() or []):
                    q, a = (d.get("q") or "").strip(), (d.get("a") or "").strip()
                    if q:
                        pool.append({"quote": q, "author": a})
            except Exception:
                pass
        if pool:
            _cache_put(key, [json.dumps(d, ensure_ascii=False) for d in pool])
    if not pool:
        one = _zenquote()
        pool = [one] if one else []
    random.shuffle(pool)
    return pool


def _translate_fr(text):
    """anglais → français via MyMemory (sans clé)."""
    r = _get("https://api.mymemory.translated.net/get",
             params={"q": text[:480], "langpair": "en|fr"})
    if not r:
        return None
    try:
        t = (((r.json() or {}).get("responseData") or {}).get("translatedText") or "").strip()
        if not t or "LIMIT" in t.upper() or "MYMEMORY WARNING" in t.upper():
            return None
        return t
    except Exception:
        return None


def _useless_fact_en():
    r = _get("https://uselessfacts.jsph.pl/api/v2/facts/random?language=en")
    if r:
        try:
            t = ((r.json() or {}).get("text") or "").strip()
            return t or None
        except Exception:
            pass
    return None


# -------------------------------------------------------------- fabrication ---
def _duration_label(target, lang):
    return content_mod.duration_label(target, lang)


_LOWER_FIRST = {"le", "la", "les", "un", "une", "des", "du", "de", "the", "a", "an", "l", "d"}


def _inline_topic(t):
    """Sujet au milieu d'une phrase : garde les noms propres (Napoleon), abaisse l'article initial."""
    first = re.split(r"[\s'\u2019]", t, maxsplit=1)[0].lower() if t else ""
    return (t[:1].lower() + t[1:]) if first in _LOWER_FIRST else t

def _hook_for(niche, lang, title, target=None):
    hooks = WEB_HOOKS.get(lang, WEB_HOOKS["fr"])
    bank = hooks.get(niche) or hooks["sujet"]
    t = _clean_title(title)
    return (random.choice(bank)
            .replace("{T}", (t[:1].upper() + t[1:]) if t else t)
            .replace("{t}", _inline_topic(t))
            .replace("{D}", _duration_label(target, lang)))


def _cta_for(niche, lang):
    pack = content_mod._merged(niche, lang) or {}
    if pack.get("ctas"):
        return random.choice(pack["ctas"])
    return "Abonne-toi pour ne rien manquer." if lang == "fr" \
        else "Follow so you don't miss the next one."


def _caption(title, hook, scenes, niche, lang, src_names, src_url):
    title = clean_wiki_ui_line(title)
    hook = clean_wiki_ui_line(hook)
    pack = content_mod._merged(niche, lang) or content_mod._merged("motivation", lang) or {}
    tags = list(dict.fromkeys(
        (pack.get("tags") or [])
        + [w for w in re.findall(r"[a-zà-ÿ]{5,}", (title or "").lower())][:3]
        + (content_mod.COMMON_TAGS_FR if lang == "fr" else content_mod.COMMON_TAGS_EN)))[:12]
    hashtags = " ".join("#" + t.replace(" ", "") for t in tags)
    detail = next((cleaned for scene in scenes[1:]
                   if (cleaned := clean_wiki_ui_line(scene)) and cleaned != hook), "")
    cap = f"{hook}\n\n{detail}\n\n{hashtags}" if detail else f"{hook}\n\n{hashtags}"
    if src_names:
        shown = src_names[:4]
        more = len(src_names) - len(shown)
        cap += "\n\n📚 Source" + ("s" if len(src_names) > 1 else "") + " : "
        cap += " ; ".join(shown) + (f" » et {more} autres" if more > 0 else "")
        cap += " (CC BY-SA / libre)"
        if src_url and "wikipedia" in (src_names[0] or "").lower():
            cap += f" — {src_url}"
    return cap, hashtags


def _story_body(facts, title, hook, cta, target, lang):
    """Turn source sentences into a paced short-form narrative.

    Facts stay verbatim: the editorial layer only provides orientation and a
    payoff.  This keeps Wikipedia claims attributable while giving the viewer a
    hook → context → turn → takeaway arc.
    """
    bridges = STORY_BRIDGES.get(lang, STORY_BRIDGES["fr"])
    payoff = STORY_PAYOFF.get(lang, STORY_PAYOFF["fr"]).format(title=_clean_title(title))
    budget = float(target or 35) * 0.95
    total = content_mod.estimate_seconds([hook, cta])
    body = []
    fact_count = 0
    for index, fact in enumerate(facts):
        # A bridge used to be its own scene.  That produced a very short,
        # visually empty shot ("Le point important arrive...") before the
        # actual fact.  Speak it with its fact instead: one scene now has one
        # useful visual idea and a more natural length.
        # Do not recycle a generic transition in long scripts. Repetition such
        # as a second "Voilà le contexte de départ" sounds automated and adds
        # no information or visual direction.
        bridge = bridges[index - 1] if 0 < index <= len(bridges) else ""
        beat = fact if not bridge else f"{bridge} {fact}"
        duration = content_mod.estimate_seconds([beat])
        # Always retain at least two facts; afterwards honour the target.
        if index >= 2 and total + duration > budget:
            continue
        body.append(beat)
        fact_count += 1
        total += duration
        if index >= 1 and total >= budget * 0.82:
            break
    if fact_count < 2:
        return None
    payoff_duration = content_mod.estimate_seconds([payoff])
    if total + payoff_duration <= budget * 1.03:
        body.append(payoff)
    return body


def _article_story_score(article):
    """Prefer a concrete story over a flat encyclopedia entry for short videos.

    This is deliberately a content-selection heuristic, not fact generation:
    all lines still come verbatim from the chosen source article.
    """
    raw_title = article.get("title", "")
    title = _clean_title(raw_title)
    facts = _sentences(article.get("text", ""), keep=_keep_for())
    text = " ".join(facts)
    signals = len(_STORY_SIGNAL_RX.findall(text))
    dates = len(re.findall(r"\b(?:1[5-9]\d{2}|20\d{2}|\d{1,2}(?:er)?\s+\w+)\b", text))
    concrete = len(_EVENT_WORD_RX.findall(f"{title} {text}"))
    penalty = 100 if (_WEAK_STORY_TITLE_RX.search(title)
                      or _NON_EVENT_TITLE_RX.search(raw_title)) else 0
    return signals * 3 + dates + concrete * 2 + min(len(facts), 5) - penalty


def _storyworthy_article(article, niche):
    """Reject Wikipedia entries that are valid but poor automatic Short topics."""
    raw_title = article.get("title", "")
    title = _clean_title(raw_title)
    if (_WEAK_STORY_TITLE_RX.search(title) or _NON_EVENT_TITLE_RX.search(raw_title)
            or _NON_EVENT_TITLE_RX.search(title)):
        return False
    text = " ".join(_sentences(article.get("text", ""), keep=_keep_for()))
    first_fact = _sentences(article.get("text", ""), keep=1)
    if first_fact and _NON_EVENT_LEAD_RX.search(first_fact[0]):
        return False
    # Keep the eligibility gate broad.  The scoring step below favours events
    # and turning points, but a strict hard gate made the Web source run out of
    # candidates and fall back to local content after only a few clicks.
    return True


def _from_articles(niche, lang, articles, target=None):
    """One source article → one coherent script. None si trop pauvre."""
    main = articles[0]
    pool = []
    for art in articles:
        pool += _sentences(art["text"], keep=_keep_for(target))
    if len(pool) < 2:
        return None
    hook = _hook_for(niche, lang, main["title"], target)
    cta = _cta_for(niche, lang)
    # The source facts are selected before the narrative beats are inserted.
    # This prevents a 30-second request from becoming a flat raw summary.
    # Keep the opening context and select the most narrative source facts,
    # rather than mechanically reading the first Wikipedia sentences.
    source_facts = _expand_story_beats(
        _select_story_facts(pool, _keep_for(target)),
        limit=_keep_for(target),
    )
    body = _story_body(source_facts, main["title"], hook, cta, target, lang)
    if not body:
        return None
    scenes = [hook] + body + [cta]
    names = ["Wikipedia — « %s »" % _clean_title(a["title"]) for a in articles]
    caption, hashtags = _caption(main["title"], hook, scenes, niche, lang,
                                 names, main.get("url", ""))
    return {
        "niche": niche, "language": lang, "title": hook[:100], "hook": hook,
        "scenes": scenes, "cta": cta, "caption": caption, "hashtags": hashtags,
        "source": "web", "source_name": "Wikipedia", "source_url": main.get("url", ""),
    }


def _from_quotes(niche, lang, chapters, target=None):
    """Citations enchaînées en chapitres (longue durée) ou 1 citation (court).
    chapters = [(quote, author), ...]"""
    hook = _hook_for(niche, lang, chapters[0][1] or "", target)
    cta = _cta_for(niche, lang)
    titles = CHAPTERS_FR if lang == "fr" else CHAPTERS_EN
    comments = COMMENT_FR if lang == "fr" else COMMENT_EN
    scenes = [hook]
    acc = content_mod.estimate_seconds([hook])
    tgt = float(target or 35)
    random.shuffle(comments)
    ci = 0
    for i, (quote, author) in enumerate(chapters):
        name = author or ("Un grand penseur" if lang == "fr" else "A great mind")
        ch = titles[min(i, len(titles) - 1)]
        block = [ch, ("Écoute bien." if lang == "fr" else "Listen closely.")
                 if len(quote) < 90 else (f"Écoute bien cette phrase de {name}."
                                          if lang == "fr" else f"Listen to this one from {name}."),
                 f"« {quote} »"]
        long_form = bool(target and target >= 60)
        if long_form or i % 2 == 1 or i == len(chapters) - 1:
            block.append(comments[ci % len(comments)])
            ci += 1
        block_s = sum(content_mod.estimate_seconds([b]) for b in block)
        if target and len(scenes) > 3 and acc + block_s > tgt * 0.97:
            continue
        scenes += block
        acc += block_s
        if acc >= tgt * 0.92:
            break
    scenes.append(cta)
    names = list(dict.fromkeys("ZenQuotes — %s" % (a or "?") for _, a in chapters))
    caption, hashtags = _caption(chapters[0][1] or niche, hook, scenes, niche, lang,
                                 names, "https://zenquotes.io")
    return {
        "niche": niche, "language": lang, "title": hook[:100], "hook": hook,
        "scenes": scenes, "cta": cta, "caption": caption, "hashtags": hashtags,
        "source": "web", "source_name": "ZenQuotes", "source_url": "https://zenquotes.io",
    }


# ------------------------------------------------------------------- entrée ---
def _query_tokens(text):
    """Normalisation légère pour contrôler la pertinence d'une source."""
    normalized = "".join(c for c in unicodedata.normalize("NFKD", text.lower())
                         if not unicodedata.combining(c))
    stop = {"the", "and", "des", "les", "une", "pour", "dans", "with", "from", "sur"}
    return {w for w in re.findall(r"[a-z]{3,}", normalized) if w not in stop}


def topic_script(niche="sujet", lang="fr", topic="", target=None, log=None, avoid_repeat=True):
    """Recherche bornée et documentée pour un sujet explicite, sans article aléatoire."""
    lang = "en" if lang == "en" else "fr"
    wanted = content_mod.target_words(target, lang)
    normalized = _query_tokens(topic)
    broad = normalized in ({"histoire", "monde"}, {"histoire", "humanite"},
                           {"world", "history"}, {"human", "history"})
    if broad:
        # Un panorama doit traverser les périodes, pas raconter une biographie.
        queries = (["Préhistoire", "Révolution néolithique", "Antiquité",
                    "Moyen Âge", "Époque moderne", "Révolution industrielle", "Époque contemporaine"]
                   if lang == "fr" else
                   ["Prehistory", "Neolithic Revolution", "Ancient history", "Middle Ages",
                    "Early modern period", "Industrial Revolution", "Contemporary history"])
        # Recherche de cadrage, puis téléchargement direct des périodes connues :
        # évite vingt requêtes de recherche et les quotas sur un simple panorama.
        _topic_titles(topic, lang)
    else:
        queries = [topic, topic + (" histoire origines" if lang == "fr" else " history origins"),
                   topic + (" évolution conséquences" if lang == "fr" else " development consequences")]
    articles, errors, seen = [], [], set()
    # Chaque requête garde le meilleur résultat pertinent. Les appels sont
    # indépendants et bornés ; les téléchargements se font par petits groupes.
    def search(query):
        _NETWORK_STATE.reason = ""
        try:
            if broad:
                direct = _wiki_full_article(lang, query)
                if direct:
                    return direct
            titles = _topic_titles(query, lang)
            intros = _wiki_intros(lang, titles[:5]) if titles else {}
            required = _query_tokens(query if broad else topic)
            for title in titles[:5]:
                intro = intros.get(title)
                if not intro or not _storyworthy_article(intro, niche):
                    continue
                if re.search(r"homonymie|disambiguation", title, re.I):
                    continue
                tokens = _query_tokens(title + " " + intro.get("text", ""))
                if required and len(tokens & required) / len(required) < .5:
                    continue
                full = _wiki_full_article(lang, title)
                return full or intro
        except Exception as exc:
            return {"failure": str(exc)}
        detail = getattr(_NETWORK_STATE, "reason", "")
        return {"failure": f"Aucun article pertinent pour « {query} ». {detail}".strip()}

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(search, queries))
    for article in results:
        if article.get("failure"):
            errors.append(article["failure"])
            continue
        if article["title"] not in seen:
            articles.append(article)
            seen.add(article["title"])
    if not articles:
        if log:
            log(" ; ".join(errors))
        return None
    _cache_put(f"local:{lang}:{topic.lower().strip()}",
               [json.dumps(a, ensure_ascii=False) for a in articles])
    script = _documented_script(articles, niche, lang, topic, target, broad, log)
    if broad and errors:
        script.setdefault("warnings", []).append("Panorama incomplet, périodes non récupérées : " + " ; ".join(errors))
    return script


def local_topic_script(topic, lang, target=None, niche="sujet"):
    """Réutilise les sources conservées, sans requête réseau ni expiration."""
    try:
        with open(_cache_path(), encoding="utf-8") as stream:
            entry = json.load(stream).get(f"local:{lang}:{topic.lower().strip()}", {})
        articles = [json.loads(a) for a in entry.get("titles", [])]
        if articles:
            if topic.startswith("__niche_"):
                topic = articles[0]["title"]
            broad = _query_tokens(topic) in ({"histoire", "monde"}, {"histoire", "humanite"},
                                            {"world", "history"}, {"human", "history"})
            script = _documented_script(articles, niche, lang, topic, target, broad)
            script["source"] = "local"
            script["source_name"] = "Sources documentées conservées hors ligne"
            return script
    except (OSError, ValueError, TypeError):
        pass
    return None


def _documented_script(articles, niche, lang, topic, target, broad=False, log=None):
    """Assemble les mêmes faits en ligne ou hors ligne avec un budget commun."""
    # Older local-topic snapshots contain the edit toolbar inside their article
    # text. Clean copies before short_scenes splits it into narration beats.
    articles = [{**article,
                 "title": clean_wiki_ui_line(article.get("title", "")),
                 "text": clean_wiki_ui_line(article.get("text", ""))}
                for article in articles]
    wanted = content_mod.target_words(target, lang)
    hook = (f"{topic.strip().capitalize()} : les grandes étapes" if lang == "fr" else
            f"{topic.strip().capitalize()}: the key turning points") if broad else _hook_for(niche, lang, topic, target)
    cta = _cta_for(niche, lang)
    bodies = []
    quota = max(12, (wanted - content_mod.word_count(hook + " " + cta)) // len(articles))
    for article in articles:
        text = _PAREN_RX.sub(" ", article["text"])
        text = re.sub(r"\[.*?\]", "", text)
        candidates = content_mod.short_scenes([text], max_words=20)
        chosen, count = [], 0
        for sentence in candidates:
            if _bad_sent.search(sentence) or content_mod.word_count(sentence) < 5:
                continue
            chosen.append(sentence)
            count += content_mod.word_count(sentence)
            if count >= quota:
                break
        bodies.extend(chosen)
    names = ["Wikipedia — « %s »" % a["title"] for a in articles]
    scenes = [hook, *bodies, cta]
    caption, hashtags = _caption(topic, hook, scenes, niche, lang, names, articles[0].get("url", ""))
    script = {"id": _sig("topic", topic + str(time.time_ns())), "niche": niche,
              "language": lang, "title": hook[:100], "hook": hook, "cta": cta,
              "scenes": scenes, "caption": caption, "hashtags": hashtags,
              "source": "web", "source_name": "Wikipedia",
              "source_url": articles[0].get("url", ""),
              # Visual evidence is deliberately independent from the selected
              # narration beats.  Keep the complete primary article so a
              # faithful illustration can use a concrete object omitted from
              # the voice-over without inventing it.
              "visual_corpus": [{
                  "title": articles[0]["title"],
                  "url": articles[0].get("url", ""),
                  "text": articles[0]["text"],
              }],
              "sources": [{"title": a["title"], "url": a.get("url", "")} for a in articles]}
    # The complete article is already local here: use it immediately to trade
    # abstract narration beats for source-ordered sentences with visual support.
    fitted = content_mod.fit_script(script, target, extra_lines=[a["text"] for a in articles])
    if not fitted["duration_ok"]:
        # Réserve des sections déjà téléchargées, sans nouvelle dépendance réseau.
        fitted = content_mod.fit_script(script, target, extra_lines=[a["text"] for a in articles])
    if log and not fitted["duration_ok"]:
        log(fitted["warnings"][-1])
    return fitted


def script_from_web(niche="motivation", lang="fr", topic="", target=None, log=None,
                    avoid_repeat=True):
    """Script frais, dimensionné à la DURÉE cible. None → repli local."""
    lang = "en" if lang == "en" else "fr"
    target = int(target or 0) or None
    used = content_mod._load_used() if avoid_repeat else set()

    def fresh(kind, ident):
        s = _sig(kind, ident)
        return (s not in used), s

    def mark(s):
        if avoid_repeat:
            content_mod._mark_used(used, s)

    try:
        # --- citations : motivation & productivité (chapitres selon la durée) ----
        if niche in ("motivation", "productivite"):
            # ~20 s parlées par chapitre (titre + citation + commentaire)
            # on empile des chapitres jusqu'à ~20 s parlées chacun — la mesure
            # se fait citation par citation (pas de plafond fixe trop court)
            need = _need_secs(target)
            single = not target               # sans durée : 1 citation, comme avant
            chapters, sigs, acc_q = [], [], 0.0
            pool = _zenquotes_many()          # un seul appel réseau ≈ 50 citations
            attempts = 0
            for q in pool:
                if (single and chapters) or (not single and (acc_q >= need or len(chapters) >= 16)):
                    break
                ok, s = fresh("quote", q["quote"])
                if not ok:
                    continue
                quote = q["quote"]
                if lang == "fr":
                    attempts += 1
                    if attempts > 20:
                        break
                    quote = _translate_fr(quote)
                    if not quote:
                        continue
                chapters.append((quote, q.get("author") or ""))
                sigs.append(s)
                # titre chapitre + transition + citation + commentaire ≈
                acc_q += (len(quote) + 36) / content_mod.CPS + 5.0
            if not chapters:
                return None
            out = _from_quotes(niche, lang, chapters, target)
            out["id"] = sigs[0]
            for s in sigs:
                mark(s)
            if log:
                log(f"   🌐 source web : ZenQuotes — {len(chapters)} citation(s) "
                    f"(durée cible ~{_need_secs(target):.0f}s)")
            return out

        # --- faits insolites EN : source dédiée (empilés selon la durée) ---------
        if niche == "faits" and lang == "en" and random.random() < 0.4:
            need_f = 1 if not target else max(1, min(14, math.ceil(_need_secs(target) / 16)))
            facts, fsigs, tries = [], [], 0
            while len(facts) < need_f and tries < need_f * 4 + 4:
                tries += 1
                fact = _useless_fact_en()
                if not fact:
                    break
                ok, s = fresh("fact", fact)
                if ok:
                    facts.append(fact)
                    fsigs.append(s)
            if facts:
                hook = _hook_for(niche, lang, facts[0][:38], target)
                cta = _cta_for(niche, lang)
                bridges = ["But wait — here's another one.", "The next one is even crazier.",
                           "And this one? Completely real.", "Ready for the next?",
                           "One more — you won't believe it.", "We're not done yet."]
                random.shuffle(bridges)
                scenes = [hook, facts[0]]
                for i, f in enumerate(facts[1:], start=1):
                    scenes += [bridges[(i - 1) % len(bridges)], f]
                scenes += ["Yes — every single one of these is real",
                           "and most people go their whole life without ever hearing them.",
                           cta]
                caption, hashtags = _caption(facts[0][:38], hook, scenes, niche, lang,
                                             ["UselessFacts"], "https://uselessfacts.net")
                for s in fsigs:
                    mark(s)
                if log:
                    log(f"   🌐 source web : UselessFacts — {len(facts)} fait(s) "
                        f"(durée cible ~{_need_secs(target):.0f}s)")
                return {"id": fsigs[0], "niche": niche, "language": lang, "title": hook[:100],
                        "hook": hook, "scenes": scenes, "cta": cta, "caption": caption,
                        "hashtags": hashtags, "source": "web",
                        "source_name": "UselessFacts", "source_url": "https://uselessfacts.net"}

        # --- Wikipedia : tout le reste -------------------------------------------
        def finish(articles, sigs):
            if target:
                articles = [_wiki_full_article(lang, a["title"]) or a for a in articles]
            out = _from_articles(niche, lang, articles, target)
            if not out:
                return None
            if target:
                out = _documented_script(articles, niche, lang, articles[0]["title"], target)
            _cache_put(f"local:{lang}:__niche_{niche}",
                       [json.dumps(a, ensure_ascii=False) for a in articles])
            out["id"] = sigs[0]
            for s in sigs:
                mark(s)
            if log:
                names = " » + « ".join(_clean_title(a["title"]) for a in articles[:3])
                if len(articles) > 3:
                    names += f" » (+{len(articles) - 3})"
                log(f"   🌐 source web : Wikipedia — « {names} » "
                    f"({len(articles)} article(s) pour ~{_need_secs(target):.0f}s)")
            return out

        if niche == "sujet" and not topic:
            return None  # sujet libre sans sujet → repli local

        if niche == "faits":
            # articles aléatoires empilés jusqu'à la durée voulue (résumés plus
            # courts que des intros : prévoir large en nombre d'essais)
            articles, sigs, acc, tries = [], [], 0.0, 0
            while acc < _need_secs(target) and len(articles) < 12 and tries < 30:
                tries += 1
                art = _wiki_random_summary(lang)
                if not art:
                    continue
                if _META_RX.search(art["title"]) or _YEAR_RX.match(art["title"]):
                    continue
                ok, s = fresh("wiki", art["title"])
                if not ok:
                    continue
                ss = _sentences(art["text"], keep=_keep_for())
                if len(ss) < 2:
                    continue
                articles.append(art)
                sigs.append(s)
                acc += sum(content_mod.estimate_seconds([x]) for x in ss)
            if not articles:
                return None
            return finish(articles, sigs)

        # catégorie de niche / sujet libre : liste de titres puis intros groupées
        if niche == "sujet" and topic:
            candidates = _topic_titles(topic, lang)          # triés par pertinence
        elif niche == "histoire":
            # One focused search still gives a fresh, unlimited pool, but
            # starts from an event/exploration/discovery rather than a random
            # encyclopedia meta-entry.
            query = random.choice(HISTORY_STORY_QUERIES[lang])
            candidates = _topic_titles(query, lang)
        elif niche in WIKI_CATS:
            candidates = list(_category_titles(WIKI_CATS[niche][0 if lang == "fr" else 1], lang))
            random.shuffle(candidates)
        else:
            candidates = []

        # Always compare a small grouped pool, then write the entire script
        # from the strongest *single* article.  This keeps a 90-second story
        # about Malpasset on Malpasset instead of suddenly adding another
        # unrelated disaster just to fill time.
        candidate_limit = BATCH
        fresh_titles, fresh_sigs = [], []
        for t in candidates:
            if _META_RX.search(t) or _YEAR_RX.match(t):
                continue
            ok, s = fresh("wiki", t)
            if not ok:
                continue
            fresh_titles.append(t)
            fresh_sigs.append(s)
            if len(fresh_titles) >= candidate_limit:
                break
        # History has one broad Web recovery below.  Do not jump to the local
        # bank merely because the first focused result set was already used or
        # contained only non-story pages.
        if not fresh_titles and niche != "histoire":
            return None
        articles, sigs, acc, i = [], [], 0.0, 0
        # Inspect one batch in one request.  The final selection below keeps
        # one article only; the duration is filled by more of its own facts.
        while i < len(fresh_titles) and len(articles) < BATCH:
            bt, bs = fresh_titles[i:i + BATCH], fresh_sigs[i:i + BATCH]
            i += len(bt)
            arts = _wiki_intros(lang, bt)                    # 1 seule requête
            for t, s in zip(bt, bs):                         # ordre conservé
                art = arts.get(t)
                if not art:
                    continue
                if not _storyworthy_article(art, niche):
                    continue
                ss = _sentences(art["text"], keep=_keep_for(target))
                # A highly relevant introduction can be one long definition.
                # For an explicit free topic, deepen that same first result
                # instead of skipping to a less relevant article merely because
                # its introduction happens to contain more punctuation.
                if len(ss) < 2 and niche == "sujet" and topic:
                    full = _wiki_full_article(lang, art["title"])
                    if full:
                        art = full
                        ss = _sentences(art["text"], keep=_keep_for(target))
                if len(ss) < 2:
                    continue
                articles.append(art)
                sigs.append(s)
                acc += sum(content_mod.estimate_seconds([x]) for x in ss)
                if len(articles) >= BATCH:
                    break
        if not articles:
            # A focused query can occasionally yield only media entries or
            # organisations.  Do not silently drop to the local bank in that
            # case: perform one broad *grouped* Web search.  This preserves a
            # wide, fresh history pool without chaining a long list of serial
            # requests or falling back to the same fixed famous battles.
            if niche == "histoire":
                recovery_pairs = []
                recovery_candidates = _topic_titles(HISTORY_BROAD_RECOVERY_QUERY[lang], lang)
                for title in recovery_candidates:
                    ok, signature = fresh("wiki", title)
                    if ok:
                        recovery_pairs.append((title, signature))
                    if len(recovery_pairs) >= BATCH:
                        break
                recovery_titles = [title for title, _ in recovery_pairs]
                recovery_map = _wiki_intros(lang, recovery_titles) if recovery_titles else {}
                recovery = [(recovery_map.get(title), signature)
                            for title, signature in recovery_pairs]
                recovery = [(article, signature) for article, signature in recovery
                            if article and _storyworthy_article(article, niche)]
                if recovery:
                    best, best_sig = max(recovery, key=lambda pair: _article_story_score(pair[0]))
                    return finish([best], [best_sig])
            # dernier recours : article aléatoire (hors-niche éventuel, mais frais)
            for _ in range(5):
                art = _wiki_random_summary(lang)
                if not art:
                    continue
                if (_META_RX.search(art["title"]) or _YEAR_RX.match(art["title"])
                        or not _storyworthy_article(art, niche)):
                    continue
                ok, s = fresh("wiki", art["title"])
                if not ok:
                    continue
                if len(_sentences(art["text"], keep=_keep_for())) < 2:
                    continue
                done = finish([art], [s])
                if done:
                    return done
            return None
        # For a free subject, Wikipedia search order is the user's relevance
        # signal. Keep the first suitable result (for example "Histoire de
        # l'humanité" for "histoire du monde") instead of replacing it with a
        # later article that merely contains more event keywords. Automatic
        # niche discovery still ranks candidates by narrative quality.
        best_index = 0 if niche == "sujet" and topic else max(
            range(len(articles)), key=lambda index: _article_story_score(articles[index])
        )
        articles, sigs = [articles[best_index]], [sigs[best_index]]
        return finish(articles, sigs)
    except Exception:
        return None
