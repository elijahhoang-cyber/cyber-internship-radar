import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from matching import rank
from providers import smartrecruiters, workday, usajobs
from resume.process import extract_profile, digest, validate_approval
from storage import SQLiteState
from tracker import get_json, notify_cover_letter


class PlatformTests(unittest.TestCase):
    def test_private_paths_are_git_ignored(self):
        import subprocess
        paths = ['private/resume.pdf', 'private/nested/profile.json', 'letters/draft.txt',
                 'cover_letter_student.txt', 'cover_letter_student.md', 'cover-letter-student.html']
        # GitHub Actions also checks out this repository, so git is available in CI.
        result = subprocess.run(['git', 'check-ignore', '--', *paths], text=True, capture_output=True)
        self.assertEqual(set(result.stdout.splitlines()), set(paths))

    def test_real_pdf_text_extraction(self):
        from pypdf import PdfWriter, PdfReader
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.pdf'
            writer = PdfWriter()
            page = writer.add_blank_page(612, 792)
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
            stream = DecodedStreamObject()
            stream.set_data(b'BT /F1 12 Tf 72 720 Td (Education) Tj 0 -20 Td (B.S. Computer Science) Tj 0 -20 Td (Projects) Tj 0 -20 Td (Built a Python log parser) Tj ET')
            page[NameObject('/Contents')] = writer._add_object(stream)
            writer.write(path)
            result = extract_profile(PdfReader(path).pages[0].extract_text())
            self.assertEqual(result['education'], 'B.S. Computer Science')
            self.assertIn('Python', result['evidence'][0]['detail'])

    def test_resume_sections_and_no_invented_facts(self):
        result = extract_profile('Education\nB.S. Computer Science\nTechnical Skills\nPython, Linux\nCertifications\nPursuing Security+\nProjects\nBuilt a Python log parser\nExperience\nHelp desk assistant')
        self.assertIn('python', result['skills'])
        self.assertEqual(result['certifications'], ['Pursuing Security+'])
        self.assertEqual(len(result['evidence']), 2)
        self.assertFalse(result['approved'])

    def test_approval_detects_edits(self):
        p = {'education': 'B.S.', 'evidence': [{'detail': 'Built a lab'}], 'approved': True}
        p['approval_sha256'] = digest(p)
        validate_approval(p)
        p['education'] = 'Ph.D.'
        with self.assertRaises(ValueError):
            validate_approval(p)

    def test_missing_info_never_counts_as_candidate_match(self):
        job = {'title': 'Cybersecurity Intern', 'description': '', 'location': ''}
        result = rank(job)
        self.assertGreaterEqual(result['score'], 60)
        self.assertLess(result['score'], 80)
        self.assertTrue(result['unknown'])

    def test_skills_projects_graduation_location(self):
        job = {'title': 'Summer 2027 Security Engineer Intern', 'description': 'University bachelor student graduating 2028. Python Linux SIEM Security+', 'location': 'Austin'}
        profile = {'education': 'B.S. at university', 'skills': ['Python', 'Linux'], 'locations': ['Austin'],
                   'graduation_year': 2027, 'evidence': [{'detail': 'Built Python log tooling', 'keywords': ['Python']}]}
        result = rank(job, profile)
        self.assertIn('python', result['matched'])
        self.assertIn('security+', result['missing'])
        self.assertTrue(any('2028' in v for v in result['missing']))

    def test_it_pathway(self):
        self.assertGreaterEqual(rank({'title': 'Information Technology Intern'})['score'], 60)

    def test_sqlite_survives_reopen(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'jobs.db'
            s = SQLiteState(path)
            expected = {'schema_version': 1, 'boards': {'example': {'seen': {}}}}
            s.save(expected)
            s.close()
            s = SQLiteState(path)
            self.assertEqual(s.load(), expected)
            s.close()

    def test_smartrecruiters_description(self):
        response = Mock(status_code=200)
        response.json.side_effect = [{'content': [{'id': '1', 'name': 'Security Intern', 'location': {}}], 'totalFound': 1},
                                     {'jobAd': {'sections': {'jobDescription': {'text': '<p>Python SIEM</p>'}}}, 'applyUrl': 'https://example.org/1'}]
        session = Mock()
        session.get.return_value = response
        jobs = smartrecruiters(session, 'Example', 'example')
        self.assertEqual(jobs[0]['description'], 'Python SIEM')

    def test_workday_public_details(self):
        session = Mock()
        session.post.return_value.json.return_value = {'total': 1, 'jobPostings': [{'title': 'Security Intern', 'externalPath': '/job/Austin/Intern_1'}]}
        session.get.return_value.json.return_value = {'jobPostingInfo': {'jobReqId': '1', 'jobDescription': '<p>Security</p>'}}
        jobs = workday(session, 'Example', 'example.wd5.External')
        self.assertEqual(jobs[0]['id'], '1')
        self.assertEqual(jobs[0]['description'], 'Security')

    def test_usajobs_requires_credentials(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            usajobs(Mock(), 'Federal', 'federal')

    def test_usajobs_parsing_and_separate_credentials(self):
        with patch.dict(os.environ, {'USAJOBS_API_KEY': 'secret', 'USAJOBS_EMAIL': 'a@example.org'}), patch('requests.Session') as factory:
            api = factory.return_value.__enter__.return_value
            api.get.return_value.status_code = 200
            api.get.return_value.json.return_value = {'SearchResult': {'SearchResultCountAll': 1, 'SearchResultItems': [
                {'MatchedObjectId': '1', 'MatchedObjectDescriptor': {'PositionTitle': 'IT Student Intern', 'PositionURI': 'https://usajobs.gov/job/1', 'UserArea': {'Details': {'JobSummary': 'Python'}}}}]}}
            jobs = usajobs(Mock(), 'Federal', 'federal')
            self.assertEqual(jobs[0]['description'], 'Python')
            self.assertEqual(api.headers.update.call_args.args[0]['Authorization-Key'], 'secret')

    @patch('tracker.time.sleep')
    def test_rate_limit_retry(self, sleep):
        session = Mock()
        session.get.side_effect = [Mock(status_code=429, headers={'Retry-After': '1'}), Mock(status_code=200)]
        get_json(session, 'https://example.org')
        self.assertEqual(session.get.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_letter_is_readable_attachment(self):
        with patch.dict(os.environ, {'DISCORD_WEBHOOK_URL': 'https://discord.com/api/webhooks/1/token'}):
            session = Mock()
            self.assertTrue(notify_cover_letter(session, {'company': 'Example'}, 'Private draft', 'local'))
            kwargs = session.post.call_args.kwargs
            self.assertEqual(kwargs['files']['files[0]'][1], b'Private draft')
            self.assertEqual(json.loads(kwargs['data']['payload_json'])['allowed_mentions'], {'parse': []})

    def test_verified_watchlist(self):
        config = json.loads(Path('config/companies.verified.json').read_text())
        self.assertGreaterEqual(len(config['boards']), 100)
        self.assertTrue(all(b.get('verified_at') and b.get('verification_url') for b in config['boards']))

    def test_workflow_contract(self):
        import yaml
        # BaseLoader preserves YAML 1.2's `on` key instead of YAML 1.1 booleans.
        workflow = yaml.load(Path('.github/workflows/monitor.yml').read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(workflow['on']['schedule'][0]['cron'], '2/5 * * * *')
        self.assertIn('workflow_dispatch', workflow['on'])
        self.assertEqual(workflow['permissions']['contents'], 'write')
        self.assertEqual(workflow['concurrency']['cancel-in-progress'], 'false')
        persistence = workflow['jobs']['check']['steps'][-1]
        self.assertEqual(persistence['if'], 'always()')


if __name__ == '__main__':
    unittest.main()
