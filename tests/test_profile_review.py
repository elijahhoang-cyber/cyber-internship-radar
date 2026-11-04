import json
import os
import unittest
from unittest.mock import patch
from cover_letters import local_letter, resume_profile_from_env, selected_evidence
from matching import rank
from resume.schema import validate_profile


class ProfileReviewTests(unittest.TestCase):
    def setUp(self):
        # Synthetic fixtures only. Never copy an actual resume into repository tests.
        self.profile = {'approved': False, 'name': 'Test Student',
                        'education': 'a B.S. in Computer Science (in progress)',
                        'education_statement': 'I am studying computer science and expect to graduate in 2029.',
                        'skills': ['Python', 'Linux', 'Splunk'], 'graduation_year': 2029,
                        'certifications': ['CompTIA Security+ (Scheduled)', 'Example CPTS (Pursuing)'],
                        'evidence': [
                            {'detail': 'I built a log-monitoring lab and wrote searches to examine authentication events.', 'keywords': ['Splunk', 'SIEM', 'logs', 'authentication'], 'project_id': 'lab'},
                            {'detail': 'I used lab telemetry to investigate a simulated incident and document what I observed.', 'keywords': ['incident response', 'triage', 'logs'], 'project_id': 'lab'},
                            {'detail': 'I developed a Python port scanner using sockets in a personal project.', 'keywords': ['Python', 'TCP', 'network', 'sockets'], 'project_id': 'scanner'}]}

    def test_draft_validation_never_implies_approval(self):
        validate_profile(self.profile)
        self.assertFalse(self.profile['approved'])
        self.assertNotIn('approval_sha256', self.profile)
        with self.assertRaises(ValueError):
            validate_profile(self.profile, require_approval=True)
        with patch.dict(os.environ, {'RESUME_PROFILE_JSON': json.dumps(self.profile)}), self.assertRaises(ValueError):
            resume_profile_from_env()

    def test_contact_data_rejected_without_echoing_value(self):
        self.profile['email'] = 'private-marker@example.invalid'
        with self.assertRaises(ValueError) as caught:
            validate_profile(self.profile)
        self.assertNotIn('private-marker', str(caught.exception))

    def test_bad_evidence_keywords_are_rejected(self):
        self.profile['evidence'][0]['keywords'] = 'a string is not a keyword list'
        with self.assertRaises(ValueError):
            validate_profile(self.profile)

    def test_scheduled_security_plus_is_not_matched_as_earned(self):
        result = rank({'title': 'Security Operations Intern', 'description': 'Security+ certification required'}, self.profile)
        self.assertIn('security+', result['missing'])
        self.assertNotIn('security+', result['matched'])

    def test_structured_pending_certification_cannot_be_marked_earned(self):
        self.profile['certification_details'] = [{'name': 'Example certification', 'status': 'scheduled', 'earned': True}]
        with self.assertRaises(ValueError):
            validate_profile(self.profile)

    def test_evidence_matching_uses_word_boundaries(self):
        p = {**self.profile, 'evidence': [{'detail': 'I built a lab.', 'keywords': ['SOC']},
                                       {'detail': 'I wrote Python code.', 'keywords': ['Python']}]}
        result = selected_evidence({'title': 'Associate Python Intern', 'description': ''}, p)
        self.assertEqual(result[0]['detail'], 'I wrote Python code.')

    def test_local_letters_grounded_and_within_word_budget(self):
        jobs = [
            {'company': 'Example Detection', 'title': 'SOC Analyst Intern', 'description': 'Monitor Splunk SIEM logs and triage incident response alerts. Security+ preferred.'},
            {'company': 'Example Networks', 'title': 'Network Security Intern', 'description': 'Use Python and TCP sockets to automate network checks.'}]
        letters = [local_letter(j, self.profile) for j in jobs]
        for job, letter in zip(jobs, letters):
            self.assertTrue(250 <= len(letter.split()) <= 350)
            self.assertIn(job['company'], letter)
            self.assertIn(job['title'], letter)
            self.assertIn('I am studying computer science', letter)
            self.assertNotIn('certified', letter.lower())
            self.assertNotIn('AWS', letter)
            self.assertNotIn('another project', letter)
        self.assertIn('exam is scheduled; I have not yet earned', letters[0])
        self.assertIn('I developed a Python port scanner', letters[1])
        self.assertNotIn('I built a log-monitoring lab', letters[1])

    def test_missing_evidence_cannot_create_accomplishments(self):
        self.profile['evidence'] = []
        with self.assertRaises(ValueError):
            local_letter({'company': 'Example', 'title': 'Security Intern'}, self.profile)
