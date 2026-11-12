r"""Branche les nouvelles sources dans ShortPilot (menu + génération).

Usage (depuis le dossier shortpilot, après avoir placé core\sources.py) :
    .\.venv\Scripts\python.exe installer_sources.py

Modifie core/content.py, app.py et templates/index.html. Sauvegardes : *.bak_sources
Relancez ensuite ShortPilot et faites Ctrl+F5 dans le navigateur.
"""
import ast
import html
import pathlib
import re
import shutil
import sys

LABELS = [
    ("actu", "📰 Actualité — ce qui se passe et pourquoi"),
    ("jour", "📅 Ce jour-là — une histoire datée"),
    ("science", "🔬 Science & découvertes"),
    ("mythes", "🧠 Mythes & réalité"),
    ("perso", "🔗 Mes sources — lien ou texte collé"),
    ("surprise", "🎲 Surprends-moi"),
]
root = pathlib.Path(".")


def read(path):
    return open(path, encoding="utf-8", newline="").read()


def write(path, text):
    shutil.copy2(path, str(path) + ".bak_sources")
    open(path, "w", encoding="utf-8", newline="").write(text)


def fail(message):
    sys.exit("ARRÊT : " + message + "\nRien n'a été modifié dans ce fichier.")


if not (root / "core" / "sources.py").exists():
    sys.exit("core\\sources.py introuvable : placez d'abord sources.py dans le dossier core.")
done = []

# 1. core/content.py : le point d'entrée generate_script gère les nouvelles sources
path = root / "core" / "content.py"
text = read(path)
if "EXTRA_SOURCE_IDS" in text:
    done.append("content.py : déjà fait")
else:
    nl = "\r\n" if "\r\n" in text else "\n"
    old = 'def generate_script(niche="motivation"'
    if text.count(old) != 1:
        fail("def generate_script introuvable dans core/content.py")
    wrapper = '''

# --- Sources supplémentaires (actualité, ce jour-là, science, mythes, mes sources) ---
EXTRA_SOURCE_IDS = ("actu", "jour", "science", "mythes", "perso", "surprise")
SOURCE_IDS = ("web", "local") + EXTRA_SOURCE_IDS


def generate_script(niche="motivation", lang="fr", topic="", avoid_repeat=True, target=None,
                    source="local", log=None):
    """Point d'entrée : sources supplémentaires, avec repli sur le moteur historique."""
    note = ""
    if source in EXTRA_SOURCE_IDS:
        try:
            from . import sources as _sources
            return _sources.generate(source, niche=niche, lang=lang, topic=topic, target=target,
                                     avoid_repeat=avoid_repeat, log=log)
        except Exception as exc:  # source indisponible : on ne bloque jamais l'utilisateur
            note = f"Source « {source} » indisponible ({exc}) : encyclopédie utilisée à la place."
            logging.getLogger(__name__).warning(note)
            if log:
                log("    " + note)
            source = "web"
    script = _generate_script_core(niche=niche, lang=lang, topic=topic, avoid_repeat=avoid_repeat,
                                   target=target, source=source, log=log)
    if note:
        script.setdefault("warnings", []).append(note)
    return script
'''.replace("\n", nl)
    new = text.replace(old, 'def _generate_script_core(niche="motivation"') .rstrip() + nl + wrapper
    if "import logging" not in new:
        fail("« import logging » absent de core/content.py")
    ast.parse(new)
    write(path, new)
    done.append("content.py : point d'entrée ajouté")

# 2. app.py : accepter les nouvelles sources (3 endroits)
path = root / "app.py"
text = read(path)
if "content.SOURCE_IDS" in text:
    done.append("app.py : déjà fait")
else:
    if text.count('("web", "local")') != 3:
        fail(f'app.py : 3 occurrences de ("web", "local") attendues, {text.count(chr(40) + chr(34) + "web" + chr(34))} trouvées')
    new = text.replace('("web", "local")', "content.SOURCE_IDS")
    ast.parse(new)
    write(path, new)
    done.append("app.py : 3 contrôles étendus")

# 3. templates/index.html : options du menu (création + réglages par défaut)
path = root / "templates" / "index.html"
text = read(path)
if 'value="actu"' in text:
    done.append("index.html : déjà fait")
else:
    nl = "\r\n" if "\r\n" in text else "\n"
    options = "".join(f'<option value="{k}">{html.escape(v, quote=False)}</option>' for k, v in LABELS)
    count = 0

    def add(match):
        global count
        count += 1
        return match.group(1) + match.group(2) + options + match.group(3)

    new = re.sub(r'(<select id="(?:d_)?csource">)(.*?)(</select>)', add, text, flags=re.S)
    if count != 2:
        fail(f"index.html : 2 menus attendus, {count} trouvés")
    write(path, new)
    done.append("index.html : 6 options ajoutées aux 2 menus")

print("OK :")
for line in done:
    print("  -", line)
print("Relancez ShortPilot (fermez la fenêtre noire, relancez ShortPilot.bat), puis Ctrl+F5.")
