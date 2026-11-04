# Cyber Internship Radar

Public-source cybersecurity and IT internship discovery, explainable ranking, and private cover-letter drafts. Python 3.11+, no mandatory paid service. Applications are never submitted automatically.

The active watchlist is `config/companies.verified.json`: 136 employer identifiers plus an authenticated USAJOBS federal search, verified against live APIs. Each entry records its verification URL, timestamp, and observed job count. A verified board does not mean it currently has an internship or that its availability is permanent.

## Run locally

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe radar.py
```

`radar.py` uses SQLite (`jobs.sqlite3`). `cloud_tracker.py` uses atomic JSON snapshots for GitHub runs. Both use the same scanner. The original `tracker.py` remains available for compatibility; use `radar.py` for the full feature set. Environment variables are read from the process; `.env` is not automatically loaded.

The first successful poll of each board establishes a silent baseline to avoid hundreds of stale alerts. Later new relevant jobs alert immediately, before any cover letters are generated. Set `initial_mode` to `alert` in a custom config to include current opportunities. Stable provider IDs and canonical application URLs prevent routine duplicates. Pending alerts and letters retry even when a posting disappears. Provider failures retain all history. Corrupt state fails closed rather than resetting history.

## Private resume workflow

Put your PDF under `private/`. Never put it in the repository root. The entire `/private/` and `/letters/` trees, PDFs, and generated letter filename patterns are ignored. Verify before importing:

```powershell
git check-ignore -v private/resume.pdf private/profile.approved.json letters/cover_letter_preview.txt
.venv/Scripts/python.exe -m resume.process extract private/resume.pdf
```

Review and edit `private/profile.draft.json`. Extraction is local and heuristic: it recognizes education, skills, certifications, projects, experience and accomplishments. Scanned PDFs need local OCR first. Verify every fact, distinguish pending certifications, and rewrite evidence entries as accurate first-person statements. Optional fields include `name`, `locations` (list), and `graduation_year`. Then:

```powershell
.venv/Scripts/python.exe -m resume.process approve private/profile.draft.json
.venv/Scripts/python.exe preview_letter.py --company Example --title "SOC Analyst Intern" --description "Investigate SIEM alerts"
```

Approval adds a hash: edits invalidate approval. This records your review, not a cryptographic identity signature. Letter previews are written only inside ignored private directories. No original PDF, extracted profile, or generated letter is saved in public job state.

For cloud personalization, only after you approve using GitHub Secrets for the profile:

```powershell
gh secret set RESUME_PROFILE_JSON --repo OWNER/cyber-internship-radar < private/profile.approved.json
```

The redirection example above is for Bash/cmd; in PowerShell use:

```powershell
Get-Content -Raw private/profile.approved.json | gh secret set RESUME_PROFILE_JSON --repo OWNER/cyber-internship-radar
```

This uploads the approved JSON to GitHub Secrets, not to source control. GitHub runners decrypt it during execution; trusted workflow code can access it. Avoid personal contact details unless you need them. The PDF stays local. Do not use public workflow artifacts for candidate data.

## Cover letters and privacy

External AI is disabled by default and currently has no user approval. Local drafts use only supplied evidence, company/title, and overlapping job keywords. The fallback is intentionally conservative, and sparse profiles produce shorter letters. It cannot manufacture meaningful company research or qualifications. Review every letter before sending.

An optional Gemini adapter accepts `GEMINI_MODEL` (default `gemini-2.5-flash`), with timeouts and a local fallback on failure. Enabling it requires an explicit user decision and `ENABLE_EXTERNAL_AI=true` plus a key. It transmits the approved profile and job description to Google; it does not upload the PDF. Google's unpaid-service terms permit product improvement use and human review and say not to submit sensitive or personal information. Review [Google's terms](https://ai.google.dev/gemini-api/terms) and [quotas](https://ai.google.dev/gemini-api/docs/rate-limits) before any opt-in. Free availability and limits are not guaranteed. AI outputs are drafts and can still contain factual errors despite grounding instructions.

Discord receives private letters only when you configure its webhook. Anyone with channel access can read the attachment. The job alert includes company, title, location, employment type when known, publication date when provided, first-detected timestamp, match score, and application link. Letters arrive separately as UTF-8 text files. Allowed mentions are disabled. The default limit is three letter attempts per run, only at score 80+; configure `max_letters_per_run` and `letter_min_score`.

## Sources and ranking

Greenhouse, Lever and Ashby use documented public APIs. SmartRecruiters uses its public Posting API with pagination and full student-posting descriptions. USAJOBS requires `USAJOBS_API_KEY` and `USAJOBS_EMAIL`; its adapter unions student-trainee job series, technical student hiring paths, cybersecurity student announcements and technical internship searches. Full qualifications are requested and duplicate announcements are merged. The federal source is now enabled in the verified configuration; its credentials remain only in GitHub Secrets. Federal Student Trainee titles and internship offering types are recognized explicitly; a student hiring path alone does not make a permanent role an internship. For SmartRecruiters, use its documented company identifier.

Workday requires individual board verification because public CXS availability and employer policies vary. The verified Capital One board is enabled. Its board format is `tenant.wd5.External` (substitute the actual host and career site). Only enable boards you have checked and are permitted to access. It does not bypass authentication or bot protection. Workday POST pagination currently defers retries to the next scan. The default list includes verified SmartRecruiters, Capital One Workday and authenticated USAJOBS sources.

Ranking uses cybersecurity/IT relevance and student-role eligibility, Summer 2027 priority, actual profile skills, relevant project evidence, education, certification keywords, preferred location, and explicit graduation year. Unknowns do not earn candidate-match points. Missing descriptions remain possible matches. Categories: 90+ Excellent, 80+ Strong, 70+ Good, 60+ Possible, below 60 Low priority. Rankings are heuristics, not eligibility guarantees; citizenship, sponsorship, clearance, degree equivalence, and nuanced location requirements still need human review. Use `matching.rank(job, profile)` for matched/missing/unknown evidence; private evidence details are not persisted publicly.

To refresh the default watchlist:

```powershell
.venv/Scripts/python.exe verify_boards.py
```

Candidate tokens in the verifier are hypotheses; only successful nonempty live boards enter its output. Review employer identity and relevance before extending it. One board per token is enabled to reduce migration duplicates.

## GitHub deployment

See [SETUP_GITHUB.md](SETUP_GITHUB.md). The five-minute schedule and manual dispatch run on GitHub without your computer. Public job history is committed to `state/seen.json`; secrets, original resumes and letters are never included. The workflow serializes scans and persists checkpoints even after ordinary scan errors. A separate test workflow covers Python 3.11-3.13.

GitHub schedules are best effort: runs can be delayed or dropped, only run from the default branch, and public schedules may be disabled after 60 days of inactivity. A weekly public-state heartbeat provides activity, but monitoring the workflow remains necessary. See [GitHub scheduling documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). Concurrency can replace queued runs, so a five-minute cron is not a five-minute detection guarantee.

Webhook delivery and Git commits cannot form one atomic transaction. A runner crash, timeout, or failed state push after Discord accepts a message can cause a duplicate next run. Normal retries deduplicate confirmed deliveries; exactly-once notification is not guaranteed by Discord webhooks. History grows over time; monitor state size and migrate to sharded state before repository file limits are reached. No paid database or hosting is required for this MVP.

Provider references: [Greenhouse](https://docs.greenhouse.io/job-board), [Lever](https://github.com/lever/postings-api), [Ashby](https://developers.ashbyhq.com/docs/public-job-posting-api), [SmartRecruiters](https://developers.smartrecruiters.com/docs/endpoints), [USAJOBS](https://developer.usajobs.gov/api-reference/get-api-search).

Public state retains complete descriptions for relevant student opportunities. Unrelated jobs retain IDs and public metadata but omit descriptions to keep history below GitHub file-size limits.

To verify Discord secret access and delivery without candidate information, manually dispatch the `Discord connection check` workflow. It sends a labeled synthetic job alert and a synthetic text attachment. Error output omits request URLs and secret values.

The manual `USAJOBS live pipeline check` workflow tests authentication and replays one live relevant federal posting through the scanner with a clearly synthetic candidate. It sends one labeled alert and one local synthetic draft, then verifies a repeat scan sends neither again. Its lower diagnostic letter threshold never changes the scheduled score-80 threshold. This does not prove the real applicant meets federal program, citizenship, clearance or scholarship eligibility. Public-board refresh preserves the federal source validation from its credentialed cloud check.
