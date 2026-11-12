import unittest
from unittest.mock import patch

from core.publish import webhook_url_ok


class LocalN8nTests(unittest.TestCase):
    def test_companion_n8n_receives_local_videos(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertTrue(webhook_url_ok('http://127.0.0.1:5678/webhook/shortpilot-studio')[0])
            self.assertTrue(webhook_url_ok('http://127.0.0.1:5678/webhook/shortpilot-youtube')[0])

    def test_other_private_targets_remain_blocked(self):
        with patch.dict('os.environ', {}, clear=True):
            for url in ('http://127.0.0.1:8000/webhook/shortpilot-studio',
                        'http://127.0.0.1:5678/rest/settings',
                        'http://127.0.0.1:5678/webhook/other'):
                with self.subTest(url=url):
                    self.assertFalse(webhook_url_ok(url)[0])
