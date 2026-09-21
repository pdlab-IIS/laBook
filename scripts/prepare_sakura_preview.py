"""Deploy a private diagnostic preview without editing existing site files.

All real paths, connection details, generated tokens, and reports belong in the
ignored deploy/local directory. This is NOT the production gateway installer.
"""

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import secrets
import shlex
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gateway.signing import sign_request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def ssh(config, command, data=None):
    options = ['-J', config['ssh_jump']] if config.get('ssh_jump') else []
    result = subprocess.run(['ssh', *options, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                             config['ssh_target'], command], input=data, capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError('Remote operation failed: ' + result.stderr.decode(errors='replace')[:400])
    return result.stdout


def request(url, *, method='GET', token=None, data=None, content_type=None):
    headers = {'User-Agent': 'laBook-preview-check/1'}
    if token:
        headers['X-LaBook-Preview-Token'] = token
    if content_type:
        headers['Content-Type'] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(NoRedirect)
    try:
        response = opener.open(req, timeout=25)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, dict(response.headers), response.read(131072)


def snapshot(config):
    routes = {}
    for route in ['/', '/wp-login.php', '/wp-json/', '/labook', '/L']:
        status, headers, _ = request(config['origin'] + route)
        routes[route] = {'status': status, 'location': headers.get('Location')}
    digest = ssh(config, 'sha256 -q ' + shlex.quote(config['site_root'] + '/.htaccess')).decode().strip()
    return {'htaccess_sha256': digest, 'routes': routes}


def archive(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for name, body in files.items():
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode = len(body), 0o600
            tar.addfile(entry, io.BytesIO(body))
    return buffer.getvalue()


def php_string(value):
    return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"


def signature_vectors():
    vectors = []
    for i, (content_type, body) in enumerate([
        ('application/json', '{"title":"試験"}'.encode()),
        ('application/octet-stream', bytes(range(256))),
        ('multipart/form-data; boundary=test-boundary', b'--test-boundary\r\nraw\x00body\r\n'),
        ('', b''),
    ]):
        secret = b'test-only-key-never-use-in-deploy!'
        req = dict(key_id='test-key', method='POST', target='/books?q=%E6%9C%AC&a=1&a=2',
                   content_type=content_type, timestamp='2000000000', nonce=f'{i:032x}', subject='test-subject')
        vectors.append(dict(secret=base64.b64encode(secret).decode(), request=req,
                            body=base64.b64encode(body).decode(), expected=sign_request(secret, body=body, **req)))
    return vectors


def deploy(config, state_path):
    before = snapshot(config)
    private = config['private_root']
    public = config['site_root'] + '/' + config['preview_dir']
    # mkdir (without -p) refuses to replace any existing application directory.
    ssh(config, 'test ! -e {pub} && umask 077 && mkdir {priv}'.format(
        pub=shlex.quote(public), priv=shlex.quote(private)))
    state = {'before': before, 'token': secrets.token_hex(32), 'expires': int(time.time()) + 7 * 86400}
    state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
    files = {
        'probe.php': (ROOT / 'gateway/sakura/preview/probe.php').read_bytes(),
        'src/Security.php': (ROOT / 'gateway/sakura/src/Security.php').read_bytes(),
        'tests/security_test.php': (ROOT / 'gateway/sakura/tests/security_test.php').read_bytes(),
        'probe-config.json': json.dumps({'token': state['token'], 'expires': state['expires']}).encode(),
    }
    ssh(config, 'tar -xzf - -C ' + shlex.quote(private), archive(files))
    test = ssh(config, 'php ' + shlex.quote(private + '/tests/security_test.php'),
               json.dumps(signature_vectors()).encode())
    state['php_security_tests'] = json.loads(test)
    entry = """<?php
ini_set('display_errors', '0');
if (PHP_VERSION_ID < 80100) { http_response_code(503); exit; }
$probeConfig = json_decode(file_get_contents(CONFIG), true);
require PROBE;
""".replace('CONFIG', php_string(private + '/probe-config.json')).replace('PROBE', php_string(private + '/probe.php'))
    # Publish only after private configuration and CLI tests are complete.
    ssh(config, 'mkdir -m 755 {pub} && cat > {entry} && chmod 644 {entry}'.format(
        pub=shlex.quote(public), entry=shlex.quote(public + '/index.php')), entry.encode())
    state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')


def check(config, state_path):
    state = json.loads(state_path.read_text(encoding='utf-8'))
    base = config['origin'] + '/' + config['preview_dir'] + '/index.php'
    checks = {}
    for label, token in [('anonymous', None), ('wrong_token', 'invalid')]:
        status, _, body = request(base, token=token)
        assert status == 404 and json.loads(body) == {'error': 'not_found'}, label
        checks[label] = 'rejected'
    status, headers, body = request(base + '?action=runtime', token=state['token'])
    assert status == 200, 'runtime probe failed'
    runtime = json.loads(body)
    assert all(runtime['extensions'].values()), 'missing Web PHP extension'
    assert 'no-store' in headers.get('Cache-Control', ''), 'cache policy missing'
    checks['runtime'] = runtime
    status, _, body = request(base + '?action=egress', token=state['token'])
    assert status == 200, 'egress probe failed'
    checks['egress'] = json.loads(body)
    methods = []
    for method in ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']:
        payload = b'' if method == 'GET' else '{"probe":"試験"}'.encode()
        status, _, body = request(base + '?action=transport', method=method, token=state['token'],
                                  data=payload if method != 'GET' else None, content_type='application/json')
        echo = json.loads(body)
        assert status == 200 and echo['method'] == method and echo['sha256'] == hashlib.sha256(payload).hexdigest()
        methods.append(method)
    checks['methods'] = methods
    image = b'laBook disposable upload probe\x00\xff'
    multipart = (b'--probe-boundary\r\nContent-Disposition: form-data; name="cover"; filename="probe.jpg"\r\n'
                 b'Content-Type: image/jpeg\r\n\r\n' + image + b'\r\n--probe-boundary--\r\n')
    status, _, body = request(base + '?action=transport', method='POST', token=state['token'], data=multipart,
                              content_type='multipart/form-data; boundary=probe-boundary')
    echo = json.loads(body)
    assert status == 200 and echo['files']['cover']['sha256'] == hashlib.sha256(image).hexdigest()
    checks['multipart'] = {'file_preserved': True, 'raw_body_available': echo['bytes'] > 0}
    status, _, _ = request(base + '?action=transport', method='POST', token=state['token'],
                           data=json.dumps({'values': list(range(2048))}).encode(), content_type='application/json')
    assert status in (403, 413), 'body limit missing'
    php_status = ssh(config, 'tail -n 1 ' + shlex.quote(config['private_root'] + '/probe-status.log')).decode().split()[-1]
    assert php_status == '413', 'PHP body limit was not exercised'
    checks['oversize'] = {'php_status': 413, 'http_status': status, 'response_rewritten': status != 413}
    status, _, _ = request(base + '?action=transport', method='POST', token=state['token'],
                           data=json.dumps({'values': list(range(17500))}).encode(), content_type='application/json')
    assert status in (403, 413), 'large diagnostic body was not rejected'
    php_status = ssh(config, 'tail -n 1 ' + shlex.quote(config['private_root'] + '/probe-status.log')).decode().split()[-1]
    checks['large_body'] = {'http_status': status, 'php_status': int(php_status),
                            'needs_investigation': status != int(php_status)}
    after = snapshot(config)
    state['checks'], state['after'], state['checked_at'] = checks, after, int(time.time())
    state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
    assert after == state['before'], 'existing routes or root htaccess changed; inspect private report'
    print(json.dumps({'status': 'checks_completed', 'existing_routes': 'unchanged',
                      'root_htaccess': 'unchanged', 'web_php': runtime['php'], 'sapi': runtime['sapi'],
                      'methods': methods, 'multipart': checks['multipart'],
                      'large_body': checks['large_body'],
                      'oversize': checks['oversize'],
                      'php_security_tests': state['php_security_tests'],
                      'private_report': str(state_path)}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--deploy', action='store_true')
    args = parser.parse_args()
    if not args.config.resolve().is_relative_to((ROOT / 'deploy/local').resolve()):
        raise ValueError('Keep configuration and generated reports inside ignored deploy/local')
    config = json.loads(args.config.read_text(encoding='utf-8'))
    for key in ['site_root', 'private_root']:
        path = PurePosixPath(config[key])
        if not path.is_absolute() or '..' in path.parts:
            raise ValueError('Absolute normalized paths are required')
    private = PurePosixPath(config['private_root'])
    if 'www' in private.parts or private.is_relative_to(PurePosixPath(config['site_root'])):
        raise ValueError('Private storage must be outside every public www directory')
    if config['preview_dir'] != 'auth-labook-preview':
        raise ValueError('Only the reserved independent preview directory is supported')
    if not config['origin'].startswith('https://') or config['origin'].endswith('/'):
        raise ValueError('HTTPS origin required, without trailing slash')
    state_path = args.config.with_name('sakura-preview-state.local.json')
    if args.deploy:
        if state_path.exists():
            raise ValueError('Preview state already exists; use check mode')
        deploy(config, state_path)
    check(config, state_path)


if __name__ == '__main__':
    main()
