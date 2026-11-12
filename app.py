# -*- coding: utf-8 -*-
"""ShortPilot — Studio automatisé de vidéos courtes (Shorts / Reels / TikTok)."""
import datetime
import hmac
import json
import os
import queue
import re
import threading
import time
import traceback
import uuid
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request, send_from_directory

from core import aiimg, autopilot, content, music, publish, render, studio3d, voice, ytclip

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "outputs")
DATA = os.path.join(BASE, "data")
SETTINGS_PATH = os.path.join(DATA, "settings.json")
LIBRARY_PATH = os.path.join(DATA, "library.json")
os.makedirs(OUT, exist_ok=True)
os.makedirs(DATA, exist_ok=True)
try:
    if os.name == "posix":
        os.chmod(DATA, 0o700)  # cookies et jetons OAuth locaux : accès propriétaire seul
except Exception:
    pass

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024

TMP = os.path.join(BASE, "tmp")
os.makedirs(TMP, exist_ok=True)

# ---------------------------------------------------------------- sécurité
# Token d'accès optionnel : OBLIGATOIRE si le serveur est exposé sur un réseau.
#   SHORTPILOT_TOKEN=un_mot_de_passe_long python3 app.py
AUTH_TOKEN = os.environ.get("SHORTPILOT_TOKEN", "").strip()


def _check_origin():
    """Anti-CSRF « drive-by localhost » : rejette les requêtes d'écriture émises
    par un site web tiers (le navigateur envoie toujours Origin sur POST cross-origin)."""
    from urllib.parse import urlparse
    origin = request.headers.get("Origin")
    if not origin:
        return True  # curl, scripts, app desktop…
    pu = urlparse(origin)
    return bool(pu.hostname) and pu.netloc.lower() == request.host.lower()


def _token_ok():
    provided = request.headers.get("X-ShortPilot-Token") or request.args.get("token") or ""
    return hmac.compare_digest(provided, AUTH_TOKEN)


@app.before_request
def guard():
    if request.endpoint == "static":
        return None
    if AUTH_TOKEN and request.path.startswith(("/api", "/media")) and not _token_ok():
        return jsonify({"error": "Token d'accès manquant ou invalide (variable SHORTPILOT_TOKEN)."}), 401
    if request.method in ("POST", "PUT", "DELETE") and not _check_origin():
        return jsonify({"error": "Origine de la requête refusée (anti-CSRF)."}), 403
    # Les API métiers n'acceptent que du JSON (sauf l'upload multipart) :
    # un POST text/plain cross-origin ne peut plus contourner le preflight CORS.
    if request.method == "POST" and request.path.startswith("/api/") \
            and request.endpoint not in ("api_yt_upload", "studio3d.import_video") and not request.is_json:
        return jsonify({"error": "Content-Type application/json requis."}), 415
    return None


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "Fichier trop volumineux (limite : 1 Go)."}), 413


def _json():
    return request.get_json(silent=True) or {}


def _int(v, default, lo, hi):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


LIB_LOCK = threading.Lock()


def library_update(fn):
    """Lecture → modification → écriture atomique de la bibliothèque."""
    with LIB_LOCK:
        lib = load_library()
        fn(lib)
        save_library(lib)


YT_URL_RX = re.compile(r"^https?://(?:(?:www|m|music)\.)?(?:youtube\.com|youtu\.be)/", re.IGNORECASE)


def _youtube_rights_confirmed(data):
    """A YouTube URL is allowed only after an explicit rights attestation."""
    return isinstance(data, dict) and data.get("rights_confirmed") is True


YOUTUBE_RIGHTS_ERROR = (
    "Confirmez que cette vidéo YouTube vous appartient ou que vous disposez "
    "d'une autorisation de téléchargement et de réutilisation."
)

JOBS = {}
JOBS_LOCK = threading.Lock()
PUBLISH_QUEUE_LOCK = threading.Lock()
TASK_Q = queue.Queue()

DEFAULT_SETTINGS = {
    "watermark": "@ShortPilot",
    "webhook_url": "",
    "youtube_privacy": "public",
    "publish_target": "webhook",
    "voice_id": "fr-denise",
    "duration": 30,
    "style": "auto",
    "music": "instrumental",
    "visuals": "comfy",
    "content_source": "web",
    "content_niche": "motivation",
    "comfyui_url": "http://127.0.0.1:8188",
    "comfyui_ckpt": "",
    "cookies_browser": "",
    "voice": True,
    "quality": "1080",
    "autopilot": {
        "enabled": False, "language": "fr", "times": ["09:00", "18:30"],
        "niches": ["motivation", "faits", "psychologie"], "auto_publish": False,
    },
}

VALID_VISUALS = frozenset(("images", "theme", "comfy", "comfy_quality", "motion"))
SETTINGS_LOCK = threading.RLock()


def _copy_json(value):
    return json.loads(json.dumps(value))


def _write_settings(value):
    """Atomic write keeps settings valid if ShortPilot is stopped mid-save."""
    tmp = SETTINGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_PATH)


def _local_comfy_url(value):
    """Images are local by design; discard stale tunnels and arbitrary remote URLs."""
    default = DEFAULT_SETTINGS["comfyui_url"]
    candidate = str(value or "").strip().rstrip("/")
    if not candidate:
        return default
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return default
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or host not in ("127.0.0.1", "localhost", "::1"):
        return default
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return default
    try:
        port = parsed.port
    except ValueError:
        return default
    host_part = "[::1]" if host == "::1" else host
    return f"{parsed.scheme}://{host_part}{':' + str(port) if port else ''}"


def _clean_settings(saved):
    """Whitelist persistent settings and migrate legacy visual modes safely."""
    raw = saved if isinstance(saved, dict) else {}
    clean = _copy_json(DEFAULT_SETTINGS)
    for key in ("watermark", "webhook_url", "voice_id", "music", "cookies_browser"):
        value = raw.get(key)
        if isinstance(value, str):
            clean[key] = value.strip()[:500]
    if raw.get("youtube_privacy") in ("public", "private", "unlisted"):
        clean["youtube_privacy"] = raw["youtube_privacy"]
    if raw.get("publish_target") in ("webhook", "youtube"):
        clean["publish_target"] = raw["publish_target"]
    if raw.get("style") in ("auto", *render.THEMES.keys()):
        clean["style"] = raw["style"]
    clean["music"] = music.normalize_selection(raw.get("music"))
    visuals = raw.get("visuals")
    clean["visuals"] = visuals if visuals in VALID_VISUALS else clean["visuals"]
    if raw.get("content_source") in content.SOURCE_IDS:
        clean["content_source"] = raw["content_source"]
    if raw.get("content_niche") in content.NICHES:
        clean["content_niche"] = raw["content_niche"]
    legacy_niche = raw.get("content_source") if raw.get("content_source") in content.LEGACY_SOURCE_IDS else None
    if legacy_niche:
        clean["content_niche"] = legacy_niche
    clean["duration"] = _int(raw.get("duration"), clean["duration"], 0, 300)
    clean["quality"] = raw.get("quality") if raw.get("quality") in ("720", "1080") else clean["quality"]
    clean["voice"] = bool(raw.get("voice", clean["voice"]))
    clean["comfyui_url"] = _local_comfy_url(raw.get("comfyui_url"))
    clean["comfyui_ckpt"] = aiimg.checkpoint_name(raw.get("comfyui_ckpt"))
    autopilot_raw = raw.get("autopilot") if isinstance(raw.get("autopilot"), dict) else {}
    ap = clean["autopilot"]
    ap["enabled"] = bool(autopilot_raw.get("enabled", ap["enabled"]))
    ap["auto_publish"] = bool(autopilot_raw.get("auto_publish", ap["auto_publish"]))
    ap["language"] = autopilot_raw.get("language") if autopilot_raw.get("language") in ("fr", "en") else ap["language"]
    times = autopilot_raw.get("times")
    if isinstance(times, list):
        ap["times"] = [str(t) for t in times if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", str(t))][:4]
    niches = autopilot_raw.get("niches")
    if isinstance(niches, list):
        ap["niches"] = [str(n)[:80] for n in niches if str(n).strip()][:20] or ap["niches"]
    if legacy_niche:
        ap["niches"] = [legacy_niche]
    return clean


def log_line(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        # Some Windows terminals still use cp1252; logging must not fail a job.
        import sys
        encoding = getattr(sys.stdout, 'encoding', None) or 'utf-8'
        print(line.encode(encoding, errors='replace').decode(encoding), flush=True)


def get_settings():
    with SETTINGS_LOCK:
        raw = {}
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            pass
        clean = _clean_settings(raw)
        # This removes obsolete credentials/tunnel values on first startup after the upgrade.
        if raw != clean:
            try:
                _write_settings(clean)
            except OSError:
                pass
        return _copy_json(clean)


def save_settings(new):
    with SETTINGS_LOCK:
        current = get_settings()
        body = new if isinstance(new, dict) else {}
        # A whitelist prevents an old browser tab (or arbitrary JSON) from restoring retired fields.
        for key in DEFAULT_SETTINGS:
            if key == "autopilot" or key not in body:
                continue
            current[key] = body[key]
        if isinstance(body.get("autopilot"), dict):
            current["autopilot"] = {**current["autopilot"], **body["autopilot"]}
        clean = _clean_settings(current)
        _write_settings(clean)
        return _copy_json(clean)


def load_library():
    try:
        with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_library(lib):
    with open(LIBRARY_PATH, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=2)


def jlog(job, msg):
    with JOBS_LOCK:
        job.setdefault("log", []).append(f"[{time.strftime('%H:%M:%S')}] {msg}")
    log_line(f"{job['id'][:8]} {msg}")


# ---------------------------------------------------------------- jobs
def new_job(kind, params):
    job = {"id": uuid.uuid4().hex, "kind": kind, "params": params,
           "status": "queued", "created": datetime.datetime.now().isoformat(timespec="seconds"),
           "log": [], "result": None, "error": None}
    with JOBS_LOCK:
        JOBS[job["id"]] = job
    TASK_Q.put(job)
    return job


def run_render_job(job):
    p = dict(job["params"])
    vid = f"{int(time.time())}_{job['id'][:8]}"
    p["out_path"] = os.path.join(OUT, f"{vid}.mp4")
    p.setdefault("badge", content.badge_for(p["script"].get("niche", ""), p["script"].get("language", "fr")))
    res = render.render_video(p, log=lambda m: jlog(job, m))
    entry = {
        "id": vid, "file": os.path.basename(res["video"]),
        "thumb": os.path.basename(res["thumb"]),
        "title": p["script"].get("title", "Sans titre"),
        "caption": p["script"].get("caption", ""),
        "hashtags": p["script"].get("hashtags", ""),
        "duration": round(res["duration"], 1),
        "niche": p["script"].get("niche"), "language": p["script"].get("language"),
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "published": [],
    }
    if res.get("visual_report"):
        entry["visual_report"] = os.path.basename(res["visual_report"])
    if res.get("attribution"):
        entry["caption"] = (entry["caption"] or "") + "\n\n🖼️ " + res["attribution"]
    if res.get("music_attrib"):
        entry["caption"] = (entry["caption"] or "") + "\n🎵 " + res["music_attrib"]
    library_update(lambda lib: lib.insert(0, entry))
    job["result"] = entry

    if p.get("auto_publish"):
        settings = get_settings()
        target = settings.get("publish_target", "webhook")
        jlog(job, f"📤 Publication automatique (cible : {target})…")
        ok, msg = _do_publish(entry, target, settings, job)
        jlog(job, ("✅ " if ok else "❌ ") + msg)


def _do_publish(entry, target, settings, job):
    vpath = os.path.join(OUT, entry["file"])
    title = entry["title"]
    caption = (entry["caption"] or "") + "\n" + (entry["hashtags"] or "")
    log = (lambda m: jlog(job, m)) if job else log_line
    if target == "youtube":
        ok, msg = publish.publish_youtube(vpath, title, caption,
                                          settings.get("youtube_privacy", "public"), log=log)
    else:
        ok, msg = publish.publish_webhook(settings.get("webhook_url", ""), vpath, caption,
                                          "all", log=log, video_id=entry["id"], title=title,
                                          duration=entry.get("duration", 0), require_public=True)
    if ok:
        def mark(lib):
            for e in lib:
                if e["id"] == entry["id"]:
                    e.setdefault("published", []).append(
                        {"target": target, "at": datetime.datetime.now().isoformat(timespec="seconds"),
                         "message": msg})
        library_update(mark)
    return ok, msg


def run_publish_job(job):
    p = job["params"]
    entry = None
    for e in load_library():
        if e["id"] == p.get("video_id"):
            entry = e
            break
    if not entry:
        raise ValueError("Vidéo introuvable dans la bibliothèque.")
    ok, msg = _do_publish(entry, p.get("target", "webhook"), get_settings(), job)
    job["result"] = {"ok": ok, "message": msg}
    if not ok:
        raise RuntimeError(msg)


def run_ytshorts_job(job):
    p = job["params"]
    settings = get_settings()
    langs = ("en", "fr") if p.get("language") == "en" else ("fr", "en")
    job["result"] = {"shorts": []}

    def emit(entry_data):
        entry = dict(entry_data)
        entry["created"] = datetime.datetime.now().isoformat(timespec="seconds")
        entry["published"] = []
        library_update(lambda lib: lib.insert(0, entry))
        job["result"]["shorts"].append(entry)

    common = dict(count=int(p.get("count") or 0), duration=int(p.get("duration") or 45),
                  framing=p.get("framing", "blur"), subtitles=bool(p.get("subtitles", True)),
                  watermark=p.get("watermark", "") or settings.get("watermark", ""),
                  langs=langs, out_dir=OUT, log=lambda m: jlog(job, m), emit=emit,
                  src_format=p.get("src_format", "auto"))
    if p.get("file_path"):
        jlog(job, "📁 Source : fichier local uploadé")
        n = ytclip.process_local(p["file_path"], **common)
    else:
        n = ytclip.process(url=p["url"], **common)
    jlog(job, f"🏁 {n} short(s) produit(s) — voir la Bibliothèque.")


def run_studio3d_job(job):
    p = job['params']
    vid = f"{int(time.time())}_{job['id'][:8]}"
    result = studio3d.ingest_recording(p['file_path'], os.path.join(OUT, vid + '.mp4'),
                                      log=lambda line: jlog(job, line))
    entry = {
        'id': vid, 'file': os.path.basename(result['video']),
        'thumb': os.path.basename(result['thumb']), 'title': p['title'],
        'caption': p['caption'], 'hashtags': '', 'duration': round(result['duration'], 1),
        'niche': 'studio3d', 'language': 'fr', 'source': 'studio3d',
        'created': datetime.datetime.now().isoformat(timespec='seconds'), 'published': [],
    }
    library_update(lambda lib: lib.insert(0, entry))
    job['result'] = entry
    jlog(job, 'Creation 3D ajoutee a la bibliotheque. Aucune publication automatique.')


def worker():
    while True:
        job = TASK_Q.get()
        try:
            with JOBS_LOCK:
                job["status"] = "running"
            jlog(job, "⏳ Début du traitement…")
            if job["kind"] == "render":
                run_render_job(job)
            elif job["kind"] == "publish":
                run_publish_job(job)
            elif job["kind"] == "ytshorts":
                run_ytshorts_job(job)
            elif job["kind"] == "studio3d":
                run_studio3d_job(job)
            with JOBS_LOCK:
                job["status"] = "done"
            jlog(job, "🏁 Terminé.")
        except Exception as e:
            with JOBS_LOCK:
                job["status"] = "error"
                job["error"] = str(e)
            jlog(job, f"❌ Erreur : {e}")
            traceback.print_exc()
        finally:
            TASK_Q.task_done()


def enqueue_render_and_publish(niche, lang="fr", auto_publish=False):
    """Utilisé par le pilote automatique."""
    settings = get_settings()
    dur = settings.get("duration", 30)
    script = content.generate_script(niche=niche, lang=lang, target=dur,
                                     source=settings.get("content_source", "web"))
    if script.get("error"):
        raise ValueError(script["error"])
    params = _render_params({}, script, settings)
    params["target"] = dur
    params["auto_publish"] = auto_publish
    new_job("render", params)


def _visual_mode(value, fallback="comfy"):
    if value in VALID_VISUALS:
        return value
    return fallback if fallback in VALID_VISUALS else "comfy"


def _render_params(data, script, settings=None):
    """Build every render job through one sanitised path (manual, batch, pilot)."""
    d = data if isinstance(data, dict) else {}
    s = settings or get_settings()
    def supplied(key):
        return d[key] if key in d else s[key]

    voice_value = supplied("voice")
    auto_publish = d.get("auto_publish", False)
    return {
        "script": script,
        "style": supplied("style") if supplied("style") in ("auto", *render.THEMES.keys()) else s["style"],
        "music": music.normalize_selection(supplied("music")),
        "visuals": _visual_mode(d.get("visuals"), s["visuals"]),
        "voice": voice_value if isinstance(voice_value, bool) else s["voice"],
        "voice_id": str(supplied("voice_id"))[:120] or s["voice_id"],
        "target": _int(d.get("duration"), s["duration"], 0, 300),
        "quality": supplied("quality") if supplied("quality") in ("720", "1080") else s["quality"],
        "watermark": str(supplied("watermark"))[:500],
        "auto_publish": auto_publish if isinstance(auto_publish, bool) else False,
        "comfyui_url": _local_comfy_url(supplied("comfyui_url")),
        "comfyui_ckpt": aiimg.checkpoint_name(supplied("comfyui_ckpt")),
    }


app.register_blueprint(studio3d.create_blueprint(BASE, lambda params: new_job('studio3d', params)))

# ---------------------------------------------------------------- routes
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/media/<path:name>")
def media(name):
    return send_from_directory(OUT, name)


@app.route("/api/config")
def api_config():
    s = get_settings()
    return jsonify({
        "niches": content.niche_labels(s.get("autopilot", {}).get("language", "fr")),
        "themes": [{"id": "auto", "label": "🧠 Auto (selon le script)", "accent": "#a5b4fc"}]
                  + [{"id": k, "label": v["label"], "accent": "#%02x%02x%02x" % v["accent"]}
                     for k, v in render.THEMES.items()],
        "musics": [{"id": "instrumental", "label": "🎻 Instrumental cinématique local — adapté au script, sans voix"},
                   {"id": "auto", "label": "🎼 Instrumental automatique local — sans voix"}]
                  + [{"id": k, "label": v["label"]} for k, v in music.PRESETS.items()],
        "voices": {"fr": voice.voices_for("fr"), "en": voice.voices_for("en")},
        "durations": content.DURATION_OPTIONS,
        "voice_available": voice.tts_available(),
        "voice_engine": voice.engine_label(),
        "youtube": publish.youtube_status(),
        "cookies_txt": os.path.exists(os.path.join(DATA, "cookies.txt")),
        "comfyui": aiimg.comfy_status(s.get("comfyui_url", ""), timeout=2.5),
        "settings": s,
    })


@app.route("/api/script", methods=["POST"])
def api_script():
    d = _json()
    lang = d.get("language", "fr")
    src = d.get("source") if d.get("source") in content.ACCEPTED_SOURCE_IDS else \
        get_settings().get("content_source", "web")
    return jsonify(content.generate_script(niche=d.get("niche", "motivation"),
                                           lang=lang, topic=d.get("topic", ""),
                                           target=d.get("duration"), source=src))


@app.route("/api/render", methods=["POST"])
def api_render():
    d = _json()
    script = d.get("script") or {}
    scenes = [s.strip()[:600] for s in (script.get("scenes") or []) if s and s.strip()][:60]
    if not scenes:
        return jsonify({"error": "Script vide : ajoutez au moins une scène."}), 400
    script["scenes"] = scenes
    visual_plans = script.get("visual_plans") or []
    expected_fingerprint = content.visual_plan_fingerprint(
        scenes, title=script.get("title", ""), niche=script.get("niche", ""), language=script.get("language", ""),
    )
    plans_locked = script.get("visual_plans_locked") is True
    fingerprint_matches = script.get("visual_plan_fingerprint") == expected_fingerprint
    if isinstance(visual_plans, list) and len(visual_plans) == len(scenes) and (plans_locked or fingerprint_matches):
        script["visual_plans"] = list(visual_plans)
        controls = script.get("visual_controls")
        if not isinstance(controls, list) or len(controls) != len(scenes):
            controls = content.visual_plan_bundle(scenes, title=script.get("title", ""),
                                                  niche=script.get("niche", ""), language=script.get("language", ""))["visual_controls"]
        script["visual_controls"] = controls
        script["visual_plan_fingerprint"] = expected_fingerprint
    else:
        # Scene text, title, niche, language, ordering, or count changed.
        # Rebuild server-side; never reuse same-length but stale briefs.
        script.update(content.visual_plan_bundle(
            scenes, title=script.get("title", ""), niche=script.get("niche", ""), language=script.get("language", ""),
        ))
    script["caption"] = (script.get("caption") or "")[:2000]
    script["title"] = (script.get("title") or "")[:120]
    if not script.get("caption"):
        script["caption"] = scenes[0]
    if _visual_mode(d.get("visuals"), get_settings()["visuals"]) in ("comfy", "comfy_quality", "motion"):
        from core.visual_planner import validate_required_terms, VisualPlanningError
        for index, (plan, control) in enumerate(zip(script["visual_plans"], script["visual_controls"]), 1):
            try:
                if not plan:
                    raise VisualPlanningError(control.get("planning_error") or "Plan visuel manquant")
                validate_required_terms(plan, control)
            except VisualPlanningError as exc:
                return jsonify({"error": f"Scène {index} : {exc}"}), 422
    job = new_job("render", _render_params(d, script))
    return jsonify({"job_id": job["id"]})


@app.route("/api/batch", methods=["POST"])
def api_batch():
    d = _json()
    count = _int(d.get("count"), 5, 1, 30)
    niches = d.get("niches") or [d.get("niche", "motivation")]
    lang = d.get("language", "fr")
    ids = []
    import random as _rnd
    src = d.get("source") if d.get("source") in content.ACCEPTED_SOURCE_IDS else \
        get_settings().get("content_source", "web")
    for _ in range(count):
        niche = _rnd.choice(niches)
        script = content.generate_script(niche=niche, lang=lang, topic=d.get("topic", ""),
                                         target=d.get("duration"), source=src)
        if script.get("error"):
            return jsonify({"error": script["error"], "jobs": ids}), 422
        job = new_job("render", _render_params(d, script))
        ids.append({"job_id": job["id"], "title": script["title"], "niche": script["niche"]})
    return jsonify({"jobs": ids})


def _job_view(job):
    return {"id": job["id"], "kind": job["kind"], "status": job["status"],
            "created": job["created"], "log": job["log"][-200:], "result": job["result"],
            "error": job["error"],
            "title": (job["params"].get("script") or {}).get("title", "") or job["params"].get("url", "")}


@app.route("/api/jobs")
def api_jobs():
    with JOBS_LOCK:
        jobs = list(JOBS.values())
    return jsonify({"jobs": [_job_view(j) for j in jobs][-50:]})


@app.route("/api/job/<jid>")
def api_job(jid):
    with JOBS_LOCK:
        job = JOBS.get(jid)
    if not job:
        return jsonify({"error": "introuvable"}), 404
    return jsonify(_job_view(job))


@app.route("/api/library")
def api_library():
    return jsonify({"items": load_library()})


@app.route("/api/yt/info", methods=["POST"])
def api_yt_info():
    d = _json()
    url = (d.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL manquante."}), 400
    if not YT_URL_RX.match(url):
        return jsonify({"error": "URL non prise en charge : indiquez un lien youtube.com ou youtu.be."}), 400
    if not _youtube_rights_confirmed(d):
        return jsonify({"error": YOUTUBE_RIGHTS_ERROR}), 400
    try:
        return jsonify(ytclip.get_info(url))
    except Exception as e:
        return jsonify({"error": str(e)[:400]}), 400


UPLOADS = os.path.join(DATA, "uploads")
os.makedirs(UPLOADS, exist_ok=True)
ALLOWED_VIDEO = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")
ALLOWED_SUBS = (".srt", ".vtt")
MAX_UPLOAD_AGE = 24 * 3600  # purge anti-remplissage du disque


def _purge_uploads():
    """Supprime les uploads de plus de 24 h qui ne sont pas référencés par un job en file."""
    try:
        protected = set()
        with JOBS_LOCK:
            for j in JOBS.values():
                if j.get("status") in ("queued", "running"):
                    fp = (j.get("params") or {}).get("file_path")
                    if fp:
                        protected.add(os.path.realpath(fp))
        cutoff = time.time() - MAX_UPLOAD_AGE
        for name in os.listdir(UPLOADS):
            p = os.path.join(UPLOADS, name)
            if os.path.isfile(p) and os.path.realpath(p) not in protected \
                    and os.path.getmtime(p) < cutoff:
                os.remove(p)
                log_line(f"🧹 Upload expiré supprimé : {name}")
    except Exception:
        pass


@app.route("/api/yt/upload", methods=["POST"])
def api_yt_upload():
    """Upload d'une vidéo locale (+ sous-titres .srt/.vtt optionnels du même nom)."""
    _purge_uploads()
    f = request.files.get("video")
    if not f or not f.filename:
        return jsonify({"error": "Aucun fichier vidéo reçu."}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_VIDEO:
        return jsonify({"error": f"Format non supporté ({ext}). Utilisez MP4/MOV/MKV/WebM."}), 400
    stem = re.sub(r"[^A-Za-z0-9_\-]+", "_", os.path.splitext(os.path.basename(f.filename))[0])[:60]
    stem = f"{stem}_{uuid.uuid4().hex[:8]}"
    vpath = os.path.join(UPLOADS, stem + ext)
    f.save(vpath)
    subsf = request.files.get("subs")
    subs_saved = None
    if subsf and subsf.filename:
        sext = os.path.splitext(subsf.filename)[1].lower()
        if sext in ALLOWED_SUBS:
            subs_saved = os.path.join(UPLOADS, stem + sext)
            subsf.save(subs_saved)
    dur = ytclip.probe_video_duration(vpath)
    size_mb = os.path.getsize(vpath) / 1e6
    return jsonify({"file_id": stem, "file_path": vpath, "duration": int(dur),
                    "size_mb": round(size_mb, 1), "name": f.filename,
                    "subs": bool(subs_saved)})


@app.route("/api/yt/shorts", methods=["POST"])
def api_yt_shorts():
    d = _json()
    url = (d.get("url") or "").strip()
    file_path = (d.get("file_path") or "").strip()
    if not url and not file_path:
        return jsonify({"error": "Fournissez une URL YouTube ou uploadez une vidéo."}), 400
    if url and not YT_URL_RX.match(url):
        return jsonify({"error": "URL non prise en charge : indiquez un lien youtube.com ou youtu.be."}), 400
    if url and not _youtube_rights_confirmed(d):
        return jsonify({"error": YOUTUBE_RIGHTS_ERROR}), 400
    if file_path:
        fp = os.path.realpath(file_path)
        up = os.path.realpath(UPLOADS)
        if not fp.startswith(up + os.sep) or not os.path.isfile(fp):
            return jsonify({"error": "Chemin refusé : utilisez un fichier envoyé via « 📁 Fichier local »."}), 400
        file_path = fp
    dur = _int(d.get("duration"), 45, 20, 300)
    src_format = d.get("src_format") if d.get("src_format") in ytclip.SRC_FORMATS else "auto"
    framing = d.get("framing") if d.get("framing") in ("blur", "center") else "blur"
    job = new_job("ytshorts", {
        "url": url, "file_path": file_path, "count": _int(d.get("count"), 0, 0, 10), "duration": dur,
        "framing": framing, "subtitles": bool(d.get("subtitles", True)),
        "watermark": d.get("watermark", ""), "language": d.get("language", "fr"),
        "src_format": src_format,
    })
    return jsonify({"job_id": job["id"]})


@app.route("/api/publish", methods=["POST"])
def api_publish():
    d = _json()
    target = d.get("target") if d.get("target") in ("webhook", "youtube") else "webhook"
    params = {"video_id": str(d.get("video_id") or "")[:64], "target": target}
    with PUBLISH_QUEUE_LOCK:
        with JOBS_LOCK:
            existing = next((j for j in JOBS.values() if j["kind"] == "publish"
                             and j["params"] == params and j["status"] in ("queued", "running")), None)
        job = existing or new_job("publish", params)
    return jsonify({"job_id": job["id"]})


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        body = _json()
        if not isinstance(body, dict):
            return jsonify({"error": "Corps JSON invalide."}), 400
        return jsonify(save_settings(body))
    return jsonify(get_settings())


@app.route("/api/delete", methods=["POST"])
def api_delete():
    d = _json()
    vid = str(d.get("video_id") or "")
    removed = {}

    def pick(lib):
        kept = []
        for e in lib:
            if e.get("id") == vid:
                removed["e"] = e
            else:
                kept.append(e)
        lib[:] = kept

    library_update(pick)
    if removed.get("e"):
        for f in (removed["e"].get("file"), removed["e"].get("thumb"), removed["e"].get("visual_report")):
            try:
                fp = os.path.realpath(os.path.join(OUT, f or ""))
                if f and fp.startswith(os.path.realpath(OUT) + os.sep) and os.path.isfile(fp):
                    os.remove(fp)
            except Exception:
                pass
    return jsonify({"ok": bool(removed.get("e"))})


if __name__ == "__main__":
    threading.Thread(target=worker, daemon=True).start()
    autopilot.start_worker(get_settings, enqueue_render_and_publish, log=log_line)
    # Écoute locale par défaut (sécurité). SHORTPILOT_HOST=0.0.0.0 pour ouvrir au réseau
    # — dans ce cas, définissez IMPÉRATIVEMENT SHORTPILOT_TOKEN.
    host = os.environ.get("SHORTPILOT_HOST", "127.0.0.1")
    port = int(os.environ.get("SHORTPILOT_PORT", "8000"))
    if host != "127.0.0.1" and not AUTH_TOKEN:
        log_line("⚠️  Écoute réseau SANS token ! Toute personne y ayant accès peut piloter l'outil."
                 " (définissez SHORTPILOT_TOKEN)")
    log_line(f"⚡ ShortPilot démarré → http://{host}:{port}")
    app.run(host=host, port=port, threaded=True, debug=False)
