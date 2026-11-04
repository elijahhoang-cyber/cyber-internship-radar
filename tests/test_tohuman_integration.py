from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile
from cryptography.fernet import Fernet

from cloud_tracker import scan, load_state
from humanization import archive
from humanization.vault import Vault


class FutureDiscoveryTests(unittest.TestCase):
    def test_future_threshold_notifications_and_baseline_exclusion(self):
        config = {'boards': [{'source': 'greenhouse', 'board': 'test', 'company': 'Example'}],
                  'tohuman': {'enabled': True}, 'seconds_between_boards': 0, 'letter_min_score': 10}
        job = {'source': 'greenhouse', 'id': 'baseline', 'title': 'Security Engineer Intern',
               'company': 'Example', 'description': 'Python', 'url': 'https://example.org/baseline', 'location': 'Remote'}
        state = {'schema_version': 1, 'boards': {}}
        fetch = Mock(return_value=[job])
        with patch.dict(os.environ, {'TOHUMAN_ARCHIVE_READY': 'true'}), patch.dict('cloud_tracker.FETCHERS', {'greenhouse': fetch}), patch('cloud_tracker.time.sleep'), patch('cloud_tracker.resume_profile_from_env', return_value={'education': 'Test', 'evidence': [{'detail': 'Test'}]}), patch('cloud_tracker.rank', return_value={'score': 95, 'category': 'Excellent match'}), patch('humanization.pipeline.queue') as queue, patch('humanization.vault.Vault'), patch('cloud_tracker.draft_letter') as generator, patch('cloud_tracker.notify_discord', return_value=True) as alert:
            scan(config, state, object(), True)
            # An old delivered example must never be opted into the new service.
            state['boards']['greenhouse:test']['seen']['baseline']['letter_sent'] = False
            scan(config, state, object(), True)
            queue.assert_not_called()
            fetch.return_value = [{**job, 'id': 'low', 'url': 'https://example.org/low'}]
            with patch('cloud_tracker.rank', return_value={'score': 79, 'category': 'Good match'}):
                scan(config, state, object(), True)
            queue.assert_not_called()
            generator.assert_not_called()
            alert.assert_called_once()
            fetch.return_value = [{**job, 'id': 'strong', 'url': 'https://example.org/strong'}]
            with patch('cloud_tracker.rank', side_effect=lambda j,p: {'score': 79 if j['id'] == 'low' else 80, 'category': 'Match'}):
                scan(config, state, object(), True)
            queue.assert_called_once()
            self.assertEqual(queue.call_args.args[1], 'greenhouse:test:strong')

    def test_corrupt_usage_ledger_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'seen.json'
            path.write_text(json.dumps({'schema_version': 1, 'boards': {}, 'tohuman': {'version': 1, 'jobs': {}, 'months': {'2026-11': {'reserved_words': -1}}}}))
            with self.assertRaises(ValueError):
                load_state(path)


class EncryptedArchiveTests(unittest.TestCase):
    def test_restore_download_never_forwards_github_credential(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'vault.enc'
            key = Fernet.generate_key()
            payload = Fernet(key).encrypt(json.dumps({'job': {'original': 'PRIVATE_ORIGINAL'}}).encode())
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w') as zipped:
                zipped.writestr('vault.enc', payload)
            session = Mock()
            session.get.side_effect = [Mock(json=lambda: {'artifacts': [{'name': 'radar-letter-vault-test', 'id': 1, 'expired': False}]}),
                                       Mock(status_code=302, headers={'Location': 'https://download.example.org/signed'})]
            with patch.object(archive, 'PATH', target), patch.dict(os.environ, {'TOHUMAN_VAULT_KEY': key.decode()}), patch('humanization.archive.requests.get', return_value=Mock(content=buf.getvalue())) as download:
                archive.restore(session, 'owner/repo', 'PRIVATE_GITHUB_TOKEN')
            self.assertNotIn('headers', download.call_args.kwargs)
            self.assertEqual(Vault(target, key).records['job']['original'], 'PRIVATE_ORIGINAL')
            self.assertNotIn(b'PRIVATE_ORIGINAL', target.read_bytes())

    def test_archive_path_traversal_is_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zipped:
            zipped.writestr('../../leak.txt', 'private')
        session = Mock()
        session.get.side_effect = [Mock(json=lambda: {'artifacts': [{'name': 'radar-letter-vault-test', 'id': 1, 'expired': False}]}),
                                   Mock(status_code=302, headers={'Location': 'https://download.example.org/signed'})]
        with patch('humanization.archive.requests.get', return_value=Mock(content=buf.getvalue())), self.assertRaises(ValueError):
            archive.restore(session, 'owner/repo', 'TOKEN')
