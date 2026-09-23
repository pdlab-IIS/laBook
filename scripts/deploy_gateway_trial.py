"""Publish an independent expiring Slack session trial with upstream relay disabled.

Never changes WordPress, the existing demo, ngrok, or RPi. Real configuration,
credentials and reports must be under deploy/local. Refuses existing directories.
"""
import argparse
import html
import http.cookiejar
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import time
import urllib.error
import urllib.parse
import urllib.request

from check_rpi_gateway import private_path
from prepare_sakura_preview import ROOT, NoRedirect, archive, php_string, snapshot, ssh


def check_web(config):
    origin = config['origin']
    base = origin + '/' + config['public_dir']
    count = 0

    def expect(ok, label):
        nonlocal count
        if not ok:
            raise RuntimeError(label)
        count += 1

    for method in ['GET', 'POST']:
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar), NoRedirect)

        def request(path, data=None, headers=None):
            req = urllib.request.Request(base + path, data=data, headers=headers or {})
            try:
                response = opener.open(req, timeout=20)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                return response.status, response.headers, response.read(131072).decode()

        status, _, _ = request('/index.php/books', headers={'Accept': 'application/json'})
        expect(status == 401, 'anonymous API must return 401')
        status, _, _ = request('/index.php/books', data=b'{}', headers={'Content-Type': 'application/json', 'Origin': origin})
        expect(status == 401, 'anonymous mutation must return 401')
        status, headers, _ = request('/index.php/L/ABC', headers={'Accept': 'text/html'})
        expect(status == 303 and '/_auth/login?return=' in headers.get('Location', ''), 'shelf login return missing')
        status, headers, body = request('/index.php/_auth/login?return=%2F%2Foutside.invalid')
        expect(status == 200, 'login form or PATH_INFO unavailable')
        nonce = re.search(r'<script nonce="([A-Za-z0-9+/=]+)">', body)
        expect(nonce is not None and "script-src 'nonce-" + nonce.group(1) + "'" in headers.get('Content-Security-Policy', ''), 'automatic login script lacks CSP nonce')
        expect('document.getElementById("slack-login").submit()' in body and '<noscript><button>' in body, 'automatic login or no-script fallback missing')
        expect('no-store' in headers.get('Cache-Control', '') and headers.get('Referrer-Policy') == 'strict-origin', 'privacy headers missing')
        token = re.search(r'name="csrf" value="([a-f0-9]{64})"', body)
        expect(token is not None, 'login CSRF missing')
        expect('value="/' + config['public_dir'] + '/index.php/"' in body, 'unsafe return URL retained')
        cookie = next(c for c in jar if c.name in ['LABOOK_GATE_PREAUTH', 'ENC_LABOOK_GATE_PREAUTH'])
        expect(cookie.secure and cookie.path == '/' + config['public_dir'] + '/'
               and cookie.get_nonstandard_attr('SameSite') == 'Lax', 'session cookie attributes invalid')
        payload = urllib.parse.urlencode({'csrf': token.group(1), 'return': '/' + config['public_dir'] + '/index.php/'}).encode()
        status, _, _ = request('/index.php/_auth/login', data=payload, headers={'Origin': 'https://outside.invalid'})
        expect(status == 403, 'wrong Origin accepted')
        status, _, _ = request('/index.php/_auth/login', data=payload, headers={'Origin': 'null'})
        expect(status == 403, 'null Origin accepted')
        status, _, _ = request('/index.php/_auth/login', data=payload)
        expect(status == 403, 'missing Origin accepted')
        status, _, _ = request('/index.php/_auth/login', data=b'csrf=wrong', headers={'Origin': origin})
        expect(status == 403, 'wrong CSRF accepted')
        status, _, body = request('/index.php/_auth/login?flow=current', data=payload, headers={'Origin': origin})
        refresh = re.search(r'<meta http-equiv="refresh" content="0;url=([^"]+)">', body)
        expect(status == 200 and refresh is not None, 'Slack navigation unavailable')
        destination = urllib.parse.urlsplit(html.unescape(refresh.group(1)))
        expect(destination.scheme == 'https' and destination.netloc.endswith('.slack.com'), 'fixed workspace entry missing')
        resume = urllib.parse.urlsplit(urllib.parse.parse_qs(destination.query)['redir'][0])
        params = urllib.parse.parse_qs(resume.query)
        expect(params['redirect_uri'] == [base + '/callback.php'], 'wrong callback')
        expect('team' not in params and 'response_mode' not in params, 'query overrode configured login flow')
        tx_cookie = next(c for c in jar if c.name in ['LABOOK_GATE_TX', 'ENC_LABOOK_GATE_TX'])
        expect(tx_cookie.secure and tx_cookie.get_nonstandard_attr('SameSite') == 'None', 'callback cookie invalid')
        state = params['state'][0]

        def callback(state_value):
            data = urllib.parse.urlencode({'state': state_value, 'error': 'access_denied'})
            return request('/callback.php' + ('?' + data if method == 'GET' else ''),
                           data=data.encode() if method == 'POST' else None)

        status, _, _ = callback('0' * 64)
        expect(status == 400, 'invalid state accepted')
        original = tx_cookie.value
        tx_cookie.value = '0' * 64
        status, _, _ = callback(state)
        expect(status == 400, 'invalid browser cookie accepted')
        tx_cookie.value = original
        status, _, _ = callback(state)
        expect(status == 400, 'cancel callback not handled')
        jar.set_cookie(tx_cookie)
        status, _, _ = callback(state)
        expect(status == 400, 'replay accepted')
        status, _, _ = request('/index.php/_auth/session')
        expect(status == 401, 'cancellation created a session')
        status, _, body = request('/index.php/_auth/logged-out')
        expect(status == 200 and 'ログアウトしました' in body and '<script' not in body, 'logout must not restart automatic login')
    return {'checks': count, 'status': 'passed', 'real_slack_login': 'pending'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--deploy', action='store_true')
    args = parser.parse_args()
    config = json.loads(private_path(args.config).read_text(encoding='utf-8-sig'))
    report_path = private_path(args.report)
    private = PurePosixPath(config['private_root'])
    public_dir = config['public_dir']
    if (not private.is_absolute() or 'www' in private.parts or '..' in private.parts
            or len(private.parts) < 4 or not private.name.startswith('labook-gateway-trial-')
            or not re.fullmatch(r'auth-labook-trial(?:-[a-z0-9]+)?', public_dir)):
        raise ValueError('Use new dedicated private and public trial directories')
    public = config['site_root'] + '/' + public_dir
    before = snapshot(config)
    report = {'before': before}
    if args.deploy:
        client = json.loads(private_path(config['client_file']).read_text(encoding='utf-8-sig'))
        settings = {key: client[key] for key in ['client_id', 'client_secret', 'expected_team_id', 'workspace_login_url']}
        settings.update(public_origin=config['origin'], public_prefix='/' + public_dir + '/index.php',
            public_url=config['origin'] + '/' + public_dir, session_generation='trial-1', revoked_subjects=[],
            login_flow='workspace-entry', relay_enabled=False, expires_at=int(time.time()) + 7 * 86400)
        if not re.fullmatch('T[A-Z0-9]+', settings['expected_team_id']):
            raise ValueError('Expected workspace must be configured')
        source = ROOT / 'gateway/sakura'
        files = {str(p.relative_to(source)).replace('\\', '/'): p.read_bytes()
                 for folder in ['src', 'tests'] for p in (source / folder).glob('*.php')}
        files['app.php'] = (source / 'app.php').read_bytes()
        files['oidc/Oidc.php'] = (ROOT / 'gateway/slack-demo/src/Oidc.php').read_bytes()
        files['config.local.json'] = json.dumps(settings).encode()
        for name, action in [('index.php', 'index'), ('callback.php', 'callback')]:
            files['public/' + name] = ("<?php\nini_set('display_errors', '0');\n"
                "if (PHP_VERSION_ID < 80200) { http_response_code(503); exit; }\n$gatewayAction = "
                + php_string(action) + ';\nrequire ' + php_string(str(private / 'app.php')) + ';\n').encode()
        q = shlex.quote
        commands = ['test ! -e ' + q(public), 'umask 077', 'mkdir ' + q(str(private)),
            'tar -xzf - -C ' + q(str(private)),
            'cp -R ' + q(config['vendor_source'] + '/vendor') + ' ' + q(str(private / 'vendor')),
            'mkdir -p ' + q(str(private / 'state/sessions'))]
        commands += ['php -l ' + q(str(private / name)) + ' >/dev/null' for name in files if name.endswith('.php')]
        commands += ['php ' + q(str(private / 'tests/session_test.php')),
                     'php ' + q(str(private / 'tests/gateway_test.php')),
                     'php ' + q(str(private / 'tests/store_test.php')),
                     'php ' + q(str(private / 'tests/auth_test.php')),
                     'mkdir -m 755 ' + q(public),
                     'cp ' + q(str(private / 'public/index.php')) + ' ' + q(str(private / 'public/callback.php')) + ' ' + q(public),
                     'chmod 644 ' + q(public + '/index.php') + ' ' + q(public + '/callback.php')]
        report['private_tests'] = ssh(config, ' && '.join(commands), archive(files)).decode()
    report['web_tests'] = check_web(config)
    report['after'] = snapshot(config)
    report['existing_unchanged'] = report['before'] == report['after']
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if not report['existing_unchanged']:
        raise RuntimeError('Existing site snapshot changed; inspect private report')
    print(json.dumps({'web_tests': report['web_tests'], 'existing_unchanged': True,
                     'login_url': config['origin'] + '/' + public_dir + '/index.php/_auth/login',
                     'callback_url': config['origin'] + '/' + public_dir + '/callback.php'}))


if __name__ == '__main__':
    main()
