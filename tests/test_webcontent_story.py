# -*- coding: utf-8 -*-
import unittest
import tempfile
from unittest.mock import patch

from core import content, webcontent
REAL_FULL_ARTICLE = webcontent._wiki_full_article


class WebStoryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        data = patch.object(content, "DATA_DIR", folder.name)
        data.start()
        self.addCleanup(data.stop)
        # Ces tests vérifient la sélection sur leurs propres sources simulées.
        full = patch.object(webcontent, "_wiki_full_article", return_value=None)
        full.start()
        self.addCleanup(full.stop)

    def test_two_minute_duration_label_is_used_everywhere(self):
        self.assertEqual(content.duration_label(120, "fr"), "2 minutes")
        self.assertEqual(webcontent._duration_label(120, "fr"), "2 minutes")
        pack = content._topic_script("histoire du monde", "fr", target=120)
        self.assertIn("2 minutes", pack["hooks"][0])
        self.assertNotIn("une minute", pack["hooks"][0])

    def test_long_local_topic_outline_does_not_repeat_sentences(self):
        script = content.generate_script(
            niche="sujet", lang="fr", topic="histoire du monde",
            target=120, source="local", avoid_repeat=False,
        )
        self.assertEqual(len(script["scenes"]), len(set(script["scenes"])))
        self.assertIn("2 minutes", script["title"])

    def test_grouped_wikipedia_extract_respects_current_api_limit(self):
        class Response:
            @staticmethod
            def json():
                return {"query": {"pages": {
                    "1": {"ns": 0, "title": "Histoire de l'humanité",
                          "extract": "Une introduction suffisamment longue. " * 8,
                          "fullurl": "https://fr.wikipedia.org/wiki/Histoire"}
                }}}

        with patch.object(webcontent, "_get", return_value=Response()) as get:
            articles = webcontent._wiki_intros("fr", ["Histoire de l'humanité", "Histoire"])
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["exintro"], "1")
        self.assertEqual(params["exchars"], "1200")
        self.assertEqual(params["exlimit"], "max")
        self.assertIn("Histoire de l'humanité", articles)

    def test_explicit_topic_deepens_a_relevant_one_sentence_intro(self):
        title = "Histoire de l'humanité"
        intro = {title: {"title": title, "text": (
            "L'histoire de l'humanité retrace en une seule longue phrase la transformation des sociétés "
            "humaines depuis la préhistoire jusqu'à la période contemporaine et leurs nombreuses évolutions."
        ), "url": ""}}
        full = {"title": title, "text": (
            "Les premières communautés humaines apparaissent durant la préhistoire. "
            "L'agriculture transforme ensuite durablement leur organisation. "
            "Puis les premières villes et les premiers États structurent de nouvelles sociétés."
        ), "url": ""}
        with patch.object(webcontent, "_topic_titles", return_value=[title]), \
             patch.object(webcontent, "_wiki_intros", return_value=intro), \
             patch.object(webcontent, "_wiki_full_article", return_value=full) as deepen:
            script = webcontent.script_from_web(
                "sujet", "fr", topic="histoire du monde", target=120, avoid_repeat=False,
            )
        self.assertIsNotNone(script)
        self.assertTrue(all(call.args == ("fr", title) for call in deepen.call_args_list))
        self.assertIn("agriculture", " ".join(script["scenes"]).lower())

    def test_full_article_reader_keeps_paragraphs_and_removes_references(self):
        class Response:
            @staticmethod
            def json():
                return {"parse": {"title": "Histoire de l'humanité", "text": (
                    "<div><p>Les premières communautés humaines apparaissent durant la préhistoire."
                    "<sup>[1]</sup> Elles évoluent progressivement.</p>"
                    "<table><tr><td>Navigation parasite</td></tr></table>"
                    "<p>L'agriculture transforme ensuite durablement leur organisation.</p></div>"
                )}}

        # La fonction réelle est conservée pour ce test de lecture HTML.
        with patch.object(webcontent, "_get", return_value=Response()):
            article = REAL_FULL_ARTICLE("fr", "Histoire de l'humanité")
        self.assertIn("premières communautés", article["text"])
        self.assertIn("agriculture", article["text"])
        self.assertNotIn("[1]", article["text"])
        self.assertNotIn("Navigation parasite", article["text"])

    def test_explicit_web_topic_retries_without_anti_repeat_before_local_fallback(self):
        web_script = {
            "source": "web", "title": "Histoire du monde : l'essentiel en 2 minutes",
            "hook": "Histoire du monde : l'essentiel en 2 minutes",
            "scenes": ["Histoire du monde : l'essentiel en 2 minutes", "Fait documenté.", "CTA"],
            "caption": "", "hashtags": "", "niche": "sujet", "language": "fr",
        }
        with patch.object(webcontent, "topic_script", side_effect=[None, web_script]) as generate:
            script = content.generate_script(
                niche="sujet", lang="fr", topic="histoire du monde",
                target=120, source="web", avoid_repeat=True,
            )
        self.assertEqual(script["source"], "web")
        self.assertTrue(generate.call_args_list[0].kwargs["avoid_repeat"])
        self.assertFalse(generate.call_args_list[1].kwargs["avoid_repeat"])

    def test_free_topic_keeps_wikipedia_search_relevance_order(self):
        titles = ["Histoire de l'humanité", "Anthropologie et histoire des mondes antiques"]
        articles = {
            titles[0]: {"title": titles[0], "text": (
                "L'histoire de l'humanité retrace le développement des sociétés humaines. "
                "Les premières communautés apparaissent avant la naissance des États. "
                "Puis plusieurs civilisations transforment durablement le monde."
            ), "url": ""},
            titles[1]: {"title": titles[1], "text": (
                "Le laboratoire est fondé après une réforme universitaire. "
                "Puis une équipe lance plusieurs programmes et devient un centre de recherche."
            ), "url": ""},
        }
        with patch.object(webcontent, "_topic_titles", return_value=titles), \
             patch.object(webcontent, "_wiki_intros", return_value=articles), \
             patch.object(webcontent.random, "choice", side_effect=lambda values: values[0]):
            script = webcontent.script_from_web(
                "sujet", "fr", topic="histoire du monde", target=120, avoid_repeat=False,
            )
        self.assertIsNotNone(script)
        self.assertIn("humanité", " ".join(script["scenes"]).lower())
        self.assertNotIn("laboratoire", " ".join(script["scenes"]).lower())

    def test_fact_selection_keeps_context_and_prefers_turning_points_in_order(self):
        facts = [
            "Le projet Aurora est un programme scientifique créé pour observer les aurores polaires depuis l'espace.",
            "Son siège regroupe plusieurs laboratoires et un centre administratif spécialisé.",
            "En 2024, une panne a interrompu les observations, puis une équipe a relancé la mission après trois semaines.",
            "Le programme dispose également d'une bibliothèque et de salles de réunion dans son bâtiment principal.",
        ]
        selected = webcontent._select_story_facts(facts, keep=2)
        self.assertEqual(selected[0], facts[0])
        self.assertEqual(selected[1], facts[2])

    def test_story_bridges_do_not_claim_an_unverified_twist(self):
        self.assertNotIn("change complètement", " ".join(webcontent.STORY_BRIDGES["fr"]))

    def test_explicit_chronological_clauses_become_separate_beats(self):
        beats = webcontent._expand_story_beats([
            "La fusée a décollé à l'aube, puis elle a quitté l'atmosphère quelques minutes plus tard."
        ])
        self.assertEqual(len(beats), 2)
        self.assertIn("décollé", beats[0])
        self.assertIn("quitté", beats[1])

    def test_story_bridge_stays_with_its_fact_in_one_visual_scene(self):
        body = webcontent._story_body(
            [
                "Apollo 11 est une mission spatiale américaine.",
                "L'alunissage a lieu après une phase d'approche sous tension.",
            ], "Apollo 11", "Accroche", "CTA", 45, "fr"
        )
        self.assertEqual(len(body), 3)  # two facts plus the closing takeaway
        self.assertIn("phase d'approche", body[1])
        self.assertIn(webcontent.STORY_BRIDGES["fr"][0], body[1])

    def test_wikipedia_headings_never_reach_the_spoken_script(self):
        sentences = webcontent._sentences(
            "L'héliopause est la frontière extérieure du système solaire. "
            "== Structure == Le vent solaire forme une bulle dans le milieu interstellaire.",
            keep=4,
        )
        self.assertEqual(len(sentences), 2)
        self.assertTrue(all("==" not in sentence for sentence in sentences))
        self.assertIn("Le vent solaire", sentences[1])

    def test_long_story_does_not_repeat_generic_bridges(self):
        facts = [f"Fait astronomique numéro {index}, avec un élément concret pour le récit." for index in range(6)]
        body = webcontent._story_body(facts, "Héliopause", "Accroche", "CTA", 120, "fr")
        self.assertEqual(sum("Voilà le contexte de départ." in beat for beat in body), 1)

    def test_story_score_prefers_a_concrete_turning_point(self):
        flat = {"title": "Concept", "text": "Un concept est une idée utilisée dans plusieurs disciplines."}
        story = {"title": "Mission Aurora", "text": (
            "La mission Aurora a été lancée en 2024. Puis une panne a interrompu "
            "les observations avant qu'une équipe relance la fusée."
        )}
        self.assertGreater(webcontent._article_story_score(story), webcontent._article_story_score(flat))

    def test_history_topic_filter_rejects_editorial_and_accepts_event(self):
        editorial = {"title": "Historiographie des Croisades", "text": (
            "L'historiographie des croisades rassemble des interprétations diverses. "
            "Les chercheurs les étudient depuis plusieurs décennies."
        )}
        event = {"title": "Mission Apollo 11", "text": (
            "La mission Apollo 11 a décollé en 1969. Puis l'équipage a réussi "
            "l'alunissage après une phase d'approche sous tension."
        )}
        self.assertFalse(webcontent._storyworthy_article(editorial, "histoire"))
        self.assertTrue(webcontent._storyworthy_article(event, "histoire"))

    def test_history_story_score_prefers_event_over_an_era(self):
        era = {"title": "Pax Europaea", "text": (
            "La Pax Europaea est une période de paix relative depuis 1945. "
            "Elle est souvent associée à la création de l'Union européenne après la guerre."
        )}
        event = {"title": "Bataille de Valmy", "text": (
            "La bataille de Valmy a lieu en 1792 pendant la Révolution française. "
            "Elle devient un tournant majeur de la guerre."
        )}
        self.assertTrue(webcontent._storyworthy_article(era, "histoire"))
        self.assertGreater(webcontent._article_story_score(event), webcontent._article_story_score(era))

    def test_history_topic_filter_rejects_a_media_work_with_event_word_in_title(self):
        media = {"title": "La Bataille de Waterloo (film)", "text": (
            "La Bataille de Waterloo est un film historique sorti en 1970. "
            "Il raconte un épisode militaire européen."
        )}
        self.assertFalse(webcontent._storyworthy_article(media, "histoire"))

    def test_history_topic_filter_rejects_a_history_journal(self):
        journal = {"title": "Annales historiques de la Révolution française", "text": (
            "Les Annales historiques de la Révolution française sont une revue historique trimestrielle. "
            "Elle est publiée depuis le début du XXe siècle."
        )}
        self.assertFalse(webcontent._storyworthy_article(journal, "histoire"))

    def test_history_topic_filter_keeps_an_organisation_but_scores_events_higher(self):
        organisation = {"title": "La Montagne", "text": (
            "La Montagne est un groupe politique qui émerge lors de la Révolution française. "
            "Elle est présente à la Convention nationale."
        )}
        event = {"title": "Révolution française", "text": (
            "La Révolution française débute en 1789 et provoque une crise politique majeure. "
            "Elle transforme durablement la France."
        )}
        self.assertTrue(webcontent._storyworthy_article(organisation, "histoire"))
        self.assertGreater(webcontent._article_story_score(event), webcontent._article_story_score(organisation))

    def test_history_generation_chooses_event_over_journal_automatically(self):
        titles = ["Annales historiques de la Révolution française", "Bataille de Valmy"]
        articles = {
            titles[0]: {"title": titles[0], "text": (
                "Les Annales historiques de la Révolution française sont une revue historique trimestrielle. "
                "Elle publie des travaux universitaires depuis plusieurs décennies."
            ), "url": ""},
            titles[1]: {"title": titles[1], "text": (
                "La bataille de Valmy a lieu en 1792 pendant les guerres de la Révolution française. "
                "Elle arrête l'avancée prussienne et devient un tournant politique majeur. "
                "La victoire permet ensuite à la Convention de proclamer la République."
            ), "url": ""},
        }
        with patch.object(webcontent, "_topic_titles", return_value=titles), \
             patch.object(webcontent, "_wiki_intros", return_value=articles):
            script = webcontent.script_from_web("histoire", "fr", target=45, avoid_repeat=False)
        self.assertIsNotNone(script)
        self.assertIn("valmy", script["title"].lower())

    def test_long_history_script_never_stitches_two_unrelated_articles(self):
        titles = ["Barrage de Malpasset", "Bazar de la Charité"]
        articles = {
            titles[0]: {"title": titles[0], "text": (
                "Le barrage de Malpasset est construit près de Fréjus pour retenir l'eau du Reyran. "
                "Le 2 décembre 1959, de fortes précipitations font monter le niveau du lac. "
                "Le barrage rompt et une vague dévaste la vallée en quelques minutes. "
                "La catastrophe entraîne une enquête sur la géologie du site et la construction de l'ouvrage."
            ), "url": ""},
            titles[1]: {"title": titles[1], "text": (
                "Le Bazar de la Charité est une vente de bienfaisance organisée à Paris. "
                "Un incendie se déclare en 1897 dans le bâtiment temporaire. "
                "La catastrophe provoque une émotion considérable dans la capitale."
            ), "url": ""},
        }
        with patch.object(webcontent, "_topic_titles", return_value=titles), \
             patch.object(webcontent, "_wiki_intros", return_value=articles):
            script = webcontent.script_from_web("histoire", "fr", target=90, avoid_repeat=False)
        self.assertIsNotNone(script)
        spoken = " ".join(script["scenes"]).lower()
        self.assertIn("malpasset", spoken)
        self.assertNotIn("bazar de la charité", spoken)

    def test_history_generation_recovers_on_web_instead_of_local_fallback(self):
        main_titles = ["Annales historiques de la Révolution française"]
        recovery_titles = ["Bataille de Valmy"]
        articles = {
            main_titles[0]: {"title": main_titles[0], "text": (
                "Les Annales historiques sont une revue universitaire. "
                "Elle publie des études depuis plusieurs décennies."
            ), "url": ""},
            recovery_titles[0]: {"title": recovery_titles[0], "text": (
                "La bataille de Valmy a lieu en 1792 pendant la Révolution française. "
                "Elle stoppe l'armée prussienne et devient un tournant majeur."
            ), "url": ""},
        }
        with patch.object(webcontent, "_topic_titles", side_effect=[main_titles, recovery_titles]), \
             patch.object(webcontent, "_wiki_intros", return_value=articles):
            script = webcontent.script_from_web("histoire", "fr", target=45, avoid_repeat=False)
        self.assertIsNotNone(script)
        self.assertEqual(script["source"], "web")
        self.assertIn("valmy", script["title"].lower())

    def test_history_recovery_does_not_repeat_a_used_battle(self):
        main_titles = ["Annales historiques de la Révolution française"]
        recovery_titles = ["Bataille de Valmy", "Bataille de Bouvines"]
        articles = {
            main_titles[0]: {"title": main_titles[0], "text": (
                "Les Annales historiques sont une revue universitaire. "
                "Elle publie des études depuis plusieurs décennies."
            ), "url": ""},
            recovery_titles[0]: {"title": recovery_titles[0], "text": (
                "La bataille de Valmy a lieu en 1792. "
                "Elle stoppe l'armée prussienne et devient un tournant majeur."
            ), "url": ""},
            recovery_titles[1]: {"title": recovery_titles[1], "text": (
                "La bataille de Bouvines a lieu en 1214 et oppose durablement les armées rivales. "
                "Elle devient un tournant majeur du règne de Philippe Auguste et de la monarchie française."
            ), "url": ""},
        }
        used = {webcontent._sig("wiki", recovery_titles[0])}
        with patch.object(webcontent, "_topic_titles", side_effect=[main_titles, recovery_titles]), \
             patch.object(webcontent, "_wiki_intros", return_value=articles), \
             patch.object(content, "_load_used", return_value=used):
            script = webcontent.script_from_web("histoire", "fr", target=45)
        self.assertIsNotNone(script)
        self.assertIn("bouvines", script["title"].lower())

    def test_all_niches_reject_an_obvious_media_article(self):
        media = {"title": "Le cerveau (film)", "text": (
            "Le cerveau est un film sorti en 1969. "
            "Il raconte une aventure imaginaire."
        )}
        for niche in ("psychologie", "argent", "sante", "tech", "faits"):
            self.assertFalse(webcontent._storyworthy_article(media, niche), niche)

    def test_local_free_topic_stays_about_the_requested_subject(self):
        pack = content._topic_script("les cuisines de Tokyo", "fr")
        self.assertTrue(all("Tokyo" in item for item in pack["items"]))
        self.assertNotIn("régularité bat le talent", " ".join(pack["items"]))

    def test_local_free_topic_turns_user_clues_into_ordered_beats(self):
        pack = content._topic_script(
            "Apollo 11, alarme, manque de carburant, phrase d'Armstrong", "fr"
        )
        text = " ".join(pack["items"])
        self.assertNotIn("1.", text)
        self.assertLess(text.index("alarme"), text.index("manque de carburant"))
        self.assertLess(text.index("manque de carburant"), text.index("phrase d'Armstrong"))


if __name__ == "__main__":
    unittest.main()
