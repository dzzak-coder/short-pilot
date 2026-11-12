"""Crash-safe one-shot ComfyUI execution protocol.

This module owns reservation and evidence persistence; it never decides visual
acceptance.  Callers supply the already validated workflow and HTTP transport.
"""
from __future__ import annotations

from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import time
import uuid


class OneShotError(RuntimeError):
    pass


def graph_hash(workflow):
    return hashlib.sha256(json.dumps(workflow, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _atomic_json(path: Path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _event(path: Path, state: str, **values):
    entry = {"at": time.time(), "state": state, **values}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return entry


def _base_report(preflight, *, attempt_id, client_id):
    return {"report_kind": "one_shot_execution", "attempt_id": attempt_id, "client_id": client_id,
            "preflight_status": "passed", "execution_status": "reserved",
            "visual_acceptance": {"accepted": None, "review": "Image non inspectée"}, **preflight}


def _report_path(folder: Path, kind: str, attempt_id: str) -> Path:
    """Give every attempt its own immutable-derived report path."""
    return folder / f"{kind}.{attempt_id}.json"


def write_reconstructed_report(folder, source_report: Path, report: dict):
    """Write a correction beside, never over, its source report."""
    folder = Path(folder)
    target = folder / (source_report.stem + ".reconstructed.json")
    if target.exists():
        target = folder / (source_report.stem + ".reconstructed." + uuid.uuid4().hex + ".json")
    _atomic_json(target, {"report_kind": "reconstructed", "source_report": source_report.name,
                          "reconstructed_at": time.time(), **report})
    return target


def run(folder, *, seed: int, preflight: dict, workflow: dict, preflight_check, submit, history, download,
        render_phase=None, max_polls=120, poll_interval=0, image_size=None, expected_image_size=None,
        validate_execution=None):
    """Submit exactly once after preflight, then follow only its prompt_id.

    `submit(workflow, client_id)` returns an object with status_code/text/json;
    `history(prompt_id)` returns a history mapping or None; `download(image)`
    returns bytes.  All filesystem state belongs to `folder`, normally a fresh
    proof directory.
    """
    folder = Path(folder)
    marker, events = folder / "generation_once.json", folder / "execution_events.jsonl"
    folder.mkdir(parents=True, exist_ok=True)
    # A historical reservation is evidence, not a cue to add a report or to
    # probe ComfyUI.  The caller must explicitly choose any recovery path.
    if marker.exists():
        raise OneShotError("Une réservation one-shot existe déjà ; reprise explicite requise")
    attempt_id, client_id = str(uuid.uuid4()), str(uuid.uuid4())
    report = _base_report(preflight, attempt_id=attempt_id, client_id=client_id)
    submission_started = False
    try:
        phase = render_phase if render_phase is not None else nullcontext()
        with phase:
            preflight_check()
            fingerprint = graph_hash(workflow)
            try:
                with marker.open("x", encoding="utf-8") as handle:
                    # This is intentionally only an immutable semaphore.  All
                    # evidence lives in the append-only journal below, so the
                    # reservation can never be rewritten with a diagnosis.
                    handle.write("x")
                    handle.flush()
                    os.fsync(handle.fileno())
            except FileExistsError as exc:
                # Another process won the reservation between our initial
                # check and exclusive creation.  It owns all evidence.
                raise OneShotError("Une autre tâche a réservé cette exécution") from exc
            _event(events, "reserved", attempt_id=attempt_id, client_id=client_id, seed=seed,
                   graph_sha256=fingerprint, code_hash=preflight.get("code_hash"),
                   plan_fingerprint=preflight.get("visual_plan_fingerprint"),
                   compiler_sha256=preflight.get("planner_compiler_sha256"), max_image_requests=1)
            _event(events, "submission_started", attempt_id=attempt_id, client_id=client_id, graph_sha256=fingerprint)
            submission_started = True
            try:
                response = submit(workflow, client_id)
            except Exception as exc:
                report.update(execution_status="indeterminate", diagnostic_corrections=["Network exception after submission_started"], error=str(exc))
                _event(events, "indeterminate", error=str(exc))
                _atomic_json(_report_path(folder, "execution_report", attempt_id), report)
                return report
            if response.status_code != 200:
                detail = " ".join((response.text or "").split())[:500]
                report.update(execution_status="rejected", response_status=response.status_code, response_detail=detail)
                _event(events, "rejected", status=response.status_code, detail=detail)
                _atomic_json(_report_path(folder, "execution_report", attempt_id), report)
                return report
            try:
                payload = response.json() or {}
            except Exception as exc:
                report.update(execution_status="indeterminate", response_detail="Invalid ComfyUI JSON", error=str(exc))
                _event(events, "indeterminate", error=str(exc))
                _atomic_json(_report_path(folder, "execution_report", attempt_id), report)
                return report
            prompt_id = payload.get("prompt_id")
            if not prompt_id:
                report.update(execution_status="indeterminate", response_detail="ComfyUI returned no prompt_id")
                _event(events, "indeterminate", detail=report["response_detail"])
                _atomic_json(_report_path(folder, "execution_report", attempt_id), report)
                return report
            report.update(execution_status="submitted", prompt_id=prompt_id, graph_sha256=fingerprint)
            report["prompt_post_count"] = 1
            _event(events, "submitted", prompt_id=prompt_id, client_id=client_id)
            entry = None
            for _ in range(max_polls):
                payload = history(prompt_id) or {}
                candidate = payload.get(prompt_id)
                status = (candidate or {}).get("status") or {}
                if candidate and status.get("status_str") == "error":
                    entry = candidate
                    break
                # A /history entry may be present while ComfyUI still runs.
                # Outputs or a terminal success are the authoritative signal.
                if candidate and (status.get("status_str") == "success" or status.get("completed") or candidate.get("outputs")):
                    entry = candidate
                    _event(events, "running", prompt_id=prompt_id)
                    break
                if poll_interval:
                    time.sleep(poll_interval)
            if not entry:
                report.update(execution_status="timeout")
                _event(events, "timeout", prompt_id=prompt_id)
                _atomic_json(_report_path(folder, "execution_report", attempt_id), report)
                return report
            status = (entry.get("status") or {}).get("status_str")
            if status == "error":
                report.update(execution_status="failed", comfy_status=status, history=entry)
                _event(events, "failed", prompt_id=prompt_id)
                _atomic_json(_report_path(folder, "execution_report", attempt_id), report)
                return report
            executed = (entry.get("prompt") or [None, None, None])[2]
            if executed != workflow:
                report.update(execution_status="failed", diagnostic_corrections=["Executed graph differs from submitted graph"])
                _event(events, "failed", prompt_id=prompt_id, detail="graph mismatch")
                _atomic_json(_report_path(folder, "execution_report", attempt_id), report)
                return report
            if validate_execution:
                try:
                    validate_execution(executed)
                except Exception as exc:
                    report.update(execution_status="failed", diagnostic_corrections=["Executed graph validation failed"], error=str(exc))
                    _event(events, "failed", prompt_id=prompt_id, detail="graph validation")
                    _atomic_json(_report_path(folder, "execution_report", attempt_id), report)
                    return report
            images = [image for output in (entry.get("outputs") or {}).values() for image in (output.get("images") or [])]
            if not images:
                report.update(execution_status="failed", history=entry)
                _event(events, "failed", prompt_id=prompt_id, detail="no image")
                _atomic_json(_report_path(folder, "execution_report", attempt_id), report)
                return report
            downloaded = []
            for index, image in enumerate(images, 1):
                raw = download(image)
                image_path = folder / ("image.png" if len(images) == 1 else f"image_{index:02d}.png")
                image_path.write_bytes(raw)
                size = image_size(image_path) if image_size else None
                evidence = {"image": image_path.name, "comfy_output": image,
                            "image_dimensions": size,
                            "image_sha256": hashlib.sha256(raw).hexdigest()}
                downloaded.append(evidence)
                if expected_image_size is not None and tuple(size or ()) != tuple(expected_image_size):
                    report.update(execution_status="failed", prompt_id=prompt_id,
                                  images=downloaded, image_count=len(downloaded),
                                  diagnostic_corrections=["Downloaded image dimensions differ from executed graph"])
                    _event(events, "failed", prompt_id=prompt_id, detail="image dimensions")
                    _atomic_json(_report_path(folder, "execution_report", attempt_id), report)
                    return report
            report.update(execution_status="succeeded", prompt_id=prompt_id, workflow=executed,
                          graph_sha256=fingerprint, images=downloaded,
                          image_count=len(downloaded))
            if len(downloaded) == 1:
                report.update(downloaded[0])
            _event(events, "succeeded", prompt_id=prompt_id,
                   images=[item["image"] for item in downloaded])
            _atomic_json(_report_path(folder, "execution_report", attempt_id), report)
            return report
    except OneShotError:
        raise
    except Exception as exc:
        if submission_started:
            report.update(execution_status="indeterminate", error=str(exc),
                          diagnostic_corrections=["Exception after submission_started"])
            _event(events, "indeterminate", error=str(exc))
            _atomic_json(_report_path(folder, "execution_report", attempt_id), report)
            return report
        report.update(preflight_status="failed", execution_status="failed", error=str(exc))
        _event(events, "preflight_failed", error=str(exc))
        _atomic_json(_report_path(folder, "preflight_report", attempt_id), report)
        return report
