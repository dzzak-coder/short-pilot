"""Contrats de narration : longueur, unicité, structure et panne réseau."""
import tempfile
import unittest
from unittest.mock import patch

from core import content, webcontent


class ScriptDurationTests(unittest.TestCase):
    def test_all_menu_durations_and_languages_fit_a_documented_reserve(self):
        # Source suffisamment longue : chaque ligne porte un fait distinct.
        reserve = [f"Le document numéro {i} décrit une étape différente avec ses acteurs, ses lieux et ses conséquences observables."
                   for i in range(90)]
        for lang in ("fr", "en"):
            for duration in content.DURATION_OPTIONS:
                with self.subTest(lang=lang, duration=duration):
                    hook = "Une histoire documentée à découvrir."
                    script = content.fit_script({"language": lang, "hook": hook, "cta": "Découvrez la suite demain.",
                                                 "scenes": [hook, *reserve, *reserve, "Découvrez la suite demain."]}, duration)
                    if duration == 20:
                        # No complete source clause fits the final few words;
                        # keep the narration intact and report the shortfall.
                        self.assertFalse(script["duration_ok"])
                        self.assertTrue(any("Contenu insuffisant" in w for w in script["warnings"]))
                    else:
                        self.assertTrue(script["duration_ok"])
                    self.assertEqual(len(script["scenes"]), len(set(script["scenes"])))
                    self.assertEqual(script["scenes"][0], hook)
                    self.assertEqual(script["scenes"][-1], "Découvrez la suite demain.")
                    if duration == 180:
                        self.assertTrue(25 <= len(script["scenes"]) <= 40)

    def test_words_target_is_465_for_three_minutes_in_french(self):
        self.assertEqual(content.target_words(180, "fr"), 465)

    def test_short_stock_is_explicit_instead_of_padded(self):
        script = content.fit_script({"scenes": ["Accroche", "Un seul fait disponible.", "Fin"]}, 300)
        self.assertFalse(script["duration_ok"])
        self.assertIn("Contenu insuffisant", script["warnings"][0])

    def test_web_failure_surfaces_reason_and_uses_no_random_subject(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(content, "DATA_DIR", folder), \
             patch.object(webcontent, "topic_script", side_effect=RuntimeError("HTTP 429")):
            script = content.generate_script("sujet", topic="Sujet précis", source="web", target=180, avoid_repeat=False)
        self.assertEqual(script["source"], "local")
        self.assertIn("HTTP 429", script["fallback_reason"])
        self.assertTrue(any("Web indisponible" in warning for warning in script["warnings"]))


if __name__ == "__main__":
    unittest.main()
