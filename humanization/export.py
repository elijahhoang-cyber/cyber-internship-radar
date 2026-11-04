"""Decrypt a downloaded vault into ignored local files; no network access."""
import argparse
from pathlib import Path
from .vault import Vault


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vault', type=Path, required=True)
    parser.add_argument('--key-file', type=Path, default=Path('private/tohuman.vault.key'))
    parser.add_argument('--output', type=Path, default=Path('letters/automatic'))
    args = parser.parse_args()
    output = args.output.resolve()
    if not any(output.is_relative_to(Path(root).resolve()) for root in ('private', 'letters')):
        parser.error('Decrypted drafts must stay inside private/ or letters/')
    vault = Vault(args.vault, args.key_file.read_bytes().strip())
    output.mkdir(parents=True, exist_ok=True)
    import hashlib
    for key, record in vault.records.items():
        stem = hashlib.sha256(key.encode()).hexdigest()[:20]
        for field in ('original', 'humanized'):
            if record.get(field):
                (output / (stem + '.' + field + '.txt')).write_text(record[field], encoding='utf-8')
    print('Private archive exported locally; contents omitted.')


if __name__ == '__main__':
    main()
