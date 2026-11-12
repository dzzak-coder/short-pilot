# -*- coding: utf-8 -*-
"""ShortPilot — sources YouTube autorisées → Shorts.
Accède à une vidéo YouTube dont l'utilisateur a confirmé les droits (+ sous-titres), la découpe en segments,
la reformate en vertical 9:16 (fond flouté ou recadrage centré) et
incruste des sous-titres stylés — puis produit N shorts prêts à publier."""
import glob
import os
import re
import shutil
import subprocess
import tempfile

import imageio_ffmpeg
from PIL import Image, ImageDraw

from .render import FONTS, _font, _wrap

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COOKIES = os.path.join(BASE, "data", "cookies.txt")
W, H = 1080, 1920

# ---------------------------------------------------------------- téléchargement
YT_CLIENTS = ["web", "android", "tv", "mweb", "ios", "web_creator", "web_embedded"]


class SubsUnavailable(Exception):
    """Les sous-titres n'ont pas pu être téléchargés (429…), la vidéo reste récupérable."""


class BotBlocked(Exception):
    """YouTube demande une authentification avant l'accès à la source."""


def _settings_json():
    try:
        import json
        with open(os.path.join(BASE, "data", "settings.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _ydl_opts(extra=None):
    opts = {
        "quiet": True, "no_warnings": True, "noplaylist": True,
        "ffmpeg_location": FFMPEG,
    }
    if os.path.exists(COOKIES):
        opts["cookiefile"] = COOKIES
    br = (_settings_json().get("cookies_browser") or "").strip().lower()
    if br and br not in ("aucun", "none", ""):
        opts["cookiesfrombrowser"] = (br,)
    if extra:
        opts.update(extra)
    return opts


def _extract(opts, url, log):
    """Tente l'extraction pour une source YouTube autorisée."""
    first_err = ""
    for client in YT_CLIENTS + [None]:
        o = dict(opts)
        if client:
            o["extractor_args"] = {"youtube": {"player_client": [client]}}
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL(o) as ydl:
                return ydl.extract_info(url, download=not o.get("skip_download"))
        except Exception as e:
            msg = str(e)
            if not first_err:
                first_err = msg
            if "subtitles" in msg.lower():
                raise SubsUnavailable(msg)
            log(f"   ↻ client « {client or 'défaut'} » refusé, nouvel essai…")
            continue
    if "bot" in first_err.lower() or "sign in" in first_err.lower():
        raise BotBlocked(first_err)
    raise RuntimeError(first_err or "Extraction impossible")


def get_info(url):
    """Infos d'une vidéo YouTube autorisée, sans la télécharger."""
    try:
        j = _extract(_ydl_opts({"skip_download": True}), url, lambda m: None)
    except BotBlocked as e:
        raise RuntimeError(
            "YouTube demande une connexion pour cette source autorisée. "
            "Connectez le navigateur choisi dans Réglages à votre compte ayant accès à la vidéo, puis réessayez.") from e
    subs = list((j.get("subtitles") or {}).keys())
    autos = list((j.get("automatic_captions") or {}).keys())
    return {
        "id": j.get("id"), "title": j.get("title", "Vidéo YouTube"),
        "duration": int(j.get("duration") or 0),
        "thumbnail": j.get("thumbnail", ""),
        "channel": j.get("channel") or j.get("uploader") or "",
        "subs": sorted(set(subs))[:8], "auto_subs": sorted(set(autos))[:8],
    }


def download(url, workdir, log, langs=("fr", "en")):
    """Récupère une source YouTube autorisée (≤720p) + meilleurs sous-titres dispo. Retourne (vid, subs, info).
    En cas d'échec des sous-titres (limite YouTube), bascule sur vidéo seule."""
    import yt_dlp
    outtmpl = os.path.join(workdir, "source.%(ext)s")
    exact = []
    for l in langs:
        exact += [l, f"{l}-{l.upper()}"]
    opts = _ydl_opts({
        "outtmpl": outtmpl,
        "format": "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b",
        "merge_output_format": "mp4",
        "writesubtitles": True, "writeautomaticsub": True,
        "subtitleslangs": exact,
        "retries": 2,
    })
    last_pct = [-1]

    def hook(d):
        if d.get("status") == "downloading" and d.get("_percent_str"):
            try:
                pct = int(float(d["_percent_str"].replace("%", "").strip()))
                if pct // 25 != last_pct[0] // 25:
                    last_pct[0] = pct
                    log(f"   ⬇️  {d['_percent_str'].strip()}")
            except Exception:
                pass

    opts["progress_hooks"] = [hook]
    log("⬇️  Récupération de la source YouTube autorisée…")
    try:
        info = _extract(opts, url, log)
    except SubsUnavailable as e:
        log(f"⚠️  Sous-titres indisponibles ({str(e)[:100]}). Nouvelle tentative sans sous-titres…")
        opts2 = _ydl_opts({
            "outtmpl": outtmpl,
            "format": "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b",
            "merge_output_format": "mp4",
            "retries": 2,
        })
        opts2["progress_hooks"] = [hook]
        info = _extract(opts2, url, log)
    except BotBlocked:
        raise RuntimeError(
            "YouTube demande une connexion ou refuse l'accès à cette source. "
            "Vérifiez que vous avez bien les droits et l'accès à cette vidéo, ou utilisez un fichier local obtenu légalement.")
    vids = [p for p in glob.glob(os.path.join(workdir, "source.*"))
            if os.path.splitext(p)[1] in (".mp4", ".mkv", ".webm", ".mov")]
    if not vids:
        raise RuntimeError("Téléchargement impossible (vidéo privée, âge requis, ou blocage YouTube).")
    vid = vids[0]
    # sous-titres : préférence de langue
    subs = [p for p in glob.glob(os.path.join(workdir, "source.*"))
            if os.path.splitext(p)[1] in (".vtt", ".srt")]
    subs.sort(key=lambda p: 0 if any(f".{l}" in os.path.basename(p) for l in langs) else 1)
    sub = subs[0] if subs else None
    log(("📝 Sous-titres trouvés : " + os.path.basename(sub)) if sub else "📝 Aucun sous-titre disponible — rendu sans sous-titres.")
    return vid, sub, {"title": info.get("title", "Short"), "duration": info.get("duration", 0),
                      "webpage_url": info.get("webpage_url", url)}


# ---------------------------------------------------------------- sous-titres
TS_RX = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})")


def _ts(s):
    m = TS_RX.search(s)
    if not m:
        return None
    h = int(m.group(1) or 0)
    ms = int(m.group(4).ljust(3, "0"))
    return h * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + ms / 1000.0


def parse_subs(path):
    """Retourne des chunks (début, fin, texte) — nettoie les sous-titres cumulatifs YouTube."""
    try:
        raw = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return []
    cues = []
    lines = raw.replace("\r", "").split("\n")
    i, n = 0, len(lines)
    while i < n:
        if "-->" in lines[i]:
            parts = lines[i].split("-->")
            start, end = _ts(parts[0]), _ts(parts[1])
            i += 1
            txt = []
            while i < n and lines[i].strip() and "-->" not in lines[i]:
                txt.append(lines[i].strip())
                i += 1
            text = " ".join(txt)
            text = re.sub(r"<[^>]+>", "", text)
            text = re.sub(r"\{\\[^}]*\}", "", text)
            text = re.sub(r"[♪♫🎵🎶\U0001F3B5\U0001F3B6]", "", text)  # glyphes absents de la police
            text = re.sub(r"\s+", " ", text).strip()
            if start is not None and end and text and end > start:
                cues.append((start, end, text))
        else:
            i += 1
    # dé-double les ASR cumulatifs de YouTube (« bonjour », « bonjour le monde », …)
    chunks = []
    prev = ""
    for s, e, t in cues:
        add = t
        if prev and t.startswith(prev):
            add = t[len(prev):].strip(" -.,")
        prev = t
        if not add:
            continue
        if e - s < 0.25 and chunks:
            ls, le, lt = chunks[-1]
            chunks[-1] = (ls, e, lt)
            continue
        chunks.append((s, e, add))
    # casse les chunks trop longs
    final = []
    for s, e, t in chunks:
        if len(t) > 95:
            words = t.split()
            half = len(words) // 2
            mid = s + (e - s) / 2
            final.append((s, mid, " ".join(words[:half])))
            final.append((mid, e, " ".join(words[half:])))
        else:
            final.append((s, e, t))
    return final


# ---------------------------------------------------------------- images incrustées
def caption_png(text, workdir, name, y_frac=0.63, size=64):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = _font("bold", size)
    lines = _wrap(d, text, f, W * 0.86)[:3]
    bbs = [d.textbbox((0, 0), ln, font=f) for ln in lines]
    hs = [b[3] - b[1] for b in bbs]
    lh = int(size * 0.18)
    total = sum(hs) + lh * (len(lines) - 1)
    y = H * y_frac - total / 2
    for ln, b, hgt in zip(lines, bbs, hs):
        wl = b[2] - b[0]
        d.text(((W - wl) / 2 - b[0], y - b[1]), ln, font=f, fill=(255, 255, 255, 255),
               stroke_width=max(3, size // 11), stroke_fill=(0, 0, 0, 255))
        y += hgt + lh
    p = os.path.join(workdir, name)
    im.save(p)
    return p


def watermark_png(text, workdir):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = _font("bold", 38)
    b = d.textbbox((0, 0), text, font=f)
    d.text((W - (b[2] - b[0]) - 44, 82), text, font=f, fill=(255, 255, 255, 220),
           stroke_width=3, stroke_fill=(0, 0, 0, 255))
    p = os.path.join(workdir, "wm.png")
    im.save(p)
    return p


# ---------------------------------------------------------------- rendu d'un short
def _has_audio(path):
    p = subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True)
    return "Audio:" in p.stderr


def render_short(src, cues, seg_start, dur, framing, watermark, out_path, workdir, log,
                 src_format="auto", src_ratio=0.0):
    """Reformate + découpe un segment.
    src_format : auto / landscape / classic / square / vertical (forcer le format source).
    Une source portrait (ratio < 0.75) passe en plein cadre natif : pas de flou inutile."""
    eff = src_format
    if eff == "auto":
        eff = "vertical" if (src_ratio and src_ratio < 0.75) else "wide"
    if eff == "vertical":
        # vidéo déjà verticale (TikTok, Short existant…) : remplir le cadre, sans floutage
        vf_base = ("[0:v]scale=%d:%d:force_original_aspect_ratio=increase,"
                   "crop=%d:%d,setsar=1[base]" % (W, H, W, H))
    else:
        vf_base = {
            "center": "[0:v]crop='min(ih*9/16,iw)':ih,scale=%d:%d,setsar=1[base]" % (W, H),
            "blur": ("[0:v]split[bgv][fgv];"
                     "[bgv]scale=96:170,gblur=sigma=15,scale=%d:%d:flags=bicubic,setsar=1[bg2];"
                     "[fgv]scale=%d:-2:flags=bicubic,setsar=1[fg2];"
                     "[bg2][fg2]overlay=(W-w)/2:(H-h)/2[base]" % (W, H, W)),
        }[framing]

    os.makedirs(workdir, exist_ok=True)
    overlays = []
    inputs = []
    prev = "base"
    idx = 1
    if watermark:
        wp = watermark_png(watermark, workdir)
        inputs.append(wp)
        overlays.append((prev, idx, 0.0, dur, f"b{idx}"))
        prev, idx = f"b{idx}", idx + 1
    for (cs, ce, ct) in cues:
        rs, re_ = cs - seg_start, ce - seg_start
        if re_ < 0 or rs > dur:
            continue
        rs, re_ = max(0.0, rs), min(dur, re_)
        if re_ - rs < 0.2:
            continue
        png = caption_png(ct, workdir, f"cap_{idx:03d}.png")
        inputs.append(png)
        overlays.append((prev, idx, rs, re_, f"b{idx}"))
        prev, idx = f"b{idx}", idx + 1

    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-ss", f"{seg_start:.3f}", "-t", f"{dur:.3f}", "-i", src]
    for p in inputs:
        cmd += ["-i", p]
    fc = [vf_base]
    for src_lbl, i, a, b, out_lbl in overlays:
        if a == 0.0 and b >= dur:
            fc.append(f"[{src_lbl}][{i}:v]overlay=0:0[{out_lbl}]")
        else:
            fc.append(f"[{src_lbl}][{i}:v]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})'[{out_lbl}]")
    audio_in = _has_audio(src)
    maps = ["-map", f"[{overlays[-1][4] if overlays else 'base'}]"]
    cmd += ["-filter_complex", ";".join(fc)] + maps
    if audio_in:
        cmd += ["-map", "0:a?", "-c:a", "aac", "-b:a", "160k"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", out_path]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    if proc.returncode != 0 or not os.path.exists(out_path):
        raise RuntimeError("ffmpeg (short) : " + (proc.stderr or "")[-600:])
    # miniature
    thumb = os.path.splitext(out_path)[0] + "_thumb.jpg"
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", f"{dur * 0.4:.2f}", "-i", out_path, "-frames:v", "1",
                    "-vf", "scale=540:960", thumb], capture_output=True, timeout=120)
    return out_path, thumb


# ---------------------------------------------------------------- orchestrateur
def plan_segments(duration, count, target):
    intro = min(duration * 0.08, 30)
    outro = min(duration * 0.05, 20)
    usable = max(target, duration - intro - outro)
    if not count:
        count = max(1, int(usable // target))
    count = min(count, 10)
    if count == 1:
        return [intro]
    if usable <= target * 1.1:
        return [intro]  # vidéo trop courte : un seul short, évite les doublons identiques
    step = (usable - target) / (count - 1)
    return [intro + i * step for i in range(count)]


def probe_video_duration(path):
    p = subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", p.stderr or "")
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return 0.0


SRC_FORMATS = {
    "auto": "🔍 Détection automatique",
    "landscape": "🖥️ 16:9 paysage",
    "classic": "📺 4:3 classique",
    "square": "⬛ 1:1 carré",
    "vertical": "📱 9:16 portrait (déjà vertical)",
}


def probe_video_size(path):
    """Dimensions (pixels) de la première piste vidéo — sert à détecter le format source."""
    p = subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True)
    m = re.search(r"Video:.*?(\d{2,5})\s*x\s*(\d{2,5})", p.stderr or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0


def _find_sidecar_subs(src):
    stem = os.path.splitext(src)[0]
    for ext in (".srt", ".vtt"):
        for cand in (stem + ext, stem + ".fr" + ext, stem + ".en" + ext):
            if os.path.exists(cand):
                return cand
    return None


def cut_from_source(src, subs_path, base_title, source_url, count, duration, framing,
                    subtitles, watermark, langs, out_dir, log, emit, src_format="auto"):
    """Cœur commun : découpe une vidéo source fichier en shorts."""
    vdur = int(round(probe_video_duration(src)))
    if vdur and vdur > 3600:
        raise RuntimeError("Vidéo trop longue (> 60 min). Choisissez une vidéo plus courte.")
    if not vdur:
        vdur = duration * max(1, count or 1)
    # --- format source : détection + message d'adaptation ---
    sw, sh = probe_video_size(src)
    ratio = sw / sh if sh else 0.0
    eff = src_format
    if eff == "auto":
        eff = "vertical" if (ratio and ratio < 0.75) else "wide"
    if eff == "vertical":
        log(f"📐 Source {sw}×{sh} — déjà verticale : plein cadre natif (aucun reformatage).")
    else:
        log(f"📐 Source {sw}×{sh} ({ratio:.2f}) — adaptation 9:16 par "
            f"{'fond flouté' if framing == 'blur' else 'recadrage centré'}.")
    cues = parse_subs(subs_path) if (subtitles and subs_path) else []
    if subtitles and not subs_path:
        log("📝 Pas de fichier de sous-titres — déposez un .srt/.vtt du même nom pour les activer.")
    log(f"🎬 Vidéo source : « {base_title[:60]} » — {vdur // 60}min{vdur % 60:02d}s")
    segs = plan_segments(vdur, count or 0, duration)
    n = len(segs)
    log(f"✂️  Découpe en {n} short(s) de ~{duration}s ({'fond flouté' if framing == 'blur' else 'recadrage centré'})…")
    import time as _t
    work = tempfile.mkdtemp(prefix="cut_", dir=os.path.join(BASE, "tmp"))
    try:
        for i, st in enumerate(segs):
            log(f"   🎥 Short {i + 1}/{n} — extrait à {int(st // 60)}m{int(st % 60):02d}s…")
            vid = f"{int(_t.time())}_{i + 1:02d}"
            out_path = os.path.join(out_dir, vid + ".mp4")
            render_short(src, cues, st, duration, framing, watermark, out_path, work, log,
                         src_format=src_format, src_ratio=ratio)
            entry = {
                "id": vid, "file": vid + ".mp4", "thumb": vid + "_thumb.jpg",
                "title": f"{base_title[:46]} · Short {i + 1}/{n}",
                "caption": (f"Extrait de la vidéo : {base_title}\n🔗 {source_url}" if source_url
                            else f"Extrait de : {base_title}"),
                "hashtags": "#shorts #reels #tiktok #clip #extrait",
                "duration": duration, "niche": "youtube", "language": langs[0] if langs else "fr",
                "type": "yt",
            }
            emit(entry)
            log(f"   ✅ Short {i + 1}/{n} prêt ({os.path.getsize(out_path) / 1e6:.1f} Mo)")
        return n
    finally:
        shutil.rmtree(work, ignore_errors=True)


def process(url, count, duration, framing, subtitles, watermark, langs, out_dir, log, emit,
            src_format="auto"):
    """Pipeline YouTube complet."""
    work = tempfile.mkdtemp(prefix="yt_", dir=os.path.join(BASE, "tmp"))
    try:
        src, subs, info = download(url, work, log, langs=langs)
        return cut_from_source(src, subs, info["title"], info["webpage_url"], count, duration,
                               framing, subtitles, watermark, langs, out_dir, log, emit,
                               src_format=src_format)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def process_local(src_path, count, duration, framing, subtitles, watermark, langs, out_dir, log, emit,
                  src_format="auto"):
    """Pipeline fichier local (MP4 téléchargé par l'utilisateur + .srt/.vtt optionnel)."""
    if not os.path.exists(src_path):
        raise RuntimeError("Fichier introuvable (upload expiré ?). Re-téléversez la vidéo.")
    subs = _find_sidecar_subs(src_path)
    if subs:
        log(f"📝 Sous-titres trouvés : {os.path.basename(subs)}")
    title = os.path.splitext(os.path.basename(src_path))[0]
    return cut_from_source(src_path, subs, title, "", count, duration, framing, subtitles,
                           watermark, langs, out_dir, log, emit, src_format=src_format)
