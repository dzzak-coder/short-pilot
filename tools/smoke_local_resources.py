"""One text-only smoke test for the Ollama/ComfyUI memory handoff.

It never calls ComfyUI /prompt and never creates an image or Short.
"""
import argparse
import json
import logging
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import local_resources, visual_planner


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    events = []

    class Journal(logging.Handler):
        def emit(self, record):
            events.append(record.getMessage())

    handler = Journal()
    logger = logging.getLogger("core.local_resources")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    result = {"mode": "text_only", "model": visual_planner.PLANNER_MODEL}
    try:
        with local_resources.text_phase(model=visual_planner.PLANNER_MODEL):
            events.append("POST /api/chat minimal")
            response = requests.post(local_resources.DEFAULT_OLLAMA_URL + "/api/chat", json={
                "model": visual_planner.PLANNER_MODEL, "stream": False, "keep_alive": 0, "think": False,
                "messages": [{"role": "user", "content": "Réponds uniquement : OK"}],
                "options": {"num_predict": 8, "temperature": 0},
            }, timeout=(5, 180))
            response.raise_for_status()
            result["response"] = (response.json().get("message") or {}).get("content", "").strip()
            if not result["response"]:
                raise RuntimeError("Ollama a répondu HTTP 200 sans contenu textuel")
        ps = requests.get(local_resources.DEFAULT_OLLAMA_URL + "/api/ps", timeout=5)
        ps.raise_for_status()
        result["ollama_models_after"] = [item.get("name") or item.get("model") for item in ps.json().get("models", [])]
        result["ok"] = True
    except Exception as exc:
        result.update(ok=False, error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        logger.removeHandler(handler)
        result["events"] = events
        args.log.parent.mkdir(parents=True, exist_ok=True)
        args.log.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
