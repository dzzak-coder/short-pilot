import json, os, re, shutil, subprocess, sys, pathlib

path = pathlib.Path("core/sources.py")
raw = path.read_bytes().decode("utf-8")
crlf = "\r\n" in raw
s = raw.replace("\r\n", "\n")

def swap(text, old, new, label):
    n = text.count(old)
    if n != 1:
        sys.exit(f"« {label} » trouvé {n} fois (attendu 1). Rien n'est modifié.")
    return text.replace(old, new)

# 1. jusqu'à 8 articles lus en parallèle
s = swap(s, "    order = pool[:4]\n", "    order = pool[:8]\n", "order")
s = swap(s, "with ThreadPoolExecutor(max_workers=4) as bodies_pool:",
         "with ThreadPoolExecutor(max_workers=8) as bodies_pool:", "pool articles")

# 2. garder l'article le plus riche
s = swap(s, '''    main, body = order[0], ""
    for candidate, text in zip(order, bodies):
        if _word_count(text) >= 120:
            main, body = candidate, text
            break
''', '''    main, body = order[0], ""
    best_words = 0
    for candidate, text in zip(order, bodies):
        words = _word_count(text)
        if words >= 120 and words > best_words:
            main, body, best_words = candidate, text, words
    if log:
        log(f"    {len(order)} articles testés, le plus riche : {best_words} mots")
''', "choix article")

# 3. relance du modèle : 3 essais
s = swap(s, "    for attempt in range(2):\n        out = _ollama_json(",
         "    for attempt in range(3):\n        out = _ollama_json(", "relance modèle")

# 4. Mythes : 40 sujets, sans répéter ceux déjà faits
topics = ["le cerveau", "le sommeil", "les requins", "le Moyen Âge", "l'alimentation",
 "le corps humain", "les dinosaures", "les pyramides d'Égypte", "les vikings", "le café",
 "les vaccins", "la Lune", "les chauves-souris", "les araignées", "les serpents",
 "le chocolat", "le sucre", "l'eau", "le rhume", "les cheveux", "les yeux", "les rêves",
 "la mémoire", "l'espace", "le Soleil", "les trous noirs", "la Grande Muraille de Chine",
 "Napoléon", "les gladiateurs", "les chevaliers", "la sorcellerie", "Christophe Colomb",
 "la foudre", "les caméléons", "les poissons rouges", "les taureaux", "les chats",
 "les chiens", "l'Antarctique", "le désert"]
block = "_MYTH_TOPICS = [" + ",\n                ".join(json.dumps(t, ensure_ascii=False) for t in topics) + "]"
s, n = re.subn(r"_MYTH_TOPICS = \[.*?\]", lambda m: block, s, count=1, flags=re.S)
if n != 1:
    sys.exit("Liste _MYTH_TOPICS introuvable. Rien n'est modifié.")
s = swap(s, "    subject = topic or random.choice(_MYTH_TOPICS)\n",
'''    _done = _used_keys() if avoid_repeat else set()
    _free = [t for t in _MYTH_TOPICS if "mythes:" + _norm(t) not in _done] or _MYTH_TOPICS
    subject = topic or random.choice(_free)
''', "choix sujet mythe")

compile(s, "sources.py", "exec")
shutil.copy(path, "core/sources.py.bak_p4")
path.write_bytes((s.replace("\n", "\r\n") if crlf else s).encode("utf-8"))
print("OK : sources.py modifié (sauvegarde : core/sources.py.bak_p4)")

env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
r = subprocess.run([sys.executable, "-c",
    "from core import sources as s; print(len(s._MYTH_TOPICS), 'sujets'); print(s._MYTH_TOPICS[4])"],
    capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
print(r.stdout or r.stderr)
r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"],
    capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
print((r.stderr or r.stdout)[-300:])
