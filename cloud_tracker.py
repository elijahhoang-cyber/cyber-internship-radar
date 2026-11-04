#!/usr/bin/env python3
"""Stateless-worker compatible monitor; persist its JSON state in Git."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
from typing import Any

import requests
from tracker import FETCHERS, USER_AGENT, notify_discord, notify_cover_letter, score_job
from cover_letters import draft_letter, resume_profile_from_env
from matching import rank

LOG = logging.getLogger('cloud_tracker')
HERE = Path(__file__).resolve().parent


def load_state(path: Path) -> dict:
    if not path.exists():
        return {'schema_version': 1, 'boards': {}}
    obj = json.loads(path.read_text(encoding='utf-8'))
    if obj.get('schema_version') != 1 or not isinstance(obj.get('boards'), dict):
        raise ValueError('Unsupported or corrupted state file; refusing to reset deduplication')
    for board in obj['boards'].values():
        if not isinstance(board, dict) or not isinstance(board.get('seen'), dict):
            raise ValueError('Corrupted board history; refusing to reset')
        for entry in board['seen'].values():
            if not isinstance(entry, dict) or not all(k in entry for k in ('first_seen', 'score', 'alerted')):
                raise ValueError('Corrupted job history; refusing to reset')
    if 'tohuman' in obj:
        ledger = obj['tohuman']
        if (not isinstance(ledger, dict) or ledger.get('version') != 1
                or not isinstance(ledger.get('jobs'), dict) or not isinstance(ledger.get('months'), dict)):
            raise ValueError('Corrupted ToHuman ledger; refusing to reset')
        statuses = {'queued', 'attempted', 'uncertain', 'skipped', 'failed', 'rejected', 'verified'}
        if any(not isinstance(r, dict) or r.get('status') not in statuses for r in ledger['jobs'].values()):
            raise ValueError('Invalid ToHuman request journal')
        if any(not isinstance(m, dict) or type(m.get('reserved_words')) is not int or m['reserved_words'] < 0 for m in ledger['months'].values()):
            raise ValueError('Invalid ToHuman monthly accounting')
    return obj


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')
    temp.replace(path)


def scan(config: dict, state: dict, session: Any, webhook_configured: bool, now: datetime | None = None, checkpoint=None) -> dict:
    now = now or datetime.now(timezone.utc)
    timestamp = now.isoformat(timespec='seconds')
    boards = config.get('boards') or []
    if not boards:
        raise ValueError('No boards configured! Edit companies.json to add your actual ATS boards.')
    if not isinstance(boards, list):
        raise ValueError('companies.json boards must be a list')
    total_new = total_matches = total_sent = total_failed = ok_boards = 0
    try:
        profile = resume_profile_from_env()
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        LOG.error('Invalid private resume profile; sending job alerts without letters: %s', type(exc).__name__)
        profile = None
    if config.get('tohuman', {}).get('enabled'):
        ledger = state.setdefault('tohuman', {'version': 1, 'jobs': {}, 'months': {}})
        if os.environ.get('TOHUMAN_ARCHIVE_READY') == 'true':
            ledger.pop('archive_notice_sent', None)
        elif webhook_configured and not ledger.get('archive_notice_sent'):
            try:
                from tracker import notify_processing_status
                if notify_processing_status(session, 'ToHuman private archive is unavailable. Discovery alerts continue; cover-letter processing is paused and no letter was sent to ToHuman. Check the workflow archive step.'):
                    ledger['archive_notice_sent'] = True
            except Exception:
                pass
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    def canonical(url):
        parts = urlsplit(url)
        query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith('utm_') and k.lower() not in ('gh_src', 'source', 'ref')))
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'), query, ''))
    urls = {canonical(entry['job']['url']): entry for b in state['boards'].values()
            for entry in b['seen'].values() if entry.get('job', {}).get('url')}
    for cfg in boards:
        source = str(cfg['source']).lower()
        company = str(cfg['company']).strip()
        token = str(cfg['board']).strip()
        if source not in FETCHERS or not re.fullmatch(r'[A-Za-z0-9_.-]+', token):
            LOG.error('Invalid board configuration: %r', cfg)
            total_failed += 1
            continue
        board_key = f'{source}:{token}'
        try:
            jobs = FETCHERS[source](session, company, token)
        except Exception as exc:
            LOG.error('Board unavailable (%s): %s; previous state retained', board_key, exc)
            total_failed += 1
            continue
        ok_boards += 1
        previous = state['boards'].get(board_key)
        if previous is None:
            previous = {'company': company, 'started_at': timestamp, 'seen': {}}
            state['boards'][board_key] = previous
            is_baseline = config.get('initial_mode', 'baseline') == 'baseline'
        else:
            is_baseline = False
        seen = previous['seen']
        for job in jobs:
            job_id = str(job['id'])
            old = seen.get(job_id)
            duplicate = urls.get(canonical(job.get('url', ''))) if job.get('url') else None
            if old is None:
                assessment = rank(job, profile)
                score = assessment['score']
                # First successful scan of EACH board is a no-alert baseline.
                old = {'first_seen': timestamp, 'score': score,
                       'alerted': is_baseline or score == 0 or duplicate is not None,
                       'letter_sent': is_baseline or score == 0 or duplicate is not None,
                       'job': job if score else {k: v for k, v in job.items() if k != 'description'},
                       'category': assessment['category']}
                if config.get('tohuman', {}).get('enabled') and not is_baseline and duplicate is None:
                    old['tohuman_future'] = True
                    old['tohuman_key'] = board_key + ':' + job_id
                seen[job_id] = old
                if job.get('url'):
                    urls[canonical(job['url'])] = old
                total_new += 1
                if score:
                    total_matches += 1
            old.setdefault('job', job)
            job = {**job, 'first_seen': old['first_seen']}
            if old['score'] and not old['alerted'] and webhook_configured:
                if checkpoint:
                    checkpoint(state)
                try:
                    if notify_discord(session, job, old['score'], old.get('category', 'Student opportunity')):
                        old['alerted'] = True
                        total_sent += 1
                        if checkpoint:
                            checkpoint(state)
                except Exception as exc:
                    LOG.error('Immediate alert failed: %s', type(exc).__name__)
        if checkpoint:
            checkpoint(state)
        LOG.info('%s: %d jobs, %s, %d tracked', company, len(jobs), 'initial baseline' if is_baseline else 'checked', len(seen))
        time.sleep(max(0, min(float(config.get('seconds_between_boards', 0.3)), 10)))
    # Durable public-job outbox: retry even when a posting disappears or a board fails.
    pending = [entry for board in state['boards'].values() for entry in board['seen'].values() if entry.get('job')]
    for phase in ('alert', 'letter'):
        letters = 0
        for old in pending:
            job = {**old['job'], 'first_seen': old['first_seen']}
            if phase == 'alert' and old['score'] and not old['alerted'] and webhook_configured:
                try:
                    if notify_discord(session, job, old['score'], old.get('category', 'Student opportunity')):
                        old['alerted'] = True
                        total_sent += 1
                        if checkpoint:
                            checkpoint(state)
                        time.sleep(1)
                except Exception as exc:
                    LOG.error('Discord alert failed: %s', type(exc).__name__)
                    total_failed += 1
            if (phase == 'letter' and old['alerted'] and not old.get('letter_sent', True)
                    and webhook_configured and profile and letters < int(config.get('max_letters_per_run', 3))):
                assessment = rank(job, profile)
                enabled = config.get('tohuman', {}).get('enabled', False)
                threshold = max(80, int(config.get('letter_min_score', 80))) if enabled else int(config.get('letter_min_score', 80))
                if assessment['score'] < threshold:
                    continue
                if enabled:
                    # Old records, including the delivered baseline examples, never
                    # enter ToHuman. Only future discoveries carry this marker.
                    if not old.get('tohuman_future') or os.environ.get('TOHUMAN_ARCHIVE_READY') != 'true':
                        continue
                    existing_request = state.get('tohuman', {}).get('jobs', {}).get(old['tohuman_key'])
                    if existing_request:
                        if existing_request.get('notified'):
                            old['letter_sent'] = True
                        continue
                    try:
                        from humanization.vault import Vault
                        from humanization.pipeline import queue
                        queue(state, old['tohuman_key'], job, profile, Vault())
                        letters += 1
                    except Exception as exc:
                        LOG.error('Private draft queue unavailable (%s)', type(exc).__name__)
                        if not old.get('draft_failure_notified'):
                            try:
                                from tracker import notify_processing_status
                                if notify_processing_status(session, 'A local cover-letter draft could not be prepared for ' + str(job['company'])[:100] + ': ' + str(job['title'])[:200] + '. No ToHuman request was made. Check workflow logs for the error class.'):
                                    old['draft_failure_notified'] = True
                            except Exception:
                                pass
                    continue
                letters += 1
                try:
                    letter, mode = draft_letter(job, profile, session)
                    if notify_cover_letter(session, job, letter, mode):
                        old['letter_sent'] = True
                        if checkpoint:
                            checkpoint(state)
                        time.sleep(1)
                except Exception as exc:
                    LOG.error('Letter delivery failed: %s', type(exc).__name__)
                    total_failed += 1
    # Weekly heartbeat ensures a long-lived public repo keeps receiving commits,
    # since public-repo schedules are disabled after 60 days of inactivity.
    last = state.get('last_heartbeat_utc', '')
    try:
        last_date = datetime.fromisoformat(last) if last else None
    except ValueError:
        last_date = None
    if ok_boards and (last_date is None or now - last_date >= timedelta(days=7)):
        state['last_heartbeat_utc'] = timestamp
    LOG.info('Done: %s new, %s candidate matches, %s Discord sent, %s errors, %s successful boards', total_new, total_matches, total_sent, total_failed, ok_boards)
    if not ok_boards:
        raise RuntimeError('Every configured board failed; refusing to overwrite state')
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=str(HERE / 'config/companies.verified.json'))
    parser.add_argument('--state', default=str(HERE / 'state/seen.json'))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    state = None
    try:
        config = json.loads(Path(args.config).read_text(encoding='utf-8'))
        humanizer_config = HERE / 'config/tohuman.json'
        if humanizer_config.exists():
            config['tohuman'] = json.loads(humanizer_config.read_text())
        state = load_state(Path(args.state))
        with requests.Session() as session:
            session.headers['User-Agent'] = USER_AGENT
            scan(config, state, session, bool(os.environ.get('DISCORD_WEBHOOK_URL', '').strip()), checkpoint=lambda obj: save_state(Path(args.state), obj))
        save_state(Path(args.state), state)
        return 0
    except Exception:
        LOG.exception('Cloud scan failed')
        return 1
    finally:
        if state is not None:
            save_state(Path(args.state), state)


if __name__ == '__main__':
    sys.exit(main())
