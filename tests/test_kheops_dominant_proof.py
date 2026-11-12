import unittest

from tools import render_kheops_dominant_proof as proof


class KheopsDominantProofTests(unittest.TestCase):
    def test_combined_workflow_has_two_branches_and_no_historical_seed(self):
        workflow = proof.build_workflow(["first pyramid", "second pyramid"])
        samplers = [node for node in workflow.values() if node["class_type"] == "KSampler"]
        outputs = [node for node in workflow.values() if node["class_type"] == "SaveImage"]
        self.assertEqual(len(samplers), 2)
        self.assertEqual(len(outputs), 2)
        self.assertEqual([node["inputs"]["seed"] for node in samplers], list(proof.SEEDS))
        self.assertNotIn(70001, proof.SEEDS)

    def test_continuity_crop_modes_vary_distance_and_position(self):
        boxes = [box for _, box in proof.CROP_MODES]
        self.assertEqual(len(set(boxes)), 6)
        self.assertIn((0.00, 0.00, 1.00, 1.00), boxes)
        self.assertTrue(any(box[0] != box[2] - 1 for box in boxes))


if __name__ == "__main__":
    unittest.main()
