# Validation record

Local validation completed November 3, 2026 (America/Chicago).

- Python 3.12.10: 39 unit/integration tests passed with `python -m unittest discover -s tests -q`.
- Live discovery: 134 successful public boards, 22,663 postings captured in ignored `private/live-smoke-state.json`. Discord, candidate-profile environment and external AI were disabled for this scan.
- Watchlist verification: 134 nonempty public employer APIs verified, with evidence in `config/companies.verified.json`.
- `git check-ignore -v` confirmed `private/resume.pdf`, `private/profile.approved.json`, nested private files, generated letters under `letters/`, and root generated-letter patterns are excluded. Automated regression test repeats these checks.
- Provider tests cover Greenhouse, Lever, Ashby, SmartRecruiters, Workday and USAJOBS using mocked responses. Live Workday and authenticated USAJOBS were not tested.
- Resume tests cover a real generated PDF with selectable text, structured section extraction, and approval invalidation after changes. No personal resume was supplied or processed.
- Discord attachment and optional AI requests were tested with mocks only. No live Discord message or external AI request was sent.
- Missing profile, incomplete descriptions, skills gaps, API failures, rate-limit retry, corrupt state rejection, deduplication by ID and URL, retry after posting disappearance, SQLite reopen and workflow configuration were tested.

Cloud deployment results will be added after actual workflow execution. External AI remains disabled pending explicit user approval. No personal resume/profile has been uploaded.
