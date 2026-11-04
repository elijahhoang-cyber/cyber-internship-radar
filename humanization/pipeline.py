"""Queue private originals; reserve public usage durably before one API request."""
from datetime import datetime, timezone
import os

ENDPOINT = 'https://tohuman.io/api/v1/humanizations/sync'


def queue(state, key, job, profile, vault):
    from cover_letters import local_letter, selected_evidence
    from resume.schema import validate_profile
    validate_profile(profile, require_approval=True)
    from .guard import sanitize
    ledger = state.setdefault('tohuman', {'version': 1, 'jobs': {}, 'months': {}})
    if key in ledger['jobs']:
        return False
    from matching import rank
    if rank(job, profile)['score'] < 80:
        return False
    if key in vault.records:
        ledger['jobs'][key] = {'status': 'uncertain', 'notified': False,
                              'reason': 'Private history exists without a matching public ledger; no resubmission'}
        return False
    original = local_letter(job, profile)
    facts = [e['detail'] for e in selected_evidence(job, profile)]
    facts.append(profile.get('education_statement') or ('My education includes ' + profile['education'].strip().rstrip('.') + '.'))
    # Pending certification sentences are factual too.
    from .guard import sentences
    facts.extend(s for s in sentences(original) if 'certification' in s.lower() or 'earned qualification' in s.lower())
    vault.records[key] = {'original': original, 'submitted': sanitize(original, profile.get('name', '')),
                          'facts': facts, 'job': job, 'name': profile.get('name', 'Applicant')}
    vault.save()
    ledger['jobs'][key] = {'status': 'queued', 'notified': False}
    return True


def process(state, vault, config, session, checkpoint, now=None):
    from .guard import verify
    now = now or datetime.now(timezone.utc)
    month = now.strftime('%Y-%m')
    ledger = state.setdefault('tohuman', {'version': 1, 'jobs': {}, 'months': {}})
    budget = ledger['months'].setdefault(month, {'reserved_words': 0})
    if (int(config.get('word_count_margin', 20)) < 0
            or int(config.get('monthly_word_cap', 2500)) < 0
            or any(int(v) < 0 for v in config.get('external_words_used', {}).values())):
        raise ValueError('Invalid word budget configuration')
    requests_made = 0
    for key, record in ledger['jobs'].items():
        if record['status'] == 'attempted':
            record.update(status='uncertain', reason='Prior request outcome unknown; automatic retry prohibited')
        if record['status'] == 'verified' and not vault.records.get(key, {}).get('humanized'):
            record.update(status='uncertain', reason='Verified output unavailable after interruption; original retained and no request retry')
        if record['status'] != 'queued':
            continue
        if requests_made >= 3:
            break  # Stay well below the documented Free burst/rate limits.
        private = vault.records.get(key)
        if private is None:
            continue  # Archive loss must never cause regeneration/resubmission.
        words = len(private['submitted'].split()) + int(config.get('word_count_margin', 20))
        cap = int(config.get('monthly_word_cap', 2500))
        reserve = int(config.get('reserve_words', 500))
        external = int(config.get('external_words_used', {}).get(month, 0))
        if not 0 <= reserve <= cap or words + budget['reserved_words'] + external > cap - reserve or budget.get('exhausted'):
            record.update(status='skipped', reason='Monthly budget or safety reserve reached')
            continue
        if budget.get('rate_limit_until', 0) > now.timestamp():
            record.update(status='skipped', reason='Provider rate window is blocked')
            continue
        api_key = os.environ.get('TOHUMAN_API_KEY', '').strip()
        if not api_key:
            record.update(status='skipped', reason='ToHuman credential unavailable')
            continue
        # Public reservation MUST be committed before POST. A timeout/crash is
        # counted conservatively and can never trigger a second humanization.
        record.update(status='attempted', month=month, reserved_words=words)
        budget['reserved_words'] += words
        private['request_started'] = True
        vault.save()
        checkpoint(state)
        requests_made += 1
        try:
            response = session.post(ENDPOINT, headers={'Authorization': 'Bearer ' + api_key},
                                    json={'content': private['submitted'], 'intensity': 'subtle'},
                                    timeout=(8, int(config.get('timeout_seconds', 120))), allow_redirects=False)
            if response.status_code != 200:
                if response.status_code == 402:
                    budget['exhausted'] = True
                if response.status_code == 429:
                    try:
                        reset = float(response.headers.get('X-RateLimit-Reset', now.timestamp() + 60))
                    except (TypeError, ValueError):
                        reset = now.timestamp() + 60
                    budget['rate_limit_until'] = max(now.timestamp() + 60, reset)
                record.update(status='failed', reason='Provider HTTP ' + str(response.status_code))
                continue
            data = response.json()
            output = data.get('output_content')
            if (data.get('status') != 'completed' or data.get('unchanged') is True
                    or not verify(private['submitted'], output, private['facts'], private['job']['company'], private['job']['title'])):
                record.update(status='rejected', reason='Rewrite did not pass conservative factual verification')
                continue
            final = output.strip() + '\n\nSincerely,\n' + private['name']
            if not 250 <= len(final.split()) <= 350:
                record.update(status='rejected', reason='Rewrite exceeded the 250-350 word budget')
                continue
            private['humanized'] = final
            record['status'] = 'verified'
        except Exception as exc:
            record.update(status='uncertain', reason='Provider failure: ' + type(exc).__name__)
        finally:
            vault.save()
    vault.save()
    checkpoint(state)


def deliver(state, vault, session):
    from tracker import notify_cover_letter
    for key, record in state.get('tohuman', {}).get('jobs', {}).items():
        if record.get('notified') or record['status'] in ('queued', 'attempted'):
            continue
        private = vault.records.get(key)
        if private is None:
            continue
        verified = record['status'] == 'verified' and bool(private.get('humanized'))
        text = private['humanized'] if verified else private['original']
        mode = 'ToHuman subtle rewrite; factual checks passed; review before submission' if verified else 'ORIGINAL LOCAL DRAFT; ToHuman not completed: ' + record.get('reason', record['status'])
        try:
            if notify_cover_letter(session, private['job'], text, mode):
                record['notified'] = True
                record['delivered'] = 'humanized' if verified else 'original'
                board, identifier = key.rsplit(':', 1)
                old = state.get('boards', {}).get(board, {}).get('seen', {}).get(identifier)
                if old is not None:
                    old['letter_sent'] = True
        except Exception:
            pass  # Cached rewrite/original permits delivery retry without another API call.
