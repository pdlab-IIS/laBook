import base64
from dataclasses import replace
import io
import json
from pathlib import Path
import secrets
import tempfile
import time
import unittest
from urllib.parse import unquote_to_bytes

from flask import Flask, redirect, request, url_for

from gateway.inbound import GatewayConfigurationError, Settings, SignedGateway
from gateway.signing import sign_request


SECRET = b'unit-test-only-signing-key-32bytes'


class GatewayInboundTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Settings('https://public.example', '/labook', ('upstream.example',),
                                 'TTEST', {'test': SECRET},
                                 str(Path(self.temp.name) / 'nonce.sqlite'), 1024)
        self.received = []

        def app(env, respond):
            self.received.append(env)
            respond('200 OK', [('Cache-Control', 'public, max-age=600'), ('Expires', 'tomorrow')])
            return [env['wsgi.input'].read()]

        self.gateway = SignedGateway(app, self.settings)

    def environ(self, target='/books?a=1&a=2', body=b'', method='GET', subject='slack:TTEST:UTEST'):
        path, _, query = target.partition('?')
        fields = dict(key_id='test', method=method, target=target, content_type='application/json',
                      body=body, timestamp=str(int(time.time())), nonce=secrets.token_hex(16), subject=subject)
        env = dict(REQUEST_METHOD=method, RAW_URI=target, QUERY_STRING=query,
                   PATH_INFO=unquote_to_bytes(path).decode('latin-1'), SCRIPT_NAME='',
                   CONTENT_LENGTH=str(len(body)), CONTENT_TYPE=fields['content_type'],
                   HTTP_HOST='upstream.example', SERVER_NAME='upstream.example', SERVER_PORT='80',
                   SERVER_PROTOCOL='HTTP/1.1')
        env.update({'wsgi.input': io.BytesIO(body), 'wsgi.url_scheme': 'http',
                    'wsgi.errors': io.StringIO(), 'wsgi.version': (1, 0), 'wsgi.multithread': False,
                    'wsgi.multiprocess': False, 'wsgi.run_once': False})
        for field in ['key_id', 'timestamp', 'nonce', 'subject']:
            env['HTTP_X_LABOOK_' + field.upper()] = fields[field]
        env['HTTP_X_LABOOK_SIGNATURE'] = sign_request(SECRET, **fields)
        return env

    def invoke(self, env, gateway=None):
        result = {}

        def start(status, headers, exc_info=None):
            result.update(status=int(status.split()[0]), headers=dict(headers))

        response = (gateway or self.gateway)(env, start)
        try:
            result['body'] = b''.join(response)
        finally:
            if hasattr(response, 'close'):
                response.close()
        return result

    def test_verified_body_identity_prefix_and_private_cache(self):
        env = self.environ(body=b'{"title":"test"}', method='POST')
        for name in ['HTTP_COOKIE', 'HTTP_AUTHORIZATION', 'HTTP_FORWARDED', 'HTTP_X_REAL_IP',
                     'HTTP_X_FORWARDED_HOST', 'HTTP_X_LABOOK_ADMIN']:
            env[name] = 'untrusted'
        result = self.invoke(env)
        self.assertEqual((result['status'], result['body']), (200, b'{"title":"test"}'))
        forwarded = self.received[0]
        self.assertEqual(forwarded['labook.gateway_subject'], 'slack:TTEST:UTEST')
        self.assertEqual(forwarded['HTTP_HOST'], 'public.example')
        self.assertEqual(forwarded['SCRIPT_NAME'], '/labook')
        self.assertEqual(forwarded['wsgi.url_scheme'], 'https')
        self.assertNotIn('HTTP_COOKIE', forwarded)
        self.assertFalse(any(k.startswith(('HTTP_X_FORWARDED_', 'HTTP_X_LABOOK_')) for k in forwarded))
        self.assertEqual(result['headers']['Cache-Control'], 'private, no-store')
        self.assertNotIn('Expires', result['headers'])

    def test_replay_rejected(self):
        env = self.environ()
        self.assertEqual(self.invoke(env)['status'], 200)
        self.assertEqual(self.invoke(env)['status'], 403)
        self.assertEqual(len(self.received), 1)

    def test_unsigned_requests_never_reach_application(self):
        for target in ['/', '/healthz', '/readyz', '/static/js/main.js', '/covers/test.jpg', '/books']:
            with self.subTest(target=target):
                env = self.environ(target)
                del env['HTTP_X_LABOOK_SIGNATURE']
                self.assertEqual(self.invoke(env)['status'], 403)
        self.assertEqual(self.received, [])

    def test_tampering_host_subject_and_raw_path_rejected(self):
        changes = [dict(HTTP_HOST='outside.example'), dict(HTTP_X_LABOOK_SUBJECT='slack:TOTHER:U1'),
                   dict(HTTP_X_LABOOK_KEY_ID='unknown'), dict(QUERY_STRING='a=2'),
                   dict(PATH_INFO='/users'), dict(RAW_URI=''), dict(SCRIPT_NAME='/already'),
                   dict(HTTP_X_LABOOK_TIMESTAMP='1'), dict(REQUEST_METHOD='DELETE'),
                   dict(CONTENT_TYPE='text/plain')]
        for change in changes:
            with self.subTest(change=change):
                self.assertEqual(self.invoke(self.environ() | change)['status'], 403)
        self.assertEqual(self.received, [])

    def test_ambiguous_even_correctly_signed_paths_rejected(self):
        for target in ['/a/../b', '/a/%2e/b', '/a%2fb', '/a%5cb', '/a%252fb',
                       '/a//b', '/a\\b', '/a%00b', '/a%zz', '/a%ff']:
            with self.subTest(target=target):
                self.assertEqual(self.invoke(self.environ(target))['status'], 403)
        self.assertEqual(self.received, [])

    def test_unicode_paths_and_raw_duplicate_query_allowed(self):
        target = '/shelves/%E6%9C%AC?a=%2F&a=%25&x=+'
        self.assertEqual(self.invoke(self.environ(target))['status'], 200)
        self.assertEqual(self.received[0]['QUERY_STRING'], 'a=%2F&a=%25&x=+')

    def test_bodies_bounded_and_complete(self):
        for env, expected in [(self.environ(body=b'x' * 1025), 413),
                              (self.environ(body=b'x') | {'CONTENT_LENGTH': '2'}, 403),
                              (self.environ() | {'CONTENT_LENGTH': '-1'}, 403),
                              (self.environ(body=b'x') | {'CONTENT_LENGTH': '2', 'wsgi.input_terminated': True}, 403),
                              (self.environ(body=b'x' * 1025) | {'CONTENT_LENGTH': '', 'wsgi.input_terminated': True}, 413)]:
            self.assertEqual(self.invoke(env)['status'], expected)
        env = self.environ(body=b'chunked')
        env.update({'CONTENT_LENGTH': '', 'wsgi.input_terminated': True})
        self.assertEqual(self.invoke(env)['body'], b'chunked')

    def test_nonce_storage_failure_fails_closed(self):
        self.gateway.settings = replace(self.settings, nonce_database=self.temp.name)
        self.assertEqual(self.invoke(self.environ())['status'], 403)
        self.assertEqual(self.received, [])

    def test_flask_redirect_uses_fixed_origin_and_prefix(self):
        app = Flask('gateway-test')

        @app.get('/L/<code>')
        def shelf(code):
            return redirect(url_for('home', location=code, _external=True))

        @app.get('/')
        def home():
            return request.environ['labook.gateway_subject']

        for prefix in ['/labook', '/trial/index.php']:
            result = self.invoke(self.environ('/L/ABC'), SignedGateway(app, replace(self.settings, public_prefix=prefix)))
            self.assertEqual(result['status'], 302)
            self.assertEqual(result['headers']['Location'], 'https://public.example' + prefix + '/?location=ABC')

    def test_private_config_validation(self):
        config = dict(public_origin=self.settings.public_origin, public_prefix='/labook',
                      upstream_hosts=['upstream.example'], slack_team_id='TTEST',
                      signing_keys={'test': base64.b64encode(SECRET).decode()},
                      nonce_database=self.settings.nonce_database, max_body_bytes=1024)
        path = Path(self.temp.name) / 'config.json'
        path.write_text(json.dumps(config))
        self.assertEqual(Settings.load(str(path)), self.settings)
        path.write_text(json.dumps(config | {'public_prefix': '/trial/index.php'}))
        self.assertEqual(Settings.load(str(path)).public_prefix, '/trial/index.php')
        for change in [dict(public_origin='http://public.example'), dict(public_origin='https://a:99999'),
                       dict(public_origin='https://a:0'), dict(public_origin='https://a/'),
                       dict(public_prefix='//a'), dict(public_prefix='/a/../b'), dict(slack_team_id=''), dict(signing_keys={}),
                       dict(signing_keys={'test': 'invalid'}), dict(upstream_hosts=[]),
                       dict(nonce_database='relative.sqlite'), dict(max_body_bytes=True)]:
            with self.subTest(fields=list(change)):
                path.write_text(json.dumps(config | change))
                with self.assertRaises(GatewayConfigurationError):
                    Settings.load(str(path))


if __name__ == '__main__':
    unittest.main()
