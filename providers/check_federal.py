"""Live federal API + scanner diagnostic. Only a synthetic candidate is used."""
from datetime import datetime, timezone
import json
import os
import sys
from unittest.mock import patch
import requests
from cloud_tracker import scan
from matching import rank
from providers import usajobs
from resume.process import digest
from tracker import SECURITY


def main():
    try:
        jobs = usajobs(None, 'US Federal Government', 'federal')
        matched = [j for j in jobs if rank(j)['score'] > 0]
        cyber = [j for j in matched if SECURITY.search(j['title'] + ' ' + j['description'])]
        print(json.dumps({'provider': 'usajobs', 'api_authenticated': True,
                          'announcements': len(jobs), 'student_matches': len(matched),
                          'security_term_student_matches': len(cyber),
                          'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}))
        for job in (cyber or matched)[:5]:
            print(json.dumps({'id': job['id'], 'title': job['title'], 'agency': job['company'],
                              'url': job['url'], 'score_without_candidate': rank(job)['score']}))
        if not matched:
            print('API PASS; no current relevant student postings returned. Live posting pipeline test skipped.')
            return 0
        if not os.environ.get('DISCORD_WEBHOOK_URL'):
            print('FAIL: Discord secret unavailable for pipeline verification.')
            return 1
        job = {**(cyber or matched)[0]}
        job['title'] = '[LIVE FEDERAL CHECK / SYNTHETIC CANDIDATE] ' + job['title']
        profile = {'name': 'SYNTHETIC TEST APPLICANT - NOT THE USER',
                   'education': 'a synthetic test bachelor degree in computer science',
                   'skills': ['Python', 'Linux'],
                   'evidence': [{'detail': 'Synthetic test example: I wrote a Python log parser',
                                 'keywords': ['Python', 'logs', 'security']}]}
        profile['approved'] = True
        profile['approval_sha256'] = digest(profile)
        config = {'boards': [{'source': 'usajobs', 'company': 'US Federal Government', 'board': 'federal'}],
                  'initial_mode': 'alert', 'letter_min_score': 0, 'max_letters_per_run': 1, 'seconds_between_boards': 0}
        state = {'schema_version': 1, 'boards': {}}
        # Replay one genuinely fetched posting through the production scanner.
        # A lower threshold is diagnostic-only; scheduled runs retain score 80+.
        with patch.dict('cloud_tracker.FETCHERS', {'usajobs': lambda *_: [job]}), patch.dict(os.environ, {
                'RESUME_PROFILE_JSON': json.dumps(profile), 'ENABLE_EXTERNAL_AI': 'false'}), requests.Session() as session:
            scan(config, state, session, True)
            entry = state['boards']['usajobs:federal']['seen'][job['id']]
            if not entry['alerted'] or not entry['letter_sent']:
                print('FAIL: Federal pipeline did not confirm both deliveries.')
                return 1
            # Repeating the same state must not deliver either message again.
            with patch('cloud_tracker.notify_discord') as alert, patch('cloud_tracker.notify_cover_letter') as letter:
                scan(config, state, session, True)
                if alert.called or letter.called:
                    print('FAIL: Repeat scan attempted duplicate notification.')
                    return 1
        if profile['name'] in json.dumps(state):
            print('FAIL: Synthetic candidate content leaked into public state.')
            return 1
        print('PASS: Live federal posting -> matching -> Discord alert -> local synthetic draft attachment; repeat scan deduplicated.')
        print('No real candidate profile used. Diagnostic threshold only; scheduled strong-match threshold unchanged. External AI disabled.')
        return 0
    except Exception as exc:
        # Never print authenticated requests, response bodies, headers or tracebacks.
        print(f'FAIL: Federal diagnostic ({type(exc).__name__}); credential values omitted.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
