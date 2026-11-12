"""Run with the isolated CAD runtime, not ShortPilot's Python."""
import json
from pathlib import Path
import unittest

from assembly_trial import build


class AssemblyChecks(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads(Path(__file__).with_name('hinge.spec.json').read_text(encoding='utf-8'))

    def test_complete_hinge_has_four_valid_non_interpenetrating_solids(self):
        records, report = build(self.spec)
        self.assertEqual(report['valid_solids'], 4)
        self.assertEqual(report['interpenetrations'], [])
        self.assertEqual(report['max_mate_residual'], 0)
        self.assertTrue(all(len(r['placed'].Solids()) == 1 for r in records.values()))

    def test_disconnected_assembly_is_rejected(self):
        self.spec['mates'].pop()
        with self.assertRaisesRegex(ValueError, 'connected assembly'):
            build(self.spec)

    def test_oversized_pin_is_rejected_by_geometry(self):
        self.spec['parts'][2]['parameters'] = {'hole_radius': 5, 'radius': 4}
        with self.assertRaisesRegex(ValueError, 'Interpenetrations'):
            build(self.spec)

    def test_short_pin_is_rejected_even_without_collisions(self):
        self.spec['parts'][2]['parameters']['height'] = 20
        with self.assertRaisesRegex(ValueError, 'heights are incompatible'):
            build(self.spec)

    def test_output_ids_cannot_escape_export_directory(self):
        self.spec['parts'][0]['id'] = '../elsewhere'
        with self.assertRaisesRegex(ValueError, 'Invalid/duplicate'):
            build(self.spec)

    def test_constraint_direction_does_not_change_placement(self):
        mate = self.spec['mates'][0]
        mate['parent'], mate['child'] = mate['child'], mate['parent']
        _, report = build(self.spec)
        self.assertEqual(report['max_mate_residual'], 0)

    def test_unsupported_product_is_not_replaced_by_hinge(self):
        with self.assertRaisesRegex(ValueError, 'non pris en charge'):
            build({'unsupported': True, 'reason': 'Moto absente de la bibliothèque'})


if __name__ == '__main__':
    unittest.main()
