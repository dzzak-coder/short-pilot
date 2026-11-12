"""Assemble the Khéops campaign into a new dated voice-only build."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import music, render, voice  # noqa: E402

FOLDER = ROOT / "outputs" / "kheops_campaign_2026-11-10"
DENSITY = ROOT / "outputs" / "text_diagnostics" / "kheops_visual_density_2026-11-10.json"
FFMPEG = render.FFMPEG


class AssemblyRefused(RuntimeError):
    pass


def run(command, *, cwd=None, timeout=1200):
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "")[-1200:])
    return result


def atempo_chain(factor):
    factors = []
    remaining = float(factor)
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    factors.append(max(remaining, 0.01))
    return ",".join(f"atempo={value:.6f}" for value in factors)


def srt_time(value):
    milliseconds = round(float(value) * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text):
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def list_windows_sapi_voices():
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "foreach ($v in $s.GetInstalledVoices()) { "
        "  $vi = $v.VoiceInfo; "
        "  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "  Write-Output ($vi.Name + '|' + $vi.Culture.Name) "
        "}; $s.Dispose()"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "Échec d’énumération des voix SAPI")[-800:])
    voices = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        name, culture = line.split("|", 1)
        voices.append({"name": name.strip(), "culture": culture.strip()})
    return voices


def validate_script_voice_language(script_language, voice_culture):
    script_lang = str(script_language or "").strip().lower().replace("_", "-")
    voice_lang = str(voice_culture or "").strip().lower().replace("_", "-")
    if not script_lang:
        raise ValueError("script.language manquant")
    if not voice_lang:
        raise ValueError("culture de voix manquante")
    if script_lang[:2] != voice_lang[:2]:
        raise ValueError(
            f"Langue du script ({script_language}) incompatible avec la culture de la voix ({voice_culture})"
        )
    return True


def select_windows_voice(script_language, preferred_name=None):
    script_lang = str(script_language or "").strip().lower().replace("_", "-")
    if not script_lang.startswith("fr-"):
        raise ValueError(
            f"Culture de script non prise en charge sans repli: '{script_language}'. "
            "Une culture fr-* est exigée."
        )
    voices = list_windows_sapi_voices()
    if preferred_name:
        for item in voices:
            if item["name"].lower() == preferred_name.lower():
                validate_script_voice_language(script_language, item["culture"])
                if not item["culture"].lower().startswith("fr-"):
                    raise ValueError(
                        f"La voix préférée '{item['name']}' a la culture {item['culture']} "
                        f"(fr-* exigée pour language={script_language})"
                    )
                return item
        raise ValueError(f"Voix Windows demandée introuvable: {preferred_name}")
    for item in voices:
        if item["culture"].lower().startswith("fr-"):
            validate_script_voice_language(script_language, item["culture"])
            return item
    raise ValueError(
        f"Aucune voix Windows de culture fr-* disponible pour language={script_language} (aucun repli silencieux)"
    )


def _synthesize_windows_sapi(texts, voice_name, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    source = output_dir / "scenes.json"
    text_blob = json.dumps(list(texts), ensure_ascii=False)
    source.write_text(text_blob, encoding="utf-8")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$ErrorActionPreference = 'Stop'; "
        f"$items = Get-Content -Raw -Encoding UTF8 -LiteralPath {_ps_quote(str(source))} | ConvertFrom-Json; "
        "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$speaker.SelectVoice({_ps_quote(voice_name)}); "
        "for($i=0; $i -lt $items.Count; $i++) { "
        f"  $path = Join-Path {_ps_quote(str(output_dir))} ('voice_{{0:D2}}.wav' -f ($i + 1)); "
        "  $speaker.SetOutputToWaveFile($path); "
        "  $speaker.Speak([string]$items[$i]) "
        "}; $speaker.Dispose()"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "Échec de synthèse SAPI")[-1200:])
    outputs = []
    for index in range(1, len(texts) + 1):
        path = output_dir / f"voice_{index:02d}.wav"
        duration = voice.probe_duration(str(path), FFMPEG)
        if not path.is_file() or duration <= 0:
            raise RuntimeError(f"Voix locale absente ou vide pour la scène {index}")
        outputs.append({"path": str(path), "duration": float(duration), "index": index})
    return outputs, sha256(source), sha256_text(text_blob)


def synthesize_local_windows(scenes, output_dir, script_language, preferred_name=None, rate_configured=0):
    voice_info = select_windows_voice(script_language, preferred_name=preferred_name)
    outputs, sent_file_sha, sent_text_sha = _synthesize_windows_sapi(scenes, voice_info["name"], output_dir)
    return {
        "engine": "windows_sapi_local",
        "voice_name": voice_info["name"],
        "voice_culture": voice_info["culture"],
        "rate_configured": rate_configured,
        "outputs": outputs,
        "text_sent_sha256": sent_text_sha,
        "text_payload_sha256": sent_file_sha,
    }


def images_per_scene(schedule):
    counts = defaultdict(int)
    for item in schedule:
        counts[int(item["scene_index"])] += 1
    return counts


def compute_scene_timings(scene_voice_durations, image_counts):
    """Calcule créneaux/durées par scène à partir de la narration RÉELLE mesurée.

    - slot = clamp(max(durée_voix + 0.3, 3.0*n), 3.0*n, 7.0*n), réparti uniformément.
    - ffmpeg atempo > 1 accélère, < 1 ralentit: on ne ralentit jamais la voix.
      * si slot >= durée_voix: atempo = 1.0, on complète par du silence (apad/atrim).
      * si slot < durée_voix: accélération requise (atempo = durée_voix/slot).
        Le plafond 7 s n'autorise atempo > 1.10 que lorsqu'il impose lui-même la contrainte;
        sinon on refuse si l'adaptation dépasse 1.10.
    - refuse si une image sort de [3, 7] s.
    """
    timings = []
    factors = []
    for scene_index, voice_duration in enumerate(scene_voice_durations, 1):
        n_images = int(image_counts.get(scene_index, 0))
        if n_images <= 0:
            raise AssemblyRefused(f"Aucune image planifiée pour la scène {scene_index}")
        raw_voice = float(voice_duration)
        min_slot = 3.0 * n_images
        cap = 7.0 * n_images
        desired = max(raw_voice + 0.3, min_slot)
        slot = min(desired, cap)
        capped_by_7s = desired > cap + 1e-9

        if slot + 1e-9 >= raw_voice:
            # Voix plus courte (ou égale) que le créneau: vitesse naturelle + silence, jamais de ralentissement.
            factor = 1.0
            slot = max(slot, raw_voice)  # garantir place pour la voix + marge éventuelle déjà incluse
            slot = min(max(slot, min_slot), cap)
            if slot < raw_voice - 1e-9:
                # ne devrait pas arriver vu le test, sécurité
                factor = raw_voice / slot
        else:
            # Créneau plus court que la voix: accélération nécessaire.
            factor = raw_voice / slot if slot > 0 else 0.0
            if capped_by_7s:
                # Le plafond 7 s impose la contrainte: accélération autorisée mais bornée à 1.10.
                if factor > 1.10 + 1e-9:
                    factor = 1.10
                    slot = raw_voice / factor
                    if slot > cap + 1e-9:
                        raise AssemblyRefused(
                            f"Scène {scene_index}: narration trop longue pour {n_images} image(s) "
                            f"au plafond 7 s/image même avec atempo 1.10 "
                            f"(voix={raw_voice:.3f}s, cap={cap:.3f}s)"
                        )
            else:
                # Pas imposé par le plafond 7 s: pas d'accélération > 1.10 par défaut.
                if factor > 1.10 + 1e-9:
                    raise AssemblyRefused(
                        f"Scène {scene_index}: atempo requis {factor:.3f} > 1.10 sans contrainte plafond 7 s "
                        f"(voix={raw_voice:.3f}s, créneau={slot:.3f}s, images={n_images})"
                    )

        per_image = slot / n_images
        if per_image < 3.0 - 1e-9 or per_image > 7.0 + 1e-9:
            raise AssemblyRefused(
                f"Scène {scene_index}: durée image hors plage 3-7 s ({per_image:.3f} s)"
            )
        # facteur appliqué réellement à l'audio (1.0 = vitesse naturelle, jamais < 1.0)
        applied_factor = max(1.0, float(factor))
        if abs(applied_factor - 1.0) < 1e-9:
            applied_factor = 1.0
        factors.append(applied_factor)
        timings.append(
            {
                "scene_index": scene_index,
                "voice_duration_seconds": round(raw_voice, 6),
                "slot_duration_seconds": round(slot, 6),
                "image_count": n_images,
                "image_duration_seconds": round(per_image, 6),
                "atempo_factor": round(applied_factor, 6),
                "capped_by_7s": bool(capped_by_7s),
            }
        )
    return timings


def distribute_scene_images(schedule, timings_by_scene):
    distributed = []
    ordered = sorted(schedule, key=lambda x: (int(x["scene_index"]), int(x["image_index"])))
    for item in ordered:
        scene_index = int(item["scene_index"])
        timing = timings_by_scene[scene_index]
        per_image = float(timing["image_duration_seconds"])
        if per_image < 3.0 or per_image > 7.0:
            raise AssemblyRefused(
                f"Image {item['image_index']} scène {scene_index} hors plage 3-7 s ({per_image:.3f} s)"
            )
        new_item = dict(item)
        new_item["duration_seconds"] = per_image
        distributed.append(new_item)
    return distributed


def load_existing_images(campaign_folder):
    execution_path = next(Path(campaign_folder).glob("execution_report.*.json"))
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    if execution.get("execution_status") != "succeeded" or execution.get("image_count") != 23:
        raise AssemblyRefused("La phase 3 n’est pas acceptée (23 images requises)")
    image_by_index = {}
    for evidence in execution.get("images", []):
        match = re.search(r"campaign_(\d+)_", evidence["comfy_output"]["filename"])
        if not match:
            raise AssemblyRefused("Nom de sortie ComfyUI non attribuable")
        path = Path(campaign_folder) / evidence["image"]
        if not path.is_file():
            raise AssemblyRefused(f"Image existante introuvable: {path}")
        image_by_index[int(match.group(1))] = path
    if sorted(image_by_index) != list(range(1, 24)):
        raise AssemblyRefused("Les 23 images ordonnées ne sont pas disponibles")
    return image_by_index


def build_assembly(
    density_path=DENSITY,
    campaign_folder=FOLDER,
    output_root=None,
    script_language=None,
    preferred_voice=None,
    rate_configured=0,
    scenes_override=None,
    schedule_override=None,
    image_source_folder=None,
    music_text_language=None,
    date_stamp=None,
):
    density = json.loads(Path(density_path).read_text(encoding="utf-8"))
    scenes = scenes_override or list(density["coverage_guided_selection"]["scenes"])
    schedule = schedule_override or list(density["image_schedule"]["images"])
    script_language = script_language or density.get("language") or density.get("script", {}).get("language")
    if not script_language:
        raise ValueError("script.language absent: fournir language (ex. fr-FR) dans la source ou en argument")
    image_by_index = load_existing_images(image_source_folder or campaign_folder)
    counts = images_per_scene(schedule)
    if sum(counts.values()) != 23:
        raise AssemblyRefused(f"image_schedule doit référencer 23 images (trouvé {sum(counts.values())})")

    stamp = date_stamp or datetime.now().strftime("%Y-%m-%d")
    output_root = Path(output_root) if output_root else (ROOT / "outputs" / f"kheops_campaign_voice_{stamp}")
    if output_root.exists():
        raise RuntimeError(f"Le dossier de sortie existe déjà: {output_root}")
    work = output_root / "assembly_work"
    output_root.mkdir(parents=True)
    work.mkdir(parents=True)

    voice_dir = work / "voice_raw"
    voice_result = synthesize_local_windows(
        scenes,
        voice_dir,
        script_language=script_language,
        preferred_name=preferred_voice,
        rate_configured=rate_configured,
    )
    raw_voice_durations = [item["duration"] for item in voice_result["outputs"]]
    timings = compute_scene_timings(raw_voice_durations, counts)
    timings_by_scene = {t["scene_index"]: t for t in timings}
    distributed = distribute_scene_images(schedule, timings_by_scene)

    fitted_voice = []
    scene_factors = [float(t["atempo_factor"]) for t in timings]
    for index, timing in enumerate(timings, 1):
        source = voice_result["outputs"][index - 1]["path"]
        source_duration = float(voice_result["outputs"][index - 1]["duration"])
        slot_duration = float(timing["slot_duration_seconds"])
        factor = float(timing["atempo_factor"])
        target = work / f"voice_{index:02d}.wav"
        if source_duration <= 0:
            raise RuntimeError(f"Durée TTS invalide pour la scène {index}")
        if abs(factor - 1.0) < 1e-6:
            af = f"apad=pad_dur={slot_duration:.3f},atrim=duration={slot_duration:.3f}"
        else:
            af = atempo_chain(factor) + f",apad=pad_dur={slot_duration:.3f},atrim=duration={slot_duration:.3f}"
        run(
            [
                FFMPEG,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                source,
                "-af",
                af,
                "-ar",
                "48000",
                "-ac",
                "2",
                str(target),
            ]
        )
        fitted_voice.append(target)

    voice_list = work / "voice_concat.txt"
    voice_list.write_text("".join(f"file '{p.name}'\n" for p in fitted_voice), encoding="utf-8")
    voice_track = work / "voice.wav"
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            voice_list.name,
            "-c:a",
            "pcm_s16le",
            voice_track.name,
        ],
        cwd=work,
    )

    scene_durations = [float(t["slot_duration_seconds"]) for t in timings]
    total_duration = sum(scene_durations)
    lang_short = (script_language or "fr")[:2].lower()
    music_path = music.instrumental_background(
        total_duration,
        path=str(work / "music.wav"),
        text=" ".join(scenes),
        scene_durations=scene_durations,
        plan=music.background_plan("auto", "sujet", " ".join(scenes), lang_short),
    )
    if not music_path:
        raise RuntimeError("La musique locale n’a pas été produite")

    segments = []
    for item in distributed:
        image = image_by_index[int(item["image_index"])]
        duration = float(item["duration_seconds"])
        segment = work / f"segment_{int(item['image_index']):02d}.mp4"
        vf = render._still_motion_filter(
            int(item["image_index"]) - 1,
            duration,
            source_w=1152,
            source_h=2048,
            width=720,
            height=1280,
        )
        run(
            [
                FFMPEG,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-loop",
                "1",
                "-t",
                f"{duration:.3f}",
                "-i",
                str(image),
                "-vf",
                vf,
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "30",
                str(segment),
            ]
        )
        segments.append(segment)

    video_list = work / "video_concat.txt"
    video_list.write_text("".join(f"file '{p.name}'\n" for p in segments), encoding="utf-8")
    base_video = work / "base.mp4"
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            video_list.name,
            "-c",
            "copy",
            base_video.name,
        ],
        cwd=work,
    )

    cue_lines, cursor = [], 0.0
    for scene, duration in zip(scenes, scene_durations):
        index = len(cue_lines) // 4 + 1
        cue_lines.extend(
            [
                str(index),
                f"{srt_time(cursor)} --> {srt_time(cursor + duration)}",
                str(scene).replace("\n", " "),
                "",
            ]
        )
        cursor += duration
    (work / "subtitles.srt").write_text("\n".join(cue_lines), encoding="utf-8")
    subtitle_filter = (
        "subtitles=subtitles.srt:force_style='FontName=Arial,FontSize=18,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,"
        "Shadow=0,Alignment=2,MarginV=70'"
    )
    final_name = f"kheops_90s_voice_{stamp}.mp4"
    final_path = output_root / final_name
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            base_video.name,
            "-i",
            voice_track.name,
            "-i",
            "music.wav",
            "-filter_complex",
            f"[0:v]{subtitle_filter}[v];[2:a]volume=0.16[m];"
            "[1:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            f"{total_duration:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(final_path),
        ],
        cwd=work,
    )

    probe = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(final_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    probe_text = probe.stderr or ""
    duration_match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", probe_text)
    probed_duration = (
        int(duration_match.group(1)) * 3600
        + int(duration_match.group(2)) * 60
        + float(duration_match.group(3))
        if duration_match
        else 0.0
    )
    per_image_durations = [float(item["duration_seconds"]) for item in distributed]
    all_in_range = all(3.0 - 1e-9 <= d <= 7.0 + 1e-9 for d in per_image_durations)
    if not all_in_range:
        raise AssemblyRefused("Une image a une durée hors plage 3-7 s après distribution")
    factor_stats = {
        "min": round(min(scene_factors), 6) if scene_factors else None,
        "max": round(max(scene_factors), 6) if scene_factors else None,
        "moyenne": round(statistics.fmean(scene_factors), 6) if scene_factors else None,
    }
    measured_narration_seconds = round(sum(raw_voice_durations), 6)
    # Budget visuel dérivé de la narration RÉELLE mesurée (23 images existantes réutilisées).
    images_planned = len(distributed)
    visual_budget = {
        "derived_from": "duree_reelle_narration_mesuree",
        "measured_narration_seconds": measured_narration_seconds,
        "images_planned": images_planned,
        "images_available_reused": 23,
        "min_seconds_per_image": 3.0,
        "max_seconds_per_image": 7.0,
        "feasible_total_min_seconds": round(3.0 * images_planned, 6),
        "feasible_total_max_seconds": round(7.0 * images_planned, 6),
        "computed_total_seconds": round(total_duration, 6),
        "target_reference_seconds": 90.0,
        "within_5_percent_of_90s": abs(total_duration - 90.0) <= 4.5,
        "note": "Durée pilotée par la narration mesurée et les contraintes 3-7 s/image sur 23 images fixes.",
    }
    report = {
        "report_kind": "kheops_campaign_voice_assembly",
        "video": final_name,
        "video_sha256": sha256(final_path),
        "duree_totale": round(total_duration, 6),
        "duree_narration_mesuree": measured_narration_seconds,
        "duree_par_scene": [
            {
                "scene_index": t["scene_index"],
                "duree_secondes": t["slot_duration_seconds"],
                "duree_voix_mesuree": t["voice_duration_seconds"],
            }
            for t in timings
        ],
        "facteur_atempo_par_scene": [
            {
                "scene_index": t["scene_index"],
                "facteur": t["atempo_factor"],
                "min": t["atempo_factor"],
                "max": t["atempo_factor"],
                "moyenne": t["atempo_factor"],
            }
            for t in timings
        ],
        "facteur_atempo_global": factor_stats,
        "duree_finale": round(probed_duration, 6),
        "voix": voice_result["voice_name"],
        "culture": voice_result["voice_culture"],
        "debit_configure": voice_result["rate_configured"],
        "sha256_texte_envoye": voice_result["text_sent_sha256"],
        "tts_engine": f"{voice_result['engine']}:{voice_result['voice_name']}",
        "tts_network_requests": 0,
        "image_count": len(distributed),
        "visual_budget": visual_budget,
        "images_planned": images_planned,
        "resolution": [720, 1280],
        "video_codec": "h264" if "Video: h264" in probe_text else None,
        "audio_codec": "aac" if "Audio: aac" in probe_text else None,
        "accepted": None,
        "acceptance_note": "accepted=null: validation humaine (écoute/visionnage) requise avant acceptation.",
        "scenes": timings,
        "source_density": str(Path(density_path)),
        "source_images": str(Path(image_source_folder or campaign_folder)),
    }
    (output_root / "assembly_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report, output_root, final_path


def _render_excerpt_wav(text, voice_name, out_wav, max_seconds=15.0):
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = out_wav.parent / f"_excerpt_{out_wav.stem}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    outputs, _, _ = _synthesize_windows_sapi([text], voice_name, tmp_dir)
    src = outputs[0]["path"]
    run(
        [
            FFMPEG,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            src,
            "-t",
            f"{float(max_seconds):.3f}",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(out_wav),
        ]
    )
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return out_wav


def find_piper_executable():
    for name in ("piper", "piper.exe", "piper-tts", "piper-tts.exe"):
        found = shutil.which(name)
        if found:
            return found
    candidates = [
        ROOT / "tools" / "piper" / "piper.exe",
        ROOT / "piper" / "piper.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "piper" / "piper.exe",
        Path.home() / ".local" / "bin" / "piper.exe",
        Path.home() / "piper" / "piper.exe",
    ]
    for path in candidates:
        if path and path.is_file():
            return str(path)
    return None


def find_piper_model(model_name="fr_FR-siwis-medium"):
    env = os.environ.get("PIPER_MODEL") or os.environ.get("PIPER_FR_SIWIS_MODEL")
    if env and Path(env).is_file():
        return str(Path(env))
    roots = [
        ROOT / "models" / "piper",
        ROOT / "tools" / "piper" / "models",
        Path.home() / ".local" / "share" / "piper",
        Path.home() / "piper" / "models",
        Path(os.environ.get("LOCALAPPDATA", "")) / "piper",
    ]
    for root in roots:
        if not root or not root.exists():
            continue
        onnx = root / f"{model_name}.onnx"
        if onnx.is_file():
            return str(onnx)
        # recursive light search (shallow)
        try:
            for p in root.rglob(f"{model_name}.onnx"):
                if p.is_file():
                    return str(p)
        except Exception:
            pass
    return None


def synthesize_piper_text(text, out_wav, model_name="fr_FR-siwis-medium", max_seconds=15.0):
    exe = find_piper_executable()
    model = find_piper_model(model_name)
    if not exe or not model:
        return None, {
            "requested_model": model_name,
            "status": "not_produced",
            "reason": "Exécutable Piper ou modèle introuvable localement.",
            "piper_executable": exe,
            "piper_model": model,
            "verification_note": "Nom/modèle vérifié: fr_FR-siwis-medium (rhasspy/piper-voices).",
        }
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    raw_wav = out_wav.with_suffix(".raw.wav")
    # Piper CLI lit stdin et écrit --output_file
    proc = subprocess.run(
        [exe, "--model", model, "--output_file", str(raw_wav)],
        input=str(text),
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=180,
    )
    if proc.returncode != 0 or not raw_wav.is_file():
        err = (proc.stderr or proc.stdout or "Échec Piper")[-800:]
        return None, {
            "requested_model": model_name,
            "status": "not_produced",
            "reason": err,
            "piper_executable": exe,
            "piper_model": model,
            "verification_note": "Nom/modèle vérifié: fr_FR-siwis-medium (rhasspy/piper-voices).",
        }
    run(
        [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw_wav),
         "-t", f"{float(max_seconds):.3f}", "-ar", "48000", "-ac", "2", str(out_wav)]
    )
    try:
        raw_wav.unlink(missing_ok=True)
    except Exception:
        pass
    return str(out_wav), {
        "requested_model": model_name,
        "status": "produced",
        "path": str(out_wav),
        "duration_seconds": round(voice.probe_duration(str(out_wav), FFMPEG), 6),
        "piper_executable": exe,
        "piper_model": model,
        "note": "Piper branché pour extrait A/B (neural, hors ligne) ; non intégré au pipeline tant que non choisi.",
        "verification_note": "Nom/modèle vérifié: fr_FR-siwis-medium (rhasspy/piper-voices).",
    }


def produce_scene1_excerpts(scene_text, out_dir, script_language="fr-FR"):
    """Extrait scène 1 avec la voix définitive (Hortense, fr-FR, SAPI hors ligne)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    hortense = select_windows_voice(script_language, preferred_name="Microsoft Hortense Desktop")
    hortense_wav = out_dir / "scene1_excerpt_hortense_15s.wav"
    _render_excerpt_wav(scene_text, hortense["name"], hortense_wav, 15.0)
    results["hortense"] = {
        "voice": hortense["name"],
        "culture": hortense["culture"],
        "path": str(hortense_wav),
        "duration_seconds": round(voice.probe_duration(str(hortense_wav), FFMPEG), 6),
        "definitive": True,
    }
    return results


def main():
    parser = argparse.ArgumentParser(description="Assemblage voix Khéops (nouveau dossier daté)")
    parser.add_argument("--language", default=None, help="Langue/culture du script, ex. fr-FR")
    parser.add_argument("--voice", default=None, help="Nom exact de voix Windows SAPI (ex. Microsoft Hortense Desktop)")
    parser.add_argument("--density", default=str(DENSITY))
    parser.add_argument("--campaign-folder", default=str(FOLDER))
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--date", dest="date_stamp", default=None)
    parser.add_argument("--excerpts-only", action="store_true", help="Produit les extraits 15s scène 1 (Hortense/Piper)")
    args = parser.parse_args()

    density = json.loads(Path(args.density).read_text(encoding="utf-8"))
    scenes = list(density["coverage_guided_selection"]["scenes"])
    language = args.language or density.get("language") or "fr-FR"

    if args.excerpts_only:
        stamp = args.date_stamp or datetime.now().strftime("%Y-%m-%d")
        out_dir = Path(args.output_root) if args.output_root else (ROOT / "outputs" / f"kheops_voice_excerpts_{stamp}")
        results = produce_scene1_excerpts(scenes[0], out_dir, script_language=language)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    report, output_root, final_path = build_assembly(
        density_path=args.density,
        campaign_folder=args.campaign_folder,
        output_root=args.output_root,
        script_language=language,
        preferred_voice=args.voice,
        rate_configured=0,
        date_stamp=args.date_stamp,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # accepted=null => en attente de validation humaine (écoute/visionnage) ; ce n'est pas un échec de génération.
    return 0 if report.get("accepted") is not False else 2


if __name__ == "__main__":
    raise SystemExit(main())
