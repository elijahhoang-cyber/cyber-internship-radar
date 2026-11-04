"""Send explicitly labeled synthetic Discord diagnostics; never load candidate data."""
import os
import sys
import requests
from tracker import notify_discord, notify_cover_letter


def main():
    if not os.environ.get('DISCORD_WEBHOOK_URL', '').strip():
        print('FAIL: DISCORD_WEBHOOK_URL is not available to this workflow.')
        return 1
    job = {'company': 'Cyber Internship Radar — TEST',
           'title': 'Notification connection test (not a real job)',
           'location': 'Synthetic test', 'employment_type': 'Test only',
           'url': 'https://github.com/elijahhoang-cyber/cyber-internship-radar', 'posted_at': ''}
    try:
        with requests.Session() as session:
            if not notify_discord(session, job, 0, 'Connection test; no application or candidate data'):
                print('FAIL: Discord did not confirm the test alert; it may be rate limited.')
                return 1
            print('PASS: Discord accepted the synthetic job alert.')
            letter = ('NOTIFICATION TEST — NOT A COVER LETTER\n\n'
                      'This synthetic text attachment verifies file delivery from GitHub Actions.\n'
                      'No resume, candidate profile, or personal information was used.\n'
                      'External AI remains disabled.\n')
            if not notify_cover_letter(session, job, letter, 'synthetic diagnostic'):
                print('FAIL: Discord did not confirm the test attachment; it may be rate limited.')
                return 1
            print('PASS: Discord accepted the synthetic UTF-8 attachment.')
            return 0
    except Exception as exc:
        # Requests exceptions include request URLs: never print the exception/traceback.
        print(f'FAIL: Discord diagnostic failed ({type(exc).__name__}); secret value omitted.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
