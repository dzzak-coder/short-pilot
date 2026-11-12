import unittest
from unittest.mock import patch

from core import content, visual_planner


class VisualPlannerIsolationTests(unittest.TestCase):
    def setUp(self):
        visual_planner._cached_plan.cache_clear()
        self.addCleanup(visual_planner._cached_plan.cache_clear)

    def test_bad_middle_scene_keeps_other_validated_plans(self):
        scene = "Un minuteur rouge sur un bureau en bois"
        raw = {"index": 0, "kind": "explicit", "subject_type": "object",
               "human_mode": "forbidden", "still_life": True, "facts": [
                   {"category": "subject", "entity": "timer", "source_span": "minuteur",
                    "english": "a timer"},
                   {"category": "color", "entity": "timer", "source_span": "rouge",
                    "english": "red timer"},
                   {"category": "setting", "entity": "timer", "source_span": "sur un bureau en bois",
                    "english": "timer on a wooden desk"},
               ]}
        response = {"plans": [
            {**raw, "index": 0},
            {**raw, "index": 1},
        ]}
        scenes = [scene, "modifier - modifier le code - modifier Wikidata", scene]
        with patch.object(visual_planner, "_request_plans", return_value=response) as request:
            script = content.with_visual_plans({"scenes": scenes, "title": "minuteur", "warnings": []})
        self.assertEqual(request.call_count, 1)
        self.assertTrue(script["visual_plans"][0])
        self.assertTrue(script["visual_plans"][1])
        self.assertTrue(script["visual_plans"][2])
        self.assertNotIn("planning_error", script["visual_controls"][0])
        self.assertTrue(script["visual_controls"][1]["needs_context"])
        self.assertEqual(script["visual_controls"][1]["kind"], "contextual")
        self.assertNotIn("planning_error", script["visual_controls"][2])
        self.assertEqual(script["warnings"], [])

    def test_no_valid_anchor_reports_each_scene_instead_of_repeating_one_error(self):
        scenes = ["Un vase bleu sur la table", "Une transition éditoriale", "Une lampe rouge au sol"]
        raw = {"plans": [
            {"index": 0, "kind": "explicit", "subject_type": "object", "facts": []},
            {"index": 1, "kind": "contextual", "subject_type": "none", "facts": []},
            {"index": 2, "kind": "explicit", "subject_type": "object", "facts": []},
        ]}
        with patch.object(visual_planner, "_cached_plan") as title_plan:
            result = visual_planner._partial_result(raw, scenes, "vase et lampe")
        errors = [control["planning_error"] for control in result["visual_controls"]]
        self.assertEqual(result["visual_plans"], ["", "", ""])
        self.assertIn("Scène 1", errors[0])
        self.assertIn("Scène 2", errors[1])
        self.assertIn("Scène 3", errors[2])
        title_plan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
