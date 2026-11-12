import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import app
from core import publish


class PublicPublicationTests(unittest.TestCase):
    def result(self):
        return {p: {"status": "published", "public": True, "url": "https://example.org/" + p}
                for p in ("youtube", "tiktok")}

    def test_only_both_confirmed_public_posts_are_a_success(self):
        result = self.result()
        self.assertTrue(publish.public_publication_result(result)[0])
        for state in ({"queued": True, "mode": "draft"}, {"status": "pending", "public": False},
                      {"status": "published", "public": False}, {}, {"status": "failed"}):
            with self.subTest(state=state):
                result["tiktok"] = state
                ok, message = publish.public_publication_result(result)
                self.assertFalse(ok)
                self.assertIn("YouTube : publié en public", message)

    def test_acknowledgement_is_not_publication_confirmation(self):
        for response in ({"received": True}, [], None, {"ok": True}):
            self.assertFalse(publish.public_publication_result(response)[0])

    def test_webhook_sends_metadata_and_checks_both_results(self):
        response = Mock(status_code=200, is_redirect=False)
        response.json.return_value = self.result()
        with patch("builtins.open", return_value=io.BytesIO(b"video")), \
                patch("requests.post", return_value=response) as post:
            ok, _ = publish.publish_webhook("http://127.0.0.1:5678/webhook/shortpilot-youtube",
                                           "test.mp4", "Caption", video_id="test", title="Title",
                                           duration=30, require_public=True)
        self.assertTrue(ok)
        self.assertEqual(post.call_args.kwargs["data"]["video_id"], "test")
        self.assertEqual(post.call_args.kwargs["data"]["mode"], "direct_public")

    def test_duplicate_clicks_reuse_the_queued_publication_job(self):
        client = app.app.test_client()
        with patch.object(app, "AUTH_TOKEN", ""), patch.object(app, "JOBS", {}), \
                patch.object(app.TASK_Q, "put") as enqueue:
            first = client.post("/api/publish", json={"video_id": "same", "target": "webhook"})
            second = client.post("/api/publish", json={"video_id": "same", "target": "webhook"})
        self.assertEqual(first.json, second.json)
        enqueue.assert_called_once()

    def test_partial_failure_does_not_mark_the_library_as_published(self):
        entry = {"id": "same", "file": "test.mp4", "title": "Title", "caption": "Caption", "hashtags": ""}
        with patch.object(publish, "publish_webhook", return_value=(False, "TikTok bloqué")), \
                patch.object(app, "library_update") as mark:
            ok, _ = app._do_publish(entry, "webhook", {"webhook_url": "local"}, None)
        self.assertFalse(ok)
        mark.assert_not_called()


if __name__ == "__main__":
    unittest.main()
