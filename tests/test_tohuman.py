from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import requests
from cryptography.fernet import Fernet, InvalidToken

from humanization.guard import sanitize, verify
from humanization.pipeline import queue, process, deliver, ENDPOINT
from humanization.vault import Vault
from resume.process import digest


class ToHumanTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.key = Fernet.generate_key()
        self.vault = Vault(Path(self.directory.name) / 'vault.enc', self.key)
        self.profile = {'approved': True, 'name': 'PRIVATE_TEST_PERSON',
                        'education': 'a bachelor degree in computer science',
                        'education_statement': 'I am studying computer science at Example University.',
                        'skills': ['Python', 'Linux', 'Splunk'],
                        'evidence': [{'id': 'lab', 'detail': 'I built a Splunk lab to collect authentication logs.', 'keywords': ['Splunk', 'logs']},
                                     {'id': 'code', 'detail': 'I wrote a Python script to inspect sample logs.', 'keywords': ['Python', 'logs']}]}
        self.profile['approval_sha256'] = digest(self.profile)
        self.job = {'source': 'greenhouse', 'id': 'new-1', 'title': 'Summer 2027 Security Operations Intern',
                    'company': 'Example Company', 'description': 'University bachelor students. Python Linux Splunk logs.',
                    'location': 'Remote', 'url': 'https://example.org/jobs/1'}
        self.state = {'schema_version': 1, 'boards': {}}
        self.config = {'monthly_word_cap': 2500, 'reserve_words': 500, 'word_count_margin': 20}
        self.now = datetime(2026, 11, 4, tzinfo=timezone.utc)
        self.env = patch.dict(os.environ, {'TOHUMAN_API_KEY': 'PRIVATE_API_KEY'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.add_job()
        self.session = Mock()
        self.session.post.side_effect = self.response

    def add_job(self, key='greenhouse:example:new-1'):
        queue(self.state, key, {**self.job, 'id': key.split(':')[-1]}, self.profile, self.vault)

    def rewrite(self, content):
        self.assertIn('An internship would let me develop', content)
        return content.replace('An internship would let me develop', 'This internship would help me develop')

    def response(self, url, **kwargs):
        result = Mock(status_code=200)
        result.json.return_value = {'status': 'completed', 'output_content': self.rewrite(kwargs['json']['content'])}
        return result

    def run_process(self, checkpoint=None, now=None):
        process(self.state, self.vault, self.config, self.session, checkpoint or (lambda s: None), now or self.now)

    def record(self):
        return self.state['tohuman']['jobs']['greenhouse:example:new-1']

    def test_documented_request_sends_only_anonymous_letter_and_subtle_intensity(self):
        self.run_process()
        args, kwargs = self.session.post.call_args
        self.assertEqual(args, (ENDPOINT,))
        self.assertEqual(set(kwargs['json']), {'content', 'intensity'})
        self.assertEqual(kwargs['json']['intensity'], 'subtle')
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer PRIVATE_API_KEY')
        self.assertNotIn('PRIVATE_TEST_PERSON', kwargs['json']['content'])
        self.assertNotIn(json.dumps(self.profile), str(kwargs['json']))
        self.assertFalse(kwargs['allow_redirects'])
        self.assertEqual(self.record()['status'], 'verified')

    def test_below_80_does_not_generate_or_queue(self):
        with patch('matching.rank', return_value={'score': 79}), patch('cover_letters.local_letter') as generator:
            self.add_job('greenhouse:example:below')
        generator.assert_not_called()
        self.assertNotIn('greenhouse:example:below', self.state['tohuman']['jobs'])

    def test_exact_80_is_eligible(self):
        with patch('matching.rank', return_value={'score': 80}):
            self.add_job('greenhouse:example:at-80')
        self.assertIn('greenhouse:example:at-80', self.state['tohuman']['jobs'])

    def test_original_is_encrypted_and_survives_reopen(self):
        payload = self.vault.path.read_bytes()
        self.assertNotIn(b'PRIVATE_TEST_PERSON', payload)
        reopened = Vault(self.vault.path, self.key)
        self.assertEqual(reopened.records, self.vault.records)
        with self.assertRaises(InvalidToken):
            Vault(self.vault.path, Fernet.generate_key())

    def test_reservation_precedes_request(self):
        snapshots = []
        def checkpoint(state):
            snapshots.append(json.loads(json.dumps(state)))
        self.run_process(checkpoint)
        self.assertEqual(snapshots[0]['tohuman']['jobs']['greenhouse:example:new-1']['status'], 'attempted')
        self.assertGreater(snapshots[0]['tohuman']['months']['2026-11']['reserved_words'], 0)

    def test_failed_durable_checkpoint_prohibits_request(self):
        with self.assertRaises(RuntimeError):
            self.run_process(lambda s: (_ for _ in ()).throw(RuntimeError('Cannot push ledger')))
        self.session.post.assert_not_called()

    def test_duplicate_queue_and_repeated_processing_never_resubmit(self):
        original = self.vault.records['greenhouse:example:new-1']['original']
        self.add_job()
        self.run_process()
        used = self.state['tohuman']['months']['2026-11']['reserved_words']
        self.run_process()
        self.session.post.assert_called_once()
        self.assertEqual(self.state['tohuman']['months']['2026-11']['reserved_words'], used)
        self.assertEqual(self.vault.records['greenhouse:example:new-1']['original'], original)

    def test_timeout_is_terminal_and_counts_conservatively(self):
        self.session.post.side_effect = requests.Timeout('PRIVATE_API_KEY')
        self.run_process()
        self.run_process()
        self.session.post.assert_called_once()
        self.assertEqual(self.record()['status'], 'uncertain')
        self.assertNotIn('PRIVATE_API_KEY', json.dumps(self.state))

    def test_restart_after_attempt_never_resubmits(self):
        self.record()['status'] = 'attempted'
        self.run_process()
        self.session.post.assert_not_called()
        self.assertEqual(self.record()['status'], 'uncertain')

    def test_missing_verified_output_after_crash_never_resubmits(self):
        self.record()['status'] = 'verified'
        self.run_process()
        self.session.post.assert_not_called()
        self.assertEqual(self.record()['status'], 'uncertain')

    def test_private_history_without_public_journal_is_not_resubmitted(self):
        self.state['tohuman']['jobs'].clear()
        self.add_job()
        self.run_process()
        self.session.post.assert_not_called()
        self.assertEqual(self.record()['status'], 'uncertain')

    def test_safety_reserve_and_external_usage(self):
        self.config['external_words_used'] = {'2026-11': 1900}
        self.run_process()
        self.session.post.assert_not_called()
        self.assertEqual(self.record()['status'], 'skipped')

    def test_invalid_budget_fails_before_request(self):
        self.config['word_count_margin'] = -1
        with self.assertRaises(ValueError):
            self.run_process()
        self.session.post.assert_not_called()

    def test_per_run_requests_stay_below_free_burst(self):
        for index in range(2, 7):
            self.add_job('greenhouse:example:new-' + str(index))
        self.run_process()
        self.assertEqual(self.session.post.call_count, 3)
        self.assertTrue(any(r['status'] == 'queued' for r in self.state['tohuman']['jobs'].values()))

    def test_monthly_reservations_never_spend_the_safety_reserve(self):
        self.config.update(monthly_word_cap=600, reserve_words=100)
        self.add_job('greenhouse:example:new-2')
        self.run_process()
        self.assertLessEqual(self.state['tohuman']['months']['2026-11']['reserved_words'], 500)
        self.session.post.assert_called_once()

    def test_monthly_rollover_does_not_reset_job_deduplication(self):
        self.run_process()
        self.add_job('greenhouse:example:new-2')
        self.run_process(now=datetime(2026, 12, 1, tzinfo=timezone.utc))
        self.assertEqual(self.session.post.call_count, 2)
        self.assertEqual(set(self.state['tohuman']['months']), {'2026-11', '2026-12'})

    def test_exhausted_account_blocks_other_requests_that_month(self):
        self.add_job('greenhouse:example:new-2')
        self.session.post.side_effect = None
        self.session.post.return_value.status_code = 402
        self.run_process()
        self.session.post.assert_called_once()
        self.assertTrue(self.state['tohuman']['months']['2026-11']['exhausted'])

    def test_rate_limit_is_not_retried(self):
        self.add_job('greenhouse:example:new-2')
        self.session.post.side_effect = None
        self.session.post.return_value.status_code = 429
        self.session.post.return_value.headers = {'X-RateLimit-Reset': str(self.now.timestamp() + 60)}
        self.run_process()
        self.session.post.assert_called_once()

    def test_server_error_is_not_retried(self):
        self.session.post.side_effect = None
        self.session.post.return_value.status_code = 500
        self.run_process()
        self.run_process()
        self.session.post.assert_called_once()

    def test_unchanged_response_is_not_humanized(self):
        self.session.post.side_effect = lambda url, **kw: Mock(status_code=200, json=lambda: {'status': 'completed', 'unchanged': True, 'output_content': kw['json']['content']})
        self.run_process()
        self.assertEqual(self.record()['status'], 'rejected')

    def test_factual_changes_and_added_certification_are_rejected(self):
        private = self.vault.records['greenhouse:example:new-1']
        good = self.rewrite(private['submitted'])
        args = (private['facts'], self.job['company'], self.job['title'])
        self.assertTrue(verify(private['submitted'], good, *args))
        self.assertFalse(verify(private['submitted'], good.replace('wrote a Python', 'wrote an AWS'), *args))
        self.assertFalse(verify(private['submitted'], good + ' I am Security+ certified.', *args))
        self.assertFalse(verify(private['submitted'], good + ' I cannot write Python.', *args))
        self.assertFalse(verify(private['submitted'], good + ' My doctorate is complete.', *args))
        self.assertFalse(verify(private['submitted'], good + '\n\nSincerely,\nInvented Name', *args))
        self.assertFalse(verify(private['submitted'], good + '\n\nRegards,\nInvented Name', *args))
        self.assertFalse(verify(private['submitted'], good.replace('2027', '2028'), *args))

    def test_sanitization_removes_contacts_and_signature_without_changing_original(self):
        original = 'Dear Hiring Team,\n\nText. user@example.org 555-123-4567 https://example.org\n\nSincerely,\nPrivate Name'
        result = sanitize(original, 'Private Name')
        for value in ('user@example.org', '555-123-4567', 'https://example.org', 'Private Name'):
            self.assertNotIn(value, result)
        self.assertIn('Private Name', original)

    @patch('tracker.notify_cover_letter', return_value=True)
    def test_successful_humanized_txt_delivery_once(self, notify):
        self.run_process()
        deliver(self.state, self.vault, object())
        deliver(self.state, self.vault, object())
        notify.assert_called_once()
        self.assertIn('ToHuman subtle', notify.call_args.args[3])
        self.assertTrue(notify.call_args.args[2].endswith('PRIVATE_TEST_PERSON'))

    @patch('tracker.notify_cover_letter', return_value=True)
    def test_failure_delivers_clearly_labeled_original(self, notify):
        self.session.post.side_effect = requests.Timeout()
        self.run_process()
        deliver(self.state, self.vault, object())
        self.assertIn('ORIGINAL LOCAL DRAFT; ToHuman not completed', notify.call_args.args[3])
        self.assertEqual(self.record()['delivered'], 'original')

    @patch('tracker.notify_cover_letter', side_effect=[requests.Timeout(), True])
    def test_discord_retry_reuses_cached_rewrite_without_api_spend(self, notify):
        self.run_process()
        deliver(self.state, self.vault, object())
        self.run_process()
        deliver(self.state, self.vault, object())
        self.session.post.assert_called_once()
        self.assertEqual(notify.call_count, 2)

    def test_public_ledger_has_no_letter_or_candidate_contents(self):
        self.run_process()
        public = json.dumps(self.state)
        self.assertNotIn('PRIVATE_TEST_PERSON', public)
        self.assertNotIn('Example University', public)
        self.assertNotIn('PRIVATE_API_KEY', public)

    def test_workflow_order_and_credit_free_validation(self):
        import yaml
        workflow = yaml.load(Path('.github/workflows/monitor.yml').read_text(), Loader=yaml.BaseLoader)
        steps = workflow['jobs']['check']['steps']
        originals = next(i for i,s in enumerate(steps) if s.get('id') == 'originals')
        process_step = next(i for i,s in enumerate(steps) if s.get('run') == 'python -m humanization.worker process')
        processed = next(i for i,s in enumerate(steps) if s.get('id') == 'processed')
        delivery = next(i for i,s in enumerate(steps) if s.get('run') == 'python -m humanization.worker deliver')
        self.assertTrue(originals < process_step < processed < delivery)
        self.assertIn('validate_only != true', steps[process_step]['if'])
        for step in steps:
            if 'upload-artifact' in step.get('uses', ''):
                self.assertEqual(step['with']['path'], 'private/automation/vault.enc')
