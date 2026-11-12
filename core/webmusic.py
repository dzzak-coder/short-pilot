# -*- coding: utf-8 -*-
"""ShortPilot — musique WEB libre de droits, choisie selon l'ambiance du script.

Source : Internet Archive (archive.org), catalogues audio libres (CC / domaine
public). L'ambiance vient de music.explain_auto() (script écouté + niche) ;
on interroge l'archive avec des mots-clés adaptés à cette ambiance, on choisit
un morceau (mémoire anti-répétition « wmusic: »), on le télécharge, on le
normalise (dynaudnorm), on le boucle s'il est trop court et on ajoute des
fondus. Attribution du morceau renvoyée pour figurer dans la légende.

Tout échec → None : le rendu retombe alors sur la synthèse procédurale
précédente (zéro casse, 100 % hors-ligne).
"""
import json
import os
import random
import re
import subprocess
import time
import urllib.parse

import requests

from . import content as content_mod

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    import shutil
    FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

UA = {"User-Agent": "ShortPilot/1.4 (studio local de videos courtes)"}
TIMEOUT = 15
CACHE_TTL = 20 * 3600
MAX_BYTES = 25 * 1024 * 1024  # pistes > 25 Mo : on passe

# Ambiance musicale (id de PRESET) → requête archive.org adaptée
MOOD_QUERIES = {
    "energie": "energetic upbeat background music instrumental",
    "chill": "lofi chill ambient background beat",
    "drama": "dramatic tension cinematic background music",
    "happy": "happy upbeat cheerful instrumental background music",
    "epique": "epic orchestral trailer cinematic music",
    "mystere": "suspense mystery dark ambient background music",
    "triste": "sad emotional piano instrumental",
    "techno": "electronic synthwave techno instrumental",
    "zen": "meditation calm relaxing ambient music",
}

_MAGICS = (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"OggS", b"RIFF", b"fLaC")


def _get(url, params=None, timeout=TIMEOUT):
    for attempt in (1, 2):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=timeout)
            if r.status_code == 200:
                return r
        except Exception:
            if attempt == 2:
                return None
    return None


def _cache_path():
    return os.path.join(content_mod.DATA_DIR, "webmusic_cache.json")


def _cache_get(key):
    try:
        with open(_cache_path(), "r", encoding="utf-8") as f:
            e = (json.load(f) or {}).get(key) or {}
        if time.time() - e.get("ts", 0) < CACHE_TTL and e.get("items"):
            return e["items"]
    except Exception:
        pass
    return None


def _cache_put(key, items):
    if not items:
        return
    try:
        data = {}
        if os.path.exists(_cache_path()):
            with open(_cache_path(), "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        data[key] = {"ts": time.time(), "items": items[:60]}
        os.makedirs(os.path.dirname(_cache_path()), exist_ok=True)
        with open(_cache_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def _search(query):
    """Identifiants de pistes candidates pour une ambiance (cache 20 h)."""
    key = "m:" + query
    cached = _cache_get(key)
    if cached is not None:
        return cached
    r = _get("https://archive.org/advancedsearch.php", params=[
        ("q", f"{query} AND mediatype:audio"),
        ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "creator"),
        ("fl[]", "licenseurl"), ("fl[]", "downloads"),
        ("rows", "25"), ("output", "json"), ("sort[]", "downloads desc"),
    ])
    items = []
    if r:
        try:
            for doc in (r.json().get("response", {}).get("docs") or []):
                if doc.get("identifier") and doc.get("title"):
                    items.append({
                        "id": doc["identifier"], "title": doc.get("title", "")[:80],
                        "creator": (doc.get("creator") or "artiste inconnu")[:50]
                        if isinstance(doc.get("creator"), str) else "artiste inconnu",
                        "license": _short_license(doc.get("licenseurl", "")),
                    })
        except Exception:
            items = []
    if items:
        _cache_put(key, items)
    return items


def _short_license(url):
    url = url or ""
    if "publicdomain/zero" in url:
        return "CC0"
    if "publicdomain/mark" in url:
        return "Domaine public"
    m = re.search(r"licenses/([a-z-]+)/([\d.]+)", url)
    if m:
        return ("CC " + m.group(1).upper().replace("PUBLICDOMAIN", "PDM")
                + " " + m.group(2)).strip()
    return ""


def _license_safe(lic):
    """Licence compatible diffusion/monetisation (pas de clause NC ni ND)."""
    low = (lic or "").lower()
    return not ("nc" in low or "nd" in low)


def _pick_file(identifier, title_hint=""):
    """Meilleur fichier audio d'un item (métadonnées archive.org). → (url, name)."""
    r = _get("https://archive.org/metadata/%s" % identifier, timeout=TIMEOUT)
    if not r:
        return None
    try:
        files = (r.json() or {}).get("files") or []
    except Exception:
        return None
    best = None
    for f in files:
        name = (f.get("name") or "")
        fmt = (f.get("format") or "").lower()
        low = name.lower()
        audio = ("mp3" in fmt and low.endswith(".mp3")) or ("ogg" in fmt and low.endswith(".ogg")) \
            or low.endswith((".mp3", ".ogg", ".wav", ".flac", ".m4a"))
        if not audio:
            continue
        try:
            size = int(f.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if size and (size < 400_000 or size > MAX_BYTES):
            continue
        try:
            length = float(f.get("length") or 0)
        except (TypeError, ValueError):
            length = 0
        if length and not (30 <= length <= 1200):
            continue
        score = 0
        if low.endswith(".mp3"):
            score += 3
        if length and length >= 55:
            score += 2
        if any(w in low for w in ("full", "complete", "version", "mix")):
            score += 1
        if any(w in low for w in ("sample", "preview", "loop", "demo", "30sec", "snippet")):
            score -= 3
        if title_hint and title_hint.split()[0].lower() in low:
            score += 1
        if best is None or score > best[0]:
            best = (score, name)
    if not best:
        return None
    url = "https://archive.org/download/%s/%s" % (identifier, urllib.parse.quote(best[1]))
    return url, best[1]


def _duration(path):
    """Durée d'un fichier audio en lisant l'en-tête ffmpeg (stderr)."""
    try:
        p = subprocess.run([FFMPEG, "-hide_banner", "-i", path],
                           capture_output=True, text=True, timeout=15)
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", p.stderr or "")
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        pass
    return 0.0


def _prepare(raw_path, total, out_wav, tempo_scale=1.0):
    """Normalise le volume, tempo optionnel, boucle et fondus. → chemin WAV."""
    try:
        tempo_scale = max(0.5, min(2.0, float(tempo_scale)))
    except (TypeError, ValueError):
        tempo_scale = 1.0
    loop = []
    dur = _duration(raw_path)
    required_source = (total + 1) * tempo_scale
    if 0 < dur < required_source:
        loop = ["-stream_loop", "-1"]  # piste courte : on boucle
    filters = []
    if abs(tempo_scale - 1.0) > 0.01:
        # atempo changes playback speed without changing pitch.  ACE-Step does
        # not always obey BPM tags, so this enforces a real audible difference.
        filters.append(f"atempo={tempo_scale:.4f}")
    filters.append("dynaudnorm=f=150:g=15")
    filters.append("afade=t=in:st=0:d=1.2")
    filters.append("afade=t=out:st=%.1f:d=2.5" % max(0.0, total - 2.5))
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error"] + loop + [
        "-i", raw_path, "-t", f"{total:.2f}",
        "-af", ",".join(filters),
        "-vn", "-ac", "1", "-ar", "44100", out_wav]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if p.returncode == 0 and os.path.exists(out_wav) and os.path.getsize(out_wav) > 100_000:
            return out_wav
    except Exception:
        pass
    return None


def track_for_mood(mood, work_dir, total, log=None, avoid_repeat=True):
    """(chemin_wav, attribution) d'une vraie piste libre pour l'ambiance `mood`.
    `total` : durée vidéo + marge (s). None si rien de concluant (→ repli synthèse)."""
    query = MOOD_QUERIES.get(mood, MOOD_QUERIES["chill"])
    used = content_mod._load_used() if avoid_repeat else set()
    items = _search(query)
    if not items and log:
        log("      🎧 archive.org injoignable — repli")
    random.shuffle(items)
    # passe 1 : licences commercialement sûres ; passe 2 : tout (NC/ND toléré,
    # licence réelle toujours affichée dans l'attribution)
    ordered = sorted(items, key=lambda it: 0 if _license_safe(it.get("license", "")) else 1)
    os.makedirs(work_dir, exist_ok=True)
    tried = 0
    for it in ordered:
        if tried >= 6:
            break
        ident = it["id"]
        sig = "wmusic:" + ident
        if sig in used:
            continue
        tried += 1
        pick = _pick_file(ident, it.get("title", ""))
        if not pick:
            continue
        url, name = pick
        raw = os.path.join(work_dir, f"webmusic_{abs(hash(ident)) % 99999:05d}"
                             + os.path.splitext(name)[1][:6].lower())
        try:
            dl = _get(url, timeout=90)
        except Exception:
            dl = None
        if not dl or len(dl.content) < 400_000 or len(dl.content) > MAX_BYTES:
            continue
        data = dl.content
        if not any(data[:8].startswith(m) for m in _MAGICS):
            continue  # pas vraiment un fichier audio
        try:
            with open(raw, "wb") as f:
                f.write(data)
        except Exception:
            continue
        wav = _prepare(raw, total, os.path.splitext(raw)[0] + ".wav")
        if not wav:
            continue
        if avoid_repeat:
            content_mod._mark_used(used, sig)
        lic = it.get("license") or "domaine public / CC (archive.org)"
        title = (it.get("title") or "piste libre").strip() or "piste libre"
        attrib = f"«{title}» par {it.get('creator') or 'artiste inconnu'} ({lic}) via Internet Archive"
        if log:
            log(f"      🎵 musique web ({lic or 'CC/PD'}) : « {title[:52]} »")
        return wav, attrib
    return None
