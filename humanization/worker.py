"""Process/deliver a queued encrypted vault without logging private contents."""
import json
import os
from pathlib import Path
import subprocess
import sys
import requests
from cloud_tracker import load_state, save_state
from .pipeline import process, deliver
from .vault import Vault


def durable_checkpoint(state):
    save_state(Path('state/seen.json'), state)
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        return
    # Only public request flags/word counts/job history enter Git. Never add vault.
    identity = ['-c', 'user.name=github-actions[bot]', '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com']
    def git(*args, allow_unchanged=False):
        result = subprocess.run(['git', *identity, *args], capture_output=True)
        if result.returncode and not allow_unchanged:
            raise RuntimeError('Public usage reservation could not be persisted')
        return result.returncode
    git('add', 'state/seen.json')
    if git('diff', '--cached', '--quiet', allow_unchanged=True) == 0:
        return
    git('commit', '-m', 'Checkpoint public letter-processing ledger [skip ci]')
    branch = os.environ.get('GITHUB_REF_NAME', 'main')
    git('pull', '--rebase', 'origin', branch)
    git('push', 'origin', 'HEAD:' + branch)


def main():
    try:
        state = load_state(Path('state/seen.json'))
        vault = Vault()
        config = json.loads(Path('config/tohuman.json').read_text())
        with requests.Session() as session:
            if sys.argv[1] == 'process':
                process(state, vault, config, session, durable_checkpoint)
            elif sys.argv[1] == 'deliver':
                deliver(state, vault, session)
                durable_checkpoint(state)
            else:
                raise ValueError('Unknown worker stage')
        print('Private letter-processing stage completed; contents omitted.')
        return 0
    except Exception as exc:
        print('Private letter-processing stage failed:', type(exc).__name__, '(private input omitted)')
        return 1


if __name__ == '__main__':
    sys.exit(main())
