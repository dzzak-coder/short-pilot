import json
import unittest
from unittest.mock import Mock, patch

from core.studio3d_vision import analyze_visual_references, search_visual_references, trusted_image_url


class VisualReferenceTests(unittest.TestCase):
    def test_image_fetch_hosts_are_strictly_bounded(self):
        for url in ('https://upload.wikimedia.org/a.jpg', 'https://thumb.wikimedia.org/a.png'):
            self.assertTrue(trusted_image_url(url))
        for url in ('http://127.0.0.1/a', 'https://upload.wikimedia.org.evil/a',
                    'https://user@upload.wikimedia.org/a', 'https://upload.wikimedia.org:abc/a',
                    'https://upload.wikimedia.org:8080/a', 'file:///a'):
            self.assertFalse(trusted_image_url(url))

    def test_untrusted_search_results_are_not_returned(self):
        response = Mock()
        response.json.return_value = {'query': {'pages': {
            '1': {'title': 'File:Good.png', 'imageinfo': [{'mime': 'image/png',
                  'thumburl': 'https://thumb.wikimedia.org/good.png',
                  'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Good.png'}]},
            '2': {'title': 'File:Bad.png', 'imageinfo': [{'mime': 'image/png',
                  'thumburl': 'http://localhost/private',
                  'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Bad.png'}]},
        }}}
        with patch('requests.get', return_value=response):
            refs = search_visual_references('hélicoptère')
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]['title'], 'File:Good.png')

    def test_real_image_bytes_must_reach_vision_model(self):
        response = Mock(status_code=200)
        response.json.return_value = {'message': {'content': json.dumps({
            'relevant': True, 'parts': [{'name': 'rotor'}], 'uncertainties': ['rear view absent']})}}
        session = Mock()
        session.post.return_value = response
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        refs = [{'title': 'Helicopter', 'imageUrl': 'https://upload.wikimedia.org/example.jpg'}]
        with patch('core.studio3d_vision.load_reference_image', return_value='image-base64'), \
                patch('requests.Session', return_value=session):
            result = analyze_visual_references('http://127.0.0.1:11434', 'hélicoptère', refs)
        payload = session.post.call_args.kwargs['json']
        self.assertEqual(payload['messages'][1]['images'], ['image-base64'])
        self.assertEqual(payload['keep_alive'], 0)
        self.assertEqual(result['imageCount'], 1)

    def test_no_reference_means_no_false_visual_reconstruction(self):
        with self.assertRaisesRegex(ValueError, 'Aucune image'):
            analyze_visual_references('http://127.0.0.1:11434', 'hélicoptère', [])

    def test_unrelated_visual_observations_are_rejected(self):
        response = Mock(status_code=200)
        response.json.return_value = {'message': {'content': '{"relevant":false,"parts":[]}'}}
        session = Mock()
        session.post.return_value = response
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        with patch('core.studio3d_vision.load_reference_image', return_value='image'), \
                patch('requests.Session', return_value=session), self.assertRaises(ValueError):
            analyze_visual_references('http://127.0.0.1:11434', 'vélo', [{'imageUrl': 'x'}])
