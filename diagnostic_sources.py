r"""Diagnostic des nouvelles sources de ShortPilot (à lancer sur ton PC).

    .\.venv\Scripts\python.exe diagnostic_sources.py
    .\.venv\Scripts\python.exe diagnostic_sources.py "intelligence artificielle"
    .\.venv\Scripts\python.exe diagnostic_sources.py "les requins" --ecrire

Sans sujet : teste chaque source sans filtre. --ecrire : écrit aussi un script de 60 s
par source qui répond (utilise Ollama s'il est allumé).
"""
import sys
import time

from core import sources

args = [a for a in sys.argv[1:] if not a.startswith("--")]
topic = args[0] if args else ""
write = "--ecrire" in sys.argv


def short(text, n=70):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n - 1] + "…"


print("== 1. Réseau : flux et API ==")
urls = []
for lang in ("fr", "en"):
    for category, feeds in sources.FEEDS[lang].items():
        urls.extend((f"{name} [{lang}/{category}]", url) for name, url in feeds)
urls.append(("Wikipédia « Ce jour-là » [fr]", "https://fr.wikipedia.org/api/rest_v1/feed/onthisday/events/11/01"))
ok = 0
for name, url in urls:
    started = time.time()
    try:
        raw = sources._http(url, timeout=10)
        entries = None if raw.lstrip()[:1] in (b"{", b"[") else len(sources._parse_feed(raw))
        info = f"{len(raw) // 1024} Ko" + (f", {entries} articles" if entries is not None else "")
        print(f"  OK     {name:<38} {info} ({time.time() - started:.1f}s)")
        ok += 1
    except sources.SourceError as exc:
        print(f"  ÉCHEC  {name:<38} {exc}")
    except Exception as exc:
        print(f"  ÉCHEC  {name:<38} {type(exc).__name__}: {short(exc)}")
print(f"  -> {ok}/{len(urls)} répondent")

print("\n== 2. Ollama (écriture naturelle) ==")
model = sources.ollama_model(force=True)
print("  modèle choisi :", model or "AUCUN (Ollama éteint ou sans modèle texte) : mise en forme simple")

print("\n== 3. Sources complètes ==" + (f" (sujet : {topic})" if topic else " (sans sujet)"))
working = []
for source_id, label in sources.SOURCE_LABELS.items():
    if source_id in ("surprise", "perso"):
        continue
    subject = topic or ("les requins" if source_id == "mythes" else "")
    started = time.time()
    try:
        bundle = sources.fetch_bundle(source_id, subject, "fr", "sujet", avoid_repeat=False)
        words = sum(sources._word_count(i["text"]) for i in bundle["items"])
        print(f"  OK     {source_id:<8} {len(bundle['items'])} élément(s), {words} mots | {short(bundle['items'][0]['title'])} ({time.time() - started:.1f}s)")
        working.append((source_id, subject))
    except sources.SourceError as exc:
        print(f"  ÉCHEC  {source_id:<8} {exc}")
    except Exception as exc:
        print(f"  ERREUR {source_id:<8} {type(exc).__name__}: {short(exc, 120)}")

if write and working:
    print("\n== 4. Scripts de 60 s ==")
    for source_id, subject in working:
        try:
            script = sources.generate(source_id, "sujet", "fr", subject, 60, avoid_repeat=False)
            print(f"  {source_id}: « {script['title']} » ({script['word_count']}/{script['target_words']} mots, angle {script['angle']})")
            for scene in script["scenes"][:3]:
                print("     -", short(scene, 95))
            for warning in script.get("warnings", []):
                print("     !", short(warning, 110))
        except Exception as exc:
            print(f"  ERREUR {source_id}: {type(exc).__name__}: {short(exc, 140)}")
print("\nTerminé. Copie ce texte dans le chat.")
