import json
import os
import unittest
from unittest.mock import Mock, patch

from cover_letters import draft_letter, local_letter, resume_profile_from_env, selected_evidence


class CoverLetterTests(unittest.TestCase):
    def setUp(self):
        self.job = {'company': 'Example Corp', 'title': 'SOC Analyst Intern',
                    'description': 'Join security operations to review SIEM alerts and logs',
                    'location': 'Houston, TX'}
        self.profile = {
            'name': 'A Student',
            'education': 'a B.S. in Computer Science',
            'evidence': [
                {'detail': 'I completed a web design project', 'keywords': ['frontend']},
                {'detail': 'I built a log monitoring lab', 'keywords': ['SOC', 'SIEM', 'logs']},
            ],
        }
        from resume.process import digest
        self.profile['approved'] = True
        self.profile['approval_sha256'] = digest(self.profile)

    def test_profile_is_absent_without_secret(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(resume_profile_from_env())

    def test_private_profile_loaded_from_secret(self):
        with patch.dict(os.environ, {'RESUME_PROFILE_JSON': json.dumps(self.profile)}):
            self.assertEqual(resume_profile_from_env()['education'], self.profile['education'])

    def test_selects_most_relevant_true_resume_fact(self):
        self.assertEqual(selected_evidence(self.job, self.profile)[0]['detail'], 'I built a log monitoring lab')

    def test_local_fallback_has_real_role_and_resume_facts(self):
        result = local_letter(self.job, self.profile)
        self.assertIn('SOC Analyst Intern', result)
        self.assertIn('Example Corp', result)
        self.assertIn('I built a log monitoring lab', result)
        self.assertNotIn('Hired', result)

    def test_default_is_zero_cost_without_ai(self):
        with patch.dict(os.environ, {}, clear=True):
            letter, mode = draft_letter(self.job, self.profile, Mock())
        self.assertIn('Example Corp', letter)
        self.assertIn('local', mode)

    def test_opted_in_ai_fails_over_to_local(self):
        fake = Mock()
        fake.post.side_effect = RuntimeError('Rate limited')
        with patch.dict(os.environ, {'ENABLE_EXTERNAL_AI': 'true', 'GEMINI_API_KEY': 'private'}, clear=True):
            letter, mode = draft_letter(self.job, self.profile, fake)
        self.assertIn('Example Corp', letter)
        self.assertIn('local', mode)

    def test_ai_does_not_put_key_in_request_url(self):
        fake = Mock()
        fake.post.return_value.json.return_value = {'candidates': [{'content': {'parts': [
            {'text': 'Dear Hiring Team,\n\nExample Corp. ' + 'One clear sentence. ' * 90 + '\nSincerely,\nA Student'}]}}]}
        fake.post.return_value.raise_for_status.return_value = None
        with patch.dict(os.environ, {'ENABLE_EXTERNAL_AI': 'true', 'GEMINI_API_KEY': 'private'}, clear=True):
            letter, mode = draft_letter(self.job, self.profile, fake)
        self.assertIn('AI', mode)
        args, kwargs = fake.post.call_args
        self.assertNotIn('private', args[0])
        self.assertEqual(kwargs['headers']['x-goog-api-key'], 'private')


if __name__ == '__main__':
    unittest.main()
