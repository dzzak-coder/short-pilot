import unittest
from unittest.mock import patch

from core import content


class SafeSceneSplitTests(unittest.TestCase):
    def test_kheops_sentence_stays_whole_across_apposition_and_participle(self):
        sentence = ("La pyramide de Khéops, ou grande pyramide de Gizeh, est un monument "
                    "construit par les Égyptiens de l'Antiquité, formant une pyramide à base carrée.")
        self.assertEqual(content.short_scenes([sentence], max_words=20), [sentence])

    def test_semicolon_splits_only_at_clause_boundary(self):
        sentence = ("La porte de pierre s'ouvre lentement ; "
                    "une lampe éclaire la chambre intérieure.")
        self.assertEqual(content.short_scenes([sentence], max_words=7),
                         ["La porte de pierre s'ouvre lentement ;",
                          "une lampe éclaire la chambre intérieure."])

    def test_colon_list_remains_in_narration(self):
        sentence = ("Durant des millénaires, elle fut la construction humaine de tous les records : "
                    "la plus haute, la plus volumineuse et la plus massive.")
        self.assertEqual(content.short_scenes([sentence], max_words=20), [sentence])

    def test_visual_proposal_is_separate_from_spoken_narration(self):
        narration = ("La porte de pierre s'ouvre lentement devant les visiteurs au fond du couloir ; "
                     "une lampe éclaire la chambre intérieure et révèle les murs de la salle ancienne.")
        script = {"scenes": [narration], "title": "La chambre", "warnings": []}
        with patch.object(content.visual_planner, "plan_scenes", return_value={
                "visual_plans": ["a stone door opening"], "visual_controls": [{}]}) as planner:
            content.with_visual_plans(script)
        self.assertEqual(script["scenes"], [narration])
        self.assertEqual(script["visual_proposals"], [
            "La porte de pierre s'ouvre lentement devant les visiteurs au fond du couloir ;"])
        self.assertEqual(planner.call_args.args[0], script["visual_proposals"])

    def test_kheops_fragments_receive_previous_explicit_subject(self):
        scenes = [
            "Le fait essentiel à connaître sur construction de la pyramide de kheops",
            ("La pyramide de Khéops, ou grande pyramide de Gizeh, est un monument construit "
             "par les Égyptiens de l'Antiquité,"),
            "formant une pyramide à base carrée.",
            "Tombeau présumé du souverain Khéops, elle fut édifiée il y a plus de 4 500 ans,",
            ("sous la IV dynastie, au centre du complexe funéraire de Khéops qui se situe "
             "à Gizeh en Égypte."),
        ]
        briefs = content.visual_briefs_for_scenes(scenes)
        self.assertEqual([brief["narration"] for brief in briefs], scenes)
        self.assertEqual(briefs[2], {
            "narration": scenes[2],
            "visual_proposition": "La pyramide de Khéops a une base carrée.",
            "antecedent": "La pyramide de Khéops",
            "needs_context": False,
        })
        self.assertEqual(briefs[3], {
            "narration": scenes[3],
            "visual_proposition": "La pyramide de Khéops fut édifiée il y a plus de 4 500 ans,",
            "antecedent": "La pyramide de Khéops",
            "needs_context": False,
        })
        self.assertEqual(briefs[4]["antecedent"], "La pyramide de Khéops")
        self.assertEqual(
            briefs[4]["visual_proposition"],
            ("La pyramide de Khéops, au centre du complexe funéraire de Khéops "
             "à Gizeh en Égypte."),
        )
        self.assertFalse(briefs[4]["needs_context"])

    def test_unresolved_fragment_is_marked_without_inventing_subject(self):
        scene = "Sous une lumière froide, au centre de la salle."
        self.assertEqual(content.visual_briefs_for_scenes([scene]), [{
            "narration": scene,
            "visual_proposition": scene,
            "antecedent": None,
            "needs_context": True,
        }])

    def test_nonillustrable_explicit_claim_reuses_valid_neighbor(self):
        scenes = [
            "La pyramide de Khéops a une base carrée.",
            "Les méthodes de construction des pyramides demeurent incertaines.",
        ]
        planned = {"visual_plans": ["a square-based pyramid"],
                   "visual_controls": [{"kind": "explicit", "human_mode": "forbidden",
                                        "required_terms": ["pyramid"]}]}
        with patch.object(content.visual_planner, "plan_scenes", return_value=planned) as planner:
            bundle = content.visual_plan_bundle(scenes, title="Khéops")
        planner.assert_called_once()
        self.assertEqual(planner.call_args.args[0], [scenes[0]])
        self.assertTrue(bundle["visual_briefs"][1]["needs_context"])
        self.assertEqual(bundle["visual_controls"][1]["kind"], "contextual")
        self.assertEqual(bundle["visual_controls"][1]["context_scene_index"], 0)
        self.assertTrue(bundle["visual_plans"][1].startswith(bundle["visual_plans"][0]))

    def test_resolved_pronoun_claims_remain_illustrable(self):
        scenes = [
            "La pyramide de Khéops a une base carrée.",
            ("Elle fut considérée dans l'Antiquité comme la première "
             "des Sept Merveilles du monde."),
            ("Durant des millénaires, elle fut la construction humaine de tous les records : "
             "la plus haute, la plus volumineuse et la plus massive."),
        ]
        briefs = content.visual_briefs_for_scenes(scenes)
        for brief in briefs[1:]:
            self.assertEqual(brief["antecedent"], "La pyramide de Khéops")
            self.assertFalse(brief["needs_context"])
            self.assertNotRegex(brief["visual_proposition"], r"\b(?:elle|il|ils|elles)\b")


if __name__ == "__main__":
    unittest.main()
