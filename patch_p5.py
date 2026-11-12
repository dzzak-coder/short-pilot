import os, re, shutil, subprocess, sys, time, pathlib

def load(p):
    raw = pathlib.Path(p).read_bytes().decode("utf-8")
    return ("\r\n" in raw), raw.replace("\r\n", "\n")

def swap(text, old, new, label):
    n = text.count(old)
    if n != 1:
        sys.exit(f"« {label} » trouvé {n} fois (attendu 1). Rien n'est modifié.")
    return text.replace(old, new)

crlf_c, c = load("core/content.py")
crlf_s, s = load("core/sources.py")
crlf_w, w = load("core/webcontent.py")

# 1. short_scenes : option grouped (morceaux d'une même phrase gardés ensemble)
c = swap(c, '''def short_scenes(lines, max_words=22):
    """Déduplique et découpe les phrases sans ajouter de faits ni de remplissage."""
    out, seen = [], set()
''', '''def short_scenes(lines, max_words=22, grouped=False):
    """Déduplique et découpe les phrases sans ajouter de faits ni de remplissage."""
    groups, seen = [], set()
''', "short_scenes entête")
c = swap(c, '''            words = sentence.split()
            while len(words) > max_words:
                # Privilégie une respiration grammaticale proche du budget.
                cuts = [i for i in range(10, min(max_words, len(words)))
                        if words[i - 1].endswith((",", ";", ":"))]
                cut = cuts[-1] if cuts else max_words
                out.append(" ".join(words[:cut]))
                words = words[cut:]
            if words:
                out.append(" ".join(words))
    # Deux phrases différentes peuvent partager un même segment après découpage.
    return list(dict.fromkeys(out))
''', '''            words = sentence.split()
            pieces = []
            while len(words) > max_words:
                # Privilégie une respiration grammaticale proche du budget.
                cuts = [i for i in range(10, min(max_words, len(words)))
                        if words[i - 1].endswith((",", ";", ":"))]
                cut = cuts[-1] if cuts else max_words
                pieces.append(" ".join(words[:cut]))
                words = words[cut:]
            if words:
                pieces.append(" ".join(words))
            groups.append(pieces)
    if not grouped:
        # Deux phrases différentes peuvent partager un même segment après découpage.
        return list(dict.fromkeys(p for g in groups for p in g))
    out, seen_pieces = [], set()
    for g in groups:
        g = [p for p in g if p not in seen_pieces]
        seen_pieces.update(g)
        if g:
            out.append(g)
    return out
''', "short_scenes corps")

# 2. fit_script : une phrase découpée est gardée entière ou retirée entière
c = swap(c, '''    pool = short_scenes([*scenes[1:-1], *extra_lines], max_words=max(7, min(20, wanted // 6)))
    body, total = [], word_count(hook) + word_count(cta)
    for sentence in pool:
        count = word_count(sentence)
        if total + count > wanted * 1.15:
            continue
        body.append(sentence)
        total += count
''', '''    pool = short_scenes([*scenes[1:-1], *extra_lines], max_words=max(7, min(20, wanted // 6)),
                        grouped=True)
    body, total = [], word_count(hook) + word_count(cta)
    for group in pool:
        count = sum(word_count(p) for p in group)
        if total + count > wanted * 1.15:
            continue
        body.extend(group)
        total += count
''', "fit_script")

# 3. Science : retirer Le Monde Planète
s, n = re.subn(r',\s*\("Le Monde Planète", "https://www\.lemonde\.fr/planete/rss_full\.xml"\)\]', ']', s)
if n != 1:
    sys.exit(f"Flux Le Monde Planète trouvé {n} fois (attendu 1). Rien n'est modifié.")

# 4. légende : retirer « en 78 mots »
s = swap(s, 'caption = written["caption"].strip() + "\\n\\n" + tags',
         'caption = re.sub(r"\\s*\\b(?:en|in)\\s+\\d+\\s+(?:mots|words)\\b", "", written["caption"]).strip() + "\\n\\n" + tags',
         "légende")

# 5. Wikipédia 429 : 3 essais
w = swap(w, "    for attempt in (1, 2):\n        try:\n            r = requests.get(url, params=params",
         "    for attempt in (1, 2, 3):\n        try:\n            r = requests.get(url, params=params", "boucle _get")
w = swap(w, "if r.status_code == 429 and attempt == 1:", "if r.status_code == 429 and attempt < 3:", "429")
w = swap(w, "            if attempt == 2:\n                return None", "            if attempt == 3:\n                return None", "fin _get")

for name, txt in (("content", c), ("sources", s), ("webcontent", w)):
    compile(txt, name + ".py", "exec")
for name in ("content", "sources", "webcontent"):
    shutil.copy(f"core/{name}.py", f"core/{name}.py.bak_p5")
for name, txt, crlf in (("content", c, crlf_c), ("sources", s, crlf_s), ("webcontent", w, crlf_w)):
    pathlib.Path(f"core/{name}.py").write_bytes((txt.replace("\n", "\r\n") if crlf else txt).encode("utf-8"))
print("OK : 3 fichiers modifiés (sauvegardes .bak_p5)")

env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
t0 = time.time()
r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"],
    capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
print((r.stderr or r.stdout)[-300:])
print(f"durée des tests : {time.time() - t0:.1f} s")
