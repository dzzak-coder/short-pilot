# -*- coding: utf-8 -*-
"""Local ComfyUI image generation for ShortPilot.

This module deliberately contains one image backend only: the local ComfyUI
workflow with a KSampler node.  Prompt analysis and semantic acceptance live in
separate modules so this transport layer stays small and predictable.
"""
from __future__ import annotations

import os
import hashlib
import re
import time
import urllib.parse
from pathlib import Path

import requests


UA = {"User-Agent": "ShortPilot/2.0 (local ComfyUI image renderer)"}
TIMEOUT_API = 20
MAX_POLL_SECONDS = 240
QUALITY_SOURCE_W = 720
QUALITY_SOURCE_H = 1280
QWEN_TURBO_UNET = "qwen_image_2.1_turbo_int8_convrot.safetensors"
QWEN_TURBO_CLIP = "qwen3vl_8b_w4a8.safetensors"
QWEN_TURBO_VAE = "qwen_image_2.1_vae_bf16.safetensors"
NEG_COMFY = (
    "overlay text, captions, subtitles, watermark, logo, signature, blurry, out of focus, "
    "low quality, jpeg artifacts, oversaturated, collage, split screen, duplicate subject, deformed, "
    "disfigured, bad anatomy, extra limbs, missing limbs, extra fingers, fused fingers, malformed hands, nudity, nsfw"
)
_CHECKPOINT_RE = re.compile(r"^[\w .()\-]{1,180}\.(?:safetensors|ckpt|pt)$", re.IGNORECASE)
HUMAN_MODES = {"required", "hands_only", "forbidden", "auto"}
HUMAN_FORBIDDEN_NEGATIVE = "person, people, human, man, woman, child, face, portrait, hands"
FAST_PROFILE = {"width": 720, "height": 1280, "steps": 6, "cfg": 2.0, "sampler_name": "euler", "scheduler": "sgm_uniform"}
QWEN_TURBO_PROFILE = {"width": 720, "height": 1280, "steps": 8, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple"}
QUALITY_PROFILE = {"width": 720, "height": 1280, "steps": 8, "cfg": 2.0, "sampler_name": "euler", "scheduler": "sgm_uniform", "refine_steps": 5, "refine_denoise": 0.25}


def checkpoint_name(value: str | None) -> str:
    """Allow a filename only, never a URL or a path supplied by a settings file."""
    candidate = str(value or "").strip()
    return candidate if _CHECKPOINT_RE.fullmatch(candidate) else ""


def _save_image(data: bytes, out_path: str) -> str | None:
    if not data or len(data) < 20_000:
        return None
    try:
        with open(out_path, "wb") as target:
            target.write(data)
        from PIL import Image
        image = Image.open(out_path)
        image.verify()
        return out_path
    except Exception:
        try:
            os.remove(out_path)
        except OSError:
            pass
        return None


def _comfy_get(server: str, path: str, timeout: int = TIMEOUT_API):
    try:
        response = requests.get(server.rstrip("/") + path, headers=UA, timeout=timeout)
        return response if response.status_code == 200 else None
    except requests.RequestException:
        return None


def comfy_online(server: str | None) -> bool:
    server = (server or "http://127.0.0.1:8188").rstrip("/")
    try:
        return requests.get(server + "/system_stats", headers=UA, timeout=2.5).status_code == 200
    except requests.RequestException:
        return False


def comfy_pick_checkpoint(server: str | None, timeout: float = TIMEOUT_API) -> str | None:
    """Return Qwen Turbo only; image generation must never fall back to SDXL."""
    info = _comfy_get(server or "", "/object_info", timeout=timeout)
    if info:
        try:
            nodes = info.json()
            unets = ((nodes.get("UNETLoader", {}).get("input", {}).get("required", {})
                      .get("unet_name")) or [[]])[0]
            clips = ((nodes.get("CLIPLoader", {}).get("input", {}).get("required", {})
                      .get("clip_name")) or [[]])[0]
            vaes = ((nodes.get("VAELoader", {}).get("input", {}).get("required", {})
                     .get("vae_name")) or [[]])[0]
            if QWEN_TURBO_UNET in unets and QWEN_TURBO_CLIP in clips and QWEN_TURBO_VAE in vaes:
                return QWEN_TURBO_UNET
        except (AttributeError, ValueError):
            pass
    return None


def _is_qwen_turbo(checkpoint: str) -> bool:
    return checkpoint == QWEN_TURBO_UNET


def _qwen_turbo_workflow(prompt: str, seed: int, w: int, h: int) -> dict:
    """Prompt-only Qwen-Image-2.1 Turbo workflow (the installed 8-step variant)."""
    return {
        "4": {"class_type": "UNETLoader", "inputs": {"unet_name": QWEN_TURBO_UNET, "weight_dtype": "default"}},
        "5": {"class_type": "CLIPLoader", "inputs": {"clip_name": QWEN_TURBO_CLIP, "type": "qwen_image", "device": "default"}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": QWEN_TURBO_VAE}},
        "7": {"class_type": "TextEncodeQwenImage21", "inputs": {"prompt": prompt, "negative_prompt": "", "resolution": max(w, h), "clip": ["5", 0]}},
        "8": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "3": {"class_type": "KSampler", "inputs": {"seed": int(seed), "steps": QWEN_TURBO_PROFILE["steps"], "cfg": QWEN_TURBO_PROFILE["cfg"], "sampler_name": QWEN_TURBO_PROFILE["sampler_name"], "scheduler": QWEN_TURBO_PROFILE["scheduler"], "denoise": 1.0, "model": ["4", 0], "positive": ["7", 0], "negative": ["7", 1], "latent_image": ["8", 0]}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["6", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"filename_prefix": "shortpilot", "images": ["9", 0]}},
    }


def _workflow(prompt: str, ckpt: str, seed: int, w: int = 720, h: int = 1280,
              reference_filename: str | None = None, negative_prompt: str | None = None,
              human_mode: str = "auto") -> dict:
    """Minimal ComfyUI workflow with the project’s preserved KSampler node.

    When a previously approved character frame is supplied, standard ComfyUI
    ``LoadImage``/``VAEEncode`` nodes turn the KSampler into image-to-image.
    This is deliberate: a textual description alone cannot constrain a
    recurring character’s identity across scenes.
    """
    profile = FAST_PROFILE
    positive_prompt, full_negative = _conditioning_text(prompt, negative_prompt, human_mode)
    workflow = {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": positive_prompt, "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {
            "text": full_negative,
            "clip": ["4", 1],
        }},
        "3": {"class_type": "KSampler", "inputs": {
            "seed": int(seed), "steps": profile["steps"], "cfg": profile["cfg"], "sampler_name": profile["sampler_name"],
            "scheduler": profile["scheduler"], "denoise": 1.0, "model": ["4", 0],
            "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0],
        }},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "shortpilot", "images": ["8", 0]}},
    }
    if reference_filename:
        workflow["10"] = {"class_type": "LoadImage", "inputs": {"image": reference_filename}}
        workflow["11"] = {"class_type": "VAEEncode", "inputs": {
            "pixels": ["10", 0], "vae": ["4", 2],
        }}
        # Moderate denoise keeps identity and silhouette while allowing the
        # requested setting/action to change.  KSampler remains the sampler.
        workflow["3"]["inputs"].update({"latent_image": ["11", 0], "denoise": 0.62})
    return workflow


def _quality_workflow(prompt: str, ckpt: str, seed: int,
                      negative_prompt: str | None = None, human_mode: str = "auto") -> dict:
    """High-quality local workflow modelled on the user's proven ComfyUI setup.

    It deliberately remains a separate workflow: an initial SDXL Lightning pass,
    4x upscale followed by a gentle second diffusion pass, then independent face
    and hand detailers.  The simple KSampler workflow above stays available for
    speed and as a safe fallback.
    """
    positive_prompt, full_negative = _conditioning_text(prompt, negative_prompt, human_mode)
    profile = QUALITY_PROFILE
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": positive_prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": full_negative, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage", "inputs": {
            "width": QUALITY_SOURCE_W, "height": QUALITY_SOURCE_H, "batch_size": 1,
        }},
        "5": {"class_type": "KSampler", "inputs": {
            "seed": int(seed), "steps": profile["steps"], "cfg": profile["cfg"], "sampler_name": profile["sampler_name"],
            "scheduler": profile["scheduler"], "denoise": 1.0, "model": ["1", 0],
            "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["4", 0],
        }},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "16": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "4x-UltraSharp.pth"}},
        "13": {"class_type": "ImageUpscaleWithModel", "inputs": {
            "upscale_model": ["16", 0], "image": ["6", 0],
        }},
        "28": {"class_type": "ImageScaleBy", "inputs": {
            "upscale_method": "lanczos", "scale_by": 0.5, "image": ["13", 0],
        }},
        "26": {"class_type": "VAEEncodeTiled", "inputs": {
            "tile_size": 1024, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8,
            "pixels": ["28", 0], "vae": ["1", 2],
        }},
        "7": {"class_type": "KSampler", "inputs": {
            "seed": int(seed) + 1, "steps": profile["refine_steps"], "cfg": 1.8, "sampler_name": profile["sampler_name"],
            "scheduler": profile["scheduler"], "denoise": profile["refine_denoise"], "model": ["1", 0],
            "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["26", 0],
        }},
        "25": {"class_type": "VAEDecodeTiled", "inputs": {
            "tile_size": 1024, "overlap": 64, "temporal_size": 64, "temporal_overlap": 8,
            "samples": ["7", 0], "vae": ["1", 2],
        }},
        "12": {"class_type": "SaveImage", "inputs": {"filename_prefix": "shortpilot", "images": ["25", 0]}},
    }
    # The detector is the evidence gate: no detected face means no inpaint.
    # Never place a detailer in object/landscape workflows.
    if human_mode == "required":
        workflow.update({"9": {"class_type": "UltralyticsDetectorProvider", "inputs": {"model_name": "bbox/face_yolov8m.pt"}},
        "22": {"class_type": "FaceDetailer", "inputs": {
            "guide_size": 512, "guide_size_for": True, "max_size": 1024, "seed": int(seed) + 2,
            "steps": 5, "cfg": 1.5, "sampler_name": "euler", "scheduler": "sgm_uniform",
            "denoise": 0.25, "feather": 5, "noise_mask": True, "force_inpaint": True,
            "bbox_threshold": 0.5, "bbox_dilation": 10, "bbox_crop_factor": 3.0,
            "sam_detection_hint": "center-1", "sam_dilation": 0, "sam_threshold": 0.93,
            "sam_bbox_expansion": 0, "sam_mask_hint_threshold": 0.7,
            "sam_mask_hint_use_negative": "False", "drop_size": 10, "wildcard": "", "cycle": 1,
            "inpaint_model": False, "noise_mask_feather": 20, "tiled_encode": True,
            "tiled_decode": True, "image": ["25", 0], "model": ["1", 0], "clip": ["1", 1],
            "vae": ["1", 2], "positive": ["2", 0], "negative": ["3", 0], "bbox_detector": ["9", 0],
        }}})
        workflow["12"]["inputs"]["images"] = ["22", 0]
    return workflow


def _conditioning_text(prompt: str, negative_prompt: str | None = None,
                       human_mode: str = "auto") -> tuple[str, str]:
    """Add only structured scene controls; never infer people from prompt words."""
    mode = human_mode if human_mode in HUMAN_MODES else "auto"
    scene_negative = HUMAN_FORBIDDEN_NEGATIVE if mode == "forbidden" else ""
    # Give explicit scene counterexamples the first CLIP token positions.
    # Long universal anatomy boilerplate must not precede object-state and
    # unrequested-prop constraints, particularly in non-human scenes.
    negatives = ", ".join(part for part in (negative_prompt or "", scene_negative, NEG_COMFY) if part)
    seen, unique = set(), []
    for term in negatives.split(","):
        term = term.strip()
        key = " ".join(term.casefold().split())
        if key and key not in seen:
            seen.add(key)
            unique.append(term)
    return prompt, ", ".join(unique)


def build_comfy_payload(visual_prompt: str, negative_prompt: str, checkpoint: str, width: int,
                        height: int, seed: int, steps: int | None = None, cfg: float | None = None,
                        sampler_name: str = "euler", scheduler: str = "sgm_uniform",
                        quality_mode: bool = False, filename_prefix: str = "shortpilot",
                        human_mode: str = "auto", visual_control: dict | None = None) -> dict:
    """One text-only builder; profiles and the separate quality graph are preserved."""
    del steps, cfg, sampler_name, scheduler
    if visual_control is not None:
        from .visual_planner import validate_required_terms
        validate_required_terms(visual_prompt, visual_control)
        from .visual_constraints import unique_terms
        negative_prompt = ", ".join(unique_terms([negative_prompt or "", *visual_control.get("negative_terms", [])]))
        human_mode = visual_control.get("human_mode", human_mode)
    if _is_qwen_turbo(checkpoint):
        if quality_mode:
            raise ValueError("Le mode qualité SDXL n’est pas compatible avec Qwen Turbo")
        return _qwen_turbo_workflow(visual_prompt, seed, width, height)
    if quality_mode:
        workflow = _quality_workflow(visual_prompt, checkpoint, seed, negative_prompt, human_mode)
        workflow["12"]["inputs"]["filename_prefix"] = filename_prefix
    else:
        workflow = _workflow(visual_prompt, checkpoint, seed, width, height, None, negative_prompt, human_mode)
        workflow["9"]["inputs"]["filename_prefix"] = filename_prefix
    return workflow


def _uploaded_reference_name(server: str, image_path: str, log=None) -> str | None:
    """Upload an approved local frame to ComfyUI's input folder safely."""
    source = Path(image_path)
    if not source.is_file():
        return None
    try:
        with source.open("rb") as image_file:
            response = requests.post(
                server + "/upload/image",
                files={"image": (source.name, image_file, "image/png")},
                data={"overwrite": "true"}, headers=UA, timeout=TIMEOUT_API,
            )
        payload = response.json() if response.status_code == 200 else {}
    except (OSError, requests.RequestException, ValueError):
        payload = {}
    name = str(payload.get("name") or "").replace("\\", "/").strip("/")
    subfolder = str(payload.get("subfolder") or "").replace("\\", "/").strip("/")
    # ComfyUI's LoadImage accepts a relative input filename.  Reject any
    # unexpected traversal returned by a broken/modified server.
    parts = [part for part in (subfolder + "/" + name).split("/") if part]
    if not name or any(part in (".", "..") for part in parts):
        if log:
            log("      🖥️ ComfyUI n’a pas accepté l’image de référence du personnage.")
        return None
    return "/".join(parts)


def _history_error(entry: dict) -> str:
    messages = ((entry.get("status") or {}).get("messages") or [])
    for message in reversed(messages):
        if isinstance(message, (list, tuple)):
            text = " ".join(str(part) for part in message[1:] if part)
        else:
            text = str(message or "")
        text = " ".join(text.split())
        if text and "execution_start" not in text.lower():
            return text[:220]
    return "erreur sans détail retourné"


def gen_comfyui(prompt: str, out_dir: str, *, server: str = "http://127.0.0.1:8188",
                ckpt: str | None = None, seed: int | None = None, width: int = 720,
                height: int = 1280, reference_image: str | None = None,
                negative_prompt: str | None = None, quality_mode: bool = False,
                human_mode: str = "auto", visual_control: dict | None = None,
                report: dict | None = None,
                log=None) -> str | None:
    """Generate one still through local ComfyUI/KSampler, returning its validated path."""
    from .visual_planner import validate_required_terms
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 900:
        raise ValueError("Plan visuel manquant ou trop long")
    if report is not None and report.get("visual_plan", prompt) != prompt:
        raise ValueError("Le plan visuel diffère du prompt positif")
    if visual_control is not None:
        validate_required_terms(prompt, visual_control)
        human_mode = visual_control.get("human_mode", human_mode)
    server = (server or "http://127.0.0.1:8188").rstrip("/")
    seed = int(seed if seed is not None else time.time()) % 2_000_000_000
    requested_ckpt = checkpoint_name(ckpt)
    if requested_ckpt and not _is_qwen_turbo(requested_ckpt):
        raise ValueError("Le backend image ShortPilot est exclusivement Qwen-Image-2.1 Turbo; aucun repli SDXL n'est autorisé")
    ckpt = requested_ckpt or comfy_pick_checkpoint(server)
    if not _is_qwen_turbo(ckpt or ""):
        if log:
            log("      🖥️ ComfyUI ne possède pas les trois composants Qwen-Image-2.1 Turbo requis.")
        return None
    if not quality_mode and (width, height) != (720, 1280):
        # Strict visual modes are portrait 9:16 end-to-end.  Avoid a post-QA
        # crop which could discard a required object near an edge.
        if log:
            log("      🖥️ Dimensions strictes invalides : 720x1280 est requis.")
        return None
    reference_filename = None
    if reference_image:
        reference_filename = _uploaded_reference_name(server, reference_image, log=log)
        if not reference_filename:
            # Do not silently degrade identity conditioning to prompt-only.
            return None
    if quality_mode and reference_filename:
        if log:
            log("      🖥️ Mode qualité ComfyUI : la référence personnage n’est pas encore compatible.")
        return None
    profile = QWEN_TURBO_PROFILE
    workflow = build_comfy_payload(prompt, negative_prompt or "", ckpt, width, height, seed,
                                   quality_mode=quality_mode, human_mode=human_mode, visual_control=visual_control)
    if reference_filename and not quality_mode and not _is_qwen_turbo(ckpt):
        workflow["10"] = {"class_type": "LoadImage", "inputs": {"image": reference_filename}}
        workflow["11"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["4", 2]}}
        workflow["3"]["inputs"].update({"latent_image": ["11", 0], "denoise": 0.62})
    if report is not None:
        qwen = _is_qwen_turbo(ckpt)
        positive_node = "7" if qwen else ("6" if not quality_mode else "2")
        negative_node = "7" if qwen else ("7" if not quality_mode else "3")
        positive_field = "prompt" if qwen else "text"
        negative_field = "negative_prompt" if qwen else "text"
        report.update({"positive_prompt": workflow[positive_node]["inputs"][positive_field],
                       "negative_prompt": "" if qwen else workflow[negative_node]["inputs"][negative_field],
                       "seed": seed, "checkpoint": ckpt, "image_backend": "Qwen-Image-2.1 Turbo", "width": width, "height": height,
                       "steps": profile["steps"], "cfg": profile["cfg"], "sampler_name": profile["sampler_name"],
                       "scheduler": profile["scheduler"], "human_mode": human_mode, "attempts": 1, "status": "submitted",
                       "positive_prompt_verified": False, "negative_prompt_active": False, "negative_prompt_verified": None,
                       "executed_positive_prompt": None, "executed_negative_prompt": None})
        if visual_control is not None:
            report["required_terms"] = visual_control.get("required_terms", [])
            report["visual_control"] = visual_control
        report["visual_plan"] = prompt
    try:
        response = requests.post(server + "/prompt", json={"prompt": workflow},
                                 headers=UA, timeout=TIMEOUT_API)
        if response.status_code != 200:
            if log:
                detail = " ".join((response.text or "").split())[:220]
                suffix = f" : {detail}" if detail else ""
                log(f"      🖥️ ComfyUI a refusé le workflow (HTTP {response.status_code}){suffix}")
            return None
        prompt_id = (response.json() or {}).get("prompt_id")
    except (requests.RequestException, ValueError):
        if log:
            log("      🖥️ ComfyUI est injoignable pendant la génération.")
        return None
    if not prompt_id:
        if log:
            log("      🖥️ ComfyUI n’a pas retourné d’identifiant de tâche.")
        return None
    if report is not None:
        report["prompt_id"] = prompt_id

    os.makedirs(out_dir, exist_ok=True)
    loops = max(1, MAX_POLL_SECONDS // 2)
    for _ in range(loops):
        time.sleep(2)
        history = _comfy_get(server, f"/history/{prompt_id}")
        if not history:
            continue
        try:
            entry = (history.json() or {}).get(prompt_id) or {}
        except ValueError:
            continue
        if (entry.get("status") or {}).get("status_str") == "error":
            if log:
                log(f"      🖥️ ComfyUI a échoué : {_history_error(entry)}")
            return None
        if entry.get("outputs"):
            # /history includes the workflow actually accepted for this prompt_id.
            # Follow the sampler's positive link, not a hard-coded CLIP label.
            history_prompt = entry.get("prompt") or []
            executed = history_prompt[2] if len(history_prompt) > 2 else None
            qwen = _is_qwen_turbo(ckpt)
            sampler_id = "5" if quality_mode else "3"
            positive_root_id = workflow[sampler_id]["inputs"]["positive"][0]
            clip_id = "7" if qwen else ("2" if quality_mode else "6")
            if not isinstance(executed, dict) or executed != workflow:
                if log:
                    log("ComfyUI : le workflow exécuté ne correspond pas au contrat soumis.")
                return None
            if report is not None:
                negative_clip_id = "7" if qwen else ("3" if quality_mode else "7")
                prompt_field = "prompt" if qwen else "text"
                negative_field = "negative_prompt" if qwen else "text"
                report.update({"positive_node_id": clip_id, "executed_positive_prompt": executed[clip_id]["inputs"][prompt_field],
                               "negative_node_id": negative_clip_id,
                               "executed_negative_prompt": executed[negative_clip_id]["inputs"][negative_field],
                               "negative_prompt_active": False,
                               "negative_prompt_verified": None,
                               "positive_root_node_id": positive_root_id,
                               "executed_clip_prompts": {key: node["inputs"].get(prompt_field, node["inputs"].get("text")) for key, node in executed.items()
                                                         if node["class_type"] in {"CLIPTextEncode", "TextEncodeQwenImage21"}},
                               "positive_prompt_verified": True, "workflow": executed,
                               "workflow_sha256": hashlib.sha256(__import__("json").dumps(executed, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()})
        for node in (entry.get("outputs") or {}).values():
            for image in (node.get("images") or []):
                filename = image.get("filename")
                if not filename:
                    continue
                params = urllib.parse.urlencode({
                    "filename": filename, "subfolder": image.get("subfolder", ""),
                    "type": image.get("type", "output"),
                })
                try:
                    raw = requests.get(server + "/view?" + params, headers=UA, timeout=TIMEOUT_API)
                except requests.RequestException:
                    continue
                path = _save_image(
                    raw.content if raw.status_code == 200 else b"",
                    os.path.join(out_dir, f"comfy_{seed}.png"),
                )
                if path:
                    if report is not None:
                        from PIL import Image
                        with Image.open(path) as result_image:
                            size = list(result_image.size)
                        report.update({"image": os.path.basename(path), "status": "success", "image_dimensions": size,
                                       "image_sha256": hashlib.sha256(raw.content).hexdigest(),
                                       "comfy_output": image})
                    return path
        if (entry.get("status") or {}).get("completed"):
            if log:
                log("      🖥️ ComfyUI a terminé sans image utilisable.")
            return None
    if log:
        log("      🖥️ ComfyUI dépasse le délai d’image de 4 minutes.")
    return None


def image_for_scene_ai(prompt: str, out_dir: str, *, seed: int | None = None,
                       server: str | None = None, ckpt: str | None = None,
                       reference_image: str | None = None, negative_prompt: str | None = None,
                       quality_mode: bool = False, human_mode: str = "auto", visual_control: dict | None = None,
                       report: dict | None = None,
                       log=None) -> str | None:
    """The sole image entry point: an already structured prompt → local KSampler."""
    from . import local_resources
    resolved_server = (server or "http://127.0.0.1:8188").rstrip("/")
    components = (QWEN_TURBO_UNET, QWEN_TURBO_CLIP, QWEN_TURBO_VAE)
    with local_resources.render_phase(comfy_url=resolved_server, required_components=components):
        return _image_for_scene_ai_locked(
            prompt, out_dir, seed=seed, server=resolved_server, ckpt=ckpt,
            reference_image=reference_image, negative_prompt=negative_prompt,
            quality_mode=quality_mode, human_mode=human_mode, visual_control=visual_control,
            report=report, log=log,
        )


def _image_for_scene_ai_locked(prompt: str, out_dir: str, *, seed: int | None = None,
                               server: str | None = None, ckpt: str | None = None,
                               reference_image: str | None = None, negative_prompt: str | None = None,
                               quality_mode: bool = False, human_mode: str = "auto", visual_control: dict | None = None,
                               report: dict | None = None,
                               log=None) -> str | None:
    if not comfy_online(server):
        if log:
            log("      🖥️ ComfyUI local est introuvable.")
        return None
    path = gen_comfyui(
        prompt, out_dir, server=server or "", ckpt=ckpt, seed=seed,
        width=720, height=1280, reference_image=reference_image,
        negative_prompt=negative_prompt, quality_mode=quality_mode, human_mode=human_mode,
        visual_control=visual_control, report=report, log=log,
    )
    if path and log:
        conditioned = " avec référence personnage" if reference_image else ""
        label = "qualité" if quality_mode else "KSampler"
        log(f"      🖼️ image locale ComfyUI/{label}{conditioned} générée.")
    return path


def comfy_status(server: str | None, timeout: float = 2.5) -> dict:
    """Fast, safe status used by the browser; it never exposes model paths."""
    server = (server or "http://127.0.0.1:8188").rstrip("/")
    try:
        online = requests.get(server + "/system_stats", headers=UA, timeout=timeout).status_code == 200
    except requests.RequestException:
        online = False
    return {"online": online, "checkpoint": comfy_pick_checkpoint(server, timeout=timeout) if online else None}
