"""Run gateway component tests in a fresh private Sakura directory, without publishing."""
import argparse
import json
from pathlib import PurePosixPath
import shlex

from check_rpi_gateway import private_path
from prepare_sakura_preview import ROOT, archive, signature_vectors, snapshot, ssh


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--check-only', action='store_true', help='Recheck an already staged private test directory')
    args = parser.parse_args()
    config = json.loads(private_path(args.config).read_text(encoding='utf-8-sig'))
    report_path = private_path(args.report)
    remote = PurePosixPath(config['test_root'])
    if (not remote.is_absolute() or '..' in remote.parts or 'www' in remote.parts
            or len(remote.parts) < 4 or not remote.name.startswith('labook-gateway-test-')):
        raise ValueError('Use a dedicated private labook-gateway-test-* directory')
    before = snapshot(config)
    files = {str(p.relative_to(ROOT / 'gateway/sakura')).replace('\\', '/'): p.read_bytes()
             for folder in ['src', 'tests'] for p in (ROOT / 'gateway/sakura' / folder).glob('*.php')}
    files['app.php'] = (ROOT / 'gateway/sakura/app.php').read_bytes()
    if not args.check_only:
        ssh(config, 'umask 077 && mkdir ' + shlex.quote(str(remote)))
        ssh(config, 'tar -xzf - -C ' + shlex.quote(str(remote)), archive(files))
    tests = {}
    # Reuse one connection: shared hosting can throttle many short SSH sessions.
    commands = ['php -l ' + shlex.quote(str(remote / name)) + ' >/dev/null' for name in files]
    commands += ['php ' + shlex.quote(str(remote / ('tests/' + name)))
                 for name in ['security_test.php', 'session_test.php', 'gateway_test.php', 'store_test.php', 'auth_test.php', 'asset_cache_test.php']]
    output = ssh(config, ' && '.join(commands), json.dumps(signature_vectors()).encode()).decode()
    decoder = json.JSONDecoder()
    for key in ['signing', 'sessions', 'gateway', 'store', 'auth', 'asset_cache']:
        result, end = decoder.raw_decode(output.lstrip())
        tests[key] = result
        output = output.lstrip()[end:]
    after = snapshot(config)
    report = dict(before=before, after=after, tests=tests, unchanged=before == after)
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(dict(tests=tests, existing_routes_unchanged=before == after)))
    if before != after:
        raise RuntimeError('Existing route snapshot changed; inspect private report')


if __name__ == '__main__':
    main()
