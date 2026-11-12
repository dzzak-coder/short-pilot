# -*- coding: utf-8 -*-
"""ShortPilot — moteur de rendu : scènes PIL + assemblage ffmpeg (zoom cinéma, transitions, mix audio)."""
import json
import os
import shutil
import subprocess
import tempfile
import unicodedata
from contextlib import ExitStack

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPS = 25

FONTS = {
    "anton": os.path.join(BASE, "fonts", "Anton.ttf"),
    "bold": os.path.join(BASE, "fonts", "Montserrat.ttf"),
    "fallback": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
}


def _font(kind, size):
    for key in (kind, "bold", "fallback"):
        p = FONTS.get(key)
        if p and os.path.exists(p):
            try:
                f = ImageFont.truetype(p, size)
                try:
                    # police variable (Montserrat) : forcer un poids très gras
                    f.set_variation_by_axes([800 if key == "bold" else 400])
                except Exception:
                    pass
                return f
            except Exception:
                continue
    return ImageFont.load_default()


THEMES = {
    "neon": {"label": "🟣 Néon", "c1": (76, 29, 149), "c2": (15, 23, 42), "accent": (34, 211, 238)},
    "feu": {"label": "🟠 Feu", "c1": (124, 45, 18), "c2": (23, 10, 6), "accent": (251, 146, 60)},
    "ocean": {"label": "🔵 Océan", "c1": (7, 89, 133), "c2": (2, 6, 23), "accent": (56, 189, 248)},
    "foret": {"label": "🟢 Forêt", "c1": (20, 83, 45), "c2": (3, 18, 10), "accent": (74, 222, 128)},
    "or": {"label": "🟡 Or & Noir", "c1": (28, 24, 8), "c2": (0, 0, 0), "accent": (250, 204, 21)},
    "minimal": {"label": "⚪ Minimal", "c1": (39, 39, 42), "c2": (9, 9, 11), "accent": (244, 244, 245)},
    "rose": {"label": "🌸 Rose", "c1": (131, 24, 67), "c2": (24, 6, 16), "accent": (244, 114, 182)},
}

# Thème « 🧠 Auto » : ambiance lexicale du script (via music.explain_auto) → thème,
# avec orientation de secours par niche.
_MOOD_THEME = {
    "epique": "feu", "energie": "feu", "techno": "neon", "mystere": "neon",
    "drama": "or", "chill": "ocean", "triste": "ocean", "zen": "foret",
    "happy": "rose", "none": "minimal",
}
_NICHE_THEME = {
    "histoire": "or", "argent": "or", "sante": "foret", "motivation": "feu",
    "productivite": "minimal", "tech": "neon", "psychologie": "neon",
    "faits": "ocean", "sujet": "neon",
    "actu": "minimal", "jour": "or", "science": "neon", "mythes": "neon",
}


def _auto_theme(niche, fulltext, log=None):
    """Choisit le thème visuel en écoutant le script (mots-clés d'ambiance)."""
    mood, reason = "", ""
    try:
        from . import music as music_mod
        mood, reason = music_mod.explain_auto(niche, fulltext, "fr")
    except Exception:
        pass
    key = _MOOD_THEME.get(mood) or _NICHE_THEME.get(niche, "neon")
    if log:
        label = " / ".join(x for x in (niche, mood) if x) or "neutre"
        log(f"   🧠 Thème auto : « {THEMES[key]['label']} » (script {label})")
    return THEMES[key]


def _background(w, h, theme, scene_i, nscenes):
    c1 = np.array(theme["c1"], float)
    c2 = np.array(theme["c2"], float)
    g = np.linspace(0, 1, h)[:, None, None]
    img = (c1[None, None, :] * (1 - g) + c2[None, None, :] * g)
    # halo lumineux décalé par scène
    yy, xx = np.mgrid[0:h, 0:w]
    cx = w * (0.3 + 0.4 * ((scene_i % 3) / 2.0))
    cy = h * (0.22 + 0.12 * ((scene_i % 2)))
    r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (w * 0.9)
    glow = np.clip(1 - r, 0, 1) ** 2 * 0.35
    acc = np.array(theme["accent"], float) / 255.0
    img = img + glow[:, :, None] * acc[None, None, :] * 255
    img = np.clip(img, 0, 255).astype(np.uint8)
    im = Image.fromarray(img, "RGB")
    # formes décoratives translucides
    deco = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(deco)
    rng = np.random.default_rng(1234 + scene_i)
    for k in range(6):
        rw = int(rng.integers(w // 6, w // 2))
        x0 = int(rng.integers(-rw // 2, w - rw // 2))
        y0 = int(rng.integers(0, h - rw // 2))
        alpha = int(rng.integers(8, 22))
        d.ellipse([x0, y0, x0 + rw, y0 + rw], fill=(255, 255, 255, alpha))
    deco = deco.filter(ImageFilter.GaussianBlur(60))
    im = Image.alpha_composite(im.convert("RGBA"), deco).convert("RGB")
    # grain léger
    arr = np.asarray(im).astype(np.int16)
    noise = np.random.default_rng(99 + scene_i).integers(-6, 7, arr.shape[:2])[:, :, None]
    im = Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8))
    return im


def _wrap(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if draw.textbbox((0, 0), t, font=font)[2] <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def _draw_centered(draw, lines, font, cx, cy, fill, stroke, lh=1.16, sw=None):
    sizes = [draw.textbbox((0, 0), ln, font=font) for ln in lines]
    heights = [b[3] - b[1] for b in sizes]
    total = sum(heights) + int(font.size * (lh - 1) * (len(lines) - 1))
    y = cy - total / 2
    for ln, b, hgt in zip(lines, sizes, heights):
        wln = b[2] - b[0]
        draw.text((cx - wln / 2 - b[0], y - b[1]), ln, font=font, fill=fill,
                  stroke_width=sw if sw is not None else max(2, font.size // 13), stroke_fill=stroke)
        y += hgt + int(font.size * (lh - 1))


def make_scene(w, h, text, theme, scene_i, nscenes, badge="", watermark="", is_hook=False,
               is_cta=False, bg_img=None, overlay_only=False):
    """Compose une scène. bg_img = photo thématique (banque d'images) ; sinon fond procédural.
    overlay_only=True → calque RGBA transparent (sous-titres/badge/barre seuls) destiné à
    être incrusté PAR-DESSUS un clip vidéo IA animé au montage."""
    if overlay_only:
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    elif bg_img:
        try:
            src = Image.open(bg_img).convert("RGB")
            sw, sh = src.size
            # recadrage « cover » plein cadre
            scale = max(w / sw, h / sh)
            src = src.resize((int(sw * scale) + 2, int(sh * scale) + 2), Image.LANCZOS)
            x0 = (src.width - w) // 2
            y0 = (src.height - h) // 2
            im = src.crop((x0, y0, x0 + w, y0 + h))
            # voile sombre global + dégradé en bas : le texte reste lisible
            base = im.convert("RGBA")
            base = Image.alpha_composite(base, Image.new("RGBA", (w, h), (0, 0, 0, 115)))
            grad = Image.new("L", (1, h))
            for yy in range(h):
                grad.putpixel((0, yy), int(120 * max(0.0, (yy / h - 0.55) / 0.45)))
            dark = Image.new("RGBA", (w, h), (0, 0, 0, 255))
            black = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            base = Image.alpha_composite(base, Image.composite(dark, black, grad.resize((w, h))))
            im = base.convert("RGB")
        except Exception:
            im = _background(w, h, theme, scene_i, nscenes)
    else:
        im = _background(w, h, theme, scene_i, nscenes)
    draw = ImageDraw.Draw(im)
    acc = theme["accent"] + (255,) if len(theme["accent"]) == 3 else theme["accent"]
    acc3 = theme["accent"]

    # Badge niche en haut
    if badge:
        bf = _font("anton", int(h * 0.028))
        bb = draw.textbbox((0, 0), badge.upper(), font=bf)
        bw, bh = bb[2] - bb[0], bb[3] - bb[1]
        pad_x, pad_y = int(w * 0.035), int(h * 0.012)
        x0 = w / 2 - bw / 2 - pad_x
        y0 = h * 0.075
        x1 = w / 2 + bw / 2 + pad_x
        y1 = y0 + bh + 2 * pad_y
        try:
            draw.rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) / 2, outline=acc, width=max(2, w // 400))
        except Exception:
            draw.rectangle([x0, y0, x1, y1], outline=acc, width=3)
        draw.text((w / 2 - bw / 2 - bb[0], y0 + pad_y - bb[1]), badge.upper(), font=bf, fill=(255, 255, 255))

    # Texte principal
    max_w = w * 0.86
    upper = text.upper() if is_hook else text
    size = int(h * (0.085 if is_hook else 0.058))
    while size > 18:
        f = _font("anton" if is_hook else "bold", size)
        lines = _wrap(draw, upper, f, max_w)
        if len(lines) <= (4 if is_hook else 5):
            widest = max(draw.textbbox((0, 0), ln, font=f)[2] for ln in lines)
            if widest <= max_w:
                break
        size -= 3
    fill = (255, 255, 255)
    _draw_centered(draw, lines, f, w / 2, h * (0.47 if not is_hook else 0.45), fill, (0, 0, 0))

    # Surlignage accent sous la première ligne du hook
    if is_hook:
        y = h * 0.45 + ((sum(draw.textbbox((0, 0), ln, font=f)[3] for ln in lines) / 2) + int(h * 0.02))
        bw_ = min(w * 0.5, draw.textbbox((0, 0), lines[0], font=f)[2] * 0.7)
        draw.rounded_rectangle([w / 2 - bw_ / 2, y, w / 2 + bw_ / 2, y + max(6, h // 260)],
                               radius=h // 520, fill=acc3)

    if is_cta:
        af = _font("bold", int(h * 0.02))
        sub = "▼" * 1
        draw.text((w / 2, h * 0.60), "", font=af)

    # Filigrane
    if watermark:
        wf = _font("bold", int(h * 0.019))
        wb = draw.textbbox((0, 0), watermark, font=wf)
        draw.text((w - (wb[2] - wb[0]) - w * 0.04, h * 0.055), watermark, font=wf, fill=(255, 255, 255, ),
                  stroke_width=2, stroke_fill=(0, 0, 0))

    # Barre de progression
    bar_w = w * 0.5
    x0 = w / 2 - bar_w / 2
    y0 = h * 0.925
    prog = (scene_i + 1) / max(1, nscenes)
    try:
        draw.rounded_rectangle([x0, y0, x0 + bar_w, y0 + h * 0.006], radius=h * 0.003, fill=(255, 255, 255, 60))
        draw.rounded_rectangle([x0, y0, x0 + bar_w * prog, y0 + h * 0.006], radius=h * 0.003, fill=acc3)
    except Exception:
        pass
    return im


def _dur_text(t):
    return max(2.6, min(6.0, 2.3 + 0.052 * len(t)))


def _local_visual_anchor(scene, fulltext, niche):
    """Give English-trained local checkpoints a non-negotiable subject anchor.

    Local Stable Diffusion checkpoints often handle a French narration poorly.
    This deliberately small, deterministic layer does not pretend to verify an
    image, but it prevents a known historical subject from being replaced by a
    generic or modern scene before ComfyUI receives the prompt.
    """
    raw = " ".join((scene or "", fulltext or "", niche or ""))
    normalized = "".join(
        c for c in unicodedata.normalize("NFD", raw.lower())
        if unicodedata.category(c) != "Mn"
    )
    astronomy_terms = (
        "planete", "planet", "atmosphere", "astronom", "espace", "space",
        "systeme solaire", "solar system", "orbite", "orbit", "surface",
        "sonde", "probe", "nasa",
    )
    mythology_terms = ("deesse", "goddess", "myth", "aphrodite")
    if "venus" in normalized and any(term in normalized for term in astronomy_terms) and not any(
        term in normalized for term in mythology_terms
    ):
        return (
            "planet Venus in outer space: dense golden clouds, a scientifically coherent atmosphere, stars and sunlight; no human figure and no Roman goddess",
            "human woman, female body, Roman goddess, Venus de Milo, nude, naked, topless, lingerie",
        )
    anchors = (
        (("lagide", "ptolemaique", "ptolemee", "pharaon", "cleopatre", "egypte", "egypt"),
         "ancient Egypt in the Ptolemaic dynasty: Egyptian pharaohs and royal court, linen garments, stone temples, hieroglyphics, desert light",
         "modern car, BMW, automobile, vehicle, highway, contemporary city"),
        (("rome", "romain", "romaine", "cesar", "gladiateur"),
         "ancient Rome: Roman citizens in authentic tunics, marble forums, temples and period architecture",
         "modern car, smartphone, contemporary clothing, modern city"),
        (("viking", "vikings"),
         "Viking Age Scandinavia: Viking people, wooden longships, northern coast and authentic historical clothing",
         "modern car, smartphone, contemporary clothing, modern city"),
        (("espace", "planete", "galaxie", "astronaute"),
         "outer space: the specified planet or spacecraft, stars and nebulae, scientifically coherent space scene",
         "car, highway, terrestrial city unless explicitly required"),
    )
    for terms, anchor, negative in anchors:
        if any(term in normalized for term in terms):
            return anchor, negative
    return (
        "the exact subject and action from the narration below; do not substitute an unrelated subject",
        "unrelated vehicles, product photography, stock photo collage",
    )


def _local_comfy_prompt(scene, fulltext, niche, style, visual_plan="", visual_control=None):
    """Return the concise plan unchanged; narration is never an SDXL prompt."""
    del scene, fulltext, niche, style
    plan = visual_plan
    if not isinstance(plan, str) or not plan.strip() or len(plan) > 900:
        raise ValueError("Plan visuel manquant pour la scène")
    from .visual_planner import validate_required_terms
    validate_required_terms(plan, visual_control or {})
    # Scene human exclusions have one owner: aiimg._conditioning_text().
    negatives = (visual_control or {}).get("negative_terms", [])
    if not isinstance(negatives, list) or any(not isinstance(term, str) for term in negatives):
        raise ValueError("Exclusions visuelles invalides")
    from .visual_constraints import unique_terms
    return plan, ", ".join(unique_terms(negatives))


def _validate_local_comfy_inputs(scenes, visual_plans, visual_controls):
    """Fail before entering render phase if any scene needs re-planning."""
    from .visual_planner import VisualPlanningError, validate_required_terms
    if not isinstance(visual_plans, list) or len(visual_plans) != len(scenes):
        raise ValueError("Plans visuels manquants : planification complète requise avant le rendu")
    if not isinstance(visual_controls, list) or len(visual_controls) != len(scenes):
        raise ValueError("Contrôles visuels manquants : planification complète requise avant le rendu")
    for index, (plan, control) in enumerate(zip(visual_plans, visual_controls), 1):
        if not plan or not isinstance(control, dict):
            detail = control.get("planning_error") if isinstance(control, dict) else ""
            raise ValueError(f"Scène {index} : " + (detail or "Fournissez un plan anglais explicite verrouillé."))
        try:
            validate_required_terms(plan, control)
        except VisualPlanningError as exc:
            raise ValueError(f"Scène {index} : plan ou contrôle visuel obsolète : {exc}") from exc


def _still_motion_filter(scene_index, duration, *, source_w, source_h, width, height):
    """Return a deterministic, varied Ken-Burns camera move for a still image."""
    frames = max(1, int(FPS * max(0.3, float(duration))))
    progress = f"on/{frames}"
    center_x = "iw/2-iw/(2*zoom)"
    center_y = "ih/2-ih/(2*zoom)"
    mode = scene_index % 6
    if mode == 0:  # push-in
        zoom, x, y = f"1+0.10*{progress}", center_x, center_y
    elif mode == 1:  # left-to-right dolly
        zoom, x, y = f"1.07+0.02*{progress}", f"(iw-iw/zoom)*{progress}", center_y
    elif mode == 2:  # pull-out
        zoom, x, y = f"1.10-0.10*{progress}", center_x, center_y
    elif mode == 3:  # right-to-left dolly
        zoom, x, y = f"1.09-0.02*{progress}", f"(iw-iw/zoom)*(1-{progress})", center_y
    elif mode == 4:  # rise
        zoom, x, y = f"1.08+0.02*{progress}", center_x, f"(ih-ih/zoom)*(1-{progress})"
    else:  # descend
        zoom, x, y = f"1.10-0.02*{progress}", center_x, f"(ih-ih/zoom)*{progress}"
    return (
        f"scale={source_w}:{source_h}:flags=bicubic,"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d=1:s={width}x{height}:fps={FPS},"
        "setsar=1,format=yuv420p"
    )


def render_video(job, log=print):
    """Rend une vidéo complète. `job` = dict(script, style, music, voice, quality, watermark, out_path, badge).
    Retourne dict avec chemins video/thumb."""
    from . import music as music_mod
    from . import voice as voice_mod

    script = job["script"]
    scenes = [s.strip() for s in script["scenes"] if s and s.strip()]
    if not scenes:
        raise ValueError("Script vide")
    lang = script.get("language", "fr")
    niche = script.get("niche", "")
    visual_plans = script.get("visual_plans") or []
    from . import content as content_mod
    expected_revision = content_mod.visual_plan_fingerprint(
        scenes, title=script.get("title", ""), niche=niche, language=lang)
    if (not isinstance(visual_plans, list) or len(visual_plans) != len(scenes) or
            (script.get("visual_plans_locked") is not True and
             script.get("visual_plan_fingerprint") != expected_revision)):
        script.update(content_mod.visual_plan_bundle(
            scenes, title=script.get("title", ""), niche=niche, language=lang))
        visual_plans = script["visual_plans"]
    visual_controls = script.get("visual_controls") or []
    if not isinstance(visual_controls, list) or len(visual_controls) != len(scenes):
        from . import content as content_mod
        visual_controls = content_mod.visual_plan_bundle(
            scenes, title=script.get("title", ""), niche=niche, language=lang,
        )["visual_controls"]
    fulltext = " ".join(scenes)  # contexte global (thème auto + musique auto/web)
    style = job.get("style") or "auto"
    if style == "auto" or style not in THEMES:
        theme = _auto_theme(niche, fulltext, log)
    else:
        theme = THEMES[style]
    quality = job.get("quality", "1080")
    w, h = (1080, 1920) if quality == "1080" else (720, 1280)
    badge = job.get("badge", "")
    watermark = job.get("watermark", "").strip()
    visuals = job.get("visuals", "theme")
    local_comfy = visuals in ("comfy", "comfy_quality", "motion")
    comfy_quality = visuals == "comfy_quality"
    montage_motion = visuals == "motion"
    if local_comfy:
        _validate_local_comfy_inputs(scenes, visual_plans, visual_controls)

    work = tempfile.mkdtemp(prefix="sp_", dir=os.path.join(BASE, "tmp"))
    final_video = job["out_path"]
    final_thumb = os.path.splitext(final_video)[0] + "_thumb.jpg"
    final_report = os.path.splitext(final_video)[0] + ".visual.json"
    staged_video = os.path.join(work, "final.mp4")
    staged_thumb = os.path.join(work, "final_thumb.jpg")
    staged_report = os.path.join(work, "final.visual.json")
    published_paths: list[str] = []
    preexisting_paths = {path for path in (final_video, final_thumb, final_report) if os.path.exists(path)}
    resource_scope = ExitStack()
    try:
        if local_comfy:
            from . import aiimg as aiimg_mod, local_resources
            server = job.get("comfyui_url", "")
            if not aiimg_mod.comfy_online(server):
                raise RuntimeError(
                    "ComfyUI local est indisponible : démarrez-le sur http://127.0.0.1:8188 puis relancez."
                )
            # Hold one interprocess reservation across every scene image.  The
            # nested image entry point is reentrant and will not reload models.
            resource_scope.enter_context(local_resources.render_phase(
                comfy_url=(server or "http://127.0.0.1:8188"),
                required_components=(aiimg_mod.QWEN_TURBO_UNET, aiimg_mod.QWEN_TURBO_CLIP, aiimg_mod.QWEN_TURBO_VAE),
            ))
        log("🎙️ Génération de la voix off…" if job.get("voice") else "⏭️  Voix off désactivée")
        from . import content as content_mod
        target = int(job.get("target") or 0) or None
        n = len(scenes)
        voices = None
        if job.get("voice"):
            voice_id = job.get("voice_id")
            # débit ajusté pour se caler sur la durée cible
            # Voix : un peu plus lente que le debit par defaut (negatif = plus lent). A regler ici.
            VOICE_BASE_RATE = -8
            VOICE_MAX_OVERRUN = 1.12   # la video peut depasser la duree cible de 12 % au plus
            VOICE_MAX_SPEEDUP = 10     # jamais plus de +10 % de vitesse
            rate_pct = VOICE_BASE_RATE
            if target:
                est = content_mod.estimate_seconds(scenes)
                allowed = target * VOICE_MAX_OVERRUN
                needed = int((est / allowed - 1) * 100) + (1 if est > allowed else 0)
                rate_pct = max(VOICE_BASE_RATE, min(VOICE_MAX_SPEEDUP, needed))
            log(f"   débit vocal {rate_pct:+d}% (cible ~{target or 'auto'}s)")
            voices = voice_mod.synthesize_scenes(scenes, lang, os.path.join(work, "vx"),
                                                 voice_id=voice_id, rate_pct=rate_pct)
            if voices:
                log(f"   voix : {voice_id or 'défaut'} ({len(voices)} répliques)")
            else:
                log("⚠️  Voix IA indisponible (réseau ?). Rendu musique seule.")
        durs = []
        if voices:
            if target:
                # pauses bornées : si le contenu est plus court que la cible (ex. 5 min demandées
                # sur une petite base), on n'allonge pas la vidéo avec de longs silences
                raw_pad = (target - sum(d for _, d in voices)) / n
                pad = max(0.55, min(2.5, raw_pad))
                if raw_pad > 2.5:
                    approx = sum(d for _, d in voices) + 2.5 * n
                    log(f"⚠️  Le contenu généré (~{target}s visés) est limité par la base de la niche "
                        f"— la vidéo fera ~{approx:.0f}s.")
            else:
                pad = 0.55
            durs = [max(2.2, d + pad) for _, d in voices]
        else:
            durs = [_dur_text(s) for s in scenes]
            if target:
                # calage exact sur la durée cible
                raw = sum(durs)
                durs = [max(1.8, d * target / raw) for d in durs]
                diff = target - sum(durs)
                durs[-1] = max(1.8, durs[-1] + diff)
        total = sum(durs)
        if target:
            log(f"🎯 Durée cible : ~{target}s")
        log(f"🎞️  {n} scènes — durée cible {total:.1f}s — {w}x{h}")

        log("🖼️  Rendu des visuels…")
        if visuals == "comfy":
            log("   🖥️ Images locales directes : ComfyUI / KSampler — sans clé API externe")
        elif visuals == "comfy_quality":
            log("   ✨ Images locales qualité : ComfyUI — upscale, seconde passe, visage et mains")
        elif visuals == "motion":
            log("   🎬 Images animées gratuites : ComfyUI local + mouvements de caméra au montage")
        elif visuals == "images":
            log("   📷 Banque d’images : photos thématiques par scène (repli graphique si hors-ligne)")
        from . import imglib as imglib_mod

        imgs = []
        visual_report = []
        attribution, used_img_urls = [], set()
        rng = np.random.default_rng(7)
        img_dir = os.path.join(work, "img")
        for i, s in enumerate(scenes):
            scene_number = i + 1
            bg_img = None
            if local_comfy:
                local_prompt, local_negative = _local_comfy_prompt(
                    s, fulltext, niche, style, visual_plans[i], visual_controls[i],
                )
                report_entry = {"index": scene_number, "narration": s, "visual_plan": visual_plans[i],
                                "visual_control": visual_controls[i],
                                "human_mode": visual_controls[i].get("human_mode", "auto")}
                bg_img = aiimg_mod.image_for_scene_ai(
                    local_prompt, img_dir,
                    seed=70_000 + scene_number, server=job.get("comfyui_url", ""),
                    ckpt=job.get("comfyui_ckpt", ""), negative_prompt=local_negative,
                    quality_mode=comfy_quality, human_mode=report_entry["human_mode"],
                    visual_control=visual_controls[i], report=report_entry, log=log,
                )
                visual_report.append(report_entry)
                if not bg_img:
                    raise RuntimeError(
                        f"Scène {scene_number} : ComfyUI n’a pas produit d’image. "
                        "Vérifiez le checkpoint puis relancez."
                    )
            elif visuals == "images":
                result = imglib_mod.image_for_scene(
                    s, lang, img_dir, log=log, niche=niche, all_text=fulltext, used=used_img_urls,
                )
                if result:
                    bg_img, attrib, _source = result
                    if attrib:
                        attribution.append(attrib)
                else:
                    log(f"      🎨 scène {scene_number} : aucune photo trouvée — thème graphique")

            im = make_scene(w, h, s, theme, i, n, badge=badge if i == 0 else "",
                            watermark=watermark, is_hook=(i == 0), is_cta=(i == n - 1), bg_img=bg_img)
            if i > 0:
                arr = np.asarray(im).astype(np.int16)
                shift = int(rng.integers(6, 14))
                im = Image.fromarray(np.clip(arr + shift, 0, 255).astype(np.uint8))
            image_path = os.path.join(work, f"scene_{i:02d}.png")
            im.save(image_path)
            imgs.append(image_path)

        log("🎵 Composition de la musique…")
        music_path = None
        music_attrib = ""
        plan = music_mod.background_plan(job.get("music") or "auto", niche, fulltext, lang)
        if plan:
            log(f"   🎵 Ambiance composée : {plan['mood']} — {plan['bpm']} BPM — {plan['mood_reason']}")
            music_path = music_mod.instrumental_background(
                total, path=os.path.join(work, "music.wav"), text=fulltext,
                scene_durations=durs, plan=plan,
            )
            log("      🎻 instrumental local sans voix")

        log("🎬 Montage vidéo (cela peut prendre 1 à 3 minutes)…")
        # ---- Passe 1 : un segment MP4 par scène (faible empreinte mémoire) ----
        scale_w, scale_h = int(w * 1.6), int(h * 1.6)
        segs = []
        for i, p in enumerate(imgs):
            dur = durs[i]
            fades = []
            if i > 0:
                fades.append("fade=t=in:st=0:d=0.35")
            fades.append(f"fade=t=out:st={max(0.0, dur - 0.35):.3f}:d=0.35")
            seg = os.path.join(work, f"seg_{i:02d}.mp4")
            if montage_motion:
                vf = _still_motion_filter(
                    i, dur, source_w=scale_w, source_h=scale_h, width=w, height=h,
                )
            else:
                vf = f"scale={w}:{h}:flags=bicubic,setsar=1,format=yuv420p"
            vf += "," + ",".join(fades)
            c = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                 "-loop", "1", "-t", f"{dur:.3f}", "-i", p,
                 "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast",
                 "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS), seg]
            proc = subprocess.run(c, capture_output=True, text=True, timeout=600)
            if proc.returncode != 0 or not os.path.exists(seg):
                raise RuntimeError(f"ffmpeg (segment {i}) a échoué : " + (proc.stderr or "")[-600:])
            segs.append(seg)
            log(f"   ✂︎ segment {i + 1}/{n} OK" + (" (mouvement 🎬)" if montage_motion else ""))

        # ---- Passe 2 : concaténation sans ré-encodage ----
        lst = os.path.join(work, "concat.txt")
        with open(lst, "w") as f:
            for s_ in segs:
                f.write(f"file '{s_}'\n")
        base = os.path.join(work, "base.mp4")
        proc = subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                               "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", base],
                              capture_output=True, text=True, timeout=300)
        if proc.returncode != 0 or not os.path.exists(base):
            raise RuntimeError("ffmpeg (concat) a échoué : " + (proc.stderr or "")[-600:])

        # ---- Passe 3 : mix audio (musique + voix) + remux (vidéo copiée) ----
        cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", base]
        labels = []
        idx = 1
        if music_path:
            cmd += ["-i", music_path]
            vol = 0.30 if voices else 0.55
            labels.append((f"[{idx}:a]atrim=0:{total + 0.5:.2f},asetpts=PTS-STARTPTS,volume={vol},"
                           f"afade=t=in:st=0:d=0.6,afade=t=out:st={max(0, total - 1.2):.2f}:d=1.2[am]", "[am]"))
            idx += 1
        if voices:
            for vi, (vp, vd) in enumerate(voices):
                cmd += ["-i", vp]
                pre = sum(durs[:vi])
                ms = max(0, int(pre * 1000))
                labels.append((f"[{idx}:a]aresample=44100,adelay={ms}|{ms},"
                               f"apad=whole_dur={total + 0.6:.2f}[av{vi}]", f"[av{vi}]"))
                idx += 1
        fc = [x[0] for x in labels]
        outs = [x[1] for x in labels]
        if len(outs) == 0:
            fc = ["anullsrc=cl=stereo:r=44100,atrim=0:%.2f[aout]" % total]
        elif len(outs) == 1:
            fc.append("".join(outs) + "anull[aout]")
        else:
            fc.append("".join(outs) + f"amix=inputs={len(outs)}:duration=longest:normalize=0,"
                      "alimiter=limit=0.95[aout]")
        cmd += ["-filter_complex", ";".join(fc),
                "-map", "0:v", "-map", "[aout]", "-c:v", "copy",
                "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-ar", "44100",
                "-t", f"{total + 0.2:.2f}", "-movflags", "+faststart", staged_video]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0 or not os.path.exists(staged_video):
            raise RuntimeError("ffmpeg (mix final) a échoué : " + (proc.stderr or "")[-600:])

        # Keep output files invisible until the complete render, including the
        # report and thumbnail, has been assembled successfully.
        Image.open(imgs[0]).resize((w // 2, h // 2)).convert("RGB").save(staged_thumb, quality=88)
        visual_report_path = ""
        if local_comfy:
            with open(staged_report, "w", encoding="utf-8") as report_file:
                json.dump({"scenes": visual_report, "mode": visuals,
                           "seed_policy": "70000 + scene index",
                           "visual_budget": script.get("visual_budget") or {},
                           "visual_anchors": script.get("visual_anchors") or [],
                           "visual_anchor_distribution": (
                               script.get("visual_anchor_distribution") or {})},
                          report_file, ensure_ascii=False, indent=2)
        os.replace(staged_video, final_video)
        published_paths.append(final_video)
        os.replace(staged_thumb, final_thumb)
        published_paths.append(final_thumb)
        if local_comfy:
            os.replace(staged_report, final_report)
            published_paths.append(final_report)
            visual_report_path = final_report
        size_mb = os.path.getsize(final_video) / 1e6
        log(f"✅ Vidéo prête : {os.path.basename(final_video)} ({size_mb:.1f} Mo, {total:.1f}s)")
        # Attribution CC complète (chaque image est créditée — exigé par les licences CC BY)
        return {"video": final_video, "thumb": final_thumb, "duration": total,
                "attribution": " ; ".join(attribution) if attribution else "",
                "music_attrib": music_attrib, "visual_report": visual_report_path}
    except Exception:
        # A failed job must not leave a thumbnail or a partial MP4 in outputs.
        # Existing files are never removed: output names are normally UUID-based,
        # but preserving a prior user asset is safer than assuming that.
        for path in published_paths:
            if path not in preexisting_paths:
                try:
                    os.remove(path)
                except OSError:
                    pass
        raise
    finally:
        resource_scope.close()
        shutil.rmtree(work, ignore_errors=True)
