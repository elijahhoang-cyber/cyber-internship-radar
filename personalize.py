"""Prepare selected discovered-job letters privately, or deliver from Actions.

Only public job identifiers and delivery status may be logged. This command
never scans boards, sends job alerts, submits applications, or calls an AI API.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

from cloud_tracker import load_state
from cover_letters import local_letter, resume_profile_from_env, selected_evidence
from matching import rank
from resume.schema import validate_profile


def prepare_letters(state, selections, profile):
    validate_profile(profile, require_approval=True)
    if not isinstance(selections, list) or not 1 <= len(selections) <= 5:
        raise ValueError('Select between one and five discovered postings')
    result = []
    used = set()
    for selection in selections:
        if not isinstance(selection, dict) or not all(isinstance(selection.get(k), str) for k in ('board', 'id')):
            raise ValueError('Each selection requires a board and job ID')
        key = (selection['board'], selection['id'])
        if key in used:
            raise ValueError('Duplicate posting in selections')
        used.add(key)
        job = dict(state['boards'][key[0]]['seen'][key[1]]['job'])
        if not job.get('description'):
            raise ValueError('Selected posting has no stored description')
        display = selection.get('display_company', job['company'])
        if not isinstance(display, str) or display.casefold() != job['company'].casefold():
            raise ValueError('Company display override may change capitalization only')
        job['company'] = display
        assessment = rank(job, profile)
        if assessment['score'] == 0:
            raise ValueError('Selected posting is not a relevant technical internship')
        letter = local_letter(job, profile)
        evidence = selected_evidence(job, profile)
        education = profile.get('education_statement') or ('My education includes ' + profile['education'].strip().rstrip('.') + '.')
        if not all(e['detail'].strip().rstrip('.') + '.' in letter for e in evidence):
            raise ValueError('Letter evidence failed its approved-profile check')
        if education not in letter or not 250 <= len(letter.split()) <= 350:
            raise ValueError('Letter failed education or word-budget verification')
        filename = 'cover_letter_' + re.sub(r'[^a-z0-9_-]+', '_', job['company'].lower()).strip('_') + '_' + re.sub(r'[^A-Za-z0-9_-]', '_', job['id']) + '.txt'
        result.append({'board': key[0], 'id': key[1], 'job': job, 'letter': letter,
                       'filename': filename, 'assessment': assessment,
                       'evidence_ids': [e.get('id', e.get('label', 'reviewed evidence')) for e in evidence],
                       'word_count': len(letter.split())})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', default='state/seen.json')
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--output', type=Path, default=Path('letters'))
    parser.add_argument('--no-save', action='store_true')
    parser.add_argument('--deliver', action='store_true')
    args = parser.parse_args()
    try:
        raw = args.selection.read_text(encoding='utf-8') if args.selection else os.environ.get('JOB_SELECTION_JSON', '')
        selections = json.loads(raw)
        profile = json.loads(args.profile.read_text(encoding='utf-8')) if args.profile else resume_profile_from_env()
        if profile is None:
            raise ValueError('Approved candidate profile is required')
        letters = prepare_letters(load_state(Path(args.state)), selections, profile)
        if not args.no_save:
            output = args.output.resolve()
            if not any(output.is_relative_to(Path(root).resolve()) for root in ('private', 'letters')):
                raise ValueError('Letter output must stay in private/ or letters/')
            output.mkdir(parents=True, exist_ok=True)
            for item in letters:
                (output / item['filename']).write_text(item['letter'] + '\n', encoding='utf-8')
            (output / 'personalization_audit.json').write_text(json.dumps([
                {k: v for k, v in item.items() if k not in ('letter', 'job')} for item in letters
            ], indent=2) + '\n', encoding='utf-8')
        if args.deliver:
            import requests
            from tracker import notify_cover_letter
            with requests.Session() as session:
                for item in letters:
                    if not notify_cover_letter(session, item['job'], item['letter'], 'Local draft from approved profile; review before use'):
                        raise RuntimeError('Discord did not confirm delivery')
                    print('DELIVERED', item['board'], item['id'])
        else:
            print('Prepared', len(letters), 'private local drafts; no external delivery requested.')
        print('Approved-profile checks passed. Candidate data and letter text omitted from logs.')
        return 0
    except Exception as exc:
        # HTTP exception text can contain webhook URLs; candidate validation errors
        # must not echo input. Keep all failure details out of public Actions logs.
        print('Personalization failed:', type(exc).__name__, '(private input omitted)')
        return 1


if __name__ == '__main__':
    sys.exit(main())
