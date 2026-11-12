# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import json
import io
import tempfile
from PIL import Image

from core import aiimg, content, render, visual_planner, visual_constraints


class LocalVisualTests(unittest.TestCase):
    TIMER_SCENE = "Un minuteur rouge sur un bureau en bois, à côté d’un planning fermé, lumière du matin"

    def setUp(self):
        visual_planner._cached_plan.cache_clear()
        self.provider = patch.object(visual_planner, "_request_plans", side_effect=self.model_response)
        self.provider.start()
        self.addCleanup(self.provider.stop)
        self.addCleanup(visual_planner._cached_plan.cache_clear)

    @classmethod
    def model_response(cls, scenes, title, niche, language, feedback=""):
        # Recorded-style semantic responses: these test the contract and
        # transport, not the intelligence or visual accuracy of a model.
        cases = {
            cls.TIMER_SCENE: ("forbidden", [("minuteur rouge", "red kitchen timer"),
                ("bureau en bois", "wooden desk"), ("à côté d’un planning fermé", "next to a closed planner"),
                ("lumière du matin", "morning sunlight")]),
            "Un minuteur bleu sonne sur une table en bois, lumière du soir": ("forbidden", [
                ("minuteur bleu", "blue kitchen timer"), ("sonne", "rings"),
                ("table en bois", "wooden table"), ("lumière du soir", "evening sunlight")]),
            "Un paysage de fjord norvégien enneigé au crépuscule, sans humain": ("forbidden", [
                ("paysage de fjord norvégien enneigé", "landscape of a snow-covered Norwegian fjord"), ("crépuscule", "twilight")]),
            "Un axolotl rose nage entre les rochers dans une rivière": ("forbidden", [
                ("axolotl rose", "pink axolotl"), ("nage", "swims"), ("rochers", "rocks"), ("rivière", "river")]),
            "Deux mains pétrissent une pâte sur une table en marbre": ("hands_only", [
                ("Deux mains", "two hands"), ("pétrissent une pâte", "kneading dough"), ("table en marbre", "marble table")]),
            "Une astronome rousse observe Saturne depuis un observatoire la nuit": ("required", [
                ("astronome rousse", "red-haired astronomer"), ("observe Saturne", "observing Saturn"),
                ("observatoire", "observatory"), ("la nuit", "at night")]),
            "La procrastination coûte du temps.": ("forbidden", [("procrastination", "unfinished paper planner beside an idle timer on a desk")]),
            "Organise ton planning ce soir.": ("hands_only", [("Organise ton planning", "two hands arranging a paper planner on a desk")]),
        }
        result = []
        for index, scene in enumerate(scenes):
            contextual = scene in ("Abonne-toi pour la suite.", "Regarde bien.", "Et maintenant ?")
            origin = title if contextual else scene
            if origin not in cases:
                result.append({"index": index, "kind": "unresolved", "human_mode": "auto", "reason": "Plan visuel requis"})
                continue
            mode, pairs = cases[origin]
            kind = "contextual" if contextual else ("metaphor" if scene.startswith(("La procrastination", "Organise")) else "explicit")
            result.append({"index": index, "kind": kind, "human_mode": mode,
                           "subject_type": {"required": "person", "hands_only": "hands"}.get(mode,
                               "landscape" if "fjord" in scene else "animal" if "axolotl" in scene else "object"),
                           "description": ", ".join(p[1] for p in pairs), "facts": [
                               {"category": "subject", "entity": b, "source_span": a, "english": b} for a, b in pairs]})
            if origin == cls.TIMER_SCENE:
                result[-1]["still_life"] = True
                result[-1]["facts"] = [
                    {"category": "subject", "entity": "kitchen timer", "source_span": "minuteur", "english": "a kitchen timer"},
                    {"category": "color", "entity": "kitchen timer", "source_span": "rouge", "english": "red kitchen timer"},
                    {"category": "setting", "entity": "kitchen timer", "source_span": "sur un bureau en bois", "english": "kitchen timer on a wooden desk"},
                    {"category": "secondary", "entity": "planner", "source_span": "planning", "english": "a planner"},
                    {"category": "state", "entity": "planner", "source_span": "fermé", "english": "closed planner", "state": "closed", "form": "bound_volume", "owner_source_span": "planning", "binding_span": "planning fermé"},
                    {"category": "relation", "entity": "kitchen timer", "source_span": "à côté d’un planning", "english": "kitchen timer beside planner"},
                    {"category": "lighting", "source_span": "lumière du matin", "english": "morning sunlight"}]
            elif origin == "Un minuteur bleu sonne sur une table en bois, lumière du soir":
                result[-1]["facts"].append({"category": "setting", "entity": "blue kitchen timer",
                    "source_span": "sur une table en bois", "english": "blue kitchen timer on a wooden table"})
            elif origin == "Un axolotl rose nage entre les rochers dans une rivière":
                result[-1]["facts"].extend([
                    {"category": "relation", "entity": "pink axolotl",
                     "source_span": "entre les rochers", "english": "pink axolotl between rocks"},
                    {"category": "setting", "entity": "pink axolotl",
                     "source_span": "dans une rivière", "english": "pink axolotl in a river"},
                ])
            elif origin == "Deux mains pétrissent une pâte sur une table en marbre":
                result[-1]["facts"].append({"category": "setting", "entity": "two hands",
                    "source_span": "sur une table en marbre", "english": "two hands on a marble table"})
        return {"plans": result}

    def test_explicit_subject_reaches_positive_clip_intact_in_both_modes(self):
        bundle = content.visual_plan_bundle([self.TIMER_SCENE], language="fr")
        plan = bundle["visual_plans"][0]
        for detail in ("red kitchen timer", "wooden desk", "closed planner", "morning sunlight"):
            self.assertIn(detail, plan)
        self.assertEqual(bundle["visual_controls"][0]["human_mode"], "forbidden")
        for quality in (False, True):
            prompt, negative = render._local_comfy_prompt(self.TIMER_SCENE, "unrelated context", "sujet", "auto",
                                                         plan, bundle["visual_controls"][0])
            payload = aiimg.build_comfy_payload(prompt, negative, "model.safetensors", 720, 1280, 70001,
                                                quality_mode=quality, human_mode="forbidden")
            sampler = payload["5" if quality else "3"]
            node = payload[sampler["inputs"]["positive"][0]]
            self.assertEqual(node["class_type"], "CLIPTextEncode")
            self.assertEqual(node["inputs"]["text"], plan)

    def test_image_assignments_keep_subject_and_vary_framing(self):
        assignments = [
            {"scene_index": 1, "image_index": 1, "anchor_id": "artifact:timer"},
            {"scene_index": 1, "image_index": 2, "anchor_id": "artifact:planner"},
        ]
        anchors = [
            {"id": "artifact:timer", "label": "minuteur rouge"},
            {"id": "artifact:planner", "label": "planning fermé"},
        ]
        bundle = content.visual_plan_bundle(
            [self.TIMER_SCENE], language="fr",
            image_assignments=assignments, visual_anchors=anchors)
        self.assertEqual(len(bundle["image_plans"]), 2)
        self.assertNotEqual(bundle["visual_plans"][0], bundle["visual_plans"][1])
        self.assertEqual(
            [control["anchor_id"] for control in bundle["visual_controls"]],
            ["artifact:timer", "artifact:planner"])
        for prompt in bundle["visual_plans"]:
            self.assertIn(self.TIMER_SCENE, prompt)
        self.assertEqual(
            bundle["visual_controls"][0]["canonical_entity"],
            bundle["visual_controls"][1]["canonical_entity"])

    def test_literal_attributes_and_action_are_not_a_timer_fixture(self):
        plan = content.visual_plans_for_scenes(["Un minuteur bleu sonne sur une table en bois, lumière du soir"])[0]
        for detail in ("blue kitchen timer", "rings", "wooden table", "evening sunlight"):
            self.assertIn(detail, plan)
        self.assertNotIn("red", plan)

    def test_local_concrete_source_is_one_intact_scene(self):
        script = content.generate_script(niche="sujet", topic=self.TIMER_SCENE, source="local")
        self.assertEqual(script["scenes"], [self.TIMER_SCENE])
        self.assertIn("closed planner", script["visual_plans"][0])

    def test_unknown_subject_is_not_replaced_with_a_generic_object(self):
        bundle = content.visual_plan_bundle(["Un minuteur écarlate suspendu à un drone"])
        self.assertEqual(bundle["visual_plans"], [""])
        self.assertIn("planning_error", bundle["visual_controls"][0])
        self.assertEqual(content.visual_plans_for_scenes(["Un perroquet rouge dans une cuisine"]), [""])

    def test_transport_posts_and_verifies_the_executed_positive(self):
        from types import SimpleNamespace
        plan = content.visual_plans_for_scenes([self.TIMER_SCENE])[0]
        posted = []
        pixels = io.BytesIO()
        Image.effect_noise((720, 1280), 80).convert("RGB").save(pixels, format="PNG")
        def post(url, **kwargs):
            posted.append(json.loads(json.dumps(kwargs["json"]["prompt"])))
            return SimpleNamespace(status_code=200, json=lambda: {"prompt_id": "test-timer"})
        def get(url, **kwargs):
            if "/view?" in url:
                return SimpleNamespace(status_code=200, content=pixels.getvalue())
            entry = {"prompt": [0, "test-timer", posted[0]], "status": {"completed": True},
                     "outputs": {"10": {"images": [{"filename": "timer.png"}]}}}
            return SimpleNamespace(status_code=200, json=lambda: {"test-timer": entry})
        with tempfile.TemporaryDirectory() as folder, patch.object(aiimg.requests, "post", side_effect=post), \
                patch.object(aiimg.requests, "get", side_effect=get), patch.object(aiimg.time, "sleep"):
            report = {}
            self.assertIsNotNone(aiimg.gen_comfyui(plan, folder, ckpt=aiimg.QWEN_TURBO_UNET, seed=70001,
                                                  human_mode="forbidden", report=report))
            self.assertEqual(posted[0]["7"]["inputs"]["prompt"], plan)
            self.assertEqual(report["executed_positive_prompt"], plan)
            self.assertTrue(report["positive_prompt_verified"])
            self.assertEqual(report["executed_negative_prompt"], "")
            self.assertFalse(report["negative_prompt_active"])
            self.assertIsNone(report["negative_prompt_verified"])

    def test_landscape_animal_hands_and_person_keep_specific_details(self):
        cases = [
            ("Un paysage de fjord norvégien enneigé au crépuscule, sans humain", "forbidden", ["Norwegian fjord", "twilight"]),
            ("Un axolotl rose nage entre les rochers dans une rivière", "forbidden", ["pink axolotl", "swims", "river"]),
            ("Deux mains pétrissent une pâte sur une table en marbre", "hands_only", ["two hands", "kneading dough", "marble table"]),
            ("Une astronome rousse observe Saturne depuis un observatoire la nuit", "required", ["red-haired astronomer", "observing Saturn", "at night"]),
        ]
        for scene, mode, expected in cases:
            with self.subTest(scene=scene):
                bundle = content.visual_plan_bundle([scene])
                self.assertEqual(bundle["visual_controls"][0]["human_mode"], mode)
                for detail in expected:
                    self.assertIn(detail, bundle["visual_plans"][0])

    def test_hook_transition_and_cta_keep_global_subject(self):
        bundle = content.visual_plan_bundle(["Regarde bien.", self.TIMER_SCENE, "Et maintenant ?", "Abonne-toi pour la suite."],
                                             title=self.TIMER_SCENE)
        for plan in bundle["visual_plans"]:
            self.assertIn("red kitchen timer", plan)
            self.assertIn("closed planner", plan)
        cta_only = content.visual_plan_bundle(["Abonne-toi pour la suite."], title=self.TIMER_SCENE)
        self.assertIn("red kitchen timer", cta_only["visual_plans"][0])

    def test_required_terms_block_mutated_prompt_before_network(self):
        control = {"human_mode": "forbidden", "required_terms": ["red kitchen timer", "closed planner"]}
        with patch.object(aiimg.requests, "post") as post:
            with self.assertRaises(visual_planner.VisualPlanningError):
                aiimg.gen_comfyui("A vase on a desk", "unused", visual_control=control)
            post.assert_not_called()
        with self.assertRaises(visual_planner.VisualPlanningError):
            render._local_comfy_prompt("", "", "", "", "red kitchen timer, open planner", control)

    def test_required_terms_do_not_match_words_on_the_wrong_objects(self):
        control = {"required_terms": ["red timer", "closed planner"], "negative_terms": []}
        with self.assertRaises(visual_planner.VisualPlanningError):
            visual_planner.validate_required_terms("A closed red timer beside an open planner.", control)

    def test_free_form_summary_cannot_drop_a_grounded_attribute(self):
        raw = self.model_response([self.TIMER_SCENE], "", "", "fr")
        raw["plans"][0]["description"] = "A kitchen timer on a desk"
        bundle = visual_planner._validate_result(raw, [self.TIMER_SCENE], "")
        self.assertIn("red kitchen timer", bundle["visual_plans"][0])
        self.assertIn("closed planner", bundle["visual_plans"][0])

    def test_compiler_keeps_a_specific_canonical_subject_in_a_natural_prompt(self):
        raw = self.model_response([self.TIMER_SCENE], "", "", "fr")
        bundle = visual_planner._validate_result(raw, [self.TIMER_SCENE], "")
        prompt = bundle["visual_plans"][0]
        self.assertIn("red kitchen timer", prompt)
        self.assertIn("on a wooden desk beside a closed planner", prompt)
        self.assertIn("opaque outer cover", prompt)
        self.assertIn("no interior pages", prompt)
        self.assertNotIn(";", prompt)

    def test_specific_animal_and_person_never_compile_to_a_generic_category(self):
        cases = [
            ("Un axolotl rose nage entre les rochers dans une rivière", "a pink axolotl"),
            ("Une astronome rousse observe Saturne depuis un observatoire la nuit", "a red-haired astronomer"),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                raw = self.model_response([source], "", "", "fr")
                bundle = visual_planner._validate_result(raw, [source], "")
                self.assertIn(expected, bundle["visual_plans"][0])
                self.assertNotIn("an animal", bundle["visual_plans"][0])
                self.assertNotIn("an object", bundle["visual_plans"][0])

    def test_dependent_fact_must_reuse_its_canonical_owner(self):
        raw = self.model_response([self.TIMER_SCENE], "", "", "fr")
        raw["plans"][0]["facts"][1]["entity"] = "object"
        with self.assertRaisesRegex(
                visual_planner.VisualPlanningError,
                r"fait color d'entité 'object'.*entités déclarées : kitchen timer, planner"):
            visual_planner._validate_result(raw, [self.TIMER_SCENE], "")

    def test_canonical_entity_english_mismatch_names_fact_and_declared_owners(self):
        facts = [{"category": "subject", "entity": "pyramid", "english": "the monument"}]
        with self.assertRaisesRegex(
                visual_planner.VisualPlanningError,
                r"fait subject d'entité 'pyramid'.*texte anglais 'the monument'.*"
                r"entités déclarées : pyramid"):
            visual_planner._validate_canonical_entities(facts, 4)

    def test_setting_and_lighting_do_not_require_owner_name_but_relation_does(self):
        frame_facts = [
            {"category": "subject", "entity": "pyramid", "english": "a pyramid"},
            {"category": "setting", "entity": "pyramid", "english": "in Giza in Egypt"},
            {"category": "lighting", "english": "desert daylight"},
        ]
        visual_planner._validate_canonical_entities(frame_facts, 3)
        with self.assertRaisesRegex(visual_planner.VisualPlanningError, "fait relation"):
            visual_planner._validate_canonical_entities(
                frame_facts + [{"category": "relation", "entity": "pyramid",
                                "english": "beside the funerary complex"}], 3)

    def test_compiled_required_terms_match_every_scene_type(self):
        cases = [
            (self.TIMER_SCENE, True),
            ("Un paysage de fjord norvégien enneigé au crépuscule, sans humain", False),
            ("Deux mains pétrissent une pâte sur une table en marbre", False),
            ("Une astronome rousse observe Saturne depuis un observatoire la nuit", False),
        ]
        for source, is_still_life in cases:
            with self.subTest(source=source):
                bundle = content.visual_plan_bundle([source], language="fr")
                plan, control = bundle["visual_plans"][0], bundle["visual_controls"][0]
                visual_planner.validate_required_terms(plan, control)
                restriction = "uncluttered still life showing only the described objects"
                self.assertEqual(restriction in plan, is_still_life)
                self.assertEqual(any(restriction in term for term in control["required_terms"]), is_still_life)

    def test_compiler_preserves_every_atomic_category_as_final_text(self):
        facts = [
            {"category": "subject", "entity": "kitchen timer", "english": "a kitchen timer"},
            {"category": "color", "entity": "kitchen timer", "english": "red kitchen timer"},
            {"category": "count", "entity": "kitchen timer", "english": "two kitchen timers"},
            {"category": "state", "entity": "kitchen timer", "english": "closed kitchen timer", "state": "closed", "form": "container"},
            {"category": "action", "entity": "kitchen timer", "english": "kitchen timer ringing"},
            {"category": "setting", "entity": "kitchen timer", "english": "kitchen timer on a wooden desk"},
            {"category": "secondary", "entity": "planner", "english": "a planner"},
            {"category": "color", "entity": "planner", "english": "yellow planner"},
            {"category": "state", "entity": "planner", "english": "closed planner", "state": "closed", "form": "bound_volume"},
            {"category": "relation", "entity": "kitchen timer", "english": "kitchen timer beside planner"},
            {"category": "relation", "entity": "kitchen timer", "english": "kitchen timer facing planner"},
            {"category": "lighting", "english": "morning light"},
        ]
        plan, required = visual_constraints.compile_final_prompt(facts, still_life=True)
        for fact in facts:
            expected = fact["english"].removeprefix("a ").removeprefix("an ")
            self.assertIn(expected, plan)
        visual_planner.validate_required_terms(plan, {"required_terms": required, "negative_terms": []})

    def test_uncovered_source_colour_is_rejected(self):
        raw = self.model_response([self.TIMER_SCENE], "", "", "fr")
        raw["plans"][0]["facts"] = [f for f in raw["plans"][0]["facts"] if f["category"] != "color"]
        with self.assertRaises(visual_planner.VisualPlanningError):
            visual_planner._validate_result(raw, [self.TIMER_SCENE], "")

    def test_no_provider_returns_actionable_error(self):
        with patch.object(visual_planner, "_request_plans", side_effect=visual_planner.VisualPlanningError("Ollama indisponible")):
            bundle = content.visual_plan_bundle([self.TIMER_SCENE])
        self.assertEqual(bundle["visual_plans"], [""])
        self.assertIn("Ollama indisponible", bundle["visual_controls"][0]["planning_error"])

    def test_human_negative_has_one_owner_and_one_occurrence(self):
        plan, negative = render._local_comfy_prompt("", "", "", "", "A timer on a desk", {"human_mode": "forbidden"})
        self.assertEqual(negative, "")
        payload = aiimg._workflow(plan, "model.safetensors", 1, human_mode="forbidden")
        self.assertEqual(payload["7"]["inputs"]["text"].count(aiimg.HUMAN_FORBIDDEN_NEGATIVE), 1)

    def test_api_rejects_manual_plan_missing_required_terms_without_queueing(self):
        import app as webapp
        script = {"scenes": [self.TIMER_SCENE], "title": "timer", "visual_plans_locked": True,
                  "visual_plans": ["A vase on a desk"],
                  "visual_controls": [{"human_mode": "forbidden", "required_terms": ["red kitchen timer"]}]}
        with webapp.app.test_request_context("/api/render", json={"script": script, "visuals": "comfy"}), \
                patch.object(webapp, "get_settings", return_value=webapp.DEFAULT_SETTINGS), \
                patch.object(webapp, "new_job") as queued:
            response, status = webapp.api_render()
        self.assertEqual(status, 422)
        self.assertIn("red kitchen timer", response.get_json()["error"])
        queued.assert_not_called()

    def test_fast_payload_is_vertical_and_reproducible(self):
        workflow = aiimg.build_comfy_payload("A planet in space", "", "model.safetensors", 720, 1280, 70001)
        self.assertEqual(workflow["3"]["inputs"]["seed"], 70001)
        self.assertEqual(workflow["5"]["inputs"]["width"], 720)
        self.assertEqual(workflow["5"]["inputs"]["height"], 1280)
        self.assertEqual(workflow["3"]["inputs"]["scheduler"], "sgm_uniform")

    def test_plans_are_concrete_english_and_aligned(self):
        scenes = ["La procrastination coûte du temps.", "Organise ton planning ce soir."]
        bundle = content.visual_plan_bundle(scenes, title="Productivité", niche="productivite", language="fr")
        self.assertEqual(len(bundle["visual_plans"]), 2)
        self.assertEqual(len(bundle["visual_controls"]), 2)
        self.assertIn("planner", bundle["visual_plans"][0].lower())
        self.assertNotIn(scenes[0], bundle["visual_plans"][0])
        self.assertTrue(bundle["visual_plan_fingerprint"])

    def test_fingerprint_changes_when_scene_changes_without_count_change(self):
        before = content.visual_plan_fingerprint(["Une planète tourne.", "Fin."], title="Espace", niche="science", language="fr")
        after = content.visual_plan_fingerprint(["Une fusée décolle.", "Fin."], title="Espace", niche="science", language="fr")
        self.assertNotEqual(before, after)

    def test_human_suppression_is_structured_only(self):
        _, forbidden = aiimg._conditioning_text("A planet in space", "", "forbidden")
        _, required = aiimg._conditioning_text("A person running", "", "required")
        _, hands = aiimg._conditioning_text("Hands writing", "", "hands_only")
        self.assertIn("person, people, human", forbidden)
        self.assertNotIn("person, people, human", required)
        self.assertNotIn("person, people, human, man, woman, child, face, portrait, hands", hands)

    def test_renderer_does_not_mix_narration_into_visual_prompt(self):
        plan = "Overhead close-up of a weekly planner being organized on a wooden desk, warm morning light, vertical composition"
        prompt, negative = render._local_comfy_prompt("Texte narratif long", "Tout le script", "productivite", "auto", plan,
                                                       {"human_mode": "forbidden"})
        self.assertEqual(prompt, plan)
        self.assertEqual(negative, "")

    def test_quality_detailer_is_absent_for_non_human_scene(self):
        landscape = aiimg._quality_workflow("A rocket over Mars", "model.safetensors", 42, human_mode="forbidden")
        person = aiimg._quality_workflow("A person running", "model.safetensors", 42, human_mode="required")
        self.assertNotIn("22", landscape)
        self.assertEqual(person["22"]["class_type"], "FaceDetailer")
        self.assertLessEqual(person["22"]["inputs"]["denoise"], 0.25)

    def test_checkpoint_rejects_urls_and_paths(self):
        self.assertEqual(aiimg.checkpoint_name("model.safetensors"), "model.safetensors")
        self.assertEqual(aiimg.checkpoint_name("http://remote/model.safetensors"), "")
        self.assertEqual(aiimg.checkpoint_name("..\\model.safetensors"), "")


if __name__ == "__main__":
    unittest.main()
