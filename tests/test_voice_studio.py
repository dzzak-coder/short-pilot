import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.voice import synthesize_studio_narration


class StudioNarrationVoiceTests(unittest.TestCase):
    def cache_folder(self):
        root = Path(__file__).resolve().parents[1] / 'tmp'
        root.mkdir(exist_ok=True)
        return tempfile.TemporaryDirectory(dir=root)

    def test_uses_denise_for_one_continuous_cached_track(self):
        with self.cache_folder() as folder:
            calls = []

            def render(text, voice_name, rate_pct, target):
                calls.append((text, voice_name, rate_pct, target))
                Path(target).write_bytes(b'ID3' + b'\0' * 2048)

            with patch('core.voice._render_edge_track', side_effect=render):
                first = synthesize_studio_narration('Une F1 prend forme.', folder)
                second = synthesize_studio_narration('Une F1 prend forme.', folder)

            self.assertEqual(first[0], second[0])
            self.assertEqual(first[1], 'edge_tts:fr-denise')
            self.assertEqual(second[1], 'edge_tts:fr-denise')
            self.assertEqual(len(calls), 1)
            text, voice_name, rate_pct, target = calls[0]
            self.assertEqual(text, 'Une F1 prend forme.')
            self.assertEqual(voice_name, 'fr-FR-DeniseNeural')
            self.assertEqual(rate_pct, 0)
            self.assertTrue(target.endswith('.mp3'))

    def test_accepts_remy_but_never_substitutes_an_unknown_voice(self):
        with self.cache_folder() as folder, \
                patch('core.voice._render_edge_track') as render:
            render.side_effect = lambda text, voice, rate, target: Path(target).write_bytes(b'ID3' + b'\0' * 2048)
            remy = synthesize_studio_narration('Texte complet.', folder, voice_id='fr-remy')
            unknown = synthesize_studio_narration('Texte complet.', folder, voice_id='fr-inconnue')

        self.assertEqual(remy[1], 'edge_tts:fr-remy')
        self.assertIsNone(unknown)
        self.assertEqual(render.call_count, 1)


if __name__ == '__main__':
    unittest.main()
