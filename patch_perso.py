import re, shutil, subprocess, sys, pathlib
p = pathlib.Path("templates/index.html")
raw = p.read_bytes().decode("utf-8")
new, n = re.subn(r'\s*<option value="perso">.*?</option>', '', raw, flags=re.S)
print(n, "option(s) retirée(s)")
if n != 2:
    sys.exit("Attendu : 2. Rien n'est modifié.")
shutil.copy(p, "templates/index.html.bak_perso")
p.write_bytes(new.encode("utf-8"))
print("Lignes restantes mentionnant perso :")
for i, l in enumerate(new.splitlines(), 1):
    if "perso" in l:
        print(f"  {i}: {l.strip()[:110]}")
r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-q"],
                   capture_output=True, text=True)
print((r.stderr or r.stdout)[-400:])
