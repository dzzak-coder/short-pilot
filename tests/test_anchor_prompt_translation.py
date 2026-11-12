import json
import re
import unittest
from pathlib import Path

from fix_prompts.prompt_builder import (
    SUBJECT_BY_ANCHOR,
    EXCLUDED,
    build_image_prompts_v2,
    english_subject,
)
from fix_prompts.anchor_translations import translate_anchor


class PromptBuilderV2Tests(unittest.TestCase):
    def _campaign_assignments(self):
        root = Path(__file__).resolve().parents[1]
        density = json.loads(
            (root / "outputs/text_diagnostics/kheops_visual_density_2026-11-10.json").read_text(encoding="utf-8")
        )
        anchors = {a["id"]: a for a in density.get("visual_anchors", [])}
        assignments = []
        for item in density["image_schedule"]["images"]:
            aid = item["anchor_id"]
            assignments.append(
                {
                    "image_index": item["image_index"],
                    "scene": item["scene_index"],
                    "anchor_id": aid,
                    "label": (anchors.get(aid) or {}).get("label") or aid,
                }
            )
        return assignments

    def test_a2_campaign_prompts_unique_and_duplicate_raises(self):
        assignments = self._campaign_assignments()
        items = build_image_prompts_v2(assignments)
        self.assertEqual(len(items), 23)
        prompts = [x["prompt"] for x in items]
        self.assertEqual(len(set(prompts)), 23, "Les 23 prompts doivent être distincts")
        # Forcer un doublon : même ancrage/assignation répétée sans possibilité d'unicité via API
        dup = [
            {"image_index": 1, "scene": 1, "anchor_id": "site:plateau_de_gizeh", "label": "plateau de Gizeh"},
            {"image_index": 2, "scene": 2, "anchor_id": "site:plateau_de_gizeh", "label": "plateau de Gizeh"},
        ]
        # Deux prompts identiques successifs doivent lever (ou être rendus uniques par variante).
        # build_image_prompts_v2 tente de désambiguïser; on vérifie qu'il ne produit jamais de doublon.
        out = build_image_prompts_v2(dup)
        self.assertEqual(len(out), 2)
        self.assertNotEqual(out[0]["prompt"], out[1]["prompt"])

    def test_a3_subject_by_anchor_has_no_french_source_labels(self):
        # Contrôle sur SUBJECT_BY_ANCHOR (pas sur une liste de mots : "corridor"/"niche" sont valides en anglais).
        self.assertGreaterEqual(len(SUBJECT_BY_ANCHOR), 19)
        french_markers = re.compile(
            r"[àâäçéèêëîïôöùûüÿœ]|"
            r"\b(pyramide de|chambre du|chambre de la|chambre funéraire|chambre de décharge|"
            r"socle rocheux|revêtement|assises|blocs de|pierres calcaires|grande galerie|"
            r"couloir|entrée|ouverture|système de décharge|herses de fermeture|"
            r"roche naturelle|plateau de|sarcophage|inscriptions)\b",
            re.IGNORECASE,
        )
        for anchor_id, subject in SUBJECT_BY_ANCHOR.items():
            self.assertIsInstance(subject, str)
            self.assertTrue(subject.strip(), f"Sujet vide pour {anchor_id}")
            self.assertIsNone(
                french_markers.search(subject),
                f"Sujet non anglais/français résiduel pour {anchor_id}: {subject!r}",
            )
            # et l'id doit être résolvable
            self.assertEqual(english_subject(anchor_id), subject)

    def test_a4_exclusions_never_injected(self):
        for label in ("basilique", "cathédrale", "île", "canal", "momie"):
            self.assertIn(label, EXCLUDED)
            self.assertIsNone(translate_anchor(label))
        assignments = [
            {"image_index": 1, "scene": 1, "anchor_id": "site:plateau_de_gizeh", "label": "plateau de Gizeh"},
            {"image_index": 2, "scene": 2, "anchor_id": "x:basilique", "label": "basilique"},
            {"image_index": 3, "scene": 3, "anchor_id": "x:ile", "label": "île"},
        ]
        items = build_image_prompts_v2(assignments, log=lambda *_: None)
        self.assertEqual([x["image_index"] for x in items], [1])
        self.assertTrue(all("basilica" not in x["prompt"].lower() for x in items))
        self.assertTrue(all("island" not in x["prompt"].lower() for x in items))


if __name__ == "__main__":
    unittest.main()