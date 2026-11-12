"""Sources de contenu supplementaires et moteur editorial de ShortPilot.

Chaque source collecte des faits (flux RSS, API ouvertes, pages Wikipedia), puis le
moteur choisit un angle narratif et ecrit un script naturel :
  * avec Ollama (local) : reecriture orale, fidele aux faits fournis, controlee ensuite ;
  * sans Ollama : mise en forme simple, sans aucune invention.
Aucune cle d'API ni abonnement. Tout est mis en cache et borne en temps.
"""
import hashlib
import html
import json
import logging
import os
import random
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from .wiki_noise import clean_wiki_ui_line

_LOG = logging.getLogger(__name__)
UA = "ShortPilot/1.0 (outil personnel de creation video)"
TIMEOUT = 12
OLLAMA_URL = os.environ.get("SHORTPILOT_OLLAMA_URL", "http://127.0.0.1:11434")

# Internal collectors, also retained for compatibility with the diagnostic tool.
SOURCE_LABELS = {
    "actu": "📰 Actualité — ce qui se passe et pourquoi",
    "jour": "📅 Ce jour-là — une histoire datée",
    "science": "🔬 Science & découvertes",
    "mythes": "🧠 Mythes & réalité",
    "perso": "🔗 Mes sources — lien ou texte collé",
    "surprise": "🎲 Surprends-moi",
}
SOURCE_IDS = tuple(SOURCE_LABELS)


class SourceError(Exception):
    """Source indisponible ou sans contenu exploitable (message lisible)."""


# --------------------------------------------------------------------------- cache
_CACHE_LOCK = threading.Lock()


def _cache_path():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "data", "sources_cache.json")


def _cache_load():
    try:
        with open(_cache_path(), encoding="utf-8") as stream:
            data = json.load(stream)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _cache_get(key, ttl):
    with _CACHE_LOCK:
        entry = _cache_load().get(key)
    if entry and time.time() - entry.get("ts", 0) < ttl:
        return entry.get("value")
    return None


def _cache_json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported cache value: {type(value).__name__}")


def _cache_put(key, value):
    with _CACHE_LOCK:
        data = _cache_load()
        data[key] = {"ts": time.time(), "value": value}
        if len(data) > 400:  # borne la taille du fichier
            for old in sorted(data, key=lambda k: data[k].get("ts", 0))[:len(data) - 400]:
                data.pop(old, None)
        try:
            os.makedirs(os.path.dirname(_cache_path()), exist_ok=True)
            tmp = _cache_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, default=_cache_json_default)
            os.replace(tmp, _cache_path())
        except (OSError, TypeError, ValueError) as exc:
            _LOG.warning("Cache non enregistré : %s", exc)


def _used_keys():
    return set(_cache_get("used", 86400 * 365) or [])


def _mark_used(key):
    used = list(_used_keys())
    used.append(key)
    _cache_put("used", used[-500:])


# --------------------------------------------------------------------------- reseau
def _http(url, params=None, timeout=TIMEOUT, accept="*/*"):
    """GET borne ; retourne les octets. Leve SourceError avec un message lisible."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": accept, "Accept-Language": "fr,en;q=0.7"})
    exc = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(3_000_000)
        except Exception as error:  # HTTPError, URLError, timeout...
            exc = error
            if getattr(error, "code", None) in (429, 503) and attempt < 2:
                wait = 2.0 * (attempt + 1)
                try:
                    wait = min(8.0, float(error.headers.get("Retry-After", wait)))
                except Exception:
                    pass
                time.sleep(wait)
                continue
            break
    code = getattr(exc, "code", "")
    host = urllib.parse.urlparse(url).netloc
    raise SourceError(f"{host} injoignable ({code or type(exc).__name__})") from exc


def _http_cached(url, params=None, ttl=1200, **kwargs):
    key = "http:" + url + "?" + json.dumps(params or {}, sort_keys=True)
    cached = _cache_get(key, ttl)
    if cached is not None:
        return cached.encode("utf-8")
    raw = _http(url, params, **kwargs)
    _cache_put(key, raw.decode("utf-8", "replace"))
    return raw


# --------------------------------------------------------------------------- texte
_STOP = {"les", "des", "une", "dans", "pour", "sur", "est", "par", "que", "qui", "aux", "du", "de", "la",
         "le", "un", "et", "en", "au", "ce", "ces", "son", "sa", "ses", "the", "and", "for", "with", "of",
         "to", "in", "on", "a", "an", "is", "d", "l"}
_NOISE_RX = re.compile(
    r"abonnez-vous|s'abonner|r[ée]serv[ée] aux abonn|newsletter|cookies?|lire aussi|\b(?:à|a) lire\b|"
    r"partagez|partager (?:cet|sur)|cliquez|inscrivez-vous|connectez-vous|copyright|tous droits|"
    r"mentions l[ée]gales|suivez-nous|retrouvez-nous|photo\s*:|cr[ée]dits? photo|laisser un commentaire|"
    r"voir les commentaires|©|vous lisez|cette page contient|pour un article|ne pas confondre|"
    r"publi[ée] le|mis [àa] jour le|temps de lecture|"
    r"t[ée]l[ée]charg|google play|app store|appstore|nos applications|notre application|"
    r"l'application (?:rfi|france ?24|mobile|gratuite)|rfi\.fr|france24\.com|"
    r"retrouvez (?:toute|notre)|[ée]coutez (?:rfi|notre)", re.I)
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÀ-ÖØ-Þ«\"“0-9])")


_PROMO_RX = re.compile(
    r"double live|plus de passion|suivez|revivez|notre live|notre direct|en direct sur|abonnez", re.I)
_LIVE_RX = re.compile(
    r"en direct|\blive\b|suivez|revivez|minute par minute|compositions? (?:probables?|officielles?)|"
    r"\bdirect\s*[:\-–—]", re.I)


def _norm(text):
    text = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _tokens(text):
    return {w for w in re.findall(r"[a-z0-9]{3,}", _norm(text)) if w not in _STOP}


def _strip_html(text):
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _word_count(text):
    return len(re.findall(r"\w+", text or ""))


def _clean_sentences(text, min_words=6, max_words=38):
    """Phrases propres : sans notices, sans parentheses, sans doublons."""
    try:
        from . import webcontent
        bad = webcontent._bad_sent
    except Exception:
        bad = None
    out, seen = [], set()
    text = re.sub(r"\s*\([^)]*\)", " ", text or "")
    text = re.sub(r"\[[^\]]*\]", "", text)
    clean_lines = [clean_wiki_ui_line(line) for line in text.splitlines()]
    for sentence in _SENT_SPLIT.split(re.sub(r"\s+", " ", " ".join(clean_lines)).strip()):
        sentence = clean_wiki_ui_line(sentence.strip(" -–—·•"))
        words = _word_count(sentence)
        if (not (min_words <= words <= max_words) or _NOISE_RX.search(sentence)
                or _PROMO_RX.search(sentence) or sentence.count(",") >= 5):
            continue
        if bad is not None and bad.search(sentence):
            continue
        signature = re.sub(r"\W+", "", sentence.lower())
        if signature in seen:
            continue
        seen.add(signature)
        out.append(sentence)
    return out


class _ParaParser(HTMLParser):
    """Paragraphes lisibles d'une page d'article, sans menus ni encarts."""
    SKIP = ("script", "style", "nav", "footer", "aside", "figure", "form", "header", "noscript")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_p = False
        self.current = []
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag == "p" and not self.skip:
            self.in_p, self.current = True, []

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag == "p" and self.in_p:
            text = re.sub(r"\s+", " ", "".join(self.current)).strip()
            text = clean_wiki_ui_line(text)
            if len(text) >= 60 and not _NOISE_RX.search(text):
                self.paragraphs.append(text)
            self.in_p = False

    def handle_data(self, data):
        if self.in_p and not self.skip:
            self.current.append(data)


def _article_text(url, limit=5000):
    """Texte d'un article a partir de son adresse ('' si indisponible)."""
    if not url or "news.google." in url:
        return ""
    try:
        raw = _http_cached(url, ttl=6 * 3600, accept="text/html")
    except SourceError:
        return ""
    parser = _ParaParser()
    try:
        parser.feed(raw.decode("utf-8", "replace"))
    except Exception:
        return ""
    return " ".join(parser.paragraphs)[:limit]


# --------------------------------------------------------------------------- flux RSS
def _parse_date(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _parse_feed(raw):
    """Articles d'un flux RSS ou Atom : titre, resume, lien, date."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise SourceError(f"flux illisible ({exc})") from exc
    items = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        fields = {}
        for child in node:
            name = _local(child.tag)
            if name == "link":
                fields.setdefault("link", child.get("href") or (child.text or "").strip())
            elif name in ("title", "description", "summary", "encoded", "content", "pubdate",
                          "updated", "published"):
                fields.setdefault(name, child.text or "")
        summary = _strip_html(fields.get("encoded") or fields.get("content")
                              or fields.get("description") or fields.get("summary") or "")
        title = _strip_html(fields.get("title", ""))
        if not title:
            continue
        items.append({"title": title, "summary": summary, "url": fields.get("link", ""),
                      "date": _parse_date(fields.get("pubdate") or fields.get("published")
                                          or fields.get("updated"))})
    return items


# flux gratuits par categorie (ajoutez les votres ici)
FEEDS = {
    "fr": {
        "une": [("France 24", "https://www.france24.com/fr/rss"), ("RFI", "https://www.rfi.fr/fr/rss"),
                ("franceinfo", "https://www.francetvinfo.fr/titres.rss"),
                ("Le Monde", "https://www.lemonde.fr/rss/une.xml")],
        "tech": [("Numerama", "https://www.numerama.com/feed/"),
                 ("01net", "https://www.01net.com/feed/")],
        "economie": [("Le Monde Économie", "https://www.lemonde.fr/economie/rss_full.xml"),
                     ("France 24", "https://www.france24.com/fr/economie/rss")],
        "sport": [("France 24 Sports", "https://www.france24.com/fr/sports/rss"),
                  ("RFI Sports", "https://www.rfi.fr/fr/sports/rss")],
        "culture": [("France 24 Culture", "https://www.france24.com/fr/culture/rss"),
                    ("Le Monde Culture", "https://www.lemonde.fr/culture/rss_full.xml")],
        "science": [("Futura", "https://www.futura-sciences.com/rss/actualites.xml"),
                    ("Sciences et Avenir", "https://www.sciencesetavenir.fr/rss.xml")],
    },
    "en": {
        "une": [("BBC News", "https://feeds.bbci.co.uk/news/rss.xml"),
                ("France 24", "https://www.france24.com/en/rss")],
        "tech": [("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml")],
        "economie": [("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml")],
        "sport": [("BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml")],
        "culture": [("BBC Culture", "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml")],
        "science": [("BBC Science", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
                    ("NASA", "https://www.nasa.gov/feed/")],
    },
}
_CATEGORY_BY_NICHE = {"argent": "economie", "finance": "economie", "sante": "science",
                      "psychologie": "science", "science": "science", "tech": "tech",
                      "technologie": "tech", "sport": "sport", "culture": "culture"}
_CATEGORY_WORDS = {
    "tech": "ia intelligence artificielle robot smartphone application logiciel numerique internet cyber openai",
    "economie": "bourse inflation economie entreprise banque marche euro dollar croissance emploi",
    "sport": "football match sport tennis rugby olympique champion coupe ligue",
    "science": "science decouverte espace nasa cerveau climat cancer virus etoile planete fusee",
    "culture": "cinema film musique livre exposition festival serie artiste",
}


def _category_for(niche, topic):
    if niche in _CATEGORY_BY_NICHE:
        return _CATEGORY_BY_NICHE[niche]
    topic_tokens = _tokens(topic)
    best = max(_CATEGORY_WORDS, key=lambda c: len(topic_tokens & _tokens(_CATEGORY_WORDS[c])))
    return best if topic_tokens & _tokens(_CATEGORY_WORDS[best]) else "une"


def _load_feeds(feeds, max_age_days):
    errors, items = [], []

    def load(feed):
        name, url = feed
        try:
            parsed = _parse_feed(_http_cached(url, ttl=1200, accept="application/rss+xml, */*"))
        except SourceError as exc:
            errors.append(f"{name} : {exc}")
            return []
        return [dict(item, source=name) for item in parsed]

    with ThreadPoolExecutor(max_workers=4) as pool:
        for batch in pool.map(load, feeds):
            items.extend(batch)
    limit = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    fresh = [i for i in items if i["date"] is None or i["date"] >= limit]
    return fresh, errors


def _relevance(item, topic_tokens):
    if not topic_tokens:
        return 0.0
    found = topic_tokens & _tokens(item["title"] + " " + item["summary"])
    return len(found) / len(topic_tokens)


def _pick_news(feeds, topic, max_age_days, avoid_repeat, log, exclude=None):
    items, errors = _load_feeds(feeds, max_age_days)
    if exclude is not None:
        kept_items = [i for i in items if not exclude.search(i["title"] + " " + i["summary"])]
        if len(kept_items) >= 3:
            items = kept_items
    if not items:
        raise SourceError("Aucun flux n'a répondu : " + (" ; ".join(errors[:3]) or "réseau indisponible"))
    wanted = _tokens(topic)
    need = 1.0 if len(wanted) <= 2 else .6
    if wanted:
        pool = [i for i in items if _relevance(i, wanted) >= need]
        if not pool:
            raise SourceError(f"Aucune actualité récente sur « {topic} » dans les flux ({len(items)} articles lus).")
    else:
        pool = [i for i in items if _word_count(i["summary"]) >= 12] or items
    used = _used_keys() if avoid_repeat else set()
    fresh = [i for i in pool if hashlib.sha1((i["url"] or i["title"]).encode()).hexdigest()[:12] not in used]
    pool = fresh or pool
    pool.sort(key=lambda i: (_relevance(i, wanted), i["date"] or datetime(1970, 1, 1, tzinfo=timezone.utc)),
              reverse=True)
    # Les meilleurs candidats sont testes en parallele : on garde le premier dont l'article
    # complet est lisible (sinon le resume du flux, plus court).
    order = pool[:8]
    if not wanted:
        random.shuffle(order)
    with ThreadPoolExecutor(max_workers=8) as bodies_pool:
        bodies = list(bodies_pool.map(lambda c: _article_text(c["url"]), order))
    main, body = order[0], ""
    best_words = 0
    for candidate, text in zip(order, bodies):
        words = _word_count(text)
        if words >= 120 and words > best_words:
            main, body, best_words = candidate, text, words
    if log:
        log(f"    {len(order)} articles testés, le plus riche : {best_words} mots")
    main_tokens = _tokens(main["title"])
    related = []
    for other in items:
        if other is main or other["source"] == main["source"] and other["title"] == main["title"]:
            continue
        other_tokens = _tokens(other["title"] + " " + other["summary"])
        shared = len(main_tokens & other_tokens)
        if other["title"] != main["title"] and shared >= min(2, max(1, len(main_tokens) // 2)):
            related.append(other)
    sources = [{"title": main["title"], "text": "", "url": main["url"], "source": main["source"],
                "date": main["date"]}]
    if log and not body:
        log("    article complet indisponible, résumé du flux utilisé")
    sources[0]["text"] = body if _word_count(body) > _word_count(main["summary"]) else main["summary"]
    if main["summary"] and main["summary"] not in sources[0]["text"]:
        sources[0]["text"] = main["summary"] + " " + sources[0]["text"]
    for other in (related[:2] if _word_count(sources[0]["text"]) < 120 else []):
        sources.append({"title": other["title"], "text": other["summary"], "url": other["url"],
                        "source": other["source"], "date": other["date"]})
    key = hashlib.sha1((main["url"] or main["title"]).encode()).hexdigest()[:12]
    return sources, key


# --------------------------------------------------------------------------- fetchers
def _add_wiki_context(items, topic, lang, need_words, log):
    """Complete une source courte avec l'introduction Wikipedia du sujet (marquee « contexte »)."""
    have = sum(_word_count(i["text"]) for i in items)
    if need_words and have >= need_words * 1.2:
        return False
    subject = topic or " ".join(sorted(_tokens(items[0]["title"]), key=len, reverse=True)[:3])
    if not subject:
        return False
    try:
        articles = _wiki_articles(subject, lang, [subject], limit=1)
    except Exception:
        return False
    for article in articles:
        items.append({"title": article["title"], "text": article["text"][:2500], "url": article.get("url", ""),
                      "source": "Wikipédia", "date": None, "context": True})
        if log:
            log(f"    contexte ajouté : Wikipédia « {article['title']} »")
        return True
    return False


def fetch_actu(topic, lang, niche, avoid_repeat=True, log=None, need_words=0):
    category = _category_for(niche, topic)
    table = FEEDS.get(lang, FEEDS["fr"])
    feeds = list(table.get(category, [])) + (table["une"][:2] if category != "une" else [])
    items, key = _pick_news(feeds, topic, 10, avoid_repeat, log, exclude=_LIVE_RX)
    label = "Actualité — " + items[0]["source"]
    if _add_wiki_context(items, topic, lang, need_words, log):
        label += " + contexte Wikipédia"
    return {"kind": "actu", "items": items, "key": key, "angle": "pourquoi_maintenant", "label": label}


_PRACTICAL_RX = re.compile(
    r"forfaits?|op[ée]rateurs?|esim|smartphones?|iphone|android|box internet|bon plan|promo|soldes|"
    r"guide d.achat|comparatif|meilleurs?\b|comment (?:choisir|bien|installer|activer|r[ée]soudre|profiter)|"
    r"\b5g\b|wi-?fi|abonnements?|black friday", re.I)


def fetch_science(topic, lang, niche, avoid_repeat=True, log=None, need_words=0):
    feeds = FEEDS.get(lang, FEEDS["fr"])["science"]
    items, key = _pick_news(feeds, topic, 45, avoid_repeat, log, exclude=_PRACTICAL_RX)
    label = "Science — " + items[0]["source"]
    if _add_wiki_context(items, topic, lang, need_words, log):
        label += " + contexte Wikipédia"
    return {"kind": "science", "items": items, "key": key, "angle": "decouverte", "label": label}


_MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
              "octobre", "novembre", "décembre"]


def fetch_jour(topic, lang, niche, avoid_repeat=True, log=None, need_words=0, today=None):
    today = today or datetime.now()
    url = "https://%s.wikipedia.org/api/rest_v1/feed/onthisday/events/%02d/%02d" % (
        lang, today.month, today.day)
    try:
        data = json.loads(_http_cached(url, ttl=6 * 3600, accept="application/json").decode("utf-8", "replace"))
    except (SourceError, ValueError) as exc:
        raise SourceError(f"« Ce jour-là » indisponible ({exc})") from exc
    events = [e for e in data.get("events", []) if e.get("pages") and len(e.get("text", "")) >= 60]
    wanted = _tokens(topic)
    if wanted:
        events = [e for e in events if wanted & _tokens(e["text"] + " " + " ".join(
            p.get("normalizedtitle", "") for p in e["pages"]))]
    if not events:
        raise SourceError("Aucun événement trouvé pour ce jour" + (f" et le sujet « {topic} »" if topic else ""))
    used = _used_keys() if avoid_repeat else set()

    def score(event):
        return len(event["text"]) + 40 * len(event["pages"]) + (60 if event.get("year", 3000) < 1950 else 0)

    events.sort(key=score, reverse=True)
    fresh = [e for e in events if "jour:%s" % e.get("year") + e["text"][:30] not in used] or events
    from . import webcontent as _wc
    best = None
    for cand in random.sample(fresh[:6], min(4, len(fresh[:6]))):
        cpage = cand["pages"][0]
        ctitle = cpage.get("normalizedtitle") or cpage.get("title") or ""
        ctext = ""
        try:
            ctext = (_wc._wiki_full_article(lang, ctitle) or {}).get("text", "")
        except Exception:
            pass
        richness = _word_count(ctext) + _word_count(cand["text"])
        if log:
            log(f"    événement {cand.get('year', '')} « {ctitle} » : {richness} mots")
        if best is None or richness > best[0]:
            best = (richness, cand, cpage, ctitle, ctext)
        if richness >= max(300, need_words * 3):
            break
    _, event, page, title, article_text = best
    month = _MONTHS_FR[today.month - 1] if lang == "fr" else today.strftime("%B")
    date_text = (f"{today.day if today.day > 1 else '1er'} {month}" if lang == "fr" else f"{month} {today.day}")
    lead = f"Le {date_text} {event.get('year', '')}, {event['text']}" if lang == "fr" else \
        f"On {date_text}, {event.get('year', '')}: {event['text']}"
    items = [{"title": title, "text": lead.strip() + " " + (article_text or page.get("extract", "")),
              "url": (page.get("content_urls", {}).get("desktop", {}) or {}).get("page", ""),
              "source": "Wikipédia", "date": None}]
    # un seul événement : pas d'événements parasites
    return {"kind": "jour", "items": items, "key": "jour:%s" % event.get("year") + event["text"][:30],
            "angle": "chronologie", "label": "Ce jour-là — Wikipédia", "date_text": date_text}


_MYTH_TOPICS = ["le cerveau",
                "le sommeil",
                "les requins",
                "le Moyen Âge",
                "l'alimentation",
                "le corps humain",
                "les dinosaures",
                "les pyramides d'Égypte",
                "les vikings",
                "le café",
                "les vaccins",
                "la Lune",
                "les chauves-souris",
                "les araignées",
                "les serpents",
                "le chocolat",
                "le sucre",
                "l'eau",
                "le rhume",
                "les cheveux",
                "les yeux",
                "les rêves",
                "la mémoire",
                "l'espace",
                "les châteaux forts",
                "les trous noirs",
                "la Grande Muraille de Chine",
                "Napoléon",
                "les gladiateurs",
                "les volcans",
                "la sorcellerie",
                "Christophe Colomb",
                "la foudre",
                "les caméléons",
                "les poissons rouges",
                "les tremblements de terre",
                "les éclipses",
                "les océans",
                "l'Antarctique",
                "le désert"]


_FICTION_RX = re.compile(
    r"\best (?:un|une) (?:s[ée]rie|film|manga|anime|album|jeu vid[ée]o|roman|bande dessin[ée]e|chanson|personnage)|"
    r"\best un (?:long[- ]m[ée]trage|dessin anim[ée])|"
    r"\bis an? (?:\w+ )?(?:series|film|manga|album|video game|novel)", re.I)


def _wiki_articles(topic, lang, queries, limit=3):
    from . import webcontent
    wanted = _tokens(topic)
    need = 1.0 if len(wanted) <= 2 else .67
    articles, seen = [], set()
    for query in queries:
        try:
            titles = webcontent._topic_titles(query, lang)
        except Exception:
            continue
        intros = {}
        try:
            intros = webcontent._wiki_intros(lang, titles[:5]) if titles else {}
        except Exception:
            pass
        for title in titles[:5]:
            intro = intros.get(title) or {}
            tokens = _tokens(title + " " + intro.get("text", ""))
            if title in seen or re.search(r"homonymie|disambiguation", title, re.I) \
                    or _FICTION_RX.search((intro.get("text") or "")[:300]):
                continue
            if wanted and len(wanted & tokens) / len(wanted) < need:
                continue
            full = webcontent._wiki_full_article(lang, title) or (intro if intro.get("text") else None)
            if full:
                seen.add(title)
                articles.append(full)
                break
        if len(articles) >= limit:
            break
    return articles


def fetch_mythes(topic, lang, niche, avoid_repeat=True, log=None, need_words=0):
    _done = _used_keys() if avoid_repeat else set()
    _free = [t for t in _MYTH_TOPICS if "mythes:" + _norm(t) not in _done] or _MYTH_TOPICS
    subject = topic or random.choice(_free)
    queries = ([subject + " idées reçues", subject, subject + " mythes et légendes"] if lang == "fr"
               else [subject + " misconceptions", subject, subject + " myths"])
    articles = _wiki_articles(subject, lang, queries)
    if not articles:
        raise SourceError(f"Aucune page Wikipédia pertinente sur « {subject} ».")
    items = [{"title": a["title"], "text": a["text"], "url": a.get("url", ""), "source": "Wikipédia",
              "date": None} for a in articles]
    return {"kind": "mythes", "items": items, "key": "mythes:" + _norm(subject), "angle": "mythe",
            "label": "Mythes & réalité — Wikipédia", "topic": subject}


def fetch_perso(topic, lang, niche, avoid_repeat=True, log=None, need_words=0):
    text = (topic or "").strip()
    if re.match(r"https?://", text):
        body = _article_text(text, limit=9000)
        if _word_count(body) < 80:
            raise SourceError("Page illisible ou trop courte : collez le texte à la place du lien.")
        host = urllib.parse.urlparse(text).netloc
        return {"kind": "perso", "items": [{"title": host, "text": body, "url": text, "source": host,
                                            "date": None}], "key": "perso:" + text[:60],
                "angle": "explique_simple", "label": "Mes sources — " + host}
    if _word_count(text) < 60:
        raise SourceError("Collez un lien (https://…) ou un texte d'au moins 60 mots dans le champ sujet.")
    return {"kind": "perso", "items": [{"title": text[:60], "text": text, "url": "", "source": "Texte fourni",
                                        "date": None}], "key": "perso:" + hashlib.sha1(text.encode()).hexdigest()[:10],
            "angle": "explique_simple", "label": "Mes sources — texte fourni"}


def fetch_bundle(source_id, topic="", lang="fr", niche="sujet", avoid_repeat=True, log=None, need_words=0):
    """Collecte seule (sans ecriture) : utile pour tester une source."""
    lang = "en" if lang == "en" else "fr"
    if source_id == "surprise":
        source_id = random.choice(["actu", "jour", "science", "mythes"])
        if log:
            log(f"    Surprends-moi : {SOURCE_LABELS[source_id]}")
    fetchers = {"actu": fetch_actu, "jour": fetch_jour, "science": fetch_science,
                "mythes": fetch_mythes, "perso": fetch_perso}
    if source_id not in fetchers:
        raise SourceError(f"Source inconnue : {source_id}")
    bundle = fetchers[source_id](topic, lang, niche, avoid_repeat, log, need_words=need_words)
    bundle["source_id"] = source_id
    return bundle


# --------------------------------------------------------------------------- angles
ANGLES = {
    "question_choc": {
        "llm": "Ouvre sur une question qui intrigue, puis réponds peu à peu avec les faits.",
        "fr": ["Et si tout ce que tu sais sur {t} était incomplet ?", "Pourquoi {t} fait-il autant parler ?",
               "{t} : as-tu vraiment tout compris ?"],
        "en": ["What if everything you know about {t} is incomplete?", "Why is {t} getting so much attention?"]},
    "mythe": {
        "llm": ("Le titre énonce une idée reçue. Alterne « On croit que » (idée répandue, formulée de façon générale) puis « En réalité » (le fait qui la corrige, tiré des faits numérotés), au moins trois fois. N'ajoute aucune croyance précise, aucun chiffre ni aucune comparaison que les faits ne soutiennent pas."),
        "fr": ["On t'a menti sur {t}.", "{t} : ce que tu crois est (peut-être) faux.", "Non, {t} ne fonctionne pas comme tu le penses."],
        "en": ["You've been lied to about {t}.", "{t}: what you believe may be wrong."]},
    "personne_ne_te_dit": {
        "llm": "Révèle le détail que presque personne ne raconte, avec un ton de confidence.",
        "fr": ["Ce que personne ne te dit sur {t}.", "{t} : le détail qu'on oublie toujours."],
        "en": ["What nobody tells you about {t}.", "{t}: the detail everyone forgets."]},
    "chronologie": {
        "llm": "Raconte comme une histoire datée : un début précis, une montée, un tournant, une conséquence.",
        "fr": ["{t} : cette journée a tout changé.", "Retour sur {t} : voilà ce qui s'est vraiment passé."],
        "en": ["{t}: the day everything changed.", "Back to {t}: what really happened."]},
    "pourquoi_maintenant": {
        "llm": "Explique ce qui vient de se passer, pourquoi ça arrive maintenant, et ce que ça change pour le spectateur.",
        "fr": ["{t} : voilà pourquoi tout le monde en parle.", "Ce qui vient de se passer avec {t}.",
               "{t} : ce que ça change pour toi."],
        "en": ["{t}: here's why everyone is talking about it.", "What just happened with {t}."]},
    "decouverte": {
        "llm": "Présente une découverte comme une enquête : ce qu'on ignorait, ce que les chercheurs ont trouvé, pourquoi c'est important.",
        "fr": ["Des chercheurs viennent de découvrir ça sur {t}.", "{t} : ce que la science vient de révéler."],
        "en": ["Scientists just found this about {t}.", "{t}: what science just revealed."]},
    "enquete": {
        "llm": "Mène une mini-enquête : une énigme, des indices, puis la réponse.",
        "fr": ["L'énigme {t} : voici les indices.", "Enquête sur {t}."],
        "en": ["The {t} mystery: here are the clues.", "Investigating {t}."]},
    "explique_simple": {
        "llm": "Explique simplement, comme à un ami curieux, avec une image ou une comparaison parlante.",
        "fr": ["{t}, expliqué simplement.", "{t} : l'essentiel, sans jargon."],
        "en": ["{t}, explained simply.", "{t}: the essentials, no jargon."]},
    "contraste": {
        "llm": "Oppose avant et après, ou idée reçue et réalité, pour créer un contraste net.",
        "fr": ["{t} : avant et après, la différence est énorme."],
        "en": ["{t}: before and after, the difference is huge."]},
}
_ANGLE_BY_NICHE = {"histoire": "chronologie", "psychologie": "personne_ne_te_dit", "faits": "question_choc",
                   "sante": "mythe", "argent": "personne_ne_te_dit",
                   "actu": "pourquoi_maintenant", "jour": "chronologie",
                   "science": "decouverte", "mythes": "mythe"}
_TRANSITIONS = {
    "fr": ["Et ce n'est pas tout.", "Mais voilà où ça devient intéressant.", "Retiens bien ce détail.",
           "Maintenant, regarde ce qui change.", "Là, tout bascule."],
    "en": ["And that's not all.", "But here's where it gets interesting.", "Remember this detail.",
           "Now look at what changes.", "That's where everything shifts."],
}


def choose_angle(bundle, niche, topic):
    if niche in ("actu", "jour", "science", "mythes"):
        return _ANGLE_BY_NICHE[niche]
    if bundle.get("angle") and bundle["angle"] in ANGLES and bundle["kind"] != "perso":
        return bundle["angle"]
    return _ANGLE_BY_NICHE.get(niche) or bundle.get("angle") or random.choice(list(ANGLES))


# --------------------------------------------------------------------------- Ollama
_MODEL_CACHE = {"ts": 0, "models": None}
_AVOID_MODELS = ("coder", "vl", "embed", "vision", "llava", "bge", "nomic")
_MODEL_PREFS = ("qwen3", "qwen2.5:14b", "qwen2.5:7b", "qwen2.5", "llama3.1", "llama3.2", "llama3",
                "mistral", "gemma", "phi")


def ollama_model(force=False):
    """Nom du meilleur modele texte installe, ou '' si Ollama est eteint."""
    if not force and time.time() - _MODEL_CACHE["ts"] < 60 and _MODEL_CACHE["models"] is not None:
        return _MODEL_CACHE["models"]
    chosen = ""
    try:
        raw = _http(OLLAMA_URL + "/api/tags", timeout=3)
        names = [m.get("name", "") for m in json.loads(raw.decode("utf-8")).get("models", [])]
        usable = [n for n in names if n and not any(bad in n.lower() for bad in _AVOID_MODELS)]
        for pref in _MODEL_PREFS:
            match = [n for n in usable if pref in n.lower()]
            if match:
                chosen = match[0]
                break
        chosen = chosen or (usable[0] if usable else "")
    except (SourceError, ValueError):
        chosen = ""
    _MODEL_CACHE.update(ts=time.time(), models=chosen)
    return chosen


def _ollama_json(model, system, prompt, timeout=240):
    from . import local_resources
    with local_resources.text_phase(model=model, ollama_url=OLLAMA_URL):
        body = json.dumps({"model": model, "stream": False, "format": "json",
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                           "options": {"temperature": .7, "num_ctx": 8192, "num_predict": 2400}}).encode("utf-8")
        request = urllib.request.Request(OLLAMA_URL + "/api/chat", data=body,
                                         headers={"Content-Type": "application/json", "User-Agent": UA})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = (payload.get("message") or {}).get("content", "")
            content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()
            return json.loads(content)
        except Exception as exc:
            raise SourceError(f"Ollama n'a pas répondu correctement ({type(exc).__name__})") from exc


_SYSTEM = {
    "fr": ("Tu es scénariste de vidéos courtes verticales (Shorts, Reels, TikTok). Tu écris pour la VOIX : "
           "phrases courtes et variées (6 à 18 mots), ton naturel et vivant, comme si tu racontais à un ami, "
           "dans un français correct : phrases complètes (sujet, verbe), accords soignés, pas de tournure bancale. "
           "RÈGLES STRICTES : tu n'utilises QUE les faits fournis. Tu n'inventes aucun chiffre, aucune date, "
           "aucun nom, aucune citation. Pas de liste, pas d'émoji, pas de « Bonjour », pas de parenthèses. "
           "Une idée visuelle par phrase. Première phrase = accroche forte. Termine par un appel à l'action court. "
           "Le titre ne contient aucune date ni jour précis, sauf si un fait fourni la donne. "
           "Les phrases s'enchaînent comme un récit continu sur UN seul sujet. "
           "Titre : majuscule seulement au début et aux noms propres, jamais à chaque mot ; ne promets jamais une résolution ou une révélation que les faits ne donnent pas. "
           "Aucune comparaison, aucun exemple ni aucun détail absents des faits fournis. Pas de points de suspension. "
           "Réponds UNIQUEMENT en JSON : {\"title\": \"...\", \"scenes\": [\"phrase 1\", \"phrase 2\", ...], "
           "\"cta\": \"...\", \"caption\": \"légende de 1 à 2 phrases\"}."),
    "en": ("You are a scriptwriter for vertical short videos. You write for the VOICE: short varied sentences "
           "(6 to 18 words), natural and lively, in correct grammatical English. STRICT RULES: use ONLY the facts provided. Never invent numbers, "
           "dates, names or quotes. No lists, no emoji, no greetings, no parentheses. One visual idea per sentence. "
           "First sentence = strong hook. End with a short call to action. Reply ONLY with JSON: "
           "{\"title\": \"...\", \"scenes\": [\"sentence 1\", ...], \"cta\": \"...\", \"caption\": \"1-2 sentences\"}."),
}


def _facts_block(items, budget_words):
    """Faits numerotes, issus des sources, dans une limite de mots."""
    lines, total = [], 0
    for index, item in enumerate(items, 1):
        for sentence in _clean_sentences(item["text"]):
            words = _word_count(sentence)
            if total + words > budget_words:
                return lines, total
            lines.append(f"[{index}] {sentence}")
            total += words
    return lines, total


_NUMBER_RX = re.compile(r"\d{1,3}(?:[\s\u202f\u00a0.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")


_SMALL_QTY_RX = re.compile(r"(?<![\d.,])(\d)\s*(?:millions?|milliards?|mille|%|pour ?cent|euros?|dollars?|€|\$)", re.I)


def _numbers(text):
    """Chiffres significatifs d'un texte (>= 2 chiffres, ou un chiffre suivi d'une grandeur :
    « 9 millions », « 5 % »), pour verifier que le script n'invente rien."""
    found = {re.sub(r"\D", "", n) for n in _NUMBER_RX.findall(text or "")}
    found = {n for n in found if len(n) >= 2}
    return found | {"q" + d for d in _SMALL_QTY_RX.findall(text or "")}


def _write_with_llm(model, bundle, angle, topic, lang, niche, target_words, log):
    facts, facts_words = _facts_block(bundle["items"], max(600, int(target_words * 3.2)))
    if facts_words < 40:
        raise SourceError("Pas assez de faits exploitables dans la source.")
    goal = min(target_words, max(30, int(facts_words * .9)))
    subject = topic or bundle["items"][0]["title"]
    lines = "\n".join(facts)
    legend = " ; ".join(f"[{n}] {i['source']}" + (" (contexte)" if i.get("context") else "")
                        for n, i in enumerate(bundle["items"], 1))
    lines = f"SOURCES : {legend}\n" + lines
    if lang == "fr":
        prompt = (f"SUJET : {subject}\nANGLE : {ANGLES[angle]['llm']}\nLONGUEUR : environ {goal} mots au total "
                  f"(soit environ {max(8, goal // 14)} phrases), pas plus que ce que les faits permettent.\n"
                  f"LANGUE : français.\n\nFAITS (seule matière autorisée) :\n{lines}")
    else:
        prompt = (f"SUBJECT: {subject}\nANGLE: {ANGLES[angle]['llm']}\nLENGTH: about {goal} words in total "
                  f"(about {max(8, goal // 14)} sentences), no more than the facts allow.\nLANGUAGE: English.\n\n"
                  f"FACTS (only allowed material):\n{lines}")
    allowed = _numbers(lines + " " + subject)
    best = None
    for attempt in range(3):
        out = _ollama_json(model, _SYSTEM[lang], prompt)
        scenes = [re.sub(r"\s+", " ", re.sub(r"\s*\([^)]*\)", "", re.sub(r"\[\d+\]", "", str(s)))).strip() for s in out.get("scenes") or []]
        scenes = [s for s in scenes if _word_count(s) >= 3]
        kept = []
        for sentence in scenes:
            if _numbers(sentence) - allowed:
                if log:
                    log("    phrase retirée (chiffre absent des sources) : " + sentence[:60])
                continue
            kept.append(sentence)
        total = sum(_word_count(s) for s in kept)
        if len(kept) >= 4 and (best is None or total > best[1]):
            best = ({**out, "scenes": kept}, total)
        if len(kept) >= 4 and total >= goal * .9:
            break
        prompt += (f"\n\nRAPPEL : ta réponse précédente faisait {total} mots ; vise {goal} mots en "
                   "t'appuyant davantage sur les faits fournis.")
    if not best:
        raise SourceError("La réécriture n'a pas produit un script exploitable.")
    return best[0]


def _write_simple(bundle, angle, topic, lang, niche, target_words, rng):
    """Mise en forme sans IA : faits des sources, accroche d'angle, transitions rares."""
    facts, _ = _facts_block(bundle["items"], max(600, int(target_words * 2.5)))
    sentences = [re.sub(r"^\[\d+\]\s*", "", f) for f in facts]
    if len(sentences) < 3:
        raise SourceError("Pas assez de phrases exploitables dans la source.")
    title_source = (topic or bundle["items"][0]["title"]).strip()
    short = title_source if len(title_source) <= 60 else title_source[:60].rsplit(" ", 1)[0]
    template = rng.choice(ANGLES[angle].get(lang) or ANGLES[angle]["fr"])
    hook = template.format(t=short)
    hook = hook[:1].upper() + hook[1:]
    body, words = [hook], 0
    for index, sentence in enumerate(sentences):
        if index and index % 5 == 0 and rng.random() < .8:
            body.append(rng.choice(_TRANSITIONS[lang]))
        body.append(sentence)
        words += _word_count(sentence)
        if words >= target_words:
            break
    return {"title": hook, "scenes": body, "cta": "", "caption": ""}


# --------------------------------------------------------------------------- assemblage
_DATE_RX = re.compile(
    r"\b(?:du\s+|le\s+)?\d{1,2}(?:er)?\s+(?:janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|"
    r"septembre|octobre|novembre|d[ée]cembre)(?:\s+\d{4})?", re.I)


def _title_without_invented_dates(title, bundle):
    # retire du titre toute date absente de la matière source
    blob = _norm(" ".join((i.get("text") or "") + " " + (i.get("title") or "") for i in bundle["items"]))
    cleaned = _DATE_RX.sub(lambda m: m.group(0) if _norm(m.group(0)) in blob else "", title or "")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" :,-–—")
    return cleaned or title


_TAGS = {
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


def _sentence_case_title(title, bundle):
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


def _pick_cta(source_id, lang, title=""):
    """Fin de vidéo tirée de la banque de la rubrique (vide si rubrique inconnue)."""
    bank = (_CTAS.get(source_id) or {}).get(lang) or []
    return random.choice(bank) if bank else ""


def generate(source_id, niche="sujet", lang="fr", topic="", target=None, avoid_repeat=True, log=None, local=False):
    """Script complet depuis une source supplementaire. Leve SourceError si impossible."""
    from . import content as content_mod
    from . import webcontent
    lang = "en" if lang == "en" else "fr"
    started = time.time()
    wanted = content_mod.target_words(target, lang)
    cache_key = "editorial:" + json.dumps([source_id, lang, _norm(topic)], ensure_ascii=False)
    warnings = []
    if local:
        bundle = _cache_get(cache_key, float("inf"))
        if not bundle:
            raise SourceError("Aucune source conservée pour cette niche et ce sujet. Générez d'abord avec la source Web.")
        warnings.append("Sources conservées hors ligne : les dates et les faits n'ont pas été actualisés.")
    else:
        try:
            bundle = fetch_bundle(source_id, topic, lang, niche, avoid_repeat, log, need_words=wanted)
            if source_id != "perso":
                _cache_put(cache_key, bundle)
        except SourceError as exc:
            bundle = _cache_get(cache_key, float("inf")) if source_id != "perso" else None
            if not bundle:
                raise
            local = True
            warnings.append(f"Web indisponible ({exc}) : sources conservées hors ligne, non actualisées.")
    angle = choose_angle(bundle, niche, topic)
    rng = random.Random(hashlib.sha1((bundle["key"] + str(time.time_ns())).encode()).hexdigest())
    model = ollama_model() if not local else ""
    written = None
    if model:
        if log:
            log(f"    écriture naturelle avec {model} (angle : {angle})")
        try:
            written = _write_with_llm(model, bundle, angle, topic, lang, niche, wanted, log)
        except SourceError as exc:
            warnings.append(f"Réécriture IA impossible ({exc}) : mise en forme simple utilisée.")
    elif not local:
        warnings.append("Ollama éteint : mise en forme simple (sans réécriture naturelle).")
    if written is None:
        written = _write_simple(bundle, angle, topic, lang, niche, wanted, rng)
    scenes = [s for s in written["scenes"] if s]
    title = _title_without_invented_dates((written.get("title") or scenes[0]).strip(), bundle)
    title = _sentence_case_title(title, bundle)
    hook = scenes[0]
    cta = _pick_cta(source_id, lang, title) or (written.get("cta") or "").strip() or webcontent._cta_for(niche, lang)
    names = [f"{bundle['label']}"] + [f"{i['source']} « {i['title'][:70]} »" for i in bundle["items"][:3] if i["title"]]
    urls = [i["url"] for i in bundle["items"] if i.get("url")]
    caption, hashtags = webcontent._caption(topic or bundle["items"][0]["title"], hook, scenes, niche, lang,
                                            names, urls[0] if urls else "")
    _tg = _tags_for(source_id, lang, title, bundle)
    if _tg and hashtags:
        caption = caption.replace(hashtags, _tg)
        hashtags = _tg
    if written.get("caption"):
        written["caption"] = re.sub(r"\s*#\w+", "", written["caption"])
        tags = hashtags if isinstance(hashtags, str) else " ".join(hashtags or [])
        caption = re.sub(r"\s*\b(?:en|in)\s+\d+\s+(?:mots|words)\b", "", written["caption"]).strip() + "\n\n" + tags + "\n\nSources : " + " ; ".join(names[:3])
    script = {"id": hashlib.sha1((bundle["key"] + str(time.time_ns())).encode()).hexdigest()[:12],
              "niche": niche, "language": lang, "title": title[:100], "hook": hook, "cta": cta,
              "scenes": [*scenes, cta], "caption": caption, "hashtags": hashtags, "angle": angle,
              "source": "local" if local else ("perso" if source_id == "perso" else "web"),
              "source_name": bundle["label"], "source_url": urls[0] if urls else "",
              "sources": [{"title": i["title"] or bundle["label"], "url": i.get("url", "")} for i in bundle["items"]],
              "warnings": warnings}
    fitted = content_mod.fit_script(script, target)
    if avoid_repeat and not local:
        _mark_used(bundle["key"])
    if log:
        log(f"    source « {bundle['label']} » : {len(bundle['items'])} élément(s), {time.time() - started:.1f}s")
    return fitted
