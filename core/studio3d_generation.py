"""Provider-neutral text/image-to-3D generation with local credential storage."""
from __future__ import annotations

import base64
import ipaddress
import json
import os
import socket
import time
import uuid
from urllib.parse import urljoin, urlsplit

import requests


PROVIDERS = frozenset(("tripo", "meshy", "local"))


class GenerationError(RuntimeError):
    pass


def _paths(base):
    return (
        os.path.join(base, "data", "studio3d_generation.json"),
        os.path.join(base, "tmp", "studio3d_models"),
    )


def _default_config():
    return {
        "provider": "tripo",
        "tripo_key": "",
        "meshy_key": "",
        "local_url": "http://127.0.0.1:7860/generate-glb",
    }


def load_config(base, public=False):
    path, _ = _paths(base)
    config = _default_config()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if isinstance(raw, dict):
            config.update({key: raw[key] for key in config if isinstance(raw.get(key), str)})
    except (OSError, ValueError):
        pass
    if config["provider"] not in PROVIDERS:
        config["provider"] = "tripo"
    if public:
        return {
            "provider": config["provider"],
            "local_url": config["local_url"],
            "configured": {
                "tripo": bool(config["tripo_key"]),
                "meshy": bool(config["meshy_key"]),
                "local": bool(config["local_url"]),
            },
        }
    return config


def _local_url(value):
    value = str(value or "").strip().rstrip("/")
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https")
            or parsed.hostname not in ("localhost", "127.0.0.1", "::1")
            or parsed.username or parsed.password or parsed.fragment):
        raise ValueError("Le moteur local doit utiliser localhost ou 127.0.0.1.")
    return value


def save_config(base, values):
    current = load_config(base)
    provider = str(values.get("provider") or current["provider"])
    if provider not in PROVIDERS:
        raise ValueError("Fournisseur 3D inconnu.")
    current["provider"] = provider
    for provider_name in ("tripo", "meshy"):
        field = provider_name + "_key"
        if field in values:
            key = str(values.get(field) or "").strip()
            if len(key) > 500:
                raise ValueError("Clé API trop longue.")
            current[field] = key
    if "local_url" in values:
        current["local_url"] = _local_url(values.get("local_url"))
    path, _ = _paths(base)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(current, handle, ensure_ascii=False, indent=2)
    os.replace(temporary, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return load_config(base, public=True)


def _request_json(session, method, url, *, headers=None, payload=None, timeout=60):
    try:
        response = session.request(method, url, headers=headers, json=payload,
                                   timeout=timeout, allow_redirects=False)
    except requests.RequestException as exc:
        raise GenerationError("Le service 3D est inaccessible.") from exc
    try:
        data = response.json()
    except ValueError:
        data = {}
    if response.status_code >= 400:
        message = data.get("message") or data.get("error") or data.get("code")
        raise GenerationError(f"Le service 3D a refusé la demande ({message or response.status_code}).")
    return data, response


def _poll(session, url, headers, parser, timeout=1200):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data, response = _request_json(session, "GET", url, headers=headers, timeout=30)
        state, result = parser(data)
        if state == "done":
            return result
        if state == "failed":
            raise GenerationError(result or "La génération 3D a échoué.")
        wait = response.headers.get("Retry-After", "5")
        try:
            wait = max(2, min(15, int(wait)))
        except (TypeError, ValueError):
            wait = 5
        time.sleep(wait)
    raise GenerationError("La génération 3D continue chez le fournisseur. Réessayez plus tard.")


def _tripo(session, prompt, key):
    if not key:
        raise GenerationError("Ajoutez d’abord une clé API Tripo dans les réglages.")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    data, _ = _request_json(session, "POST",
        "https://openapi.tripo3d.com/v3/generation/text-to-model", headers=headers,
        payload={"prompt": prompt, "texture": True, "pbr": True,
                 "texture_quality": "detailed"})
    task_id = ((data.get("data") or {}).get("task_id"))
    if not task_id:
        raise GenerationError("Tripo n’a pas renvoyé d’identifiant de génération.")

    def parse(payload):
        task = payload.get("data") or {}
        state = str(task.get("status") or "").lower()
        if state == "success":
            return "done", (task.get("output") or {}).get("model_url")
        if state in ("failed", "cancelled", "banned"):
            return "failed", task.get("message") or "La génération Tripo a échoué."
        return "wait", None

    return _poll(session, f"https://openapi.tripo3d.com/v3/tasks/{task_id}", headers, parse)


def _meshy_poll(session, task_id, headers):
    def parse(payload):
        state = str(payload.get("status") or "").upper()
        if state == "SUCCEEDED":
            return "done", payload
        if state in ("FAILED", "CANCELED"):
            error = payload.get("task_error") or {}
            return "failed", error.get("message") if isinstance(error, dict) else str(error)
        return "wait", None
    return _poll(session, f"https://api.meshy.ai/openapi/v2/text-to-3d/{task_id}", headers, parse)


def _meshy(session, prompt, key, image_data=None):
    if not key:
        raise GenerationError("Ajoutez d’abord une clé API Meshy dans les réglages.")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if image_data:
        data, _ = _request_json(session, "POST", "https://api.meshy.ai/openapi/v1/image-to-3d",
            headers=headers, payload={"image_url": image_data, "ai_model": "latest",
                                      "should_texture": True, "enable_pbr": True,
                                      "target_formats": ["glb"]}, timeout=120)
        task_id = data.get("result")
        if not task_id:
            raise GenerationError("Meshy n’a pas renvoyé d’identifiant de génération.")

        def parse_image(payload):
            state = str(payload.get("status") or "").upper()
            if state == "SUCCEEDED":
                return "done", (payload.get("model_urls") or {}).get("glb")
            if state in ("FAILED", "CANCELED"):
                return "failed", "La génération Meshy a échoué."
            return "wait", None
        return _poll(session, f"https://api.meshy.ai/openapi/v1/image-to-3d/{task_id}", headers, parse_image)

    preview, _ = _request_json(session, "POST", "https://api.meshy.ai/openapi/v2/text-to-3d",
        headers=headers, payload={"mode": "preview", "prompt": prompt,
                                  "ai_model": "latest", "target_formats": ["glb"]})
    preview_id = preview.get("result")
    if not preview_id:
        raise GenerationError("Meshy n’a pas renvoyé d’identifiant de prévisualisation.")
    _meshy_poll(session, preview_id, headers)
    refine, _ = _request_json(session, "POST", "https://api.meshy.ai/openapi/v2/text-to-3d",
        headers=headers, payload={"mode": "refine", "preview_task_id": preview_id,
                                  "enable_pbr": True, "target_formats": ["glb"]})
    refine_id = refine.get("result")
    if not refine_id:
        raise GenerationError("Meshy n’a pas lancé la texturation.")
    result = _meshy_poll(session, refine_id, headers)
    return (result.get("model_urls") or {}).get("glb")


def _local(session, prompt, url, image_data=None):
    url = _local_url(url)
    try:
        response = session.post(url, json={"prompt": prompt, "image": image_data,
                                           "format": "glb"}, timeout=(5, 1200),
                                allow_redirects=False)
    except requests.RequestException as exc:
        raise GenerationError("Le moteur 3D local est inaccessible.") from exc
    if response.status_code >= 400:
        raise GenerationError(f"Le moteur local a renvoyé une erreur {response.status_code}.")
    if response.headers.get("Content-Type", "").split(";", 1)[0] in (
            "model/gltf-binary", "application/octet-stream"):
        return response.content
    try:
        data = response.json()
    except ValueError as exc:
        raise GenerationError("Le moteur local doit renvoyer un GLB ou une réponse JSON.") from exc
    return data.get("glb_url") or data.get("model_url")


def _public_https_url(value):
    parsed = urlsplit(str(value or ""))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise GenerationError("Le fournisseur n’a pas renvoyé une adresse GLB HTTPS valide.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise GenerationError("L’adresse du modèle généré est introuvable.") from exc
    if not addresses or any(ipaddress.ip_address(address).is_private
                            or ipaddress.ip_address(address).is_loopback
                            or ipaddress.ip_address(address).is_link_local for address in addresses):
        raise GenerationError("L’adresse du modèle généré n’est pas publique.")
    return parsed.geturl()


def _download_glb(session, url):
    current = _public_https_url(url)
    for _ in range(4):
        try:
            response = session.get(current, timeout=(10, 180), allow_redirects=False, stream=True)
        except requests.RequestException as exc:
            raise GenerationError("Le GLB généré n’a pas pu être téléchargé.") from exc
        if response.status_code in (301, 302, 303, 307, 308):
            current = _public_https_url(urljoin(current, response.headers.get("Location", "")))
            continue
        if response.status_code != 200:
            raise GenerationError(f"Téléchargement du GLB impossible ({response.status_code}).")
        output = bytearray()
        for chunk in response.iter_content(1024 * 1024):
            output.extend(chunk)
            if len(output) > 400 * 1024 * 1024:
                raise GenerationError("Le GLB dépasse la limite de 400 Mo.")
        return bytes(output)
    raise GenerationError("Trop de redirections pendant le téléchargement du GLB.")


def generate_model(base, payload):
    config = load_config(base)
    provider = str(payload.get("provider") or config["provider"])
    if provider not in PROVIDERS:
        raise GenerationError("Fournisseur 3D inconnu.")
    prompt = str(payload.get("prompt") or "").strip()[:4000]
    image_data = payload.get("image")
    if not prompt and not image_data:
        raise GenerationError("Ajoutez une description ou une image.")
    if image_data:
        image_data = str(image_data)
        if len(image_data) > 28 * 1024 * 1024 or not image_data.startswith("data:image/"):
            raise GenerationError("Image invalide ou trop volumineuse (20 Mo maximum).")
        try:
            base64.b64decode(image_data.split(",", 1)[1], validate=True)
        except (IndexError, ValueError) as exc:
            raise GenerationError("Image encodée invalide.") from exc
    with requests.Session() as session:
        session.trust_env = False
        if provider == "tripo":
            if image_data:
                raise GenerationError("L’image directe sera ajoutée à Tripo plus tard ; utilisez Meshy ou le moteur local.")
            result = _tripo(session, prompt, config["tripo_key"])
        elif provider == "meshy":
            result = _meshy(session, prompt, config["meshy_key"], image_data)
        else:
            result = _local(session, prompt, config["local_url"], image_data)
        content = result if isinstance(result, (bytes, bytearray)) else _download_glb(session, result)
    if len(content) < 12 or bytes(content[:4]) != b"glTF":
        raise GenerationError("Le fournisseur n’a pas renvoyé un fichier GLB valide.")
    _, directory = _paths(base)
    os.makedirs(directory, exist_ok=True)
    name = uuid.uuid4().hex + ".glb"
    path = os.path.join(directory, name)
    with open(path, "wb") as handle:
        handle.write(content)
    return {"ok": True, "provider": provider, "file": name,
            "url": "/api/studio3d/generated/" + name}
