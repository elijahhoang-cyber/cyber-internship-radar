# Validation record

Local validation completed November 3, 2026 (America/Chicago).

- Python 3.12.10: 43 unit/integration tests passed with `python -m unittest discover -s tests -q`.
- Live discovery: 134 successful public boards, 22,663 postings captured in ignored `private/live-smoke-state.json`. Discord, candidate-profile environment and external AI were disabled for this scan.
- Watchlist verification: 134 nonempty public employer APIs verified, with evidence in `config/companies.verified.json`.
- `git check-ignore -v` confirmed `private/resume.pdf`, `private/profile.approved.json`, nested private files, generated letters under `letters/`, and root generated-letter patterns are excluded. Automated regression test repeats these checks.
- Provider tests cover Greenhouse, Lever, Ashby, SmartRecruiters, Workday and USAJOBS using mocked responses. Live SmartRecruiters and Workday checks subsequently succeeded; authenticated USAJOBS remains untested without API credentials.
- Resume tests cover a real generated PDF with selectable text, structured section extraction, and approval invalidation after changes. No personal resume was supplied or processed.
- Discord attachment and optional AI requests were tested with mocks only. A subsequent authorized cloud diagnostic sent a labeled synthetic alert and UTF-8 attachment successfully; no external AI request was sent.
- Missing profile, incomplete descriptions, skills gaps, API failures, rate-limit retry, corrupt state rejection, deduplication by ID and URL, retry after posting disappearance, SQLite reopen and workflow configuration were tested.

Cloud deployment succeeded. External AI remains disabled pending explicit user approval. No personal resume/profile has been uploaded.

Initial GitHub test matrix passed on Python 3.11, 3.12 and 3.13: https://github.com/elijahhoang-cyber/cyber-internship-radar/actions/runs/41771562931 .

Cloud baseline run succeeded: https://github.com/elijahhoang-cyber/cyber-internship-radar/actions/runs/41772018522 - 134 boards, 22,669 public postings, 20 candidate opportunities, zero provider errors; public history committed successfully.

Cloud repeat run succeeded: https://github.com/elijahhoang-cyber/cyber-internship-radar/actions/runs/41772353341 - zero new postings, zero duplicate notifications, no unnecessary state commit.

Discord diagnostic succeeded: https://github.com/elijahhoang-cyber/cyber-internship-radar/actions/runs/41772722339 - GitHub Actions accessed DISCORD_WEBHOOK_URL and Discord accepted both the synthetic job alert and synthetic text attachment. No webhook value was logged. Diagnostic regression tests cover missing secret and exception redaction.

Additional live adapters: SmartRecruiters returned 2 public postings; Capital One Workday returned 2,025. Both boards were reverified and added, bringing the active watchlist to 136. USAJOBS parsing and credential requirements passed mocked tests, but a live authenticated request is pending credentials.

The first cloud persistence attempt exposed a missing Git identity during rebase; the workflow now configures the bot identity for the checkout, fetches complete history and retries push races. Subsequent manual runs passed. Actions were upgraded to their Node 24 versions after the deprecated runtime warning.

Final 136-board deployment passed in 2m54s: https://github.com/elijahhoang-cyber/cyber-internship-radar/actions/runs/41772957696 . The scan initialized the two added boards (2,027 postings), retained the prior 22,669, reported zero provider errors and saved state. Total retained history: 24,696 public postings. The final Node 24 workflow test matrix passed: https://github.com/elijahhoang-cyber/cyber-internship-radar/actions/runs/41772957101 .

External AI repository variable was rechecked as false. Only the Discord webhook secret was configured at verification time; no candidate profile, resume or AI credential was uploaded. Legacy local-runner notification exception logging also omits exception text so webhook request URLs cannot appear there.

Federal integration validation (November 3, 2026, America/Chicago): USAJOBS_API_KEY and USAJOBS_EMAIL were supplied by the user through GitHub Secrets. No credential values were retrieved locally, printed or committed.

Authenticated federal pipeline check passed: https://github.com/elijahhoang-cyber/cyber-internship-radar/actions/runs/41774390319 . Four focused, paginated full-field searches returned 62 unique public announcements. Matching identified one security-related student opportunity: CISA Scholarship for Service (SFS) Internship, announcement 891497900, https://www.usajobs.gov/job/891497900 . Its opportunity score without a candidate profile was 45/100; discovery does not establish applicant eligibility or a strong personal match.

That real API posting was replayed through the production scanner using a clearly labeled synthetic candidate. Discord accepted the labeled alert and a local synthetic cover-letter attachment. Replaying the same state attempted neither notification again. No real candidate profile or external AI was used. The diagnostic used a lower letter threshold solely for exercising the delivery path; scheduled scans retain the score-80 threshold and approved-profile requirement.

The USAJOBS source is enabled alongside 136 employer boards. Union searches cover student-trainee series, student technical hiring paths, cybersecurity student announcements and technical internships. Full qualifications and formatted descriptions are normalized; overlapping announcements deduplicate by stable ID. Student Trainee and internship offering metadata are recognized, while a student hiring path or the word INTERNAL alone cannot turn a permanent job into an internship. Public watchlist refresh preserves authenticated source verification performed in GitHub.

All 53 local tests passed. The expanded Python 3.11/3.12/3.13 cloud matrix passed: https://github.com/elijahhoang-cyber/cyber-internship-radar/actions/runs/41774386041 . External AI was rechecked as false.

Combined deployment run passed in 2m56s: https://github.com/elijahhoang-cyber/cyber-internship-radar/actions/runs/41774386907 . All six provider types succeeded across 137 configured source entries (136 employer boards plus federal search), with zero errors. USAJOBS initialized a 62-announcement baseline and identified one relevant internship. Initial baseline announcements intentionally do not generate production alerts; the separate authorized live diagnostic delivered the representative alert and synthetic draft. Future newly detected federal matches use the normal alert, deduplication and approved-profile/score-80 letter rules. Persistent state was committed successfully, and the scheduled workflow remains active.
