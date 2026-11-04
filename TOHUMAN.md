# ToHuman integration

The six discovery providers and five-minute cron are unchanged. This extension applies only to future cybersecurity/IT internship discoveries scoring at least 80. Lower scores still receive normal job alerts but produce no cover letters. Existing history, including already-delivered examples, is not opted into humanization. Manual local personalization also enforces score 80.

## Verified provider contract

Official references checked November 3, 2026: [quickstart](https://tohuman.io/docs/quickstart), [humanizations](https://tohuman.io/docs/humanizations), [errors](https://tohuman.io/docs/errors), [rate limits](https://tohuman.io/docs/rate-limits), [pricing](https://tohuman.io/pricing).

Use `POST https://tohuman.io/api/v1/humanizations/sync`, bearer authentication, and JSON containing only `content` and `intensity: subtle`. A successful completed result supplies `output_content`. The documented synchronous limit is 2,000 words; these letters are 250-350 words. Documentation lists Free at 2,500 words/month, 60 requests/minute and burst 10. No undocumented usage endpoint or idempotency behavior is assumed. No detector outcome is promised.

## Processing and privacy

1. Send the ordinary job alert immediately.
2. Generate a local draft from the approved secret. Preserve the exact original in an encrypted vault.
3. Upload the encrypted-original archive before any text-processing request.
4. Reserve the request and its budget in public job-state metadata and successfully push that checkpoint before POST.
5. Send only the letter body to ToHuman. Remove the sign-off name, email addresses, phone numbers and web links. No resume, profile object, job description, evidence metadata, document title, callback URL or other secrets enter the request.
6. Apply conservative factual checks. Restore the sign-off locally only after verification.
7. Upload the encrypted result before Discord delivery. A cached result can be delivered again after a webhook failure without another ToHuman request.

Only `TOHUMAN_API_KEY` from GitHub Secrets authenticates ToHuman. Gemini and other optional external AI remain disabled; the monitor no longer receives a Gemini key. The worker receives no resume-profile secret. Only the discovery/draft stage reads that profile.

The vault uses authenticated Fernet encryption via cryptography. Its key is `TOHUMAN_VAULT_KEY`, a separate GitHub Secret, with a local backup under ignored `private/tohuman.vault.key`. Only `private/automation/vault.enc` is uploaded. Plaintext letters and profiles are not committed or uploaded as workflow artifacts. Artifacts on a public repository may be downloadable by others, but contain ciphertext only. Do not delete or rotate the key without preserving the old key and migrating the archive.

Two encrypted snapshots are retained; each has 90-day retention and running monitoring refreshes the archive. If monitoring stops longer than retention, archives can expire. Download a backup before disabling monitoring. Archive restoration or decryption failures pause private processing and send an operational notice while discovery alerts continue. No original is regenerated to bypass a missing request history.

To read originals locally, download an encrypted vault artifact to an ignored folder, then run:

```powershell
.venv/Scripts/python.exe -m humanization.export --vault private/download/vault.enc --key-file private/tohuman.vault.key --output letters/automatic
```

## Quota accounting and interruptions

`config/tohuman.json` defaults to a 2,500-word cap, a 500-word reserve and a 20-word counting margin per request. Each attempt reserves at least 350 words plus that margin, covering the largest accepted output; input and successful output word counts are also recorded. At most three POSTs are attempted per run. Public `state/seen.json` stores job/request flags and monthly reserved-word counts, never letter text or candidate facts. Accounting uses UTC calendar months.

This is a conservative app-local usage ledger, not a live account balance. Successes, ambiguous timeouts and rejected requests remain reserved to avoid accidental overspending. Actual provider billing/counting may differ. Record usage outside this automation under `external_words_used` by YYYY-MM; the API does not document an account-usage endpoint. Provider 402 blocks that accounting month, while 429 blocks further requests until the documented reset time. No plan upgrades or word-pack purchases are automated.

A job receives at most one humanization POST. There are no automatic POST retries after timeout, 4xx, 5xx, malformed output or failed factual verification. A successfully persisted reservation prevents duplicate requests across restarts. If a runner dies after the reservation, or a verified result is lost before its encrypted upload, the outcome is treated as uncertain and the original is retained. This conservative choice can leave a reserved job unprocessed even when no request actually reached the service.

On failure, Discord receives the original attachment clearly marked `ORIGINAL LOCAL DRAFT; ToHuman not completed`, with a short reason. Only verified, changed output gets the ToHuman label. Delivery failures retry from the encrypted cache. As with all Discord webhooks, a timeout after Discord accepts a message can still cause duplicate delivery; it cannot cause duplicate humanization.

## Factual verification limits

Education and selected qualification/accomplishment sentences must remain unchanged apart from case and whitespace. Employer/title, numbers, key negations and certification status must survive. New first-person claims and newly introduced technical skills are rejected. Unchanged responses and out-of-budget lengths are also rejected.

This intentionally rejects some legitimate paraphrases. It is a conservative automatic guard, not proof of semantic equivalence or a substitute for human review. No external model is used for verification. Every draft still needs review before submission; applications are never submitted automatically.

## Validation without credits

Dispatch `monitor.yml` with `validate_only=true` to test discovery, encryption, artifact restoration and checkpointing while the ToHuman POST stage is skipped. The automated API tests use mocks only. No existing delivered letters should be submitted for a smoke test.
