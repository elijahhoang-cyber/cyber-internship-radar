"""Additional public job-source adapters; existing adapters remain in tracker."""
from __future__ import annotations
import os
import re


def smartrecruiters(session, company, board):
    from tracker import get_json, text_only
    base = f'https://api.smartrecruiters.com/v1/companies/{board}/postings'
    out = []
    for offset in range(0, 10000, 100):
        data = get_json(session, base, {'limit': 100, 'offset': offset})
        for item in data['content']:
            title = item.get('name', '')
            # Retrieve full descriptions only for plausible student positions.
            detail = get_json(session, f"{base}/{item['id']}") if re.search(r'intern|co.?op|student', title, re.I) else item
            sections = detail.get('jobAd', {}).get('sections', {})
            out.append({'id': str(item['id']), 'source': 'smartrecruiters', 'company': company,
                        'title': title, 'location': ', '.join(str(v) for k, v in item.get('location', {}).items() if k in ('city', 'region', 'country') and v),
                        'url': detail.get('applyUrl') or f"https://jobs.smartrecruiters.com/{board}/{item['id']}",
                        'description': text_only(' '.join(s.get('text', '') for s in sections.values())),
                        'employment_type': item.get('typeOfEmployment', {}).get('label', ''),
                        'posted_at': item.get('releasedDate', '')})
        if offset + len(data['content']) >= data['totalFound']:
            return out
    raise ValueError('SmartRecruiters pagination cap reached')


def usajobs(session, company, board):
    from providers.federal import fetch
    if not os.environ.get('USAJOBS_API_KEY') or not os.environ.get('USAJOBS_EMAIL'):
        raise ValueError('USAJOBS_API_KEY and USAJOBS_EMAIL are required')
    # A separate session prevents credential headers reaching other providers.
    import requests
    with requests.Session() as api:
        api.headers.update({'Host': 'data.usajobs.gov', 'User-Agent': os.environ['USAJOBS_EMAIL'],
                            'Authorization-Key': os.environ['USAJOBS_API_KEY']})
        return fetch(api, company)


def workday(session, company, board):
    """Opt-in public CXS board. Token is tenant.host.site; no login/bypass."""
    from tracker import text_only
    parts = board.split('.', 2)
    if len(parts) != 3 or not re.fullmatch(r'wd\d+', parts[1]):
        raise ValueError('Workday board must be tenant.wdN.site')
    tenant, host, site = parts
    base = f'https://{tenant}.{host}.myworkdayjobs.com'
    api = f'{base}/wday/cxs/{tenant}/{site}'
    out = []
    for offset in range(0, 10000, 20):
        response = session.post(api + '/jobs', json={'appliedFacets': {}, 'limit': 20, 'offset': offset, 'searchText': ''}, timeout=(8, 25))
        response.raise_for_status()
        data = response.json()
        for item in data['jobPostings']:
            path = item['externalPath']
            if not path.startswith('/job/') or '..' in path:
                raise ValueError('Unexpected Workday path')
            detail = {}
            if re.search(r'intern|co.?op|student', item['title'], re.I):
                result = session.get(api + path, timeout=(8, 25))
                result.raise_for_status()
                detail = result.json()['jobPostingInfo']
            out.append({'source': 'workday', 'company': company, 'id': detail.get('jobReqId') or path,
                        'title': item['title'], 'location': item.get('locationsText', ''),
                        'url': f'{base}/{site}{path}', 'description': text_only(detail.get('jobDescription', '')),
                        'employment_type': detail.get('timeType', ''), 'posted_at': detail.get('startDate', '')})
        if offset + len(data['jobPostings']) >= data['total']:
            return out
    raise ValueError('Workday pagination cap reached')
