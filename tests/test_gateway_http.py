"""Real Gunicorn HTTP tests; use a loopback-only probe with no business data."""
import base64
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest

from gateway.signing import sign_request


@unittest.skipIf(os.name == 'nt', 'Gunicorn HTTP tests run on the isolated Linux target')
class GatewayHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.secret = secrets.token_bytes(32)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            cls.port = sock.getsockname()[1]
        cls.host = '127.0.0.1:' + str(cls.port)
        root = Path(__file__).resolve().parents[1]
        config = Path(cls.temp.name) / 'config.json'
        config.write_text(json.dumps(dict(public_origin='https://public.example', public_prefix='/labook',
            upstream_hosts=[cls.host], slack_team_id='TTEST',
            signing_keys={'http-test': base64.b64encode(cls.secret).decode()},
            nonce_database=str(Path(cls.temp.name) / 'nonces.sqlite'), max_body_bytes=1024)))
        os.chmod(config, 0o600)
        env = os.environ | {'LABOOK_GATEWAY_CONFIG': str(config), 'PYTHONPATH': str(root),
                           'PYTHONDONTWRITEBYTECODE': '1'}
        log = open(Path(cls.temp.name) / 'gunicorn.log', 'w+b')
        cls.addClassCleanup(log.close)
        cls.server = subprocess.Popen([sys.executable, '-m', 'gunicorn', '--bind', cls.host,
            '--workers', '2', '--chdir', str(root / 'tests/fixtures'), 'gateway_probe:application'],
            env=env, stdout=log, stderr=log)
        cls.addClassCleanup(cls.stop_server)
        for _ in range(100):
            if cls.server.poll() is not None:
                raise RuntimeError('Isolated Gunicorn failed to start; inspect private test log')
            try:
                if cls.send('/healthz', {})[0] == 403:
                    return
            except OSError:
                pass
            time.sleep(0.1)
        raise RuntimeError('Isolated Gunicorn did not become ready')

    @classmethod
    def stop_server(cls):
        cls.server.terminate()
        try:
            cls.server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait(timeout=5)

    @classmethod
    def send(cls, target, headers, body=b'', method='GET', chunked=False):
        connection = http.client.HTTPConnection('127.0.0.1', cls.port, timeout=5)
        try:
            connection.request(method, target, body=iter([body]) if chunked else body,
                               headers=headers, encode_chunked=chunked)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def headers(self, target, body=b'', method='GET', **overrides):
        req = dict(key_id='http-test', method=method, target=target, content_type='application/octet-stream',
                   body=body, timestamp=str(int(time.time())), nonce=secrets.token_hex(16),
                   subject='slack:TTEST:UTEST') | overrides
        headers = {'X-LaBook-' + k.replace('_', '-'): req[k] for k in ['key_id', 'timestamp', 'nonce', 'subject']}
        headers.update({'X-LaBook-Signature': sign_request(self.secret, **req),
                        'Content-Type': req['content_type']})
        return headers

    def test_binary_and_chunked_body_integrity(self):
        body = bytes(range(256))
        for chunked in [False, True]:
            status, headers, output = self.send('/echo?q=%E6%9C%AC&a=1&a=2',
                self.headers('/echo?q=%E6%9C%AC&a=1&a=2', body, 'POST'), body, 'POST', chunked)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(output)['body_hex'], body.hex())
            self.assertEqual(headers['Cache-Control'], 'private, no-store')

    def test_unsigned_replay_tamper_expiry_and_other_workspace(self):
        self.assertEqual(self.send('/healthz', {})[0], 403)
        headers = self.headers('/echo')
        self.assertEqual(self.send('/echo', headers)[0], 200)
        self.assertEqual(self.send('/echo', headers)[0], 403)
        self.assertEqual(self.send('/different', self.headers('/echo'))[0], 403)
        self.assertEqual(self.send('/echo', self.headers('/echo', timestamp='1'))[0], 403)
        self.assertEqual(self.send('/echo', self.headers('/echo', subject='slack:TOTHER:U1'))[0], 403)

    def test_raw_paths_query_and_fixed_public_redirect(self):
        target = '/%E6%9C%AC?a=1&a=2&x=%25'
        status, _, output = self.send(target, self.headers(target) | {'Cookie': 'wordpress=untrusted',
            'X-Forwarded-Host': 'attacker.example', 'X-Forwarded-Prefix': '/wrong'})
        self.assertEqual(status, 200)
        result = json.loads(output)
        self.assertEqual(result['path'], '/本')
        self.assertEqual(result['query'], 'a=1&a=2&x=%25')
        self.assertIsNone(result['cookie'])
        self.assertEqual(result['host'], 'public.example')
        self.assertEqual(result['script_root'], '/labook')
        status, headers, _ = self.send('/redirect', self.headers('/redirect'))
        self.assertEqual((status, headers['Location']), (302, 'https://public.example/labook/destination'))
        for target in ['/a%2fb', '/a/../b', '/a//b', '/a%252fb']:
            self.assertEqual(self.send(target, self.headers(target))[0], 403)

    def test_body_limit(self):
        body = b'x' * 1025
        self.assertEqual(self.send('/echo', self.headers('/echo', body, 'POST'), body, 'POST')[0], 413)
        self.assertEqual(self.send('/echo', self.headers('/echo', body, 'POST'), body, 'POST', True)[0], 413)


if __name__ == '__main__':
    unittest.main()
