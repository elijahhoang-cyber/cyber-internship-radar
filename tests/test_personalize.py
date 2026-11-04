import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from matching import rank
from personalize import prepare_letters, main
from resume.process import digest
from tracker import score_job


class PersonalizationTests(unittest.TestCase):
    def setUp(self):
        self.profile = {'approved': True, 'name': 'PRIVATE_TEST_CANDIDATE',
                        'education': 'a B.S. in Computer Science (in progress)',
                        'skills': ['Python', 'TCP/IP troubleshooting'],
                        'evidence': [{'id': 'scanner', 'detail': 'I wrote a Python TCP port scanner using sockets.', 'keywords': ['Python', 'TCP']}]}
        self.profile['approval_sha256'] = digest(self.profile)
        self.job = {'id': '123', 'source': 'greenhouse', 'title': 'Information Security Engineer Intern',
                    'company': 'example company', 'location': 'Remote',
                    'url': 'https://example.org/123', 'description': 'Coding in languages such as Python, JavaScript, or similar. Networking fundamentals.'}
        self.state = {'schema_version': 1, 'boards': {'greenhouse:example': {'seen': {'123': {
            'job': self.job, 'first_seen': '2026-11-04T00:00:00+00:00', 'score': 60, 'alerted': True, 'letter_sent': True}}}}}
        self.selection = [{'board': 'greenhouse:example', 'id': '123', 'display_company': 'Example Company'}]

    def test_alternative_language_and_networking_foundations(self):
        result = rank(self.job, self.profile)
        self.assertIn('python', result['matched'])
        self.assertIn('networking', result['matched'])
        self.assertNotIn('javascript', result['missing'])
        self.assertNotIn('javascript', result['matched'])

    def test_clearance_stays_unknown(self):
        self.job['description'] += ' Eligibility and willingness to obtain a US security clearance.'
        self.assertTrue(any('clearance' in note for note in rank(self.job, self.profile)['unknown']))

    def test_physical_security_and_marketing_are_not_cyber_matches(self):
        physical = {**self.job, 'title': 'Security Analyst Intern', 'description': 'The Security Team leads physical security, program security and enterprise risk management.'}
        marketing = {**self.job, 'title': 'Marketing Intern', 'description': 'Cybersecurity products and cybersecurity communications.'}
        self.assertEqual(score_job(physical), 0)
        self.assertEqual(score_job(marketing), 0)

    def test_phd_role_is_not_a_strong_undergraduate_match(self):
        result = rank({**self.job, 'title': 'PhD Intern, Security Engineer'}, self.profile)
        self.assertLess(result['score'], 60)
        self.assertTrue(any('PhD' in gap for gap in result['missing']))

    def test_prepared_letter_contains_only_approved_candidate_evidence(self):
        result = prepare_letters(self.state, self.selection, self.profile)[0]
        self.assertTrue(250 <= result['word_count'] <= 350)
        self.assertIn(self.profile['evidence'][0]['detail'], result['letter'])
        self.assertEqual(result['job']['company'], 'Example Company')
        self.assertEqual(self.job['company'], 'example company')

    def test_unapproved_profile_and_duplicate_selection_rejected(self):
        with self.assertRaises(ValueError):
            prepare_letters(self.state, self.selection * 2, self.profile)
        self.profile['approved'] = False
        with self.assertRaises(ValueError):
            prepare_letters(self.state, self.selection, self.profile)

    def test_company_override_cannot_replace_the_employer(self):
        self.selection[0]['display_company'] = 'Different employer'
        with self.assertRaises(ValueError):
            prepare_letters(self.state, self.selection, self.profile)

    def run_cloud(self, delivery):
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / 'state.json'
            state_path.write_text(json.dumps(self.state))
            env = {'RESUME_PROFILE_JSON': json.dumps(self.profile), 'JOB_SELECTION_JSON': json.dumps(self.selection),
                   'DISCORD_WEBHOOK_URL': 'PRIVATE_WEBHOOK', 'ENABLE_EXTERNAL_AI': 'false'}
            with patch.dict(os.environ, env), patch('sys.argv', ['personalize.py', '--state', str(state_path), '--deliver', '--no-save']), patch('tracker.notify_cover_letter', side_effect=delivery) as sender, patch('pathlib.Path.write_text', side_effect=AssertionError('No private files in cloud run')), contextlib.redirect_stdout(io.StringIO()) as output:
                status = main()
            return status, output.getvalue(), sender

    def test_cloud_delivers_attachment_without_persisting_or_logging_candidate(self):
        status, output, sender = self.run_cloud(lambda *args: True)
        self.assertEqual(status, 0)
        sender.assert_called_once()
        self.assertNotIn('PRIVATE_TEST_CANDIDATE', output)
        self.assertNotIn('PRIVATE_WEBHOOK', output)
        self.assertIn('DELIVERED greenhouse:example 123', output)

    def test_delivery_exception_never_exposes_webhook_or_candidate(self):
        def failure(*args):
            raise RuntimeError('PRIVATE_WEBHOOK PRIVATE_TEST_CANDIDATE')
        status, output, sender = self.run_cloud(failure)
        self.assertEqual(status, 1)
        self.assertNotIn('PRIVATE_WEBHOOK', output)
        self.assertNotIn('PRIVATE_TEST_CANDIDATE', output)

    def test_workflow_receives_no_external_ai_key_and_publishes_no_artifacts(self):
        import yaml
        workflow = yaml.load(Path('.github/workflows/personalize.yml').read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(workflow['permissions']['contents'], 'read')
        step = workflow['jobs']['letters']['steps'][-1]
        self.assertEqual(step['env']['ENABLE_EXTERNAL_AI'], 'false')
        self.assertNotIn('GEMINI_API_KEY', step['env'])
        self.assertIn('--no-save', step['run'])
        self.assertFalse(any('upload-artifact' in step.get('uses', '') for step in workflow['jobs']['letters']['steps']))
