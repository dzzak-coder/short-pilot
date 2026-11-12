import os
import tempfile
import unittest
from unittest.mock import patch

import app as appmod


class YouTubeSourceRightsTests(unittest.TestCase):
    def setUp(self):
        appmod.app.config.update(TESTING=True)
        self.client = appmod.app.test_client()

    def test_youtube_job_rejects_url_without_explicit_rights_confirmation(self):
        response = self.client.post('/api/yt/shorts', json={'url': 'https://www.youtube.com/watch?v=allowed-source'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Confirmez', response.get_json()['error'])

    def test_youtube_job_rejects_truthy_string_confirmation(self):
        response = self.client.post('/api/yt/shorts', json={'url': 'https://youtu.be/allowed-source', 'rights_confirmed': 'true'})
        self.assertEqual(response.status_code, 400)

    def test_youtube_job_accepts_explicit_boolean_confirmation(self):
        with patch.object(appmod, 'new_job', return_value={'id': 'rights-ok'}) as new_job:
            response = self.client.post('/api/yt/shorts', json={'url': 'https://youtu.be/allowed-source', 'rights_confirmed': True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {'job_id': 'rights-ok'})
        self.assertTrue(new_job.call_args.args[1]['url'])

    def test_youtube_info_requires_the_same_confirmation(self):
        response = self.client.post('/api/yt/info', json={'url': 'https://youtu.be/allowed-source'})
        self.assertEqual(response.status_code, 400)

    def test_uploaded_local_file_does_not_require_youtube_confirmation(self):
        fd, path = tempfile.mkstemp(suffix='.mp4', dir=appmod.UPLOADS)
        os.close(fd)
        try:
            with patch.object(appmod, 'new_job', return_value={'id': 'local-ok'}):
                response = self.client.post('/api/yt/shorts', json={'file_path': path})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json(), {'job_id': 'local-ok'})
        finally:
            os.remove(path)


if __name__ == '__main__':
    unittest.main()
