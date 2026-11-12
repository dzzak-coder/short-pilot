# -*- coding: utf-8 -*-
"""ShortPilot — musique IA LOCALE : ACE-Step (3.5 B) via votre ComfyUI.

Un morceau sur mesure, généré sur VOTRE GPU, à partir de l'ambiance détectée
dans le script (music.explain_auto). Aucun compte, aucune clé, gratuit à vie.

  • Modèle : ACE-Step v1 3.5B — licence **Apache 2.0** (diffusion/monetisation OK) ;
  • Nœuds requis : intégrés aux ComfyUI récents (type « CheckpointLoaderSimple »,
    « TextEncodeAceStepAudio », « VAEDecodeAudio », « SaveAudioMP3 »…), aucun
    plugin à installer. Workflow = structure standard, soumise par l'API /prompt ;
  • Robustesse : tout échec (ComfyUI éteint, modèle absent, nœuds trop anciens)
    → None → la chaîne de relais du rendu prend la main (🌐 Web Auto → synthèse).

Le morceau téléchargé (MP3) est ensuite normalisé + fondus via webmusic._prepare.
"""
import json
import os
import re
import secrets
import time
import unicodedata
import urllib.parse

import requests

from . import imglib  # UA partagé

UA = imglib.UA
TIMEOUT_API = 20
MAX_SECONDS = 420          # plafond ACE (vidéos ≤ 5 min = 301 s ici)

# Ambiance (id de music.PRESETS) → tags ACE-Step (anglais, comme entraîné)
_INSTRUMENTAL_ONLY = (
    "strictly instrumental soundtrack, no vocals, no singing, no choir, no humming, "
    "no spoken words, no lyrics, no vocal samples"
)

MOOD_TAGS = {
    "energie": "energetic upbeat electronic score, driving beat, motivational, dynamic synth",
    "chill": "lo-fi instrumental score, jazzy piano, smooth, mellow, relaxing background",
    "drama": "cinematic drama score, tense strings, emotional trailer ambiance, orchestral",
    "happy": "upbeat cheerful instrumental score, bright acoustic, playful, sunny",
    "epique": "epic orchestral cinematic score, powerful drums, heroic brass, rising tension",
    "mystere": "dark suspense ambient score, mysterious thriller atmosphere, deep drones, minimal textures, tense",
    "triste": "sad emotional piano, melancholic cinematic strings, slow, tender",
    "techno": "futuristic instrumental techno, dark synthwave, driving bass, cyberpunk night",
    "zen": "meditation ambient score, calm zen, soft warm pads, healing, very slow, gentle",
}

# A fixed mood alone makes a music model gravitate to the same arrangement.
# These are intentionally production-safe instrumental alternatives; a recent
# variant is not reused for the same mood when another is available.
MOOD_VARIANTS = {
    "energie": ("crisp electro percussion and punchy bass", "bright funk guitar and handclaps", "hybrid cinematic drums and synth arpeggios"),
    "chill": ("dusty vinyl texture and Rhodes electric piano", "warm acoustic guitar and soft brushed drums", "ambient marimba, airy pads and minimal beat"),
    "drama": ("intimate piano and restrained low strings", "slow pulse, cello ostinato and distant percussion", "dark orchestral swells and sparse impacts"),
    "happy": ("ukulele and bright hand percussion", "playful mallet melody and light claps", "sunny acoustic guitar and buoyant rhythm"),
    "epique": ("heroic brass, taiko drums and rising strings", "ancient frame drums and cinematic choir-like pads", "powerful low strings, toms and restrained brass"),
    "mystere": ("subtle analog pulse and whispering textures", "low piano notes, distant metallic hits and drones", "minimal plucked strings and dark ambient pads"),
    "triste": ("felt piano and delicate cello", "slow acoustic guitar and soft string harmonies", "solitary piano with wide reverberation"),
    "techno": ("driving arpeggiator and punchy electronic drums", "dark modular synth pulse and crisp hi-hats", "futuristic bass sequence and spacious digital textures"),
    "zen": ("soft bamboo flute and warm drones", "gentle handpan and airy pads", "quiet piano, soft rain texture and slow pads"),
}
MOOD_TEMPOS = {
    # (annonce au modele, facteur applique apres generation). Le facteur rend
    # l'ecart perceptible meme si ACE-Step ignore partiellement le tag BPM.
    "energie": (("104 BPM", 0.86), ("122 BPM", 1.00), ("136 BPM", 1.13)),
    "chill": (("66 BPM", 0.85), ("78 BPM", 1.00), ("88 BPM", 1.13)),
    "drama": (("58 BPM", 0.86), ("68 BPM", 1.00), ("78 BPM", 1.13)),
    "happy": (("100 BPM", 0.89), ("112 BPM", 1.00), ("124 BPM", 1.11)),
    "epique": (("72 BPM", 0.84), ("88 BPM", 1.00), ("100 BPM", 1.14)),
    "mystere": (("56 BPM", 0.86), ("64 BPM", 1.00), ("76 BPM", 1.15)),
    "triste": (("58 BPM", 0.88), ("66 BPM", 1.00), ("74 BPM", 1.12)),
    "techno": (("118 BPM", 0.89), ("132 BPM", 1.00), ("140 BPM", 1.08)),
    "zen": (("48 BPM", 0.86), ("56 BPM", 1.00), ("64 BPM", 1.14)),
}
_HISTORY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ace_music_history.json")


def _recent_variants(mood):
    try:
        with open(_HISTORY_PATH, "r", encoding="utf-8") as source:
            history = json.load(source)
    except (OSError, ValueError, TypeError):
        history = []
    if not isinstance(history, list):
        history = []
    return [str(item.get("variant", "")) for item in history if item.get("mood") == mood][-3:], history


def _choose_variant(mood):
    variants = MOOD_VARIANTS.get(mood, MOOD_VARIANTS["chill"])
    recent, history = _recent_variants(mood)
    available = [variant for variant in variants if variant not in recent] or list(variants)
    variant = secrets.choice(available)
    history = (history + [{"mood": mood, "variant": variant}])[-24:]
    try:
        os.makedirs(os.path.dirname(_HISTORY_PATH), exist_ok=True)
        tmp = _HISTORY_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as target:
            json.dump(history, target, ensure_ascii=False)
        os.replace(tmp, _HISTORY_PATH)
    except OSError:
        pass
    return variant


def _subject_tags(text="", niche=""):
    """Add concrete, local-only musical direction from the actual narration."""
    raw = f"{text} {niche}".lower()
    normalized = "".join(
        char for char in unicodedata.normalize("NFD", raw)
        if unicodedata.category(char) != "Mn"
    )
    subjects = (
        (("tokyo", "japon", "japan", "ramen", "sushi"),
         "late-night Tokyo documentary score, subtle kitchen percussion, restrained bass pulse, soft electric piano, urban night ambience"),
        (("cuisine", "cuisines", "restaurant", "chef", "cuisinier", "recette", "gastronomie"),
         "culinary documentary score, tactile light percussion, warm rhythm, subtle kitchen ambience, keep the narration clearly in front"),
        (("lagide", "ptolemaique", "ptolemee", "pharaon", "cleopatre", "egypte"),
         "ancient Egyptian inspired ceremonial atmosphere, ney flute, oud, frame drums, desert reverberation"),
        (("avion de chasse", "fighter jet", "aviation", "pilote"),
         "high-energy cinematic electronic pulse, aerial tension, propulsive percussion, modern action score"),
        (("rome", "romain", "cesar", "gladiateur"),
         "ancient Roman inspired cinematic score, lyre, hand drums, dignified brass and strings"),
        (("viking", "vikings"),
         "Nordic cinematic folk atmosphere, war drums, low strings, distant horn, cold open landscape"),
        (("nasa", "espace", "galaxie", "astronaute", "fusee", "planete", "lancement"),
         "cinematic space exploration score, wide orchestra, slow-building strings, restrained brass, distant choir-free pads, awe and scale"),
    )
    for terms, tags in subjects:
        if any(term in normalized for term in terms):
            return tags
    return "narration-led background score, fit the subject literally, avoid unrelated genre clichés"


def _pick_ace_checkpoint(server, log=None):
    """Cherche un checkpoint ACE-Step parmi ceux installés (nom contenant « ace »)."""
    r = None
    try:
        r = requests.get(server + "/object_info/CheckpointLoaderSimple", headers=UA, timeout=TIMEOUT_API)
        names = ((r.json().get("CheckpointLoaderSimple", {})
                  .get("input", {}).get("required", {}).get("ckpt_name")) or [[]])[0]
    except Exception:
        names = []
    for cand in names or []:
        if re.search(r"ace[-_ ]?step", cand or "", re.I):
            return cand
    if log:
        log("      🖥️  ComfyUI répond mais AUCUN modèle ACE-Step trouvé — téléchargez "
            "ace_step_v1_3.5b.safetensors (dépôt Comfy-Org/ACE-Step_ComfyUI_repackaged, "
            "dossier all_in_one) dans ComfyUI/models/checkpoints puis régénérez")
    return None


def _workflow(tags, seconds, ckpt, seed):
    """Workflow API ComfyUI : ACE-Step → MP3 (structure standard des nœuds intégrés)."""
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "TextEncodeAceStepAudio",
              # An empty lyric text with a high strength can still make ACE-Step
              # invent vocal syllables.  Zero explicitly disables the lyric path.
              "inputs": {"clip": ["1", 1], "tags": tags, "lyrics": "", "lyrics_strength": 0.0}},
        "3": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}},
        "4": {"class_type": "EmptyAceStepLatentAudio",
              "inputs": {"seconds": int(seconds), "batch_size": 1}},
        "5": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": 5.0}},
        "6": {"class_type": "LatentOperationTonemapReinhard", "inputs": {"multiplier": 1.0}},
        "7": {"class_type": "LatentApplyOperationCFG",
              "inputs": {"model": ["5", 0], "operation": ["6", 0]}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["7", 0], "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0], "seed": int(seed), "steps": 50,
                         "cfg": 5.0, "sampler_name": "euler", "scheduler": "simple",
                         "denoise": 1.0}},
        "9": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["8", 0], "vae": ["1", 2]}},
        "10": {"class_type": "SaveAudioMP3",
               "inputs": {"audio": ["9", 0], "filename_prefix": "shortpilot_ace",
                          "quality": "V0"}},
    }


def _download_audio(server, entry, out_path):
    """Récupère le fichier audio depuis /view (image/audio partagent cet endpoint)."""
    name = entry.get("filename")
    if not name:
        return None
    params = urllib.parse.urlencode({"filename": name,
                                     "subfolder": entry.get("subfolder", ""),
                                     "type": entry.get("type", "output")})
    try:
        r = requests.get(server + "/view?" + params, headers=UA, timeout=60)
        if r.status_code != 200 or len(r.content) < 50_000:
            return None
        head = r.content[:4]
        if not (head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
            return None  # pas vraiment un MP3
        with open(out_path, "wb") as f:
            f.write(r.content)
        return out_path
    except Exception:
        return None


def track_for_mood_local(mood, work_dir, total, server="", text="", niche="", log=None):
    """(chemin_mp3_ou_echo, attribution) — None si impossible de générer.
    `total` : durée vidéo + marge (s). La normalisation est faite par l'appelant."""
    from . import aiimg
    from . import webmusic  # normalisation/fondus partagés
    server = (server or "http://127.0.0.1:8188").rstrip("/")
    if not aiimg.comfy_online(server):
        if log:
            log(f"      🖥️  Musique IA locale : ComfyUI éteint ({server}) — serveur non lancé ?")
        return None
    ckpt = _pick_ace_checkpoint(server, log=log)
    if not ckpt:
        return None
    variant = _choose_variant(mood)
    tempo, tempo_scale = secrets.choice(MOOD_TEMPOS.get(mood, MOOD_TEMPOS["chill"]))
    tags = (
        MOOD_TAGS.get(mood, MOOD_TAGS["chill"])
        + ", " + tempo + ", " + variant
        + ", " + _subject_tags(text, niche)
        + ", background music under French narration, " + _INSTRUMENTAL_ONLY
    )
    seconds = max(12, min(MAX_SECONDS, int(round(total + 1)) + 1))
    seed = secrets.randbelow(2_000_000_000)
    if log:
        log(f"      🎼 ACE-Step local : {tempo}, variation « {variant[:32]} » — génération {seconds}s")
    try:
        r = requests.post(server + "/prompt", json={"prompt": _workflow(tags, seconds, ckpt, seed)},
                          headers=UA, timeout=TIMEOUT_API)
        if r.status_code != 200:
            # nœuds trop anciens ou nom de classe inconnu : ComfyUI répond 400
            if log:
                log(f"      🖥️  ComfyUI a refusé le workflow (HTTP {r.status_code}) — "
                    "mettez ComfyUI à jour (nœuds audio ACE-Step requis) — repli")
            return None
        pid = (r.json() or {}).get("prompt_id")
        if not pid:
            return None
    except Exception:
        return None
    os.makedirs(work_dir, exist_ok=True)
    raw = os.path.join(work_dir, f"acemusic_{seed % 99999:05d}.mp3")
    waited = 0
    # une vidéo de 5 min peut demander plusieurs minutes de génération : patience
    while waited < 420:
        time.sleep(2)
        waited += 2
        try:
            h = requests.get(server + f"/history/{pid}", headers=UA, timeout=TIMEOUT_API)
            if h.status_code != 200:
                continue
            entry = (h.json() or {}).get(pid) or {}
            if entry.get("status", {}).get("status_str") == "error":
                if log:
                    log("      🖥️  ACE-Step : génération en erreur côté ComfyUI — repli")
                return None
            outputs = entry.get("outputs") or {}
            done_ok = False
            for node in outputs.values():
                for key in ("audio", "audios", "images", "gifs"):
                    for media in (node.get(key) or []):
                        if _download_audio(server, media, raw):
                            done_ok = True
                            break
                    if done_ok:
                        break
                if done_ok:
                    break
            if done_ok:
                # normalisation + fondus communs (comme les pistes web)
                wav = webmusic._prepare(raw, total,
                                        os.path.splitext(raw)[0] + ".wav",
                                        tempo_scale=tempo_scale)
                if not wav:
                    return None
                if log:
                    log(f"      🎵 musique IA locale : « ACE-Step ({mood or 'chill'}) » "
                        f"— normalisée, {seconds}s")
                return wav, ("musique générée par IA (ACE-Step 3.5B, Apache 2.0, "
                             "génération locale ComfyUI)")
            if entry.get("status", {}).get("completed"):
                return None
        except Exception:
            continue
    if log:
        log("      🖥️  ACE-Step : génération trop longue (abandon > 7 min) — repli")
    return None
