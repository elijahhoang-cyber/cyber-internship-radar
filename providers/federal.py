"""Documented USAJOBS searches, including federal student-trainee job series."""
import logging
import re

ENDPOINT = 'https://data.usajobs.gov/api/Search'
# Keyword matches every supplied word. Union focused searches instead of requiring
# every announcement to contain the phrase "information technology student".
QUERIES = (
    {'JobCategoryCode': '2299;1599'},
    {'HiringPath': 'student', 'JobCategoryCode': '2210;1550;0854;0855'},
    {'HiringPath': 'student', 'Keyword': 'cybersecurity'},
    {'JobCategoryCode': '2210;1550;0854;0855', 'Keyword': 'intern'},
)
LOG = logging.getLogger(__name__)


def normalize(entry, company):
    from tracker import text_only
    j = entry['MatchedObjectDescriptor']
    details = j.get('UserArea', {}).get('Details', {})
    title = j['PositionTitle']
    offering = ', '.join(v.get('Name', '') for v in j.get('PositionOfferingType', []))
    description = ' '.join(str(details.get(k) or '') for k in
                           ('JobSummary', 'Qualifications', 'Education', 'Requirements', 'MajorDuties'))
    description += ' ' + str(j.get('QualificationSummary') or '')
    description += ' ' + ' '.join(str(v.get('Content') or '') for v in j.get('PositionFormattedDescription', []))
    return {'source': 'usajobs', 'company': j.get('OrganizationName') or company,
            'id': str(entry['MatchedObjectId']), 'title': title,
            'location': j.get('PositionLocationDisplay', ''), 'url': j['PositionURI'],
            'description': text_only(description),
            'employment_type': ' / '.join(filter(None, [offering, ', '.join(v.get('Name', '') for v in j.get('PositionSchedule', []))])),
            'intern_type': bool(re.search(r'\b(?:student\s+(?:trainee|volunteer)|intern(?:ship)?s?|co[ -]?op)\b', title + ' ' + offering, re.I)),
            'hiring_paths': details.get('HiringPath') or [],
            'posted_at': j.get('PublicationStartDate', ''), 'closes_at': j.get('ApplicationCloseDate', '')}


def fetch(api, company):
    from tracker import get_json
    out = {}
    for index, query in enumerate(QUERIES, 1):
        for page in range(1, 101):
            data = get_json(api, ENDPOINT, {**query, 'Fields': 'Full', 'ResultsPerPage': 500,
                                          'Page': page, 'SortField': 'opendate', 'SortDirection': 'desc'})['SearchResult']
            for entry in data['SearchResultItems']:
                job = normalize(entry, company)
                out[job['id']] = job
            if page * 500 >= int(data['SearchResultCountAll']):
                LOG.info('USAJOBS search %d: %d announcements', index, int(data['SearchResultCountAll']))
                break
        else:
            raise ValueError('USAJOBS pagination cap reached; previous state must be retained')
    return list(out.values())
