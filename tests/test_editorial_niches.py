"""Regression coverage for niche routing, offline facts and music preferences."""
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import app
from core import content, music, render, sources


class EditorialNicheTests(unittest.TestCase):
    def bundle(self, niche):
        return {"kind": niche, "key": niche + ":fixture", "label": "Source documentée",
                "angle": sources._ANGLE_BY_NICHE[niche],
                "items": [{"title": "Sujet documenté", "url": "https://example.org/article",
                           "source": "Document", "date": datetime(2026, 11, 2, 12, tzinfo=timezone.utc),
                           "text": " ".join(
                               f"Le document numéro {i} décrit une étape précise avec ses acteurs et ses conséquences."
                               for i in range(15))}]}

    def test_each_niche_keeps_its_facts_angle_and_identity_online_and_offline(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(sources, "_cache_path", return_value=os.path.join(folder, "cache.json")), \
                patch.object(sources, "ollama_model", return_value=""), \
                patch.object(sources, "_http", side_effect=AssertionError("unexpected network")):
            for lang in ("fr", "en"):
                for niche in content.EDITORIAL_NICHES:
                    with self.subTest(niche=niche, lang=lang):
                        with patch.object(sources, "fetch_bundle", return_value=self.bundle(niche)) as fetch:
                            online = content.generate_script(niche, lang=lang, source="web", avoid_repeat=False)
                            self.assertEqual(fetch.call_args.args[:4], (niche, "", lang, niche))
                        with patch.object(sources, "fetch_bundle", side_effect=AssertionError("offline")):
                            offline = content.generate_script(niche, lang=lang, source="local", avoid_repeat=False)
                        saved = sources._cache_get('editorial:' + sources.json.dumps([niche, lang, ""]), 60)
                        self.assertEqual(saved["items"][0]["date"], "2026-11-02T12:00:00+00:00")
                        for script in (online, offline):
                            self.assertEqual(script["niche"], niche)
                            self.assertEqual(script["angle"], sources._ANGLE_BY_NICHE[niche])
                            self.assertIn("document", " ".join(script["scenes"]).lower())
                            self.assertNotIn("#motivation", script["hashtags"])
                            self.assertTrue(content.badge_for(script["niche"], lang))
                        self.assertEqual(offline["source"], "local")
                        self.assertTrue(any("actualis" in w for w in offline["warnings"]))
                        self.assertIn(niche, render._NICHE_THEME)
                        self.assertIn(niche, music.NICHE_MUSIC)

    def test_no_cached_facts_never_becomes_motivational_stock(self):
        with patch.object(sources, "_cache_get", return_value=None):
            result = content.generate_script("actu", source="local")
        self.assertIn("error", result)
        self.assertNotIn("scenes", result)

    def test_personal_source_obeys_selected_niche_angle(self):
        bundle = self.bundle("science")
        bundle.update(kind="perso", angle="explique_simple")
        self.assertEqual(sources.choose_angle(bundle, "science", ""), "decouverte")

    def test_surprise_and_legacy_source_resolve_before_generation(self):
        with patch.object(content.random, "choice", return_value="science"), \
                patch.object(sources, "generate", return_value={"niche": "science"}) as generate:
            result = content.generate_script("surprise", source="web")
            self.assertEqual(result["niche"], "science")
            self.assertEqual(generate.call_args.args, ("science",))
            self.assertEqual(generate.call_args.kwargs["niche"], "science")
            content.generate_script("motivation", source="science")
            self.assertEqual(generate.call_args.kwargs["niche"], "science")

    def test_legacy_preferences_migrate_idempotently_to_visible_options(self):
        clean = app._clean_settings({"music": "webauto", "content_source": "science"})
        self.assertEqual(clean["music"], "instrumental")
        self.assertEqual(clean["content_source"], "web")
        self.assertEqual(clean["content_niche"], "science")
        self.assertEqual(clean["autopilot"]["niches"], ["science"])
        self.assertEqual(app._clean_settings(clean), clean)

    def test_batch_and_pilot_use_resolved_niche_and_stop_on_missing_facts(self):
        settings = app._clean_settings({})
        client = app.app.test_client()
        with patch.object(app, "AUTH_TOKEN", ""), patch.object(app, "get_settings", return_value=settings), \
                patch.object(content, "generate_script", return_value={"niche": "science", "title": "Découverte"}), \
                patch.object(app, "new_job", return_value={"id": "test"}) as job:
            response = client.post("/api/batch", json={"count": 1, "niches": ["surprise"]})
            self.assertEqual(response.json["jobs"][0]["niche"], "science")
            app.enqueue_render_and_publish("science")
            self.assertEqual(job.call_args.args[1]["script"]["niche"], "science")
        with patch.object(app, "AUTH_TOKEN", ""), patch.object(app, "get_settings", return_value=settings), \
                patch.object(content, "generate_script", return_value={"error": "Sources indisponibles"}), \
                patch.object(app, "new_job") as job:
            response = client.post("/api/batch", json={"count": 1, "niches": ["actu"]})
            self.assertEqual(response.status_code, 422)
            job.assert_not_called()


class MusicSelectionTests(unittest.TestCase):
    def test_manual_mood_wins_over_conflicting_narration(self):
        for selection, text, expected in (
            ("zen", "La guerre, les batailles et les empires.", "zen"),
            ("happy", "Le deuil, les larmes et la tristesse.", "joyeux"),
            ("epique", "La paix, le sommeil et la méditation.", "epique"),
        ):
            plan = music.background_plan(selection, "sujet", text)
            self.assertEqual(plan["mood"], expected)
            self.assertEqual(plan["mood_reason"], "choix manuel")

    def test_rendering_does_not_reanalyse_the_announced_plan(self):
        plan = music.background_plan("auto", "science", "La NASA explore les galaxies.")
        with tempfile.TemporaryDirectory() as folder, patch.object(music, "SR", 8000), \
                patch.object(music, "score_plan", side_effect=AssertionError("second analysis")):
            music.instrumental_background(3, path=os.path.join(folder, "music.wav"), plan=plan)
        self.assertEqual(plan["mood"], "espace")
        self.assertIsNone(music.background_plan("none", "science", "NASA"))

    def test_short_keywords_do_not_match_inside_unrelated_words(self):
        self.assertIsNone(music._subject_direction("La famille partage son quotidien.")[0])


if __name__ == "__main__":
    unittest.main()
