import tempfile
import unittest
from pathlib import Path

from core.studio3d_generation import load_config, save_config


class Studio3DGenerationConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_public_config_never_exposes_api_keys(self):
        save_config(str(self.base), {
            'provider': 'meshy',
            'tripo_key': 'tripo-secret',
            'meshy_key': 'meshy-secret',
            'local_url': 'http://127.0.0.1:7860/generate-glb',
        })
        public = load_config(str(self.base), public=True)
        self.assertEqual(public['provider'], 'meshy')
        self.assertEqual(public['configured'], {'tripo': True, 'meshy': True, 'local': True})
        self.assertNotIn('tripo_key', public)
        self.assertNotIn('meshy_key', public)

    def test_local_provider_rejects_remote_host(self):
        with self.assertRaisesRegex(ValueError, 'localhost'):
            save_config(str(self.base), {
                'provider': 'local',
                'local_url': 'https://example.com/generate',
            })

    def test_blank_key_does_not_remove_existing_key_unless_sent(self):
        save_config(str(self.base), {'provider': 'tripo', 'tripo_key': 'secret'})
        save_config(str(self.base), {'provider': 'local'})
        self.assertEqual(load_config(str(self.base))['tripo_key'], 'secret')


if __name__ == '__main__':
    unittest.main()
