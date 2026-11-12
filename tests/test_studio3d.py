import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask

from core.studio3d import clean_script, create_blueprint, ingest_recording, local_ai_url, generated_script_parses


class Studio3dIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        (self.base / 'tmp').mkdir()
        self.received = []
        self.app = Flask(__name__)
        self.app.register_blueprint(create_blueprint(str(self.base), self.enqueue))
        self.client = self.app.test_client()

    def enqueue(self, params):
        self.received.append(params)
        return {'id': 'test-job'}

    def test_only_local_ai_servers_allowed(self):
        self.assertEqual(local_ai_url('http://127.0.0.1:11434/', ''), 'http://127.0.0.1:11434')
        for url in ('https://example.com', 'file:///etc/passwd', 'http://user:pass@localhost',
                    'http://127.0.0.1.evil.test', 'http://localhost?target=elsewhere'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                local_ai_url(url, '')

    def test_extracts_model_code_without_thinking_or_markdown(self):
        self.assertEqual(clean_script('<think>draft</think>\n```js\nHolo.box();\n```'), 'Holo.box();')

    def model_session(self, responses):
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.post.side_effect = [Mock(status_code=200, json=Mock(return_value=item)) for item in responses]
        return session

    def test_ollama_truncated_mid_string_is_resumed_without_changing_boundary(self):
        session = self.model_session([
            {'message': {'content': '```js\ncad.box({name:"Héli'}, 'done_reason': 'length'},
            {'message': {'content': 'coptère",w:2});\n```'}, 'done_reason': 'stop'},
        ])
        with patch('requests.Session', return_value=session):
            response = self.client.post('/api/local-ai/generate', json={'userPrompt': 'hélicoptère'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 'cad.box({name:"Hélicoptère",w:2});')
        self.assertEqual(response.json['continuations'], 1)
        self.assertEqual(session.post.call_count, 2)
        self.assertIn('Héli', session.post.call_args.kwargs['json']['messages'][-2]['content'])

    def test_compatible_provider_truncation_is_also_resumed(self):
        session = self.model_session([
            {'choices': [{'message': {'content': 'cad.box({'}, 'finish_reason': 'length'}]},
            {'choices': [{'message': {'content': 'w:2});'}, 'finish_reason': 'stop'}]},
        ])
        with patch('requests.Session', return_value=session):
            response = self.client.post('/api/local-ai/generate', json={'provider': 'openai-local', 'userPrompt': 'objet'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 'cad.box({w:2});')

    def test_second_truncation_stops_without_partial_code_or_infinite_retry(self):
        session = self.model_session([
            {'message': {'content': 'cad.box({'}, 'done_reason': 'length'},
            {'message': {'content': 'w:2,'}, 'done_reason': 'length'},
        ])
        with patch('requests.Session', return_value=session):
            response = self.client.post('/api/local-ai/generate', json={'userPrompt': 'objet'})
        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.json['generationFailure'])
        self.assertNotIn('code', response.json)
        self.assertEqual(session.post.call_count, 2)

    def test_syntax_check_parses_without_executing_model_code(self):
        good = generated_script_parses('throw new Error("must not execute");')
        if good is None:
            self.skipTest('Node parser not installed')
        self.assertTrue(good)
        self.assertFalse(generated_script_parses('cad.box({name:"unfinished'))

    def test_invalid_code_even_reported_as_complete_is_not_returned(self):
        session = self.model_session([{'message': {'content': 'cad.box({'}, 'done_reason': 'stop'}])
        with patch('requests.Session', return_value=session), patch('core.studio3d.generated_script_parses', return_value=False):
            response = self.client.post('/api/local-ai/generate', json={'userPrompt': 'objet'})
        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.json['generationFailure'])
        self.assertNotIn('code', response.json)

    def test_slow_model_is_not_reported_as_offline_and_has_more_time(self):
        import requests
        session = self.model_session([])
        session.post.side_effect = requests.ReadTimeout('still generating')
        with patch('requests.Session', return_value=session):
            response = self.client.post('/api/local-ai/generate', json={'userPrompt': 'objet'})
        self.assertEqual(response.status_code, 504)
        self.assertEqual(response.json['errorCode'], 'MODEL_TIMEOUT')
        self.assertTrue(response.json['generationFailure'])
        self.assertNotIn('code', response.json)
        self.assertEqual(session.post.call_args.kwargs['timeout'], (3, 240))

    def test_connection_failure_is_distinct_from_slow_generation(self):
        import requests
        session = self.model_session([])
        session.post.side_effect = requests.ConnectionError('refused')
        with patch('requests.Session', return_value=session):
            response = self.client.post('/api/local-ai/generate', json={'userPrompt': 'objet'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json['errorCode'], 'MODEL_UNREACHABLE')
        self.assertTrue(response.json['generationFailure'])
        self.assertNotIn('code', response.json)

    def test_model_http_error_explicitly_blocks_substitution(self):
        session = self.model_session([])
        session.post.side_effect = None
        session.post.return_value = Mock(status_code=500)
        with patch('requests.Session', return_value=session):
            response = self.client.post('/api/local-ai/generate', json={'userPrompt': 'objet'})
        self.assertEqual(response.status_code, 502)
        self.assertTrue(response.json['generationFailure'])
        self.assertNotIn('code', response.json)

    def test_visual_failure_never_silently_generates_an_unrelated_object(self):
        with patch('core.studio3d_vision.analyze_visual_references', side_effect=ValueError('Image illisible.')):
            response = self.client.post('/api/local-ai/generate', json={
                'provider': 'ollama', 'userPrompt': 'hélicoptère', 'useVisualReferences': True})
        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.json['visualFailure'])
        self.assertNotIn('code', response.json)

    def test_visual_observations_reach_the_code_generator(self):
        from unittest.mock import Mock
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.post.return_value.status_code = 200
        import json
        session.post.return_value.json.return_value = {'message': {'content': json.dumps({'title': 'Test', 'parts': [
            {'name': 'pièce', 'kind': 'box', 'size': [1, 1, 1], 'pos': [i, 0, 0], 'rot': [0, 0, 0],
             'material': 'wood', 'stage': 'structure'} for i in range(6)]})}}
        with patch('core.studio3d_vision.analyze_visual_references', return_value={
                'observations': 'rotor au-dessus du fuselage', 'imageCount': 2}), \
                patch('requests.Session', return_value=session):
            response = self.client.post('/api/local-ai/generate', json={
                'provider': 'ollama', 'userPrompt': 'hélicoptère', 'useVisualReferences': True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['visualAnalysis']['imageCount'], 2)
        self.assertIn('rotor au-dessus du fuselage', session.post.call_args.kwargs['json']['messages'][1]['content'])

    def test_bundle_and_audio_served_beneath_studio_path(self):
        dist = self.base / 'studio3d' / 'dist'
        (dist / 'audio').mkdir(parents=True)
        (dist / 'index.html').write_text('<title>3D studio</title>')
        (dist / 'audio' / 'demo.mp3').write_bytes(b'demo')
        with self.client.get('/studio3d/') as response:
            self.assertEqual(response.status_code, 200)
        with self.client.get('/studio3d/audio/demo.mp3') as response:
            self.assertEqual(response.data, b'demo')
        self.assertEqual(self.client.get('/studio3d/../../app.py').status_code, 404)

    def test_studio_tts_serves_denise_neural_audio_and_reports_voice(self):
        voice = self.base / 'tmp' / 'denise.mp3'
        voice.write_bytes(b'ID3' + b'\0' * 2048)
        with patch('core.voice.synthesize_studio_narration', return_value=(str(voice), 'edge_tts:fr-denise')) as synth:
            with self.client.post('/api/local-tts/speak', json={
                    'text': 'Bonjour la Formule Un.', 'voice_id': 'fr-denise'}) as response:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, 'audio/mpeg')
                self.assertEqual(response.headers['X-ShortPilot-Voice-Mode'], 'edge_tts:fr-denise')
                self.assertEqual(response.headers['X-ShortPilot-Voice-Id'], 'fr-denise')
        synth.assert_called_once_with(
            'Bonjour la Formule Un.',
            str(self.base / 'tmp' / 'studio3d_voice_cache'),
            voice_id='fr-denise',
        )

    def test_studio_tts_rejects_unknown_voice_instead_of_substituting(self):
        with patch('core.voice.synthesize_studio_narration') as synth:
            response = self.client.post('/api/local-tts/speak', json={
                'text': 'Bonjour.', 'voice_id': 'fr-inconnue',
            })
        self.assertEqual(response.status_code, 400)
        synth.assert_not_called()

    def test_studio_tts_returns_no_content_when_local_voice_is_unavailable(self):
        with patch('core.voice.synthesize_studio_narration', return_value=None):
            response = self.client.post('/api/local-tts/speak', json={'text': 'Bonjour.'})
        self.assertEqual(response.status_code, 204)

    def test_objaverse_search_clamps_parameters_and_hides_local_paths(self):
        result = {
            'uid': '123e4567-e89b-12d3-a456-426614174000',
            'name': 'test', 'cached': True,
        }
        with patch('core.studio3d.OBJAVERSE_AVAILABLE', True), \
                patch('core.studio3d.get_objaverse_stats', return_value={'annotations_loaded': True}), \
                patch('core.studio3d.search_objaverse', return_value=[result]) as search:
            response = self.client.post('/api/studio3d/objaverse/search', json={
                'query': 'vélo', 'limit': 999, 'min_parts': 99,
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['results'], [result])
        search.assert_called_once_with('vélo', limit=20, min_parts=2)

    def test_objaverse_rejects_path_like_uid_before_cache_or_download(self):
        with patch('core.studio3d.OBJAVERSE_AVAILABLE', True), \
                patch('core.studio3d.download_objaverse_model') as download:
            response = self.client.post('/api/studio3d/objaverse/download', json={'uid': '../../app'})
        self.assertEqual(response.status_code, 400)
        download.assert_not_called()

    def test_objaverse_cached_model_is_served_only_for_valid_uuid(self):
        valid_uid = '123e4567-e89b-12d3-a456-426614174000'
        cached = self.base / 'model.glb'
        cached.write_bytes(b'glb')
        with patch('core.studio3d.get_cached_model_path', return_value=str(cached)):
            with self.client.get('/api/studio3d/objaverse/serve', query_string={'uid': valid_uid}) as response:
                self.assertEqual(response.status_code, 200)
            self.assertEqual(self.client.get('/api/studio3d/objaverse/serve', query_string={'uid': '../../app'}).status_code, 400)

    def test_invalid_media_rejected_without_creating_job(self):
        r = self.client.post('/api/studio3d/import', data={'video': (io.BytesIO(b'not video'), 'evil.mp4')})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.received, [])

    def test_webm_upload_is_saved_and_enqueued_with_safe_filename(self):
        r = self.client.post('/api/studio3d/import', data={
            'video': (io.BytesIO(b'\x1aE\xdf\xa3' + b'12345678'), '../../escape.webm'),
            'title': 'Mon satellite', 'caption': 'Sequence 3D',
        })
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.json['job_id'], 'test-job')
        path = Path(self.received[0]['file_path'])
        self.assertEqual(path.parent, self.base / 'tmp')
        self.assertEqual(path.suffix, '.webm')
        self.assertEqual(self.received[0]['title'], 'Mon satellite')

    def test_failed_conversion_removes_partial_files(self):
        source = self.base / 'tmp' / 'bad.webm'
        source.write_bytes(b'bad')
        output = self.base / 'video.mp4'
        with patch('subprocess.run') as run:
            run.return_value.returncode = 1
            with self.assertRaises(RuntimeError):
                ingest_recording(str(source), str(output), log=lambda _: None)
        self.assertFalse(source.exists())
        self.assertFalse(output.exists())

    def test_main_page_and_multipart_guard(self):
        import app as host
        with patch.object(host, 'AUTH_TOKEN', ''):
            client = host.app.test_client()
            response = client.get('/')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'studio3d-frame', response.data)
            self.assertIn(b'height:100dvh', response.data)
            self.assertNotIn(b'height:82vh', response.data)
            self.assertNotIn(b'min-height:700px', response.data)
            response = client.post('/api/studio3d/import', data={})
            self.assertEqual(response.status_code, 400)
            response = client.post('/api/studio3d/import', data={}, headers={'Origin': 'https://untrusted.example'})
            self.assertEqual(response.status_code, 403)
