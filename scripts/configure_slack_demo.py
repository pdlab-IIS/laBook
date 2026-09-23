"""Apply Slack demo credentials from ignored files without printing their values."""
import argparse
import json
from pathlib import Path
import re
import shlex

from prepare_sakura_preview import ssh, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True, help='Ignored deployment config')
    parser.add_argument('--credentials', type=Path, required=True, help='Ignored Slack client JSON')
    args = parser.parse_args()
    for path in [args.config, args.credentials]:
        if not path.resolve().is_relative_to((ROOT / 'deploy/local').resolve()):
            raise ValueError('Both files must be in ignored deploy/local')
    env = json.loads(args.config.read_text(encoding='utf-8-sig'))
    client = json.loads(args.credentials.read_text(encoding='utf-8-sig'))
    if not isinstance(client.get('client_id'), str) or not re.fullmatch(r'[0-9]+\.[0-9]+', client['client_id']):
        raise ValueError('Invalid Client ID')
    if not isinstance(client.get('client_secret'), str) or not client['client_secret'].strip():
        raise ValueError('Client Secret is required')
    team = client.get('expected_team_id', '')
    if not isinstance(team, str) or (team and not re.fullmatch(r'T[A-Z0-9]+', team)):
        raise ValueError('Invalid Workspace ID')
    login_url = client.get('workspace_login_url')
    if login_url is not None and (not isinstance(login_url, str) or (login_url and not re.fullmatch(
            r'https://[a-z0-9-]+(?:\.enterprise)?\.slack\.com/', login_url))):
        raise ValueError('Invalid Slack workspace login URL')
    remote = env['private_root'] + '/config.local.json'
    current = json.loads(ssh(env, 'cat ' + shlex.quote(remote)))
    current.update(client_id=client['client_id'], client_secret=client['client_secret'], expected_team_id=team)
    if login_url is not None:
        current['workspace_login_url'] = login_url
    # Preserve public URL and expiry. Updating credentials never extends exposure.
    ssh(env, 'umask 077 && cat > ' + shlex.quote(remote + '.next')
        + ' && mv ' + shlex.quote(remote + '.next') + ' ' + shlex.quote(remote), json.dumps(current).encode())
    print('Slack demo client configured. No credentials were printed. Expiry was preserved.')


if __name__ == '__main__':
    main()
