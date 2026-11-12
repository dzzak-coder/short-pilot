import json
import unittest
from core.studio3d_scene import visual_scene_code


class VisualSceneTests(unittest.TestCase):
    def scene(self):
        return {'title': 'Scène', 'parts': [
            {'name': 'pièce', 'kind': 'ellipsoid', 'size': [2, 1, 1], 'pos': [i, 0, 0],
             'rot': [0, 0, 0], 'material': 'wood', 'stage': 'structure'} for i in range(6)]}

    def test_dimensions_and_positions_reach_supported_api(self):
        code = visual_scene_code(json.dumps(self.scene()))
        self.assertIn('"scale": [1.0, 0.5, 0.5]', code)
        self.assertIn('"pos": [5.0, 0.0, 0.0]', code)
        self.assertEqual(code.count('cad.sphere('), 6)

    def test_superposed_or_nonfinite_scene_is_rejected(self):
        spec = self.scene()
        for p in spec['parts']:
            p['pos'] = [0, 0, 0]
        with self.assertRaisesRegex(ValueError, 'superposés'):
            visual_scene_code(json.dumps(spec))
        spec = self.scene(); spec['parts'][0]['pos'][0] = float('inf')
        with self.assertRaises(ValueError):
            visual_scene_code(json.dumps(spec))

    def test_labels_cannot_become_executable_code(self):
        spec = self.scene(); spec['parts'][0]['name'] = '\"); alert(1); //'
        code = visual_scene_code(json.dumps(spec))
        first = code.splitlines()[1]
        args = json.loads(first[len('cad.sphere('):-2])
        self.assertEqual(args['name'], spec['parts'][0]['name'])
