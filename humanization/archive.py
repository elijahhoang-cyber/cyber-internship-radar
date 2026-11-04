"""Restore encrypted Actions artifacts; never extract an archive to arbitrary paths."""
import io
import json
import os
from pathlib import Path
import sys
import zipfile
import requests
from .vault import Vault, PATH

PREFIX = 'radar-letter-vault-'


def artifacts(session, repository, token):
    response = session.get(f'https://api.github.com/repos/{repository}/actions/artifacts',
                           headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json'},
                           params={'per_page': 100}, timeout=(8, 30))
    response.raise_for_status()
    return [a for a in response.json()['artifacts'] if a['name'].startswith(PREFIX) and not a['expired']]


def restore(session, repository, token):
    items = artifacts(session, repository, token)
    if items:
        newest = max(items, key=lambda a: a['id'])
        response = session.get(f"https://api.github.com/repos/{repository}/actions/artifacts/{newest['id']}/zip",
                               headers={'Authorization': 'Bearer ' + token}, allow_redirects=False, timeout=(8, 30))
        if response.status_code != 302:
            raise ValueError('Unexpected artifact redirect')
        url = response.headers['Location']
        if not url.startswith('https://'):
            raise ValueError('Artifact download must use HTTPS')
        # No GitHub credential is forwarded to the signed download host.
        result = requests.get(url, timeout=(8, 60))
        result.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
            names = archive.namelist()
            if names != ['vault.enc'] or archive.getinfo('vault.enc').file_size > 20_000_000:
                raise ValueError('Invalid private archive envelope')
            payload = archive.read('vault.enc')
        PATH.parent.mkdir(parents=True, exist_ok=True)
        PATH.write_bytes(payload)
    elif Path('state/seen.json').exists():
        state = json.loads(Path('state/seen.json').read_text())
        if state.get('tohuman', {}).get('jobs'):
            raise ValueError('Prior private archive unavailable; refusing to recreate originals')
    Vault(PATH).save()  # Authenticate/decrypt before any private processing.


def cleanup(session, repository, token):
    items = sorted(artifacts(session, repository, token), key=lambda a: a['id'], reverse=True)
    for item in items[2:]:
        response = session.delete(f"https://api.github.com/repos/{repository}/actions/artifacts/{item['id']}",
                                  headers={'Authorization': 'Bearer ' + token}, timeout=(8, 30))
        response.raise_for_status()


def main():
    mode = sys.argv[1]
    try:
        with requests.Session() as session:
            if mode == 'restore':
                restore(session, os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN'])
            elif mode == 'cleanup':
                cleanup(session, os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN'])
            else:
                raise ValueError('Unknown archive operation')
        if mode == 'restore':
            with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                output.write('ready=true\n')
        print('Encrypted archive operation complete; private contents omitted.')
        return 0
    except Exception as exc:
        print('Encrypted archive unavailable:', type(exc).__name__, '(private input omitted)')
        return 1


if __name__ == '__main__':
    sys.exit(main())
