"""Text contract regressions: no live model or image generation in the suite."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core import aiimg, content, render, visual_constraints as vc, visual_planner


class SceneConstraintTests(unittest.TestCase):
    def atoms(self):
        return [
            {"category": "subject", "entity": "sketchbook", "source_span": "carnet", "english": "a sketchbook"},
            {"category": "color", "entity": "sketchbook", "source_span": "bleu", "english": "blue sketchbook"},
            {"category": "count", "entity": "sketchbook", "source_span": "Un", "english": "one sketchbook"},
            {"category": "state", "entity": "sketchbook", "source_span": "fermé", "english": "closed sketchbook",
             "state": "closed", "form": "bound_volume", "owner_source_span": "carnet", "binding_span": "carnet bleu fermé"},
            {"category": "secondary", "entity": "box", "source_span": "boîte", "english": "a box"},
            {"category": "state", "entity": "box", "source_span": "ouverte", "english": "open box",
             "state": "open", "form": "container", "owner_source_span": "boîte", "binding_span": "boîte ouverte"},
            {"category": "relation", "entity": "sketchbook", "source_span": "à côté", "english": "sketchbook beside box"},
            {"category": "setting", "entity": "sketchbook", "source_span": "sur table", "english": "sketchbook on table"},
            {"category": "lighting", "source_span": "au crépuscule", "english": "twilight"}]

    def test_closed_volume_requires_visible_exterior_and_entity_bound_counterexamples(self):
        contract = vc.compile_atoms(self.atoms(), still_life=True)
        self.assertIn("sketchbook with opaque outer cover facing the camera and covers pressed together", contract["positive_terms"])
        self.assertIn("sketchbook with exposed interior pages", contract["negative_terms"])
        self.assertIn("open sketchbook", contract["negative_terms"])
        self.assertNotIn("open box", contract["negative_terms"])
        self.assertNotIn("visible pages", contract["negative_terms"])

    def test_state_compilation_is_generic_across_physical_forms(self):
        for entity, form, evidence in [("suitcase", "container", "opening fully covered"),
                                       ("hatch", "door", "shut flush in its frame"),
                                       ("atlas", "bound_volume", "opaque outer cover")]:
            atom = {"category": "state", "entity": entity, "english": "closed " + entity,
                    "state": "closed", "form": form}
            result = vc.compile_atoms([atom])
            self.assertIn(evidence, ", ".join(result["positive_terms"]))
            self.assertIn("open " + entity, result["negative_terms"])

    def test_open_volume_has_pages_without_global_page_suppression(self):
        atoms = self.atoms()
        atoms[5].update(entity="atlas", english="open atlas", form="bound_volume")
        result = vc.compile_atoms(atoms)
        self.assertIn("atlas open with interior pages visible", result["positive_terms"])
        self.assertIn("closed atlas", result["negative_terms"])
        self.assertNotIn("interior pages", result["negative_terms"])

    def test_still_life_restriction_does_not_apply_to_other_scene_types(self):
        for subject, mode in [("landscape", "forbidden"), ("animal", "forbidden"),
                              ("hands", "hands_only"), ("person", "required")]:
            result = vc.compile_atoms(self.atoms(), still_life=True, subject_type=subject, human_mode=mode)
            self.assertFalse(result["still_life"])
            self.assertNotIn("additional foreground objects", result["negative_terms"])
        self.assertFalse(vc.compile_atoms(self.atoms())["still_life"])
        self.assertTrue(vc.compile_atoms(self.atoms(), still_life=True)["still_life"])

    def test_source_atoms_and_relations_survive_compilation_and_renderer(self):
        source = "Un carnet bleu fermé à côté boîte ouverte sur table au crépuscule"
        raw = {"plans": [{"index": 0, "kind": "explicit", "subject_type": "object", "still_life": True,
                          "facts": self.atoms()}]}
        bundle = visual_planner._validate_result(raw, [source], "")
        plan, control = bundle["visual_plans"][0], bundle["visual_controls"][0]
        prompt, negative = render._local_comfy_prompt("", "", "", "", plan, control)
        self.assertEqual(prompt, plan)
        self.assertEqual(control["source_facts"], self.atoms())
        workflow = aiimg.build_comfy_payload(prompt, negative, "model.safetensors", 720, 1280, 70001, visual_control=control)
        self.assertEqual(workflow["6"]["inputs"]["text"], plan)
        for term in control["required_terms"]:
            self.assertIn(term, plan)
        for term in control["negative_terms"]:
            self.assertEqual(workflow["7"]["inputs"]["text"].split(", ").count(term), 1)

    def test_source_number_is_not_silently_dropped(self):
        atoms = self.atoms()
        atoms[2]["source_span"] = "Un"
        raw = {"plans": [{"index": 0, "kind": "explicit", "subject_type": "object", "facts": atoms}]}
        with self.assertRaises(visual_planner.VisualPlanningError):
            visual_planner._validate_result(raw, ["2 carnets bleus fermés"], "")

    def test_invalid_state_or_unbound_owner_fails_closed(self):
        for field, value in [("state", "unknown"), ("form", "unknown"), ("entity", "")]:
            atom = copy.deepcopy(self.atoms()[3])
            atom[field] = value
            with self.assertRaises(ValueError):
                vc.compile_atoms([atom])

    def test_state_cannot_be_attached_to_a_nearby_different_object(self):
        facts = [
            {"category": "subject", "entity": "timer", "source_span": "minuteur", "english": "a timer"},
            {"category": "secondary", "entity": "planner", "source_span": "planning", "english": "a planner"},
            {"category": "state", "entity": "timer", "source_span": "fermé", "english": "closed timer",
             "state": "closed", "form": "container", "owner_source_span": "planning", "binding_span": "planning fermé"},
        ]
        with self.assertRaisesRegex(visual_planner.VisualPlanningError, "propriétaire"):
            visual_planner._validate_state_owners(facts, 1)

    def test_invalid_state_value_preempts_entity_diagnostics(self):
        facts = [{"category": "subject", "entity": "pyramid", "source_span": "pyramide",
                  "english": "a pyramid"},
                 {"category": "state", "entity": "text_display", "source_span": "édifiée",
                  "english": "constructed", "state": "constructed"}]
        with self.assertRaisesRegex(
                visual_planner.VisualPlanningError,
                r"constructed n'est pas un état \(attendu : open ou closed\)"):
            visual_planner._validate_state_values(facts, 4)

        raw = {"plans": [{"index": 0, "kind": "explicit", "subject_type": "object",
                          "human_mode": "forbidden", "facts": facts}]}
        with self.assertRaisesRegex(
                visual_planner.VisualPlanningError,
                r"constructed n'est pas un état \(attendu : open ou closed\)"):
            visual_planner._validate_result(raw, ["La pyramide fut édifiée."], "")

    def test_state_requires_a_source_binding_to_its_owner(self):
        facts = self.atoms()
        facts[3].pop("binding_span")
        raw = {"plans": [{"index": 0, "kind": "explicit", "subject_type": "object", "facts": facts}]}
        with self.assertRaisesRegex(visual_planner.VisualPlanningError, "liaison propriétaire/source"):
            visual_planner._validate_result(raw, ["Un carnet bleu fermé à côté boîte ouverte sur table au crépuscule"], "")

    def test_negative_cannot_exclude_requested_fact_or_all_functional_markings(self):
        for negative in ["blue sketchbook", "numbers", "text", "letters", "markings"]:
            atoms = self.atoms()
            atoms[0]["negative_terms"] = [negative]
            with self.assertRaises(ValueError):
                vc.compile_atoms(atoms)
        for forbidden in ("text", "words", "letters", "numbers", "digits"):
            self.assertNotIn(forbidden, aiimg.NEG_COMFY.split(", "))
        for targeted in ("overlay text", "captions", "subtitles", "watermark", "logo"):
            self.assertIn(targeted, aiimg.NEG_COMFY.split(", "))

    def test_negatives_deduplicate_case_whitespace_and_all_entry_points(self):
        control = {"human_mode": "forbidden", "negative_terms": ["open sketchbook", "OPEN  sketchbook", "PERSON", "logo"]}
        plan, scene_negative = render._local_comfy_prompt("", "", "", "", "A closed sketchbook", control)
        self.assertEqual(scene_negative, "open sketchbook, PERSON, logo")
        workflow = aiimg.build_comfy_payload(plan, scene_negative, "model.safetensors", 720, 1280, 70001, visual_control=control)
        terms = [" ".join(t.casefold().split()) for t in workflow["7"]["inputs"]["text"].split(",")]
        self.assertEqual(len(terms), len(set(terms)))
        self.assertEqual(terms.count("person"), 1)

    def test_legacy_experiments_cannot_replace_positive_or_add_nodes(self):
        control = {"human_mode": "forbidden", "global_context_prompt": "empty room", "structural_guide": {"enabled": True},
                   "regions": [{"prompt": "wrong object"}]}
        workflow = aiimg.build_comfy_payload("A closed atlas", "", "model.safetensors", 720, 1280, 70001, visual_control=control)
        self.assertEqual(set(workflow), {"3", "4", "5", "6", "7", "8", "9"})
        self.assertEqual(workflow["6"]["inputs"]["text"], "A closed atlas")
        self.assertEqual(workflow["3"]["inputs"]["positive"], ["6", 0])
        self.assertEqual(workflow["3"]["inputs"]["negative"], ["7", 0])
        self.assertEqual(workflow["3"]["inputs"]["steps"], 6)
        self.assertEqual(workflow["3"]["inputs"]["cfg"], 2)

    def test_positive_is_not_even_whitespace_normalized(self):
        original = "A closed atlas,  twilight "
        prompt, _ = render._local_comfy_prompt("", "", "", "", original)
        self.assertEqual(aiimg.build_comfy_payload(prompt, "", "model.safetensors", 720, 1280, 70001)["6"]["inputs"]["text"], original)

    def test_report_plan_mismatch_stops_before_submission(self):
        with patch.object(aiimg.requests, "post") as post:
            with self.assertRaises(ValueError):
                aiimg.gen_comfyui("An atlas", "unused", report={"visual_plan": "A vase"})
            post.assert_not_called()

    def test_executed_negative_tampering_is_rejected_without_download_or_retry(self):
        posted = []
        def post(url, **kwargs):
            posted.append(copy.deepcopy(kwargs["json"]["prompt"]))
            return SimpleNamespace(status_code=200, json=lambda: {"prompt_id": "tampered"})
        def get(url, **kwargs):
            self.assertNotIn("/view?", url)
            changed = copy.deepcopy(posted[0])
            changed["7"]["inputs"]["negative_prompt"] = "wrong negative"
            return SimpleNamespace(status_code=200, json=lambda: {"tampered": {
                "prompt": [0, "tampered", changed], "outputs": {"10": {"images": [{"filename": "x.png"}]}}}})
        import tempfile
        with tempfile.TemporaryDirectory() as folder, patch.object(aiimg.requests, "post", side_effect=post), \
                patch.object(aiimg.requests, "get", side_effect=get), patch.object(aiimg.time, "sleep"):
            report = {}
            self.assertIsNone(aiimg.gen_comfyui("An atlas", folder, ckpt=aiimg.QWEN_TURBO_UNET, report=report))
        self.assertEqual(len(posted), 1)
        self.assertIsNone(report["negative_prompt_verified"])
        self.assertIsNone(report["executed_negative_prompt"])

    def test_version_five_invalidates_previous_plan_fingerprints(self):
        current = content.visual_plan_fingerprint(["A scene"])
        with patch.object(content, "VISUAL_PLANNER_VERSION", 4):
            self.assertNotEqual(content.visual_plan_fingerprint(["A scene"]), current)
        self.assertGreaterEqual(content.VISUAL_PLANNER_VERSION, 6)


if __name__ == "__main__":
    unittest.main()
