import json
import multiprocessing
import tempfile
import threading
import unittest
from pathlib import Path

from core import oneshot


class Response:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload or {}, text
    def json(self):
        return self._payload


class FakeHTTP:
    """Deliberately tiny HTTP double: every GET/POST is evidence in a test."""
    def __init__(self, replies=None):
        self.replies = replies or {}
        self.get_calls, self.post_calls, self.api_generate_calls = [], [], []

    def get(self, path):
        self.get_calls.append(path)
        reply = self.replies.get(path)
        if isinstance(reply, Exception):
            raise reply
        return reply if reply is not None else Response(200, {})

    def post(self, path, payload=None):
        self.post_calls.append((path, payload))
        if path == "/api/generate":
            self.api_generate_calls.append(payload)
        return Response(400, text="deliberate stop")


def _process_attempt(folder, gate, submissions, outcomes):
    """Windows-spawn-safe contender for the exclusive marker test."""
    workflow = {"3": {"inputs": {"seed": 7, "steps": 8, "cfg": 1.0,
                                    "sampler_name": "euler", "scheduler": "simple"}}}
    gate.wait(10)
    try:
        report = oneshot.run(
            folder, seed=7, preflight={"code_hash": "code", "visual_plan_fingerprint": "plan"}, workflow=workflow,
            preflight_check=lambda: None,
            submit=lambda *_: (submissions.put(1) or Response(400, text="stop")),
            history=lambda _: {}, download=lambda _: b"")
        outcomes.put(report["execution_status"])
    except oneshot.OneShotError:
        outcomes.put("reserved_elsewhere")


class OneShotTests(unittest.TestCase):
    def setUp(self):
        self.workflow = {"3": {"inputs": {"seed": 7, "steps": 8, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple"}}}
        self.preflight = {"code_hash": "code", "visual_plan_fingerprint": "plan"}

    def _http_preflight(self, client, *, preflight=None, workflow=None, required_term=True):
        """The complete pre-marker contract, driven solely by FakeHTTP."""
        preflight, workflow = preflight or self.preflight, workflow or self.workflow
        stats = client.get("/system_stats")
        if stats.status_code != 200:
            raise RuntimeError("/system_stats unavailable")
        info = client.get("/object_info")
        if info.status_code != 200:
            raise RuntimeError("/object_info unavailable")
        data = info.json()
        required = {
            "UNETLoader": ("unet_name", "qwen_image_2.1_turbo_int8_convrot.safetensors"),
            "CLIPLoader": ("clip_name", "qwen3vl_8b_w4a8.safetensors"),
            "VAELoader": ("vae_name", "qwen_image_2.1_vae_bf16.safetensors"),
        }
        for node, (field, value) in required.items():
            values = (((data.get(node) or {}).get("input") or {}).get("required") or {}).get(field, [[]])[0]
            if value not in values:
                raise RuntimeError("Qwen component missing: " + value)
        queue = client.get("/queue")
        if queue.status_code != 200 or (queue.json().get("queue_running") or queue.json().get("queue_pending")):
            raise RuntimeError("external queue conflict")
        ps = client.get("/api/ps")
        if ps.status_code != 200 or ps.json().get("models"):
            raise RuntimeError("active Ollama model")
        if preflight.get("code_hash") != "code":
            raise RuntimeError("code fingerprint mismatch")
        if preflight.get("visual_plan_fingerprint") != "plan":
            raise RuntimeError("plan fingerprint mismatch")
        if preflight.get("graph_sha256", oneshot.graph_hash(self.workflow)) != oneshot.graph_hash(workflow):
            raise RuntimeError("graph fingerprint mismatch")
        if not required_term:
            raise RuntimeError("required plan term missing")

    @staticmethod
    def _green_replies():
        return {
            "/system_stats": Response(200, {"system": {}, "devices": []}),
            "/object_info": Response(200, {
                "UNETLoader": {"input": {"required": {"unet_name": [["qwen_image_2.1_turbo_int8_convrot.safetensors"]]}}},
                "CLIPLoader": {"input": {"required": {"clip_name": [["qwen3vl_8b_w4a8.safetensors"]]}}},
                "VAELoader": {"input": {"required": {"vae_name": [["qwen_image_2.1_vae_bf16.safetensors"]]}}},
            }),
            "/queue": Response(200, {"queue_running": [], "queue_pending": []}),
            "/api/ps": Response(200, {"models": []}),
        }

    def _assert_preflight_failure(self, client, **kwargs):
        with tempfile.TemporaryDirectory() as root:
            result = self.execute(root, preflight_check=lambda: self._http_preflight(client, **kwargs),
                                  submit=lambda *_: client.post("/prompt"))
            self.assertEqual(result["preflight_status"], "failed")
            self.assertFalse(Path(root, "generation_once.json").exists())
            self.assertEqual(client.post_calls, [])
            self.assertEqual(client.api_generate_calls, [])

    def test_preflight_system_stats_timeout_has_zero_marker_and_post(self):
        self._assert_preflight_failure(FakeHTTP({"/system_stats": TimeoutError("timeout")}))

    def test_preflight_system_stats_http_500_has_zero_marker_and_post(self):
        self._assert_preflight_failure(FakeHTTP({"/system_stats": Response(500, {})}))

    def test_preflight_missing_unet_has_zero_marker_and_post(self):
        replies = self._green_replies(); replies["/object_info"]._payload["UNETLoader"]["input"]["required"]["unet_name"] = [[]]
        self._assert_preflight_failure(FakeHTTP(replies))

    def test_preflight_missing_clip_has_zero_marker_and_post(self):
        replies = self._green_replies(); replies["/object_info"]._payload["CLIPLoader"]["input"]["required"]["clip_name"] = [[]]
        self._assert_preflight_failure(FakeHTTP(replies))

    def test_preflight_missing_vae_has_zero_marker_and_post(self):
        replies = self._green_replies(); replies["/object_info"]._payload["VAELoader"]["input"]["required"]["vae_name"] = [[]]
        self._assert_preflight_failure(FakeHTTP(replies))

    def test_preflight_external_queue_has_zero_marker_and_post(self):
        replies = self._green_replies(); replies["/queue"] = Response(200, {"queue_pending": [[99, "other-client"]]})
        self._assert_preflight_failure(FakeHTTP(replies))

    def test_preflight_active_ollama_has_zero_marker_post_and_unload(self):
        replies = self._green_replies(); replies["/api/ps"] = Response(200, {"models": [{"name": "other"}]})
        self._assert_preflight_failure(FakeHTTP(replies))

    def test_preflight_plan_hash_mismatch_has_zero_marker_and_post(self):
        data = dict(self.preflight, visual_plan_fingerprint="other")
        self._assert_preflight_failure(FakeHTTP(self._green_replies()), preflight=data)

    def test_preflight_code_hash_mismatch_has_zero_marker_and_post(self):
        data = dict(self.preflight, code_hash="other")
        self._assert_preflight_failure(FakeHTTP(self._green_replies()), preflight=data)

    def test_preflight_graph_hash_mismatch_has_zero_marker_and_post(self):
        # Harness contract only: production records the submitted graph hash,
        # but does not compare it with a separately stored expected graph hash.
        data = dict(self.preflight, graph_sha256="other")
        self._assert_preflight_failure(FakeHTTP(self._green_replies()), preflight=data)

    def test_preflight_invalid_plan_has_zero_marker_and_post(self):
        self._assert_preflight_failure(FakeHTTP(self._green_replies()), required_term=False)

    def test_green_preflight_creates_x_marker_then_one_post(self):
        with tempfile.TemporaryDirectory() as root:
            client = FakeHTTP(self._green_replies())
            result = self.execute(root, preflight_check=lambda: self._http_preflight(client),
                                  submit=lambda *_: client.post("/prompt"))
            self.assertEqual(result["execution_status"], "rejected")
            self.assertEqual(Path(root, "generation_once.json").read_text(encoding="utf-8"), "x")
            self.assertEqual([path for path, _ in client.post_calls], ["/prompt"])
            self.assertEqual(client.api_generate_calls, [])

    def execute(self, folder, **kwargs):
        defaults = {"preflight_check": lambda: None, "submit": lambda *_: Response(200, {"prompt_id": "p"}),
                    "history": lambda _: {}, "download": lambda _: b"png"}
        defaults.update(kwargs)
        return oneshot.run(folder, seed=7, preflight=self.preflight, workflow=self.workflow, **defaults)

    def test_preflight_failure_creates_no_marker_or_post(self):
        with tempfile.TemporaryDirectory() as root:
            called = []
            result = oneshot.run(root, seed=7, preflight=self.preflight, workflow=self.workflow,
                preflight_check=lambda: (_ for _ in ()).throw(RuntimeError("missing Qwen")),
                submit=lambda *_: called.append(True), history=lambda _: {}, download=lambda _: b"")
            self.assertEqual(result["preflight_status"], "failed")
            self.assertFalse(Path(root, "generation_once.json").exists())
            self.assertEqual(called, [])

    def test_empty_history_polls_then_success_without_false_rejection(self):
        with tempfile.TemporaryDirectory() as root:
            success = {"p": {"status": {"status_str": "success"}, "prompt": [0, "p", self.workflow],
                               "outputs": {"x": {"images": [{"filename": "x.png"}]}}}}
            polls = [{}, {}, {}, success]
            result = self.execute(root, history=lambda _: polls.pop(0), max_polls=4, image_size=lambda _: [1, 1])
            self.assertEqual(result["execution_status"], "succeeded")
            self.assertIsNone(result["visual_acceptance"]["accepted"])
            states = [json.loads(line)["state"] for line in Path(root, "execution_events.jsonl").read_text().splitlines()]
            self.assertIn("submitted", states)
            self.assertIn("succeeded", states)

    def test_one_prompt_can_persist_multiple_images(self):
        with tempfile.TemporaryDirectory() as root:
            success = {"p": {"status": {"status_str": "success"},
                               "prompt": [0, "p", self.workflow],
                               "outputs": {
                                   "a": {"images": [{"filename": "a.png"}]},
                                   "b": {"images": [{"filename": "b.png"}]},
                               }}}
            result = self.execute(
                root, history=lambda _: success,
                download=lambda image: (image["filename"] * 10).encode(),
                image_size=lambda _: [720, 1280], expected_image_size=(720, 1280))
            self.assertEqual(result["execution_status"], "succeeded")
            self.assertEqual(result["prompt_post_count"], 1)
            self.assertEqual(result["image_count"], 2)
            self.assertEqual([item["image"] for item in result["images"]],
                             ["image_01.png", "image_02.png"])
            self.assertTrue(Path(root, "image_01.png").exists())
            self.assertTrue(Path(root, "image_02.png").exists())

    def test_journal_identifies_attempt_and_is_flushed_before_post(self):
        with tempfile.TemporaryDirectory() as root:
            observed = {}
            success = {"p": {"status": {"status_str": "success"}, "prompt": [0, "p", self.workflow],
                               "outputs": {"x": {"images": [{"filename": "x.png"}]}}}}
            def submit(*_):
                observed["entries"] = [json.loads(line) for line in Path(root, "execution_events.jsonl").read_text(encoding="utf-8").splitlines()]
                return Response(200, {"prompt_id": "p"})
            self.execute(root, submit=submit, history=lambda _: success, image_size=lambda _: [1, 1])
            reserved, started = observed["entries"]
            self.assertEqual(started["state"], "submission_started")
            self.assertTrue(reserved["attempt_id"] and reserved["client_id"] and reserved["graph_sha256"])
            self.assertEqual(started["attempt_id"], reserved["attempt_id"])
            self.assertEqual(started["client_id"], reserved["client_id"])
            self.assertLessEqual(reserved["at"], started["at"])

    def test_timeout_keeps_prompt_id_and_never_retries(self):
        with tempfile.TemporaryDirectory() as root:
            count = []
            result = oneshot.run(root, seed=7, preflight=self.preflight, workflow=self.workflow,
                preflight_check=lambda: None, submit=lambda *_: (count.append(1) or Response(200, {"prompt_id": "p"})),
                history=lambda _: {}, download=lambda _: b"", max_polls=2)
            self.assertEqual(result["execution_status"], "timeout")
            self.assertEqual(result["prompt_id"], "p")
            self.assertIsNone(result["visual_acceptance"]["accepted"])
            self.assertEqual(len(count), 1)

    def test_rejection_and_network_indeterminate_never_retry(self):
        with tempfile.TemporaryDirectory() as root:
            rejected_posts = []
            rejected = self.execute(root, submit=lambda *_: (rejected_posts.append(1) or Response(400, text="bad graph")))
            self.assertEqual(rejected["execution_status"], "rejected")
            self.assertEqual(rejected["response_detail"], "bad graph")
            self.assertEqual(len(rejected_posts), 1)
        with tempfile.TemporaryDirectory() as root:
            network_posts = []
            indeterminate = self.execute(root, submit=lambda *_: (network_posts.append(1) or (_ for _ in ()).throw(OSError("lost"))))
            self.assertEqual(indeterminate["execution_status"], "indeterminate")
            self.assertEqual(len(network_posts), 1)

    def test_existing_marker_stops_before_submission(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "generation_once.json").write_text("{}")
            called = []
            with self.assertRaises(oneshot.OneShotError):
                self.execute(root, submit=lambda *_: called.append(True))
            self.assertEqual(called, [])

    def test_existing_marker_stops_before_any_network_preflight(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "generation_once.json").write_text("x", encoding="utf-8")
            client = FakeHTTP(self._green_replies())
            with self.assertRaises(oneshot.OneShotError):
                self.execute(root, preflight_check=lambda: self._http_preflight(client),
                             submit=lambda *_: client.post("/prompt"))
            self.assertEqual(client.get_calls, [])
            self.assertEqual(client.post_calls, [])

    def test_two_concurrent_attempts_create_one_marker_and_at_most_one_post(self):
        with tempfile.TemporaryDirectory() as root:
            calls, results = [], []
            gate = threading.Barrier(2)
            def attempt():
                gate.wait()
                try:
                    results.append(self.execute(root, submit=lambda *_: (calls.append(1) or Response(400, text="stop"))))
                except oneshot.OneShotError:
                    results.append("reserved_elsewhere")
            threads = [threading.Thread(target=attempt) for _ in range(2)]
            [thread.start() for thread in threads]
            [thread.join() for thread in threads]
            self.assertTrue(Path(root, "generation_once.json").exists())
            self.assertLessEqual(len(calls), 1)
            self.assertIn("reserved_elsewhere", results)

    def test_two_processes_create_one_marker_and_at_most_one_post(self):
        with tempfile.TemporaryDirectory() as root:
            context = multiprocessing.get_context("spawn")
            gate, submissions, outcomes = context.Event(), context.Queue(), context.Queue()
            processes = [context.Process(target=_process_attempt, args=(root, gate, submissions, outcomes)) for _ in range(2)]
            for process in processes:
                process.start()
            gate.set()
            for process in processes:
                process.join(15)
                self.assertEqual(process.exitcode, 0)
            self.assertTrue(Path(root, "generation_once.json").exists())
            self.assertEqual(submissions.get(timeout=2), 1)
            self.assertTrue(submissions.empty())
            self.assertCountEqual([outcomes.get(timeout=2) for _ in processes], ["rejected", "reserved_elsewhere"])

    def test_graph_mismatch_fails_after_history_without_visual_acceptance(self):
        with tempfile.TemporaryDirectory() as root:
            changed = {"3": {"inputs": {"seed": 99}}}
            entry = {"p": {"status": {"status_str": "success"}, "prompt": [0, "p", changed],
                            "outputs": {"x": {"images": [{"filename": "x.png"}]}}}}
            result = self.execute(root, history=lambda _: entry)
            self.assertEqual(result["execution_status"], "failed")
            self.assertIsNone(result["visual_acceptance"]["accepted"])

    def test_running_history_entry_waits_for_success_and_image_dimensions_are_checked(self):
        with tempfile.TemporaryDirectory() as root:
            running = {"p": {"status": {"status_str": "running"}}}
            success = {"p": {"status": {"status_str": "success"}, "prompt": [0, "p", self.workflow],
                               "outputs": {"x": {"images": [{"filename": "x.png"}]}}}}
            polls = [running, success]
            result = self.execute(root, history=lambda _: polls.pop(0), max_polls=2,
                                  image_size=lambda _: [1280, 720], expected_image_size=(720, 1280))
            self.assertEqual(result["execution_status"], "failed")
            self.assertIsNone(result["visual_acceptance"]["accepted"])

    def test_diagnostic_correction_creates_distinct_report(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root, "report.json")
            source.write_text('{"old": true}', encoding="utf-8")
            corrected = oneshot.write_reconstructed_report(root, source, {"execution_status": "succeeded"})
            self.assertTrue(source.exists())
            self.assertNotEqual(source, corrected)
            self.assertEqual(json.loads(corrected.read_text())["source_report"], "report.json")


if __name__ == "__main__":
    unittest.main()
