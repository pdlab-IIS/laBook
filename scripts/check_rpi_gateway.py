"""Stage only isolated gateway tests over SSH; never deploy the production app.

Config and report paths must be inside ignored deploy/local. The remote root is
created exclusively and must not exist. The temporary HTTP server binds loopback
and is stopped by unittest cleanup. No ngrok, service, or business DB is changed.
"""
import argparse
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import sys

from prepare_sakura_preview import ROOT, archive, ssh


def private_path(value):
    path = Path(value).resolve()
    if not path.is_relative_to(ROOT / 'deploy/local'):
        raise ValueError('Configuration and reports must be in deploy/local')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    config = json.loads(private_path(args.config).read_text(encoding='utf-8-sig'))
    report_path = private_path(args.report)
    remote = PurePosixPath(config['test_root'])
    if (not remote.is_absolute() or '..' in remote.parts or len(remote.parts) < 4
            or not remote.name.startswith('labook-gateway-test-')):
        raise ValueError('Use a dedicated absolute labook-gateway-test-* directory')
    files = {}
    for name in ['gateway/__init__.py', 'gateway/inbound.py', 'gateway/signing.py',
                 'tests/test_gateway_signing.py', 'tests/test_gateway_inbound.py',
                 'tests/test_gateway_http.py', 'tests/fixtures/gateway_probe.py']:
        files[name] = (ROOT / name).read_bytes()
    service = shlex.quote(config['service'])
    before = ssh(config, 'systemctl is-active ' + service).decode().strip()
    if before != 'active':
        raise RuntimeError('Production service is not active; investigate before testing')
    ssh(config, 'umask 077 && mkdir ' + shlex.quote(str(remote)))
    ssh(config, 'tar -xzf - -C ' + shlex.quote(str(remote)), archive(files))
    command = ('cd ' + shlex.quote(str(remote)) + ' && PYTHONDONTWRITEBYTECODE=1 '
               + shlex.quote(config['python']) + ' -m unittest discover -s tests -p '
               + shlex.quote('test_gateway*.py') + ' -v')
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                             config['ssh_target'], command], capture_output=True, timeout=90)
    after = ssh(config, 'systemctl is-active ' + service).decode().strip()
    report = dict(service_before=before, service_after=after, tests_passed=result.returncode == 0,
                  output=(result.stdout + result.stderr).decode(errors='replace'), test_root=str(remote))
    report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(report['output'])
    print('Existing service state preserved:', before == after == 'active')
    return 0 if report['tests_passed'] and after == 'active' else 1


if __name__ == '__main__':
    sys.exit(main())
