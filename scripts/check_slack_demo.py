"""Exercise only the demo's callback boundary, without contacting Slack.

Configuration stays in an ignored local file. No codes, cookies, credentials,
authorization URLs, or identities are written to output.
"""
import argparse
import html
import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from prepare_sakura_preview import NoRedirect


def check(config, flow='select-workspace'):
    base = config['origin'].rstrip('/') + '/slack-signin-demo/'
    entry = 'index.php' + ('?flow=' + flow if flow != 'select-workspace' else '')
    count = 0

    def expect(condition, label):
        nonlocal count
        if not condition:
            raise RuntimeError(label)
        count += 1

    for method in ['GET', 'POST']:
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar), NoRedirect)

        def request(path, data=None):
            try:
                response = opener.open(base + path, data=data, timeout=20)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                return response.status, response.headers, response.read(131072).decode()

        status, headers, body = request(entry)
        expect(status == 200, 'top unavailable')
        csrf = re.search(r'name="csrf" value="([a-f0-9]{64})"', body)
        expect(csrf is not None, 'login form unavailable')
        status, headers, body = request(entry, urllib.parse.urlencode(
            {'action': 'login', 'csrf': csrf.group(1)}).encode())
        location = urllib.parse.urlsplit(headers.get('Location', ''))
        if flow == 'workspace-entry':
            refresh = re.search(r'<meta http-equiv="refresh" content="0;url=([^"]+)">', body)
            expect(status == 200 and refresh is not None, 'workspace navigation page invalid')
            location = urllib.parse.urlsplit(html.unescape(refresh.group(1)))
            expect(location.scheme == 'https'
                   and re.fullmatch(r'[a-z0-9-]+\.slack\.com', location.netloc)
                   and location.path == '/', 'workspace redirect invalid')
            outer = urllib.parse.parse_qs(location.query)
            resume = urllib.parse.urlsplit(outer['redir'][0])
            expect(not resume.netloc and not resume.scheme and resume.path == '/oauth',
                   'workspace continuation invalid')
            location = resume
        else:
            expect(status == 303 and location.scheme == 'https'
                   and location.netloc == 'slack.com'
                   and location.path == '/openid/connect/authorize', 'login redirect invalid')
        params = urllib.parse.parse_qs(location.query)
        expect(('response_mode' not in params) if flow != 'current'
               else params.get('response_mode') == ['form_post'], 'response mode invalid')
        if flow == 'select-workspace':
            expect('team' not in params, 'workspace hint still present')
        state = params['state'][0]
        # Some hosting edges wrap cookie names/values before sending them.
        cookie = next(c for c in jar if c.name in ['LABOOK_SLACK_TX', 'ENC_LABOOK_SLACK_TX'])
        expect(cookie.secure and cookie.get_nonstandard_attr('SameSite') == 'None',
               'callback cookie attributes invalid')

        def callback(value):
            payload = urllib.parse.urlencode({'state': value, 'error': 'access_denied'})
            return request('callback.php' + ('?' + payload if method == 'GET' else ''),
                           payload.encode() if method == 'POST' else None)

        # Wrong browser binding cannot consume the legitimate transaction.
        original = cookie.value
        cookie.value = '0' * 64
        status, _, body = callback(state)
        expect(status == 400 and any(code in body for code in ['state_invalid', 'cookie_missing']),
               'tampered browser cookie accepted')
        cookie.value = original
        status, _, body = callback('1' * 64)
        expect(status == 400 and 'state_invalid' in body, 'wrong state accepted')
        jar.clear(cookie.domain, cookie.path, cookie.name)
        status, _, body = callback(state)
        expect(status == 400 and 'cookie_missing' in body, 'missing cookie accepted')
        jar.set_cookie(cookie)
        status, headers, _ = callback(state)
        expect(status == 303 and headers.get('Location') == base + 'index.php',
               method + ' callback did not return to top')
        status, headers, body = request('index.php')
        expect(status == 200 and 'キャンセルまたは拒否' in body
               and 'Slackログインに成功しました' not in body, 'cancel result invalid')
        expect('no-store' in headers.get('Cache-Control', '')
               and headers.get('Referrer-Policy') == 'no-referrer', 'privacy headers missing')
        jar.set_cookie(cookie)
        status, _, body = callback(state)
        expect(status == 400 and 'state_invalid' in body, 'replayed response accepted')
        status, _, body = request('index.php', urllib.parse.urlencode(
            {'action': 'login', 'csrf': 'wrong'}).encode())
        expect(status == 400 and 'csrf_invalid' in body, 'invalid CSRF accepted')
    return {'status': 'passed', 'checks': count,
            'note': 'Simulated cancellation only; real Slack login and browser SameSite behavior require a user trial.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--flow', choices=['current', 'standard', 'select-workspace', 'workspace-entry'], default='select-workspace')
    args = parser.parse_args()
    print(json.dumps(check(json.loads(args.config.read_text(encoding='utf-8')), args.flow)))
