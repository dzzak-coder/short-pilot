# Politique de sécurité — ShortPilot

## Modèle de menace

ShortPilot est conçu pour tourner **sur la machine de l'utilisateur** (`127.0.0.1`,
mono-utilisateur, sans compte). Dans ce cadre, les mécanismes suivants s'appliquent :

- **Aucune donnée personnelle n'est versionnée** : cookies, tokens OAuth, webhook,
  bibliothèque et vidéos sont couverts par `.gitignore`.
- **Anti-CSRF « drive-by localhost »** : toute requête POST dont l'en-tête `Origin`
  ne correspond pas à l'hôte est rejetée (403), et seul `application/json` est accepté
  sur les API (415) — un site web malveillant ne peut pas piloter votre instance locale
  via votre navigateur.
- **Anti-SSRF** : les URL de webhook doivent être HTTP(S) et résoudre vers une adresse
  IP **publique**. Les webhooks sur votre propre réseau (n8n auto-hébergé…) nécessitent
  `SHORTPILOT_ALLOW_PRIVATE_WEBHOOK=1`. Les URL d'analyse YouTube sont restreintes aux
  domaines `youtube.com` / `youtu.be`.
- **Uploads bornés** : 1 Go max (HTTP 413 JSON), extensions vidéo/sous-titres sur liste
  blanche, nom de fichier assaini, purge automatique après 24 h (les fichiers référencés
  par un job en file sont protégés).
- **Traversal** : les accès fichiers passent par `realpath` + vérification de préfixe
  (lecture média, suppression, découpe locale).

## Exposer ShortPilot sur un réseau

Si vous exposez l'outil au-delà de `localhost` (LAN, VPS…) :

```bash
SHORTPILOT_HOST=0.0.0.0 SHORTPILOT_TOKEN=un_mot_de_passe_long_et_aleatoire python3 app.py
```

- `SHORTPILOT_TOKEN` active un contrôle d'accès sur toutes les routes `/api/*` et
  `/media/*` (l'interface web vous le demandera une fois, puis le mémorisera).
- Sans token, le serveur **affiche un avertissement** au démarrage.
- Pour un déploiement public, placez de plus l'outil derrière un reverse proxy HTTPS
  et un serveur WSGI de production (gunicorn/waitress).

## Signaler une vulnérabilité

Merci de ne **pas** ouvrir d'issue publique pour une vulnérabilité : ouvrez plutôt un
*Security Advisory* privé sur GitHub (onglet Security → "Report a vulnerability").
Décrivez : le scénario d'attaque, les endpoints concernés, une preuve de concept,
et l'impact. Nous accusons réception sous 72 h.

## Bonnes pratiques utilisateur

- Ne committez/ ne partagez jamais `data/cookies.txt`, `data/client_secrets.json`,
  `data/youtube_token.json` : **ce sont des secrets**.
- Le mode 📺 YouTube → Shorts n'est destiné qu'à du contenu dont vous détenez les
  droits (les vôtres, Creative Commons, autorisation écrite).
- Dépendances : `pip-audit -r requirements.txt` avant chaque déploiement.
