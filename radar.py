"""Unified local SQLite runner; GitHub uses cloud_tracker.py and public JSON state."""
import argparse
import json
import logging
import os
from pathlib import Path
import requests
from cloud_tracker import scan
from storage import SQLiteState
from tracker import USER_AGENT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='config/companies.verified.json')
    parser.add_argument('--db', default='jobs.sqlite3')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    config = json.loads(Path(args.config).read_text(encoding='utf-8'))
    store = SQLiteState(args.db)
    try:
        state = store.load()
        with requests.Session() as session:
            session.headers['User-Agent'] = USER_AGENT
            scan(config, state, session, bool(os.environ.get('DISCORD_WEBHOOK_URL')), checkpoint=store.save)
        store.save(state)
    finally:
        store.close()


if __name__ == '__main__':
    main()
