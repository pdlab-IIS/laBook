"""Deploy only the independent Slack sign-in demo; real settings stay ignored."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sys
import time
import urllib.request

from prepare_sakura_preview import ssh, archive, php_string, snapshot, request, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if not args.config.resolve().is_relative_to((ROOT / 'deploy/local').resolve()):
        raise ValueError('Real configuration must be inside deploy/local')
    env = json.loads(args.config.read_text(encoding='utf-8'))
    private = env['private_root']
    public = env['site_root'] + '/slack-signin-demo'
    base = env['origin'] + '/slack-signin-demo'
    before = snapshot(env)
    report = {'before': before}
    report_path = args.config.with_name('slack-demo-report.local.json')
    source = ROOT / 'gateway/slack-demo'
    if not args.check_only:
        # Refuse to overwrite another installation or anything inside public storage.
        if '/www/' in private or not private.startswith('/home/') or '/..' in private:
            raise ValueError('Private directory must be outside www')
        ssh(env, f'test ! -e {shlex.quote(public)} && umask 077 && mkdir {shlex.quote(private)}')
        # Pin Composer by the official checksum fetched over validated HTTPS.
        phar = urllib.request.urlopen('https://getcomposer.org/download/latest-stable/composer.phar', timeout=30).read()
        expected = urllib.request.urlopen('https://getcomposer.org/download/latest-stable/composer.phar.sha256sum', timeout=30).read().decode().split()[0]
        if hashlib.sha256(phar).hexdigest() != expected:
            raise RuntimeError('Composer checksum mismatch')
        files = {str(p.relative_to(source)).replace('\\', '/'): p.read_bytes()
                 for p in source.rglob('*') if p.is_file() and 'vendor' not in p.parts
                 and '.local.' not in p.name}
        files['composer.phar'] = phar
        config = {'client_id': '', 'client_secret': '', 'expected_team_id': '',
                  'public_url': base, 'expires_at': int(time.time()) + 14 * 86400}
        files['config.local.json'] = json.dumps(config).encode()
        ssh(env, 'tar -xzf - -C ' + shlex.quote(private), archive(files))
        command = ('cd ' + shlex.quote(private)
                   + ' && umask 077 && mkdir -p state/sessions'
                   + ' && php composer.phar install --no-dev --no-interaction --no-plugins --no-scripts --prefer-dist'
                   + ' && php composer.phar audit --no-interaction --no-dev'
                   + ' && php tests/run.php')
        output = ssh(env, command).decode()
        report['security_tests'] = json.loads(output.strip().splitlines()[-1])
        # Lockfile contains public dependency metadata only.
        (source / 'composer.lock').write_bytes(ssh(env, 'cat ' + shlex.quote(private + '/composer.lock')))
        entry = "<?php\nini_set('display_errors', '0');\nif (PHP_VERSION_ID < 80200) { http_response_code(503); exit; }\n$demoAction = ACTION;\nrequire APP;\n"
        public_files = {name: entry.replace('ACTION', php_string(action)).replace('APP', php_string(private + '/app.php')).encode()
                        for name, action in [('index.php', 'index'), ('callback.php', 'callback')]}
        ssh(env, 'mkdir -m 755 ' + shlex.quote(public))
        ssh(env, 'tar -xzf - -C ' + shlex.quote(public), archive(public_files))
        ssh(env, 'chmod 644 ' + shlex.quote(public + '/index.php') + ' ' + shlex.quote(public + '/callback.php'))
    status, headers, body = request(base + '/index.php')
    assert status == 200 and 'Slack Appの設定待ち'.encode() in body, 'setup page failed'
    assert 'no-store' in headers.get('Cache-Control', ''), 'cache policy missing'
    assert 'frame-ancestors' in headers.get('Content-Security-Policy', ''), 'CSP missing'
    assert b'client_secret' not in body, 'secret field exposed'
    status, _, body = request(base + '/callback.php', method='POST', data=b'state=invalid&code=fake', content_type='application/x-www-form-urlencoded')
    assert status == 400 and '成功しました'.encode() not in body, 'invalid callback accepted'
    after = snapshot(env)
    report['after'] = after
    report['web_checks'] = {'setup': 'passed', 'invalid_callback': 'rejected', 'existing_unchanged': before == after}
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    assert before == after, 'existing routes or root htaccess changed'
    print(json.dumps({'status': 'demo_ready_configuration_pending', 'tests': report.get('security_tests'),
                      'web_checks': report['web_checks'], 'public_url': base + '/index.php'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
