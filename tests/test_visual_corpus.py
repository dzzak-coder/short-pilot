import unittest

from core import content, visual_corpus


class VisualCorpusTests(unittest.TestCase):
    def test_extracts_only_verbatim_concrete_anchors_and_deduplicates(self):
        text = (
            "La théorie reste incertaine. "
            "Le couloir ascendant mène à la chambre du roi. "
            "Le couloir ascendant contient des blocs de granit rose."
        )
        anchors = visual_corpus.extract_visual_anchors([
            {"title": "Source locale abstraite ou web", "text": text}
        ])
        labels = [item["label"].casefold() for item in anchors]
        self.assertEqual(labels.count("couloir ascendant"), 1)
        self.assertIn("chambre du roi", labels)
        self.assertIn("blocs de granit rose", labels)
        self.assertNotIn("théorie", labels)
        for item in anchors:
            self.assertIn(item["label"], item["evidence"])

    def test_budget_reports_required_numbers_and_verdict(self):
        report = visual_corpus.visual_budget(
            90, 13, seconds_per_image=4, corpus_word_count=3000, anchors_before=2)
        self.assertEqual(report["images_needed"], 23)
        self.assertEqual(report["anchors_required"], {
            "minimum_50_percent": 12, "target_60_percent": 14})
        self.assertEqual(report["verdict"], "thin")
        self.assertEqual(report["anchors_available_before_corpus"], 2)
        self.assertEqual(report["anchors_gain"], 11)

    def test_budget_is_source_origin_agnostic(self):
        local = visual_corpus.extract_visual_anchors([{"text": "Une statue devant un temple."}])
        web = visual_corpus.extract_visual_anchors([{"text": "Une statue devant un temple."}])
        self.assertEqual(local, web)

    def test_seconds_per_image_is_bounded(self):
        with self.assertRaises(ValueError):
            visual_corpus.visual_budget(30, 4, seconds_per_image=2.9)
        with self.assertRaises(ValueError):
            visual_corpus.visual_budget(30, 4, seconds_per_image=5.1)

    def test_comparison_objects_are_rejected_but_subject_parts_remain(self):
        text = (
            "Elle était plus haute que la basilique Saint-Pierre de Rome. "
            "Elle détint le record jusqu'en 1311, année qui vit l'érection de la cathédrale de Lincoln. "
            "Contrairement à la pyramide de Khéphren, elle conserve un revêtement de calcaire."
        )
        anchors = visual_corpus.extract_visual_anchors([
            {"title": "Pyramide de Khéops", "text": text}
        ])
        labels = {item["label"].casefold() for item in anchors}
        self.assertNotIn("basilique", labels)
        self.assertNotIn("cathédrale", labels)
        self.assertNotIn("pyramide de khéphren", labels)
        self.assertIn("revêtement de calcaire", labels)

    def test_reported_historical_objects_are_contextual(self):
        anchors = visual_corpus.extract_visual_anchors([{
            "title": "Pyramide de Khéops",
            "text": ("Selon lequel le roi reposait sur une île, entourée d'un canal. "
                     "La chambre du roi contient un sarcophage."),
        }])
        scopes = {item["label"].casefold(): item["scope"] for item in anchors}
        self.assertEqual(scopes["île"], "contextual")
        self.assertEqual(scopes["canal"], "contextual")
        self.assertEqual(scopes["chambre du roi"], "principal")

    def test_distribution_reports_zero_one_and_multiple(self):
        anchors = visual_corpus.extract_visual_anchors([{
            "title": "Pyramide de Khéops",
            "text": ("Le sarcophage est vide. "
                     "Le couloir ascendant mène à la chambre du roi."),
        }])
        distribution = visual_corpus.distribute_visual_anchors(
            ["Le sarcophage.", "Le couloir ascendant et la chambre du roi.",
             "Une controverse abstraite."], anchors)
        self.assertEqual(distribution["scenes_with_0_anchors"], 1)
        self.assertEqual(distribution["scenes_with_1_anchor"], 1)
        self.assertEqual(distribution["scenes_with_2plus_anchors"], 1)
        self.assertEqual(distribution["orphan_scene_indices"], [3])
        self.assertEqual(distribution["distinct_anchors_used"], 3)

    def test_frequent_term_cannot_assign_anchor_by_itself(self):
        anchors = visual_corpus.extract_visual_anchors([{
            "title": "Pyramide de Khéops",
            "text": ("La construction utilise des blocs bouchons. "
                     "La construction comprend une grande galerie."),
        }])
        distribution = visual_corpus.distribute_visual_anchors(
            ["La construction bat des records.",
             "La construction reste mystérieuse.",
             "La construction demeure incertaine.",
             "La grande galerie traverse le monument."], anchors)
        self.assertIn("construction", distribution["generic_terms_excluded_as_sole_signal"])
        self.assertEqual(distribution["scenes"][0]["anchors_available"], 0)
        self.assertGreaterEqual(distribution["scenes"][3]["anchors_available"], 1)

    def test_distribution_reports_distinct_usage_and_reuse(self):
        anchors = visual_corpus.extract_visual_anchors([{
            "text": "Le sarcophage repose dans la chambre du roi.",
        }])
        distribution = visual_corpus.distribute_visual_anchors(
            ["Le sarcophage est vide.", "Ce sarcophage est en pierre."], anchors)
        self.assertEqual(distribution["distinct_anchors_used"], 1)
        self.assertEqual(distribution["anchor_reuse"], [{
            "anchor_id": "artifact:sarcophage",
            "label": "sarcophage",
            "scene_indices": [1, 2],
            "scene_count": 2,
            "reuse_count": 1,
            "scene_share_rate": 1.0,
        }])

    def test_inflected_second_is_not_a_matching_term(self):
        self.assertNotIn("second", visual_corpus._tokens("une minute et trente secondes"))

    def test_budget_uses_scene_coverage_and_proposes_sustainable_duration(self):
        report = visual_corpus.visual_budget(
            90, 11, scene_count=12, scenes_without_anchor=6,
            visually_distinct_subjects=7)
        self.assertEqual(report["verdict"], "insufficient")
        self.assertEqual(report["scene_coverage"]["scenes_without_anchor_rate"], .5)
        self.assertEqual(report["sustainable_duration_seconds"], 45.0)
        self.assertEqual(report["visually_distinct_subjects"], 7)

    def test_base_labels_collapse_to_one_visual_subject(self):
        anchors = [
            {"id": "site:plateau_de_gizeh", "label": "plateau de Gizeh",
             "scope": "principal", "evidence": "plateau de Gizeh"},
            {"id": "construction_part:stone_courses", "label": "assises de la pyramide",
             "scope": "principal", "evidence": "assises de la pyramide"},
            {"id": "construction_part:socle_rocheux", "label": "socle rocheux",
             "scope": "principal", "evidence": "socle rocheux"},
            {"id": "site:roche_naturelle", "label": "roche naturelle",
             "scope": "principal", "evidence": "roche naturelle"},
        ]
        distribution = visual_corpus.distribute_visual_anchors([
            "Le plateau de Gizeh, les assises de la pyramide, le socle rocheux "
            "et la roche naturelle forment la base."
        ], anchors)
        self.assertEqual(distribution["distinct_anchors_used"], 4)
        self.assertEqual(distribution["visually_distinct_subjects"], 1)
        self.assertEqual(len(distribution["visual_subjects"][0]["anchor_ids"]), 4)

    def test_coverage_guided_selection_prefers_concrete_facts_in_source_order(self):
        anchors = visual_corpus.extract_visual_anchors([{
            "text": ("Le sarcophage repose dans la chambre du roi. "
                     "La grande galerie rejoint le couloir ascendant."),
        }])
        groups = [
            ["Les théories restent très controversées aujourd'hui."],
            ["Le sarcophage repose dans la chambre du roi."],
            ["Cette histoire bat tous les records connus."],
            ["La grande galerie rejoint le couloir ascendant."],
        ]
        selected = content._coverage_guided_groups(
            groups, anchors, base_words=0, wanted=15)
        flattened = [sentence for group in selected for sentence in group]
        self.assertEqual(flattened, [groups[1][0], groups[3][0]])

    def test_same_generic_terms_can_be_fixed_across_before_after_comparison(self):
        anchors = visual_corpus.extract_visual_anchors([{
            "title": "Pyramide de Khéops",
            "text": "La grande galerie contient un sarcophage.",
        }])
        fixed = ["construction", "kheop", "pyramide"]
        before = visual_corpus.distribute_visual_anchors(
            ["Construction de la pyramide de Khéops.", "La grande galerie."],
            anchors, generic_terms=fixed)
        after = visual_corpus.distribute_visual_anchors(
            ["La chambre rejoint la grande galerie.", "Le sarcophage est vide."],
            anchors, generic_terms=fixed)
        self.assertEqual(before["generic_terms_excluded_as_sole_signal"], fixed)
        self.assertEqual(after["generic_terms_excluded_as_sole_signal"], fixed)
        self.assertTrue(after["generic_terms_fixed_for_comparison"])

    def test_indirect_anchor_propagation_is_capped_at_three_scenes(self):
        anchors = [{
            "id": "artifact:sarcophage", "label": "sarcophage", "scope": "principal",
            "evidence": "La chambre funéraire contient un tombeau royal en pierre.",
        }]
        scenes = [
            f"La chambre funéraire montre un tombeau royal, étape {index}."
            for index in range(5)
        ]
        distribution = visual_corpus.distribute_visual_anchors(
            scenes, anchors, generic_terms=[])
        reuse = distribution["anchor_reuse"][0]
        self.assertEqual(reuse["scene_count"], 3)
        self.assertEqual(
            distribution["anchors_with_implicit_matches_capped"][0][
                "implicit_matches_before"], 5)

    def test_image_schedule_meets_duration_reuse_and_order_contract(self):
        scenes = [f"Scène concrète numéro {index}" for index in range(19)]
        rows = []
        for index, scene in enumerate(scenes, 1):
            anchors = [
                {"anchor_id": f"artifact:scene_{index}_a", "score": 3},
                {"anchor_id": f"artifact:scene_{index}_b", "score": 2},
            ]
            rows.append({"scene_index": index, "narration": scene,
                         "anchors_available": 2, "anchors": anchors})
        schedule = visual_corpus.plan_image_schedule(
            scenes, {"scenes": rows}, duration_seconds=90)
        self.assertTrue(schedule["selection_accepted"])
        self.assertEqual(schedule["images_planned"], 23)
        self.assertEqual([item["image_index"] for item in schedule["images"]],
                         list(range(1, 24)))
        self.assertGreaterEqual(schedule["minimum_image_duration_seconds"], 3)
        self.assertLessEqual(schedule["maximum_image_duration_seconds"], 7)
        self.assertLessEqual(schedule["reframe_rate"], .25)
        for scene_index in range(1, 20):
            anchors = [item["anchor_id"] for item in schedule["images"]
                       if item["scene_index"] == scene_index]
            self.assertEqual(len(anchors), len(set(anchors)))


if __name__ == "__main__":
    unittest.main()
