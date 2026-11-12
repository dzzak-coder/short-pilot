# -*- coding: utf-8 -*-
"""ShortPilot — publication : YouTube (API officielle) + Webhook universel (Make/Zapier/n8n)."""
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
CLIENT_SECRETS = os.path.join(DATA, "client_secrets.json")
TOKEN_PATH = os.path.join(DATA, "youtube_token.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

_YT_LIBS = None


def yt_libs_ok():
    global _YT_LIBS
    if _YT_LIBS is None:
        try:
            import googleapiclient.discovery  # noqa
            import google_auth_oauthlib.flow  # noqa
            _YT_LIBS = True
        except Exception:
            _YT_LIBS = False
    return _YT_LIBS


def youtube_status():
    if not yt_libs_ok():
        return {"configured": False, "reason": "Bibliothèques Google non installées (voir requirements.txt)."}
    if not os.path.exists(CLIENT_SECRETS):
        return {"configured": False, "reason": "Fichier data/client_secrets.json manquant."}
    return {"configured": True, "authenticated": os.path.exists(TOKEN_PATH),
            "reason": "" if os.path.exists(TOKEN_PATH) else "Prêt — la 1ère publication ouvrira la connexion Google."}


def _yt_service(log):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        log("🔐 Connexion à votre compte Google/YouTube… (une fenêtre navigateur s'ouvre)")
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
        creds = flow.run_local_server(port=8099, open_browser=True)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def publish_youtube(video_path, title, description, privacy="public", log=print):
    """Upload YouTube officiel. '#Shorts' dans le titre => classé Short automatiquement."""
    st = youtube_status()
    if not yt_libs_ok():
        return False, st["reason"]
    if not st["configured"]:
        return False, "YouTube non configuré : placez client_secrets.json dans data/ (voir onglet Publication)."
    try:
        from googleapiclient.http import MediaFileUpload
        yt = _yt_service(log)
        t = title or "Short"
        if "#shorts" not in t.lower():
            t = (t + " #Shorts")[:100]
        body = {
            "snippet": {"title": t[:100], "description": (description or "")[:4900], "categoryId": "22"},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
        }
        media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
        req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        log("⬆️  Envoi vers YouTube…")
        resp = None
        while resp is None:
            status, resp = req.next_chunk()
            if status:
                log(f"   … {int(status.progress() * 100)}%")
        vid = resp.get("id")
        return True, f"Publié sur YouTube ✅ https://youtube.com/shorts/{vid}"
    except Exception as e:
        return False, f"Échec YouTube : {e}"


def webhook_url_ok(url):
    """Anti-SSRF : l'URL du webhook doit être HTTP(S) et pointer vers une adresse
    publique (refus des IP privées/locales/de lien local, ex. 169.254.169.254).
    Définir SHORTPILOT_ALLOW_PRIVATE_WEBHOOK=1 pour auto-héberger n8n en local."""
    from urllib.parse import urlparse
    pu = urlparse(url or "")
    if pu.scheme not in ("http", "https") or not pu.hostname:
        return False, "L'URL du webhook doit commencer par http:// ou https://."
    # Exact opt-in destination for the companion local n8n workflow. Never
    # authorize other loopback ports, paths, credentials or redirect targets.
    if (pu.scheme == "http" and pu.hostname == "127.0.0.1"
            and pu.port == 5678 and pu.path in ("/webhook/shortpilot-studio", "/webhook/shortpilot-youtube")
            and not pu.username and not pu.password and not pu.query and not pu.fragment):
        return True, ""
    if os.environ.get("SHORTPILOT_ALLOW_PRIVATE_WEBHOOK"):
        return True, ""
    try:
        import socket, ipaddress
        port = pu.port or (443 if pu.scheme == "https" else 80)
        infos = socket.getaddrinfo(pu.hostname, port, proto=socket.IPPROTO_TCP)
        ips = {info[4][0] for info in infos}
    except Exception as e:
        return False, (f"Impossible de résoudre le domaine du webhook ({e}) — vérifiez l'orthographe "
                       "de l'URL et votre connexion réseau. Le webhook est bloqué par précaution (anti-SSRF).")
    for ip in ips:
        a = ipaddress.ip_address(ip)
        if (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved
                or a.is_multicast or a.is_unspecified):
            return False, ("URL de webhook refusée : adresse privée/locale "
                           "(protection anti-SSRF). Pour un webhook sur votre propre réseau, "
                           "définissez SHORTPILOT_ALLOW_PRIVATE_WEBHOOK=1.")
    return True, ""


def publish_webhook(url, video_path, caption, platform="all", log=print, *,
                    video_id="", title="", duration=0, require_public=False):
    """Envoie la vidéo + métadonnées à un webhook (Make.com, Zapier, n8n…)
    qui peut ensuite publier sur TikTok / Instagram Reels / YouTube / LinkedIn…"""
    if not url:
        return False, "Aucune URL de webhook configurée (onglet Publication)."
    try:
        import requests
        # anti-SSRF v2 : les redirections sont suivies à la main et chaque cible
        # intermédiaire est re-vérifiée (une IP publique → IP privée est bloquée)
        hops = 0
        while True:
            ok, why = webhook_url_ok(url)
            if not ok:
                log(f"🛡️  Webhook bloqué : {why}")
                return False, f"Webhook bloqué (sécurité) : {why}"
            with open(video_path, "rb") as fh:
                meth = requests.post(
                    url,
                    data={"caption": caption or "", "platform": platform,
                          "filename": os.path.basename(video_path), "video_id": video_id,
                          "title": title, "duration": str(duration or 0),
                          "privacy": "public", "mode": "direct_public" if require_public else "webhook"},
                    files={"video": (os.path.basename(video_path), fh, "video/mp4")},
                    timeout=600, allow_redirects=False,
                )
            if meth.is_redirect and meth.headers.get("Location") and hops < 3:
                from urllib.parse import urljoin
                hops += 1
                url = urljoin(url, meth.headers["Location"])
                log(f"   ↪️  Webhook : redirection ({hops}/3)…")
                continue
            r = meth
            break
        if r.status_code < 400:
            if require_public:
                try:
                    result = r.json()
                except ValueError:
                    return False, "Réception confirmée, mais aucune confirmation de publication publique YouTube + TikTok reçue."
                return public_publication_result(result)
            return True, f"Reçu par le webhook ✅ (HTTP {r.status_code}) — consultez votre automation pour le statut de publication."
        return False, f"Webhook en erreur : HTTP {r.status_code} — {r.text[:300]}"
    except Exception as e:
        return False, f"Échec webhook : {e}"


def public_publication_result(result):
    """Never equate an accepted webhook, a draft or processing with public posts."""
    if not isinstance(result, dict):
        return False, "Réponse de publication invalide."
    confirmed = []
    messages = []
    for platform, label in (("youtube", "YouTube"), ("tiktok", "TikTok")):
        state = result.get(platform)
        state = state if isinstance(state, dict) else {}
        public = state.get("status") == "published" and state.get("public") is True
        confirmed.append(public)
        if public:
            messages.append(f"{label} : publié en public ✅" + (" " + str(state["url"]) if state.get("url") else ""))
        elif state.get("mode") == "draft" or state.get("queued"):
            messages.append(f"{label} : brouillon envoyé, publication publique non effectuée.")
        else:
            messages.append(str(state.get("message") or f"{label} : publication publique non confirmée."))
    return all(confirmed), "\n".join(messages)
