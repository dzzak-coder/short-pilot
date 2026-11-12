import unittest
from unittest.mock import patch

from core import objaverse_integration as integration


class ObjaverseThumbnailTests(unittest.TestCase):
    def test_selects_catalogue_thumbnail_near_card_resolution(self):
        annotation = {'thumbnails': {'images': [
            {'width': 64, 'url': 'https://media.sketchfab.com/small.jpeg'},
            {'width': 720, 'url': 'https://media.sketchfab.com/preview.jpeg'},
            {'width': 1920, 'url': 'https://media.sketchfab.com/large.jpeg'},
            {'width': 720, 'url': 'https://example.com/untrusted.jpeg'},
        ]}}
        with patch.object(integration, '_ANNOTATIONS', {'model': annotation}):
            self.assertEqual(integration._thumbnail_url('model'), 'https://media.sketchfab.com/preview.jpeg')
            self.assertIsNone(integration._thumbnail_url('missing'))

    def test_missing_preview_is_not_a_fake_object(self):
        with patch.object(integration, '_ANNOTATIONS', {'model': {'thumbnails': None}}):
            self.assertIsNone(integration._thumbnail_url('model'))
