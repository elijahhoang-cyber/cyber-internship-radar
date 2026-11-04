"""Encrypted private letter archive. Only vault.enc is uploaded as an artifact."""
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet

PATH = Path('private/automation/vault.enc')


class Vault:
    def __init__(self, path=PATH, key=None):
        self.path = Path(path)
        self.cipher = Fernet(key or os.environ['TOHUMAN_VAULT_KEY'].encode())
        self.records = json.loads(self.cipher.decrypt(self.path.read_bytes())) if self.path.exists() else {}
        if not isinstance(self.records, dict):
            raise ValueError('Invalid private archive')

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_bytes(self.cipher.encrypt(json.dumps(self.records).encode()))
        temp.replace(self.path)
