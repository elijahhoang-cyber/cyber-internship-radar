"""SQLite persistence for the same scanner used in cloud runs."""
import json
import sqlite3


class SQLiteState:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS radar_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')

    def load(self):
        row = self.db.execute('SELECT payload FROM radar_state WHERE id=1').fetchone()
        return json.loads(row[0]) if row else {'schema_version': 1, 'boards': {}}

    def save(self, state):
        with self.db:
            self.db.execute('INSERT INTO radar_state VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (json.dumps(state),))

    def close(self):
        self.db.close()
