# Deploy Cyber Internship Radar

1. Run tests and verify private-file exclusion as described in README.
2. Authenticate with `gh auth login -h github.com`.
3. Use a new public repository named `cyber-internship-radar`. Never overwrite an existing repository. Push only reviewed, explicit source paths; do not use `git add -f`.
4. Allow Actions to write repository contents. The workflow requests `contents: write`; branch protection must allow the bot's state commits.
5. Set `DISCORD_WEBHOOK_URL` interactively: `gh secret set DISCORD_WEBHOOK_URL --repo OWNER/cyber-internship-radar`. Do not paste it into a command argument, source file, or chat.
6. External AI must stay disabled until the user explicitly approves. No resume/profile secret is required for discovery. Once locally reviewed, the approved profile can be passed as a GitHub Secret with the command in README, after user authorization for that upload.
7. Run `gh workflow run monitor.yml --repo OWNER/cyber-internship-radar`, then `gh run list --repo OWNER/cyber-internship-radar` and `gh run watch RUN_ID --repo OWNER/cyber-internship-radar --exit-status`.
8. Check that the baseline run commits public state, then dispatch again to verify history restoration and deduplication. Neither run sends existing baseline jobs.

The schedule is `2/5 * * * *` UTC. GitHub may delay or drop scheduled runs. Manual dispatch remains available. Alerts require a Discord webhook; letters additionally need an approved candidate profile and a strong match. A successful workflow without those secrets verifies discovery and persistence, not Discord delivery or personalized generation.

Public state contains public job data, scores, and delivery flags. Never add profiles, resume text, letter text, or contact information to it. Avoid workflow changes from untrusted branches accessing secrets. The testing workflow does not receive secrets.

A live notification check is available with `gh workflow run discord-check.yml --repo OWNER/cyber-internship-radar`. This explicitly sends two synthetic test notifications using the webhook secret, with no resume or AI access.

Federal monitoring is enabled. Configure `USAJOBS_API_KEY` and `USAJOBS_EMAIL` as repository secrets, then dispatch `federal-check.yml` for a live API and synthetic-candidate pipeline diagnostic. This workflow deliberately receives no personal resume/profile or AI key. Credentials stay in authenticated request headers and are never persisted in job state.
