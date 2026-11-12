"""Exclusive orchestration for local Ollama and ComfyUI model memory.

The services themselves remain running.  This module only serializes ShortPilot
work that may load a heavy local model, and releases the other service's model
memory before the work starts.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import time

import requests


DEFAULT_COMFY_URL = "http://127.0.0.1:8188"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT = 30.0
_LOCK_PATH = Path(tempfile.gettempdir()) / "shortpilot-local-model-resource.lock"
_LOG = logging.getLogger(__name__)
_THREAD_GATE = threading.Condition(threading.RLock())
_OWNER = None
_ACTIVE_PHASE = None
_DEPTH = 0
_HANDLE = None
_OWNED_OLLAMA_MODELS: set[str] = set()


class LocalResourceError(ValueError):
    """A local model service cannot safely enter the requested phase."""


class LocalResourceBusyError(LocalResourceError):
    """Another ShortPilot process owns the shared model-memory lock."""


@dataclass(frozen=True)
class ResourceSnapshot:
    ram_free: int | None = None
    vram_free: int | None = None


def _owner_token():
    return os.getpid(), threading.get_ident()


def _lock_metadata():
    try:
        return _LOCK_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _try_file_lock(handle) -> bool:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    # The desktop target is Windows.  Keeping the fallback explicit prevents a
    # silent non-interprocess lock if tests run on another platform.
    import fcntl
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock_file(handle):
    handle.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def resource_lock(phase: str, *, timeout: float = DEFAULT_TIMEOUT):
    """Acquire the Windows-safe, reentrant, interprocess ShortPilot lock.

    The yielded boolean is true only for the outermost acquisition by this
    thread.  Nested ShortPilot calls therefore do not deadlock or repeat model
    handoff operations.
    """
    global _OWNER, _ACTIVE_PHASE, _DEPTH, _HANDLE
    if phase not in {"text", "render"}:
        raise ValueError("Phase de ressource locale inconnue")
    token = _owner_token()
    deadline = time.monotonic() + max(0.0, float(timeout))
    with _THREAD_GATE:
        while _OWNER is not None and _OWNER != token:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LocalResourceBusyError("Ressource locale déjà utilisée par une autre tâche ShortPilot")
            _THREAD_GATE.wait(remaining)
        if _OWNER == token:
            if _ACTIVE_PHASE != phase:
                raise LocalResourceError(
                    f"Transition locale imbriquée interdite : {_ACTIVE_PHASE} → {phase}; "
                    "terminez la phase active avant de changer de modèle"
                )
            _DEPTH += 1
            outer = False
        else:
            _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
            handle = open(_LOCK_PATH, "a+b")
            if not handle.tell():
                handle.write(b" ")
                handle.flush()
            while True:
                if _OWNER is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        handle.close()
                        raise LocalResourceBusyError("Ressource locale déjà utilisée par une autre tâche ShortPilot")
                    _THREAD_GATE.wait(remaining)
                    continue
                if _try_file_lock(handle):
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    handle.close()
                    detail = _lock_metadata()
                    suffix = f" ({detail})" if detail else ""
                    raise LocalResourceBusyError("Ressource locale déjà utilisée par une autre tâche ShortPilot" + suffix)
                _THREAD_GATE.release()
                try:
                    time.sleep(min(0.05, remaining))
                finally:
                    _THREAD_GATE.acquire()
            handle.seek(0)
            handle.truncate()
            handle.write(json.dumps({"pid": token[0], "thread": token[1], "phase": phase, "at": time.time()}).encode("utf-8"))
            handle.flush()
            _OWNER, _ACTIVE_PHASE, _DEPTH, _HANDLE, outer = token, phase, 1, handle, True
    try:
        yield outer
    finally:
        with _THREAD_GATE:
            _DEPTH -= 1
            if _DEPTH == 0:
                handle, _HANDLE, _OWNER, _ACTIVE_PHASE = _HANDLE, None, None, None
                try:
                    _unlock_file(handle)
                finally:
                    handle.close()
                    _THREAD_GATE.notify_all()


def _json(method: str, url: str, *, payload=None, timeout: float = 5.0):
    try:
        response = requests.request(method, url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise LocalResourceError(f"Service local inaccessible : {url} ({type(exc).__name__})") from exc
    if response.status_code != 200:
        detail = " ".join((response.text or "").split())[:240]
        raise LocalResourceError(f"Service local a refusé {url} (HTTP {response.status_code}{': ' + detail if detail else ''})")
    try:
        return response.json()
    except ValueError as exc:
        raise LocalResourceError(f"Réponse JSON invalide de {url}") from exc


def _connection_refused(exc: requests.RequestException) -> bool:
    text = str(exc).casefold()
    return "actively refused" in text or "connection refused" in text or "winerror 10061" in text


def _comfy_snapshot(server: str) -> ResourceSnapshot | None:
    try:
        response = requests.get(server.rstrip("/") + "/system_stats", timeout=5)
    except requests.RequestException as exc:
        if _connection_refused(exc):
            return None
        raise LocalResourceError(f"État ComfyUI inconnu : /system_stats ({type(exc).__name__})") from exc
    if response.status_code != 200:
        detail = " ".join((response.text or "").split())[:240]
        raise LocalResourceError(f"État ComfyUI invalide : /system_stats HTTP {response.status_code}{': ' + detail if detail else ''}")
    try:
        data = response.json()
        system = data.get("system") or {}
        devices = data.get("devices") or []
        vram = devices[0].get("vram_free") if devices else None
        snapshot = ResourceSnapshot(system.get("ram_free"), vram)
        _LOG.info("Ressources locales : RAM libre=%s, VRAM libre=%s", snapshot.ram_free, snapshot.vram_free)
        return snapshot
    except (AttributeError, ValueError, IndexError):
        raise LocalResourceError("/system_stats ComfyUI est invalide")


def _free_comfy(server: str):
    url = server.rstrip("/") + "/free"
    try:
        response = requests.post(url, json={"unload_models": True, "free_memory": True}, timeout=20)
    except requests.RequestException as exc:
        raise LocalResourceError(f"/free ComfyUI a échoué ({type(exc).__name__})") from exc
    if response.status_code != 200:
        detail = " ".join((response.text or "").split())[:240]
        raise LocalResourceError(f"/free ComfyUI a refusé la libération (HTTP {response.status_code}{': ' + detail if detail else ''})")


def _ollama_models(ollama_url: str) -> list[str]:
    _LOG.info("Ressource locale : GET /api/ps")
    data = _json("GET", ollama_url.rstrip("/") + "/api/ps")
    return [str(item.get("name") or item.get("model") or "") for item in (data.get("models") or []) if isinstance(item, dict)]


def _unload_owned_ollama(model: str, ollama_url: str):
    if model not in _OWNED_OLLAMA_MODELS:
        return
    if model not in _ollama_models(ollama_url):
        _OWNED_OLLAMA_MODELS.discard(model)
        return
    _LOG.info("Ressource locale : déchargement Ollama ciblé de %s", model)
    _json("POST", ollama_url.rstrip("/") + "/api/generate", payload={"model": model, "prompt": "", "keep_alive": 0, "stream": False}, timeout=20)
    if model in _ollama_models(ollama_url):
        raise LocalResourceError(f"Ollama conserve encore le modèle ShortPilot {model}")
    _OWNED_OLLAMA_MODELS.discard(model)


def _prepare_text(comfy_url: str, ollama_url: str, model: str | None):
    snapshot = _comfy_snapshot(comfy_url)
    if snapshot is not None:
        _LOG.info("Ressource locale : GET /queue avant phase texte")
        queue = _json("GET", comfy_url.rstrip("/") + "/queue")
        if queue.get("queue_running") or queue.get("queue_pending"):
            raise LocalResourceError("ComfyUI exécute ou attend un rendu externe ; mémoire non déchargée")
        _LOG.info("Ressource locale : POST /free avant Ollama")
        _free_comfy(comfy_url)
        # A 200 only acknowledges the request.  Record the post-free state
        # without asserting an arbitrary amount of released memory.
        if _comfy_snapshot(comfy_url) is None:
            raise LocalResourceError("ComfyUI est devenu indisponible après /free ; mémoire non vérifiable")
    active = [name for name in _ollama_models(ollama_url) if name]
    external = [name for name in active if name not in _OWNED_OLLAMA_MODELS]
    if external:
        raise LocalResourceError("Ollama utilise déjà un modèle externe : " + ", ".join(external))
    if model:
        _OWNED_OLLAMA_MODELS.add(model)


def _prepare_render(comfy_url: str, ollama_url: str, components: tuple[str, str, str] | None):
    active = [name for name in _ollama_models(ollama_url) if name]
    for model in list(active):
        if model in _OWNED_OLLAMA_MODELS:
            _unload_owned_ollama(model, ollama_url)
    active = [name for name in _ollama_models(ollama_url) if name]
    if active:
        raise LocalResourceError("Ollama conserve un modèle actif ; aucun POST ComfyUI autorisé : " + ", ".join(active))
    snapshot = _comfy_snapshot(comfy_url)
    if snapshot is None:
        raise LocalResourceError("ComfyUI local est indisponible et aucun lanceur ShortPilot géré n'est configuré")
    if components:
        info = _json("GET", comfy_url.rstrip("/") + "/object_info", timeout=20)
        unet, clip, vae = components
        try:
            unets = info["UNETLoader"]["input"]["required"]["unet_name"][0]
            clips = info["CLIPLoader"]["input"]["required"]["clip_name"][0]
            vaes = info["VAELoader"]["input"]["required"]["vae_name"][0]
        except (KeyError, TypeError, IndexError) as exc:
            raise LocalResourceError("/object_info ComfyUI incomplet") from exc
        missing = [name for name, values in ((unet, unets), (clip, clips), (vae, vaes)) if name not in values]
        if missing:
            raise LocalResourceError("Composants Qwen-Image indisponibles : " + ", ".join(missing))


@contextmanager
def text_phase(*, model: str | None = None, comfy_url: str = DEFAULT_COMFY_URL,
               ollama_url: str = DEFAULT_OLLAMA_URL, timeout: float = DEFAULT_TIMEOUT):
    """Reserve the shared resource for all nested local text/planning calls."""
    with resource_lock("text", timeout=timeout) as outer:
        if outer:
            _prepare_text(comfy_url, ollama_url, model)
        body_error = None
        try:
            yield
        except BaseException as exc:
            body_error = exc
            raise
        finally:
            if outer and model:
                try:
                    _unload_owned_ollama(model, ollama_url)
                except LocalResourceError as cleanup_error:
                    if body_error is not None:
                        raise LocalResourceError(
                            f"Erreur de phase texte : {body_error}; échec de déchargement Ollama : {cleanup_error}"
                        ) from cleanup_error
                    raise


@contextmanager
def render_phase(*, comfy_url: str = DEFAULT_COMFY_URL, ollama_url: str = DEFAULT_OLLAMA_URL,
                 required_components: tuple[str, str, str] | None = None,
                 timeout: float = DEFAULT_TIMEOUT):
    """Reserve the shared resource for an entire ShortPilot image series."""
    with resource_lock("render", timeout=timeout) as outer:
        if outer:
            _prepare_render(comfy_url, ollama_url, required_components)
        yield
