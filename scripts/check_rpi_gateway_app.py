"""Stage the real application and run isolated loopback integration on the RPi.

Never starts ngrok, modifies system services or copies real library data/secrets.
Configuration/report paths must be in ignored deploy/local.
"""
import argparse
import json
from pathlib import PurePosixPath
import shlex
import subprocess
from check_rpi_gateway import private_path
from prepare_sakura_preview import ROOT,archive,ssh


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True);parser.add_argument('--report',required=True)
    args=parser.parse_args()
    c=json.loads(private_path(args.config).read_text(encoding='utf-8-sig'))
    report_path=private_path(args.report)
    root=PurePosixPath(c['test_root'])
    if not root.is_absolute() or '..' in root.parts or len(root.parts)<4 or not root.name.startswith('labook-integration-test-'):
        raise ValueError('Use a new isolated integration directory')
    files={}
    for name in ['app.py','db.py','user_entities.py','config.py','fetch_book_info.py','http_config.py','logger_config.py','outbound_policy.py']:
        files[name]=(ROOT/name).read_bytes()
    for folder,pattern in [('routes','*.py'),('gateway','*.py'),('templates','*.html')]:
        for p in (ROOT/folder).glob(pattern):files[p.relative_to(ROOT).as_posix()]=p.read_bytes()
    # Copy tracked static assets only, never covers, env, keys or local files.
    for name in subprocess.check_output(['git','ls-files','static'],cwd=ROOT,text=True).splitlines():
        files[name]=(ROOT/name).read_bytes()
    files['run_trial.py']=(ROOT/'tests/run_isolated_gateway_app.py').read_bytes()
    gateway=json.loads(private_path(c['gateway_file']).read_text(encoding='utf-8-sig'))
    if gateway['nonce_database']!=str(root/'state/nonces.sqlite'):
        raise ValueError('Nonce DB must stay in the isolated trial directory')
    files['gateway.local.json']=json.dumps(gateway).encode()
    q=shlex.quote
    before=ssh(c,'systemctl show '+q(c['service'])+' -p ActiveState -p MainPID -p ExecMainStartTimestampMonotonic').decode()
    if 'ActiveState=active' not in before:raise RuntimeError('Production service is not active')
    command=' && '.join(['umask 077','mkdir '+q(str(root)),'tar -xzf - -C '+q(str(root)),
        'mkdir '+q(str(root/'state'))+' '+q(str(root/'covers')),'cd '+q(str(root)),
        'PYTHONDONTWRITEBYTECODE=1 '+q(c['python'])+' run_trial.py'])
    output=ssh(c,command,archive(files)).decode()
    tests=json.loads(output)
    after=ssh(c,'systemctl show '+q(c['service'])+' -p ActiveState -p MainPID -p ExecMainStartTimestampMonotonic').decode()
    result={'tests':tests,'production_service_unchanged':before==after,'service_before':before,'service_after':after}
    report_path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'checks':tests['checks'],'status':tests['status'],'trial_process_stopped':tests['trial_process_stopped'],'production_service_unchanged':before==after}))
    if before!=after:raise RuntimeError('Production service state changed; inspect report')


if __name__=='__main__':main()
