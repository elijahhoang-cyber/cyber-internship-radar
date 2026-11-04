import contextlib
import io
import json
import os
import unittest
from unittest.mock import Mock, patch
from providers.federal import fetch, normalize, QUERIES
from providers.check_federal import main
from matching import rank


def announcement(identifier='1', **overrides):
    descriptor = {'PositionTitle': 'Student Trainee (Information Technology)',
                  'PositionURI': 'https://www.usajobs.gov/job/' + identifier,
                  'OrganizationName': 'Test Federal Agency',
                  'QualificationSummary': 'Current undergraduate student. Python and Linux.',
                  'PositionOfferingType': [{'Name': 'Internships'}],
                  'UserArea': {'Details': {'JobSummary': 'Cybersecurity and incident response internship.', 'HiringPath': ['student']}}}
    descriptor.update(overrides)
    return {'MatchedObjectId': identifier, 'MatchedObjectDescriptor': descriptor}


class FederalTests(unittest.TestCase):
    def test_student_trainee_reaches_matching_with_full_qualifications(self):
        job = normalize(announcement(), 'Federal')
        self.assertTrue(job['intern_type'])
        self.assertIn('Python', job['description'])
        self.assertEqual(job['hiring_paths'], ['student'])
        self.assertGreaterEqual(rank(job)['score'], 60)

    def test_student_hiring_path_alone_does_not_make_job_an_internship(self):
        job = normalize(announcement(PositionTitle='IT Specialist', PositionOfferingType=[{'Name': 'Permanent'}],
                                     UserArea={'Details': {'JobSummary': 'Cybersecurity operations.', 'HiringPath': ['student']}}), 'Federal')
        self.assertFalse(job['intern_type'])
        self.assertEqual(rank(job)['score'], 0)

    @patch('tracker.get_json')
    def test_union_deduplicates_and_requests_full_fields(self, get):
        get.return_value = {'SearchResult': {'SearchResultCountAll': 1, 'SearchResultItems': [announcement()]}}
        self.assertEqual(len(fetch(object(), 'Federal')), 1)
        self.assertEqual(get.call_count, len(QUERIES))
        self.assertTrue(all(c.args[2]['Fields'] == 'Full' for c in get.call_args_list))
        self.assertTrue(any('2299' in c.args[2].get('JobCategoryCode', '') for c in get.call_args_list))

    @patch('providers.federal.QUERIES', ({'JobCategoryCode': '2299'},))
    @patch('tracker.get_json')
    def test_pagination(self, get):
        get.side_effect = [{'SearchResult': {'SearchResultCountAll': 501, 'SearchResultItems': [announcement('1')]}},
                           {'SearchResult': {'SearchResultCountAll': 501, 'SearchResultItems': [announcement('2')]}}]
        self.assertEqual(len(fetch(object(), 'Federal')), 2)
        self.assertEqual(get.call_args.args[2]['Page'], 2)

    @patch('tracker.get_json', return_value={'SearchResult': {'SearchResultCountAll': 0, 'SearchResultItems': []}})
    def test_no_current_announcements_is_valid(self, get):
        self.assertEqual(fetch(object(), 'Federal'), [])

    @patch('providers.check_federal.usajobs', side_effect=RuntimeError('SECRET_VALUE user@example.org'))
    def test_diagnostic_redacts_authenticated_error(self, fetch):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 1)
        self.assertNotIn('SECRET_VALUE', output.getvalue())
        self.assertNotIn('user@example.org', output.getvalue())

    @patch('providers.check_federal.usajobs', return_value=[])
    def test_empty_live_search_does_not_claim_detection(self, fetch):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 0)
        self.assertIn('Live posting pipeline test skipped', output.getvalue())

    @patch('cloud_tracker.time.sleep')
    @patch('cloud_tracker.notify_cover_letter', return_value=True)
    @patch('cloud_tracker.notify_discord', return_value=True)
    def test_live_posting_scanner_handoff_uses_only_synthetic_candidate(self, alert, letter, sleep):
        job = normalize(announcement(), 'Federal')
        with patch('providers.check_federal.usajobs', return_value=[job]), patch.dict(os.environ, {
                'DISCORD_WEBHOOK_URL': 'FAKE_WEBHOOK', 'RESUME_PROFILE_JSON': 'REAL_CANDIDATE_MARKER', 'ENABLE_EXTERNAL_AI': 'true'}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(), 0)
        alert.assert_called_once()
        letter.assert_called_once()
        self.assertIn('SYNTHETIC TEST APPLICANT', letter.call_args.args[2])
        self.assertNotIn('REAL_CANDIDATE_MARKER', str(letter.call_args))
        self.assertNotIn('FAKE_WEBHOOK', output.getvalue())
        self.assertIn('repeat scan deduplicated', output.getvalue())
