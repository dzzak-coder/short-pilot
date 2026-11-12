import unittest

from core import visual_planner


class VisualWordCoverageTests(unittest.TestCase):
    def test_grammar_is_not_required_but_action_and_qualification_are(self):
        words = visual_planner._content_words(
            "Cette grande pyramide est un monument construit par les Égyptiens qui ont vécu là"
        )
        self.assertTrue({"grande", "pyramide", "monument", "construit", "égyptiens", "vécu"} <= words)
        self.assertFalse({"cette", "est", "un", "par", "les", "qui", "ont"} & words)

    def test_spatial_relation_requires_atom_even_when_preposition_is_function_word(self):
        scene = "Un vase rouge sur une table"
        facts = [
            {"category": "subject", "entity": "vase", "source_span": "vase", "english": "a vase"},
            {"category": "color", "entity": "vase", "source_span": "rouge", "english": "red vase"},
            {"category": "secondary", "entity": "table", "source_span": "table", "english": "a table"},
        ]
        item = {"index": 0, "kind": "explicit", "subject_type": "object",
                "human_mode": "forbidden", "still_life": True, "facts": facts}
        with self.assertRaisesRegex(visual_planner.VisualPlanningError, "relation spatiale"):
            visual_planner._validate_result({"plans": [item]}, [scene], "")
        item["facts"] = facts + [{"category": "setting", "entity": "vase",
                                  "source_span": "sur une table", "english": "vase on a table"}]
        result = visual_planner._validate_result({"plans": [item]}, [scene], "")
        self.assertTrue(result["visual_plans"][0])


if __name__ == "__main__":
    unittest.main()
