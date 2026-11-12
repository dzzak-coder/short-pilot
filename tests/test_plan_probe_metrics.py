import unittest

from tools import plan_probe


class PlanProbeMetricsTests(unittest.TestCase):
    def test_continuity_suffix_does_not_create_another_visual_subject(self):
        anchor = "A pyramid centered in the Giza funerary complex."
        copied = anchor + plan_probe.CONTINUITY_SUFFIX
        self.assertEqual(plan_probe._visual_subject_key(anchor),
                         plan_probe._visual_subject_key(copied))


if __name__ == "__main__":
    unittest.main()
