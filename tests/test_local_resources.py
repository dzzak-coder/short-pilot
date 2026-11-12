"""Interprocess and handoff regressions for local-model resource orchestration."""
import multiprocessing
import unittest
from unittest.mock import patch

import requests

from core import local_resources, render


class _Response:
    def __init__(self, status_code=200, text="", payload=None, json_error=False):
        self.status_code, self.text, self.payload, self.json_error = status_code, text, payload, json_error

    def json(self):
        if self.json_error:
            raise ValueError("empty body")
        return self.payload


def _hold_resource(ready, release):
    from core import local_resources as child_resources
    with child_resources.resource_lock("text", timeout=5):
        ready.set()
        release.wait(5)


class LocalResourceLockTests(unittest.TestCase):
    def setUp(self):
        local_resources._OWNED_OLLAMA_MODELS.clear()

    def test_same_phase_is_reentrant_but_mixed_phase_is_rejected(self):
        with local_resources.resource_lock("text", timeout=1) as outer:
            self.assertTrue(outer)
            with local_resources.resource_lock("text", timeout=1) as nested:
                self.assertFalse(nested)
            with self.assertRaisesRegex(local_resources.LocalResourceError, "text → render"):
                with local_resources.resource_lock("render", timeout=1):
                    pass

    def test_second_process_times_out_with_clear_conflict(self):
        context = multiprocessing.get_context("spawn")
        ready, release = context.Event(), context.Event()
        child = context.Process(target=_hold_resource, args=(ready, release))
        child.start()
        try:
            self.assertTrue(ready.wait(5))
            with self.assertRaises(local_resources.LocalResourceBusyError):
                with local_resources.resource_lock("render", timeout=0.15):
                    pass
        finally:
            release.set()
            child.join(5)
            if child.is_alive():
                child.terminate()
                child.join(2)
        self.assertEqual(child.exitcode, 0)

    def test_free_empty_body_precedes_ollama_and_second_snapshot_is_taken(self):
        events = []
        snapshots = [local_resources.ResourceSnapshot(10, 20), local_resources.ResourceSnapshot(11, 21)]
        def json_call(method, url, **_kwargs):
            events.append(url.rsplit("/", 1)[-1])
            return {"queue_running": [], "queue_pending": []} if url.endswith("/queue") else {"models": []}
        def free_call(url, **_kwargs):
            events.append("free")
            return _Response(200, "", json_error=True)
        with patch.object(local_resources, "_comfy_snapshot", side_effect=snapshots) as snapshot, \
                patch.object(local_resources, "_json", side_effect=json_call), \
                patch.object(local_resources.requests, "post", side_effect=free_call):
            with local_resources.text_phase(model="qwen3.8:27b", timeout=1):
                events.append("ollama-call")
        self.assertEqual(events[:3], ["queue", "free", "ps"])
        self.assertLess(events.index("free"), events.index("ollama-call"))
        self.assertEqual(snapshot.call_count, 2)

    def test_free_failure_prevents_ollama(self):
        with patch.object(local_resources, "_comfy_snapshot", return_value=local_resources.ResourceSnapshot(1, 2)), \
                patch.object(local_resources, "_json", return_value={"queue_running": [], "queue_pending": []}), \
                patch.object(local_resources, "_free_comfy", side_effect=local_resources.LocalResourceError("free cassé")), \
                patch.object(local_resources, "_ollama_models") as models:
            with self.assertRaisesRegex(local_resources.LocalResourceError, "free cassé"):
                with local_resources.text_phase(model="qwen3.8:27b", timeout=1):
                    pass
        models.assert_not_called()

    def test_comfy_timeout_is_not_treated_as_offline_and_blocks_ollama(self):
        with patch.object(local_resources.requests, "get", side_effect=requests.Timeout("slow")), \
                patch.object(local_resources, "_ollama_models") as models:
            with self.assertRaisesRegex(local_resources.LocalResourceError, "État ComfyUI inconnu"):
                with local_resources.text_phase(model="qwen3.8:27b", timeout=1):
                    pass
        models.assert_not_called()

    def test_comfy_connection_refused_is_offline_and_does_not_start_it(self):
        refused = requests.ConnectionError("[WinError 10061] connection refused")
        with patch.object(local_resources.requests, "get", side_effect=refused), \
                patch.object(local_resources, "_ollama_models", return_value=[]), \
                patch.object(local_resources, "_free_comfy") as free:
            with local_resources.text_phase(model="qwen3.8:27b", timeout=1):
                pass
        free.assert_not_called()

    def test_render_phase_refuses_any_active_ollama_model_before_comfy_post(self):
        with patch.object(local_resources, "_ollama_models", return_value=["qwen3.8:27b"]):
            with self.assertRaisesRegex(local_resources.LocalResourceError, "aucun POST ComfyUI"):
                with local_resources.render_phase(timeout=1):
                    pass

    def test_unload_uses_non_streaming_payload_and_fails_if_model_remains(self):
        model = "qwen3.8:27b"
        local_resources._OWNED_OLLAMA_MODELS.add(model)
        with patch.object(local_resources, "_ollama_models", side_effect=[[model], [model]]), \
                patch.object(local_resources, "_json", return_value={}) as call:
            with self.assertRaisesRegex(local_resources.LocalResourceError, "conserve encore"):
                local_resources._unload_owned_ollama(model, "http://ollama")
        self.assertEqual(call.call_args.kwargs["payload"], {"model": model, "prompt": "", "keep_alive": 0, "stream": False})

    def test_mixed_transition_after_render_starts_never_calls_text_preparation(self):
        with local_resources.resource_lock("render", timeout=1), \
                patch.object(local_resources, "_prepare_text") as prepare_text:
            with self.assertRaisesRegex(local_resources.LocalResourceError, "render → text"):
                with local_resources.text_phase(model="qwen3.8:27b", timeout=1):
                    pass
        prepare_text.assert_not_called()

    def test_invalid_second_plan_stops_batch_before_render_phase(self):
        plans = ["valid plan", ""]
        controls = [{"required_terms": ["valid plan"], "negative_terms": []}, {"required_terms": [], "negative_terms": []}]
        with self.assertRaisesRegex(ValueError, "Scène 2"):
            render._validate_local_comfy_inputs(["one", "two"], plans, controls)

    def test_lock_releases_after_prepare_or_cleanup_exception_and_keeps_both_errors(self):
        with patch.object(local_resources, "_prepare_text", side_effect=local_resources.LocalResourceError("préparation")):
            with self.assertRaisesRegex(local_resources.LocalResourceError, "préparation"):
                with local_resources.text_phase(model="qwen3.8:27b", timeout=1):
                    pass
        with local_resources.resource_lock("render", timeout=1):
            pass
        with patch.object(local_resources, "_prepare_text"), \
                patch.object(local_resources, "_unload_owned_ollama", side_effect=local_resources.LocalResourceError("déchargement")):
            with self.assertRaisesRegex(local_resources.LocalResourceError, "Erreur de phase texte.*déchargement"):
                with local_resources.text_phase(model="qwen3.8:27b", timeout=1):
                    raise ValueError("corps")
        with local_resources.resource_lock("render", timeout=1):
            pass


if __name__ == "__main__":
    unittest.main()
