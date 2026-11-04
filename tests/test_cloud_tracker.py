from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from cloud_tracker import load_state, save_state, scan


class CloudTrackerTests(unittest.TestCase):
    def setUp(self):
        self.config = {'boards': [{'source': 'greenhouse', 'board': 'example', 'company': 'Example'}], 'seconds_between_boards': 0}
        self.job = {'company': 'Example', 'title': 'Cybersecurity Intern', 'description': 'SOC',
                    'id': '123', 'url': 'https://example.org/job/123', 'location': 'Remote', 'source': 'greenhouse'}
        self.state = {'schema_version': 1, 'boards': {}}
        self.now = datetime(2026, 10, 26, tzinfo=timezone.utc)
        self.fetcher = Mock(return_value=[self.job])
        self.fetch_patch = patch.dict('cloud_tracker.FETCHERS', {'greenhouse': self.fetcher})
        self.sleep_patch = patch('cloud_tracker.time.sleep')
        self.fetch_patch.start()
        self.sleep_patch.start()
        self.addCleanup(self.fetch_patch.stop)
        self.addCleanup(self.sleep_patch.stop)

    @patch('cloud_tracker.notify_discord')
    def test_first_board_scan_creates_baseline(self, alert):
        result = scan(self.config, self.state, object(), True, self.now)
        self.assertTrue(result['boards']['greenhouse:example']['seen']['123']['alerted'])
        alert.assert_not_called()

    @patch('cloud_tracker.notify_discord', return_value=True)
    def test_new_job_is_alerted_once(self, alert):
        scan(self.config, self.state, object(), True, self.now)
        self.fetcher.return_value = [self.job, {**self.job, 'id': '124', 'url': 'https://example.org/job/124'}]
        scan(self.config, self.state, object(), True, self.now + timedelta(minutes=5))
        self.assertTrue(self.state['boards']['greenhouse:example']['seen']['124']['alerted'])
        scan(self.config, self.state, object(), True, self.now + timedelta(minutes=10))
        self.assertEqual(alert.call_count, 1)

    @patch('cloud_tracker.notify_discord', return_value=True)
    def test_failed_notification_is_retried(self, alert):
        scan(self.config, self.state, object(), False, self.now)
        self.fetcher.return_value = [self.job, {**self.job, 'id': '124', 'url': 'https://example.org/job/124'}]
        scan(self.config, self.state, object(), False, self.now + timedelta(minutes=5))
        self.assertFalse(self.state['boards']['greenhouse:example']['seen']['124']['alerted'])
        scan(self.config, self.state, object(), True, self.now + timedelta(minutes=10))
        self.assertEqual(alert.call_count, 1)

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'state.json'
            save_state(p, self.state)
            self.assertEqual(load_state(p), self.state)

    def test_board_failure_does_not_initialize_it(self):
        self.fetcher.side_effect = RuntimeError('down')
        with self.assertRaises(RuntimeError):
            scan(self.config, self.state, object(), True, self.now)
        self.assertEqual(self.state['boards'], {})

    def test_heartbeat_after_one_week(self):
        self.fetcher.return_value = []
        scan(self.config, self.state, object(), False, self.now)
        initial = self.state['last_heartbeat_utc']
        scan(self.config, self.state, object(), False, self.now + timedelta(days=1))
        self.assertEqual(initial, self.state['last_heartbeat_utc'])
        scan(self.config, self.state, object(), False, self.now + timedelta(days=8))
        self.assertNotEqual(initial, self.state['last_heartbeat_utc'])

    @patch('cloud_tracker.notify_discord', return_value=True)
    def test_same_url_new_identifier_does_not_repeat(self, alert):
        scan(self.config, self.state, object(), True, self.now)
        self.fetcher.return_value = [{**self.job, 'id': 'new-id'}]
        scan(self.config, self.state, object(), True, self.now)
        alert.assert_not_called()

    @patch('cloud_tracker.notify_discord', return_value=True)
    def test_pending_posting_retried_after_disappearing(self, alert):
        scan(self.config, self.state, object(), False, self.now)
        self.fetcher.return_value = [{**self.job, 'id': '2', 'url': 'https://example.org/2'}]
        scan(self.config, self.state, object(), False, self.now)
        self.fetcher.return_value = []
        scan(self.config, self.state, object(), True, self.now)
        alert.assert_called_once()

    def test_corrupt_state_refuses_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.json'
            path.write_text('{"schema_version": 1, "boards": {"x": {}}}')
            with self.assertRaises(ValueError):
                load_state(path)

if __name__ == '__main__':
    unittest.main()

class EndToEndLetterTests(unittest.TestCase):
    def setUp(self):
        self.config = {'boards': [{'source': 'greenhouse', 'board': 'example', 'company': 'Example'}], 'seconds_between_boards': 0, 'letter_min_score': 60}
        self.job = {'company': 'Example', 'title': 'Security Operations Intern', 'description': 'SIEM',
                    'id': '1', 'url': 'https://example.org/1', 'location': 'Remote', 'source': 'greenhouse'}
        self.state = {'schema_version': 1, 'boards': {}}
        self.fetcher = Mock(return_value=[self.job])
        self.fetch_patch = patch.dict('cloud_tracker.FETCHERS', {'greenhouse': self.fetcher})
        self.profile_patch = patch('cloud_tracker.resume_profile_from_env', return_value={'education': 'B.S.', 'evidence': [{'detail':'I built a lab'}]})
        self.sleep_patch = patch('cloud_tracker.time.sleep')
        for p in (self.fetch_patch, self.profile_patch, self.sleep_patch):
            p.start()
            self.addCleanup(p.stop)

    @patch('cloud_tracker.draft_letter', return_value=('A draft', 'local'))
    @patch('cloud_tracker.notify_cover_letter', return_value=True)
    @patch('cloud_tracker.notify_discord', return_value=True)
    def test_first_alert_then_letter_without_spam(self, alert, letter_alert, draft):
        scan(self.config, self.state, object(), True)
        self.fetcher.return_value = [self.job, {**self.job, 'id': '2', 'url': 'https://example.org/2'}]
        scan(self.config, self.state, object(), True)
        self.assertEqual(alert.call_count, 1)
        self.assertEqual(letter_alert.call_count, 1)
        self.assertTrue(self.state['boards']['greenhouse:example']['seen']['2']['letter_sent'])
        scan(self.config, self.state, object(), True)
        self.assertEqual(alert.call_count, 1)
        self.assertEqual(letter_alert.call_count, 1)

    @patch('cloud_tracker.draft_letter', return_value=('A draft', 'local'))
    @patch('cloud_tracker.notify_cover_letter', side_effect=[RuntimeError('no discord'), True])
    @patch('cloud_tracker.notify_discord', return_value=True)
    def test_letter_failure_retries_without_duplicate_job_alert(self, alert, letter_alert, draft):
        scan(self.config, self.state, object(), True)
        self.fetcher.return_value = [self.job, {**self.job, 'id': '2', 'url': 'https://example.org/2'}]
        scan(self.config, self.state, object(), True)
        job_state = self.state['boards']['greenhouse:example']['seen']['2']
        self.assertTrue(job_state['alerted'])
        self.assertFalse(job_state['letter_sent'])
        scan(self.config, self.state, object(), True)
        self.assertTrue(job_state['letter_sent'])
        self.assertEqual(alert.call_count, 1)
        self.assertEqual(letter_alert.call_count, 2)
