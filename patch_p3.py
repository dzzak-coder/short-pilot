import os, shutil, subprocess, sys, pathlib

def load(path):
    raw = pathlib.Path(path).read_bytes().decode("utf-8")
    return ("\r\n" in raw), raw.replace("\r\n", "\n")

def swap(text, old, new, label):
    n = text.count(old)
    if n != 1:
        sys.exit(f"« {label} » trouvé {n} fois (attendu 1). Rien n'est modifié.")
    return text.replace(old, new)

crlf_s, s = load("core/sources.py")
crlf_c, c = load("core/content.py")
if "_pick_cta" not in s:
    sys.exit("Le correctif 2 (hashtags/fins) n'est pas dans sources.py. Rien n'est modifié.")

# 1. pubs des sites sources
s = swap(s, r'''r"publi[ée] le|mis [àa] jour le|temps de lecture", re.I)''',
 r'''r"publi[ée] le|mis [àa] jour le|temps de lecture|"
    r"t[ée]l[ée]charg|google play|app store|appstore|nos applications|notre application|"
    r"l'application (?:rfi|france ?24|mobile|gratuite)|rfi\.fr|france24\.com|"
    r"retrouvez (?:toute|notre)|[ée]coutez (?:rfi|notre)", re.I)''', "bruit")

# 2. parenthèses écrites par le modèle
s = swap(s, r'''re.sub(r"\[\d+\]", "", str(s))''',
 r'''re.sub(r"\s*\([^)]*\)", "", re.sub(r"\[\d+\]", "", str(s)))''', "parenthèses LLM")

# 3. nouvelle tentative sur 429 / 503
s = swap(s, '''    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(3_000_000)
    except Exception as exc:  # HTTPError, URLError, timeout...
        code = getattr(exc, "code", "")
        host = urllib.parse.urlparse(url).netloc
        raise SourceError(f"{host} injoignable ({code or type(exc).__name__})") from exc''',
'''    exc = None
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
    raise SourceError(f"{host} injoignable ({code or type(exc).__name__})") from exc''', "_http")

# 4. Ce jour-là : un seul événement, le plus riche parmi 4
s = swap(s, '''    event = random.choice(fresh[:5])
    page = event["pages"][0]
    title = page.get("normalizedtitle") or page.get("title") or ""
    article_text = ""
    try:
        from . import webcontent
        article = webcontent._wiki_full_article(lang, title)
        article_text = (article or {}).get("text", "")
    except Exception:
        pass
''', '''    from . import webcontent as _wc
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
''', "choix événement")
s = swap(s, '''    for other in fresh[:8]:
        if other is event:
            continue
        items.append({"title": "", "text": f"En {other.get('year', '')}, {other['text']}",
                      "url": "", "source": "Wikipédia", "date": None})
        if len(items) >= 3:
            break
''', '''    # un seul événement : pas d'événements parasites
''', "événements parasites")

# 5. rubriques éditoriales : toujours le web (le cache sert de secours dans generate)
c = swap(c, 'avoid_repeat=avoid_repeat, log=log, local=source == "local")',
         'avoid_repeat=avoid_repeat, log=log, local=False)', "mode local")

compile(s, "sources.py", "exec"); compile(c, "content.py", "exec")
shutil.copy("core/sources.py", "core/sources.py.bak_p3")
shutil.copy("core/content.py", "core/content.py.bak_p3")
pathlib.Path("core/sources.py").write_bytes((s.replace("\n", "\r\n") if crlf_s else s).encode("utf-8"))
pathlib.Path("core/content.py").write_bytes((c.replace("\n", "\r\n") if crlf_c else c).encode("utf-8"))
print("OK : sources.py et content.py modifiés (sauvegardes .bak_p3)")

env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
chk = ("from core import sources as s; "
       "print(s._tags_for('mythes','fr','Les Mythes et Vérités sur les Requins')); "
       "print(s._pick_cta('actu','fr')); "
       "print(bool(s._NOISE_RX.search('Téléchargez l application RFI')))")
r = subprocess.run([sys.executable, "-c", chk], capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=env)
print(r.stdout or r.stderr)
r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
print((r.stderr or r.stdout)[-500:])
