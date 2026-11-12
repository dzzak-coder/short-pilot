# -*- coding: utf-8 -*-
import unittest
import tempfile
import os
import wave
import numpy as np
from unittest.mock import patch

from core import acomusic, music


class MusicDirectionTests(unittest.TestCase):
    def test_five_subjects_give_distinct_repeatable_audio_without_explicit_seed(self):
        themes = ["La guerre transforme les empires.", "Le mystère de la forêt obscure.",
                  "La science explore les galaxies.", "Le deuil et la nostalgie.",
                  "La paix, la respiration et le sommeil."]
        with tempfile.TemporaryDirectory() as folder, patch.object(music, "SR", 8000):
            tracks = []
            for index, text in enumerate([*themes, themes[0]]):
                path = os.path.join(folder, f"theme_{index}.wav")
                music.instrumental_background(6, "epique", path, text=text, scene_durations=[1, 2, 2, 1])
                with wave.open(path) as wav:
                    self.assertEqual(wav.getnframes(), 48000)
                    tracks.append(wav.readframes(wav.getnframes()))
            self.assertEqual(len(set(tracks[:5])), 5)
            self.assertEqual(tracks[0], tracks[-1])

    def test_nasa_uses_epic_space_direction_not_techno(self):
        mood, _ = music.explain_auto("sujet", "La NASA prépare le lancement d'une fusée vers Mars.")
        self.assertEqual(mood, "epique")
        self.assertIn("cinematic space exploration", acomusic._subject_tags("NASA fusée Mars"))

    def test_instrumental_background_has_no_voice_or_sample_source(self):
        with patch.object(music, "cinematic_background", return_value="instrumental.wav") as synth:
            path = music.instrumental_background(42, "epique", "out.wav", text="NASA")
        self.assertEqual(path, "instrumental.wav")
        synth.assert_called_once_with(42, "epique", "out.wav", text="NASA", seed=None)

    def test_space_is_calm_and_each_composition_varies(self):
        plans = [music.score_plan("epique", "Le Système solaire et la planète Vénus", seed=i)
                 for i in range(5)]
        self.assertTrue(all(p["spatial"] and 54 <= p["bpm"] <= 72 for p in plans))
        self.assertGreater(len({(p["root"], p["progression"], p["motif"]) for p in plans}), 1)

    def test_actual_audio_varies_and_remains_stereo_without_clipping(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(music, "SR", 8000):
            tracks = []
            for seed in (7, 7, 8):
                path = os.path.join(folder, f"score_{len(tracks)}.wav")
                music.instrumental_background(5, "epique", path, text="NASA système solaire", seed=seed)
                with wave.open(path) as wav:
                    self.assertEqual((wav.getnchannels(), wav.getnframes(), wav.getframerate()), (2, 40000, 8000))
                    tracks.append(wav.readframes(wav.getnframes()))
            self.assertEqual(tracks[0], tracks[1])
            self.assertNotEqual(tracks[0], tracks[2])
            pcm = np.frombuffer(tracks[0], dtype="<i2")
            self.assertGreater(np.max(np.abs(pcm)), 100)
            self.assertLess(np.max(np.abs(pcm)), 32767)


if __name__ == "__main__":
    unittest.main()
