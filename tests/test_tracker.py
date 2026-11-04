import unittest
from unittest.mock import Mock
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tracker import fetch_greenhouse, fetch_lever, fetch_ashby, score_job


class FakeSession:
    def __init__(self, data):
        self.data = data
    def get(self, url, params=None, timeout=None):
        result = Mock(status_code=200)
        result.json.return_value = self.data
        return result


class TrackerTests(unittest.TestCase):
    def test_greenhouse(self):
        r = fetch_greenhouse(FakeSession({'jobs': [{'id': 10, 'title':'Cybersecurity Intern', 'location': {'name':'Austin, TX'}, 'absolute_url':'https://example.com/a', 'content': '<p>SOC training</p>'}]}), 'A', 'a')
        self.assertEqual(r[0]['id'], '10')
        self.assertEqual(score_job(r[0]), 95)
    def test_lever(self):
        r = fetch_lever(FakeSession([{'id':'123','text':'Information Security Co-op','categories':{'location':'Texas'},'hostedUrl':'https://example.com/b','descriptionPlain':'Build detections'}]), 'B', 'b')
        self.assertEqual(score_job(r[0]), 95)
    def test_ashby(self):
        r = fetch_ashby(FakeSession({'jobs':[{'jobUrl':'https://example.com/1','title':'Application Security Engineer','employmentType':'Intern','publishedAt':'2026-10-26T00:00:00Z','isListed':True}]}), 'C', 'c')
        self.assertEqual(score_job(r[0]), 95)
    def test_disallow_physical_security(self):
        self.assertEqual(score_job({'title':'Physical Security Intern', 'description':'Physical security guard'}), 0)
    def test_nonintern(self):
        self.assertEqual(score_job({'title':'Cybersecurity Engineer', 'description':'Full-time role'}), 0)


if __name__ == '__main__':
    unittest.main()
