# -*- coding: utf-8 -*-
"""ShortPilot — voix off IA.
Moteur principal : Edge-TTS (voix neurales réalistes, multi-voix FR/EN, réglage de débit).
Repli automatique : gTTS si Edge-TTS est indisponible (hors-ligne…)."""
import os
import re
import subprocess
import hashlib
import tempfile

VOICES = {
    "fr": [
        {"id": "fr-denise",   "vx": "fr-FR-DeniseNeural",               "label": "Denise — femme, naturelle"},
        {"id": "fr-henri",    "vx": "fr-FR-HenriNeural",                "label": "Henri — homme, posé"},
        {"id": "fr-eloise",   "vx": "fr-FR-EloiseNeural",               "label": "Éloïse — femme, jeune & dynamique"},
        {"id": "fr-vivienne", "vx": "fr-FR-VivienneMultilingualNeural", "label": "Vivienne — femme, douce"},
        {"id": "fr-remy",     "vx": "fr-FR-RemyMultilingualNeural",     "label": "Rémy — homme, dynamique"},
        {"id": "fr-sylvie",   "vx": "fr-CA-SylvieNeural",               "label": "Sylvie — femme, canadienne"},
        {"id": "fr-antoine",  "vx": "fr-CA-AntoineNeural",              "label": "Antoine — homme, canadien"},
        {"id": "fr-jean",     "vx": "fr-CA-JeanNeural",                 "label": "Jean — homme, grave"},
        {"id": "fr-charline", "vx": "fr-BE-CharlineNeural",             "label": "Charline — femme, belge"},
        {"id": "fr-gerard",   "vx": "fr-BE-GerardNeural",               "label": "Gérard — homme, belge"},
        {"id": "fr-ariane",   "vx": "fr-CH-ArianeNeural",               "label": "Ariane — femme, suisse"},
        {"id": "fr-fabrice",  "vx": "fr-CH-FabriceNeural",              "label": "Fabrice — homme, suisse"},
    ],
    "en": [
        {"id": "en-aria",        "vx": "en-US-AriaNeural",               "label": "Aria — female, natural (US)"},
        {"id": "en-christopher", "vx": "en-US-ChristopherNeural",        "label": "Christopher — male, deep (US)"},
        {"id": "en-jenny",       "vx": "en-US-JennyNeural",              "label": "Jenny — female, friendly (US)"},
        {"id": "en-ryan",        "vx": "en-GB-RyanNeural",               "label": "Ryan — male, British"},
        {"id": "en-andrew",      "vx": "en-US-AndrewMultilingualNeural", "label": "Andrew — male, warm (US)"},
        {"id": "en-ava",         "vx": "en-US-AvaMultilingualNeural",    "label": "Ava — female, bright (US)"},
        {"id": "en-brian",       "vx": "en-US-BrianMultilingualNeural",  "label": "Brian — male, casual (US)"},
        {"id": "en-emma",        "vx": "en-US-EmmaMultilingualNeural",   "label": "Emma — female, cheerful (US)"},
        {"id": "en-guy",         "vx": "en-US-GuyNeural",                "label": "Guy — male, newscaster (US)"},
        {"id": "en-eric",        "vx": "en-US-EricNeural",               "label": "Eric — male, neutral (US)"},
        {"id": "en-steffan",     "vx": "en-US-SteffanNeural",            "label": "Steffan — male, young (US)"},
        {"id": "en-sonia",       "vx": "en-GB-SoniaNeural",              "label": "Sonia — female, British"},
        {"id": "en-natasha",     "vx": "en-AU-NatashaNeural",            "label": "Natasha — female, Australian"},
        {"id": "en-clara",       "vx": "en-CA-ClaraNeural",              "label": "Clara — female, Canadian"},
        {"id": "en-liam",        "vx": "en-CA-LiamNeural",               "label": "Liam — male, Canadian"},
    ],
}
DEFAULT_VOICE = {"fr": "fr-denise", "en": "en-aria"}

_EDGE_OK = None
_GTTS_OK = None


def _net_ok(url):
    try:
        import requests
        requests.head(url, timeout=5)
        return True
    except Exception:
        return False


def edge_available():
    global _EDGE_OK
    if _EDGE_OK is None:
        try:
            import edge_tts  # noqa
            _EDGE_OK = _net_ok("https://speech.platform.bing.com")
        except Exception:
            _EDGE_OK = False
    return _EDGE_OK


def tts_available():
    global _GTTS_OK
    if edge_available():
        return True
    if _GTTS_OK is None:
        try:
            import gtts  # noqa
            _GTTS_OK = _net_ok("https://translate.google.com")
        except Exception:
            _GTTS_OK = False
    return _GTTS_OK


def engine_label():
    if edge_available():
        return "Voix neurales réalistes (multi-voix)"
    if tts_available():
        return "Voix standard (repli)"
    return "Indisponible (hors-ligne)"


def resolve_voice(lang, voice_id):
    lst = VOICES.get(lang if lang in VOICES else "fr", VOICES["fr"])
    ids = {v["id"]: v["vx"] for v in lst}
    if voice_id in ids:
        return ids[voice_id]
    return ids.get(DEFAULT_VOICE.get(lang, DEFAULT_VOICE["fr"]), lst[0]["vx"])


def probe_duration(path, ffmpeg=None):
    if ffmpeg is None:
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return 0.0
    try:
        p = subprocess.run([ffmpeg, "-hide_banner", "-i", path],
                           capture_output=True, text=True, timeout=30)
        m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", p.stderr or "")
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        pass
    return 0.0


def _edge_synth(texts, vx, rate_pct, outdir):
    import asyncio
    import edge_tts

    async def one(txt, path):
        c = edge_tts.Communicate(txt, vx, rate=f"{int(rate_pct):+d}%")
        await c.save(path)

    out = []
    for i, txt in enumerate(texts):
        path = os.path.join(outdir, f"voice_{i}.mp3")
        asyncio.run(one(txt, path))
        out.append((path, probe_duration(path)))
    return out


def _gtts_synth(texts, lang, outdir):
    from gtts import gTTS
    out = []
    for i, txt in enumerate(texts):
        path = os.path.join(outdir, f"voice_{i}.mp3")
        gTTS(text=txt, lang="fr" if lang == "fr" else "en").save(path)
        out.append((path, probe_duration(path)))
    return out


def synthesize_scenes(texts, lang, outdir, voice_id=None, rate_pct=0):
    """Retourne une liste de (chemin_mp3, durée) ou None si échec total."""
    texts = [(t or "").strip() for t in texts]
    texts = [t for t in texts if t]
    if not texts:
        return []
    os.makedirs(outdir, exist_ok=True)
    if edge_available():
        try:
            return _edge_synth(texts, resolve_voice(lang, voice_id), rate_pct, outdir)
        except Exception:
            pass  # repli gTTS
    try:
        return _gtts_synth(texts, lang, outdir)
    except Exception:
        return None


def voices_for(lang):
    return [dict(v) for v in VOICES.get(lang, VOICES["fr"])]


STUDIO_VOICE_IDS = {'fr-denise', 'fr-remy'}


def _render_edge_track(text, voice_name, rate_pct, target):
    """Render one uninterrupted neural track with the regular voice-off engine."""
    import asyncio
    import edge_tts

    async def render():
        communicate = edge_tts.Communicate(
            text,
            voice_name,
            rate=f"{int(rate_pct):+d}%",
            connect_timeout=10,
            receive_timeout=20,
        )
        await communicate.save(target)

    asyncio.run(asyncio.wait_for(render(), timeout=45))


def synthesize_studio_narration(text, cache_dir, voice_id='fr-denise', rate_pct=0):
    """Render the complete Studio narration as one cached Edge-TTS track.

    This deliberately has no fallback: an Objaverse narration requested with
    Denise (or Remy) must never switch to a different, robotic voice.
    """
    text = str(text or '').strip()
    voice_id = str(voice_id or 'fr-denise').strip()
    if not text or voice_id not in STUDIO_VOICE_IDS:
        return None

    os.makedirs(cache_dir, exist_ok=True)
    rate_pct = max(-30, min(30, int(rate_pct or 0)))
    voice_name = resolve_voice('fr', voice_id)
    cache_key = hashlib.sha256(
        f'edge-studio-v1|{voice_id}|{rate_pct}|{text}'.encode('utf-8')
    ).hexdigest()
    target = os.path.join(cache_dir, f'{cache_key}.mp3')
    mode = f'edge_tts:{voice_id}'
    if os.path.isfile(target) and os.path.getsize(target) > 1024:
        return target, mode

    temporary = tempfile.NamedTemporaryFile(
        prefix=f'{cache_key}-', suffix='.mp3', dir=cache_dir, delete=False
    )
    temporary_path = temporary.name
    temporary.close()
    try:
        _render_edge_track(text, voice_name, rate_pct, temporary_path)
        if not os.path.isfile(temporary_path) or os.path.getsize(temporary_path) <= 1024:
            return None
        os.replace(temporary_path, target)
    except (OSError, RuntimeError, TimeoutError, ValueError):
        return None
    finally:
        try:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
        except OSError:
            pass
    return target, mode
