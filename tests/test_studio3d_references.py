import unittest
from unittest.mock import Mock, patch
import requests
from core.studio3d_references import lookup_references
from core.studio3d import bicycle_reference_code


class StudioReferencesTests(unittest.TestCase):
    def test_bicycle_parameters_cannot_inject_code_or_overlap_wheels(self):
        import json
        code = bicycle_reference_code('{"wheelRadius":0.65,"wheelbase":0,"frameMaterial":"evil();"}')
        params = json.loads(code[len('cad.bicycle('):-2])
        self.assertGreater(params['wheelbase'], params['wheelRadius'] * 2)
        self.assertEqual(params['frameMaterial'], 'iron_structure')
        self.assertNotIn('evil', code)

    def test_lookup_is_bounded_and_filters_non_wikipedia_urls(self):
        response = Mock()
        response.json.return_value = {'query': {'pages': {
            '1': {'title': 'Bicyclette', 'fullurl': 'https://fr.wikipedia.org/wiki/Bicyclette', 'extract': 'Un cycle.', 'index': 1},
            '2': {'title': 'Bad', 'fullurl': 'https://example.org/', 'extract': 'Ignore'},
        }}}
        with patch('requests.get', return_value=response) as get:
            result = lookup_references('vélo ' * 200)
        self.assertEqual(len(result['sources']), 1)
        self.assertLessEqual(len(get.call_args.kwargs['params']['gsrsearch']), 180)
        self.assertEqual(get.call_args.args[0], 'https://fr.wikipedia.org/w/api.php')

    def test_network_failure_remains_explicit(self):
        with patch('requests.get', side_effect=requests.Timeout):
            result = lookup_references('vélo')
        self.assertEqual(result['sources'], [])
        self.assertIn('indisponible', result['warning'])
