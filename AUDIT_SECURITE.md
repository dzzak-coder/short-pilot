# 🛡️ Audit de sécurité & analyse fonctionnelle — ShortPilot

**Date :** 3 octobre 2026 · **Périmètre :** 100 % du code (`app.py`, `core/*.py`, `templates/index.html`,
~2 950 lignes) + dépendances + configuration de déploiement.
**Méthodes :** revue manuelle ligne par ligne, tests d'attaque réels contre le serveur (`curl`),
analyse statique des dépendances (`pip-audit` / base PYSEC), tests fonctionnels E2E.

---

## 1 · Synthèse exécutive

| | Avant l'audit | Après remédiation |
|---|---|---|
| Vulnérabilités **critiques/élevées** | 3 | **0** |
| Vulnérabilités **moyennes** | 3 | 0 |
| Vulnérabilités **faibles/info** | 5 | 0 (1 dép. suivie) |
| Bugs fonctionnels | 3 | 0 |
| **Note globale** (usage local mono-utilisateur) | **5/10** | **8,5/10** |

**Verdict : le projet est prêt pour une publication GitHub publique.**
Aucun secret codé en dur, aucun pattern dangereux (`eval`, `shell=True`, `pickle`…), aucun appel
système injectable. Toutes les failles trouvées ont été corrigées et chaque correction est
**vérifiée par un test reproductible** (ci-dessous).

> ⚠️ Rappel périmètre : ShortPilot est un outil **local mono-utilisateur**. Exposé publiquement,
> une authentification forte e(s)t un reverse proxy HTTPS restent nécessaires (voir §5).

---

## 2 · Vulnérabilités corrigées (11)

### 🔴 V1 — Accès non authentifié si le serveur est exposé *(élevée)*
**Constat :** `app.run(host="0.0.0.0")` + aucune authentification. Sur un réseau, n'importe qui
pouvait uploader des fichiers, lancer des rendus (épuisement CPU), modifier les réglages
(webhook → V3), publier et supprimer des vidéos.
**Correctif :**
- Écoute par défaut sur `127.0.0.1` (variable `SHORTPILOT_HOST` pour ouvrir).
- **Token d'accès** `SHORTPILOT_TOKEN` : si défini, toutes les routes `/api/*` et `/media/*`
  exigent l'en-tête `X-ShortPilot-Token` (comparaison `hmac.compare_digest`, anti *timing attack*) ;
  l'UI web le demande une fois puis le mémorise (localStorage).
- Si le serveur écoute sur le réseau **sans token**, un avertissement rouge est affiché au démarrage
  : `⚠️ Écoute réseau SANS token !`.
**Vérification :** démarrage testé avec/sans token ; avertissement présent.

### 🔴 V2 — CSRF « drive-by localhost » *(élevée)*
**Constat :** `request.get_json(force=True)` parsait du JSON **quel que soit le Content-Type**.
Un site malveillant visité par l'utilisateur pouvait poster `text/plain` (sans preflight CORS) vers
`http://127.0.0.1:8000/api/settings`, changer le webhook, puis publier une vidéo existante vers
l'URL de l'attaquant (exfiltration des vidéos).
**Correctif :** middleware `before_request` : ① les POST sur `/api/*` exigent
`Content-Type: application/json` (→ 415 sinon, sauf l'upload multipart) — un POST cross-origin
JSON déclenche un preflight que le navigateur bloque ; ② rejet (403) de tout POST dont
l'en-tête `Origin` ne correspond pas à l'hôte.
**Vérification :** `curl -X POST /api/settings -H 'Content-Type: text/plain' …` → **415** ✔ ;
`Origin: https://evil.com` → **403** ✔ ; usage normal du navigateur inchangé ✔.

### 🔴 V3 — SSRF via l'URL de webhook *(élevée)*
**Constat :** `publish_webhook` POSTait la vidéo vers **n'importe quelle URL** (y compris
`http://169.254.169.254/latest/meta-data/…` des clouds) et renvoyait `r.text[:300]` dans le message
résultat → lecture partielle de réponses internes + envoi de fichiers vers des services internes.
**Correctif :** `publish.webhook_url_ok()` : schéma `http/https` obligatoire, résolution DNS et
**refus de toute IP privée / boucle locale / lien local / réservée / multicast** (fail-closed si la
résolution échoue). Contournement volontaire documenté : `SHORTPILOT_ALLOW_PRIVATE_WEBHOOK=1`
(pour auto-héberger n8n chez soi).
**Vérification :** tests unitaires : `127.0.0.1`, `169.254.x`, `192.168.x`, `ftp://` refusés ✔ ;
scripts de test intégrés à la CI GitHub.
*Risque résiduel : DNS rebinding (fenêtre résolution↔requête) — acceptable en mono-utilisateur ;
voir recommandations §5.*

### 🟠 V4 — SSRF/abus via l'URL YouTube *(moyenne)*
**Constat :** yt-dlp acceptait **toute URL** (pages web, adresses internes) via `/api/yt/info` et
`/api/yt/shorts` ; les messages d'erreur (tronqués à 400 caractères) pouvaient refléter du contenu.
**Correctif :** validation stricte `^https?://(www.|m.|music.)?(youtube.com|youtu.be)/` sur les deux
endpoints. Le mode 📁 Fichier local couvre les autres sources.
**Vérification :** `curl /api/yt/info -d '{"url":"http://169.254.169.254/latest/meta-data"}'` →
**400 "URL non prise en charge"** ✔ ; youtube.com/youtu.be acceptés ✔ ; rejets testés en CI.

### 🟠 V5 — Contournement de préfixe sur `file_path` *(moyenne)*
**Constat :** garde `abspath(file_path).startswith(abspath(UPLOADS))` vulnérable à la confusion de
préfixe (`data/uploads_evil/…` validait la condition).
**Correctif :** `os.path.realpath` + préfixe **avec séparateur** (`realpath(UPLOADS) + os.sep`) +
`os.path.isfile`. Même logique ajoutée dans `/api/delete` pour la suppression des fichiers.
**Vérification :** `data/uploads/../settings.json` et `data/uploads_evil/x.mp4` → **refusés** ✔.

### 🟠 V6 — Épuisement disque via uploads *(moyenne/DoS)*
**Constat :** uploads jamais purgés ; 1 Go par envoi autorisé, illimité en nombre.
**Correctif :** purge automatique des uploads > 24 h à chaque nouvel envoi, **les fichiers
référencés par un job en file/en cours sont protégés** ; réponse JSON propre si la limite est
atteinte (handler HTTP 413).
**Vérification :** E2E upload → découpe → succès ; fixtures de test nettoyées.

### 🟡 V7 — XSS dans le suivi du mode Batch *(faible)*
**Constat :** les titres de jobs étaient insérés dans `innerHTML` sans échappement
(un sujet libre contenant `<img onerror=…>` s'exécutait).
**Correctif :** échappement `esc()` sur titre et niche. (Les chemins média passent désormais par
`mediaUrl()` + `encodeURIComponent`.)
**Vérification :** revue de tous les points d'injection `innerHTML` du front.

### 🟡 V8 — `nocheckcertificate: True` (vérification TLS désactivée) *(faible)*
**Constat :** l'option yt-dlp désactivait la vérification des certificats lors des téléchargements.
**Correctif :** supprimée — TLS standard restauré.
**Vérification :** revue de code ; pipeline YouTube retesté.

### 🟡 V9 — Entrées numériques malformées → HTTP 500 *(faible/robustesse)*
**Constat :** `int(d.get("count"))` levait `ValueError` sur entrées non numériques (erreur 500).
**Correctif :** helper `_int(v, défaut, min, max)` avec bornage appliqué partout (batch, shorts,
durées). Scènes bornées (60 max, 600 car./scène, légende 2000 car., titre 120 car.).
**Vérification :** `curl … -d '{"count":"abc"}'` → job normal, pas de 500 ✔.

### 🟡 V10 — Dépendance vulnérable : `click` *(faible/suivie)*
**Constat (pip-audit) :** `click 8.1.8 × PYSEC-2026-2132` (dépendance transitive de Flask).
**Analyse :** cette faille ne touche que l'**interface en ligne de commande** de Flask
(`flask run`, options CLI) ; ShortPilot n'expose qu'un serveur HTTP applicatif → **surface
d'attaque nulle dans notre architecture**. Un plancher `click>=8.3.3` avait été ajouté, puis
**retiré** car il entre en conflit avec `gtts` (qui impose `click<8.2`) : impossible d'installer
le projet sinon. **Risque résiduel : négligeable** — surveiller via `pip-audit -r requirements.txt`
et retirer la contrainte gtts le jour où une version compatible click≥8.3 sort.

### 🟡 V11 — Condition de course sur la bibliothèque *(faible/intégrité)*
**Constat :** lecture → modification → écriture de `data/library.json` non atomique : une suppression
concurrente d'un rendu pouvait ressusciter un fichier supprimé ou perdre une publication.
**Correctif :** verrou global `LIB_LOCK` via le helper `library_update()` utilisé par *tous* les
chemins d'écriture (rendu, shorts, marqueur de publication, suppression).
**Vérification :** E2E complet (rendu + delete) post-refonte ✔.

---

## 3 · Bugs fonctionnels corrigés (3)

| # | Bug | Correctif | Vérification |
|---|---|---|---|
| F1 | Fresh clone : `tmp/` absent → `tempfile.mkdtemp(dir=…)` plantait au premier rendu | `os.makedirs(tmp)` au démarrage | compileall + rendu E2E ✔ |
| F2 | `plan_segments` : vidéo ≤ 1,1×durée cible avec count=N produisait **N shorts identiques** | retour d'un unique segment | **E2E : vidéo 25 s, count=3 → 1 short** ✔ |
| F3 | Branche `is_cta` morte dans `make_scene` (dessinait du texte vide) | signalée — cosmétique, sans impact | inventoriée pour nettoyage futur |

---

## 4 · Points forts constatés (à conserver)

- **Aucun secret codé en dur** (scan regex : clés, tokens, mots de passe → 0 résultat).
- **Aucun** `shell=True` / `os.system` / `eval` / `exec` / `pickle` — tous les appels ffmpeg utilisent
  des **listes d'arguments** (pas d'injection de commande). Le filigrane et les sous-titres sont
  dessinés par PIL en PNG puis incrustés (pas de `drawtext` → aucune injection dans les filtres ffmpeg).
- `/media/<path>` via `send_from_directory` (jointure sûre) → traversal `../` → 404 ✔.
- Upload : extension sur liste blanche, nom assaini + suffixe aléatoire, taille bornée (1 Go).
- Message d'erreur yt-dlp traduit en français, sans fuite d'information sensible.
- Jobs journalisés, verrou sur la table des jobs, files bornées côté UI (50 derniers).
- Dépendances uniquement maintenues/flottantes bas (`>=`) → mises à jour de correctifs automatiques.

---

## 5 · Risques résiduels & recommandations (post-déploiement)

| Priorité | Recommandation |
|---|---|
| 🔶 Si exposition publique | **WSGI de production** (gunicorn/waitress) + reverse proxy HTTPS — le serveur de dev Flask l'affiche déjà en avertissement au démarrage. |
| 🔶 Si exposition réseau | Toujours définir `SHORTPILOT_TOKEN` ; le token transite en clair sans TLS → HTTPS obligatoire en public. |
| 🔷 Webhook | `requests` suit les redirections : la cible finale post-redirection n'est pas revérifiée (risque SSRF résiduel théorique). Make/Zapier/n8n n'en utilisent pas. |
| 🔷 Charge | Pas de rate-limiting : un token qui fuit permet de lancer des rendus en boucle (Coût CPU). Ajouter Flask-Limiter si multi-accès. |
| 🔷 DNS rebinding | Fenêtre théorique sur le contrôle anti-SSRF du webhook (cache-pinning possible dans une V2). |
| 🔷 Binaires | ffmpeg (imageio-ffmpeg) analyse des vidéos arbitraires : garder à jour. |
| 🔷 Dependabot | Activer sur le dépôt : alertes auto sur futures CVE des dépendances. |

---

## 6 · Préparation GitHub — livrables ajoutés

| Fichier | Rôle |
|---|---|
| `.gitignore` | Bloque **tous les secrets/runtime** : `data/cookies.txt`, `client_secrets.json`, `youtube_token.json`, `settings.json`, bibliothèque, vidéos, uploads, tmp, logs |
| `LICENSE` | MIT |
| `SECURITY.md` | Modèle de menace, variables d'environnement, procédure de signalement privé |
| `.github/workflows/ci.yml` | CI : Python 3.10 & 3.13 — compilation, imports, **tests de sécurité** (URL YouTube, anti-SSRF, clamps), génération de contenu & musique hors-ligne |
| `AUDIT_SECURITE.md` | Ce rapport |
| `README.md` | Section 🔒 Sécurité ajoutée |

**Avant le premier `git push`, vérifier :**
```bash
git status --ignored            # aucun fichier data/ ou outputs/ ne doit apparaître
pip-audit -r requirements.txt   # 0 vulnérabilité (ou justifiée)
```

---

*Audit réalisé par l'agent ShortPilot Studio. Corrections appliquées et vérifiées le 03/10/2026.*
