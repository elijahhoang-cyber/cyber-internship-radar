"""Verify candidate boards live; only successful, nonempty public APIs are enabled."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import requests

# Candidates are hypotheses, not verified configuration. Re-run to refresh evidence.
GREENHOUSE = '''cloudflare crowdstrike sentinelone paloaltonetworks zscaler okta auth0 tenable rapid7 qualys
rubrik netskope wiz snyk lacework arcticwolf dragos recordedfuture threatlocker huntress
abnormalsecurity materialsecurity saltsecurity orcasecurity island chainguard socket contrastsecurity
veracode sonatype blackduck hackerone bugcrowd cobaltio synack pentera axonius torq tines
expel redcanary binarydefense deepwatch reliaquest vectra extrahop darktrace fortinet
datadog mongodb elastic confluent hashicorp grafanalabs cockroachlabs yugabyte redis neo4j
snowflake databricks dbtlabs fivetran airbyte amplitude mixpanel segment twilio stripe plaid
affirm brex chime coinbase robinhood block square rippling gusto ramp deel remote
asana airtable notion figma canva dropbox box slack discord reddit pinterest lyft doordash
instacart airbnb flexport faire verkada samsara motive anduril palantir spacex rocketlab
relativity relativityspace astranis planet capellaspace zipline skydio shieldai scaleai openai
anthropic huggingface cohere togetherai perplexity character runway modal replicate coreweave
vanta drata secureframe trustcloud auditboard onetrust bigid immuta cyera sentra
sailpoint saviynt cyberark beyondtrust delinea teleport strongdm keepersecurity 1password
bitwarden dashlane lastpass proton nordsecurity tailscale ngrok netlify vercel retool
launchdarkly harness circleci gitlab github buildkite docker postman sentry sourcegraph
duolingo roblox unity epicgames niantic twitch spotify soundcloud grammarly coursera
udemy brilliant khanacademy handshake wayup newrelic pagerduty sumologic splunk
akamai fastly digitalocean linode vultr upstart sofi addepar betterment wealthfront
toast hubspot klaviyo braze iterable intercom zendesk freshworks calendly zoominfo
appliedintuition aurora nuro waabi zoox rivian lucidmotors tesla cribl
arcesium clearstreet point72 janestreet hudsonrivertrading citadel jumptrading imc optiver'''.split()
LEVER = '''1password wealthfront palantir zoox shieldai nuro netskope insomniac databricks
plaid scaleai spotify veeva lifeatcanva quantumscape stackadapt lever knowbe4
illumio druva cohesity alertenterprise recordedfuture arcticwolf oowlish wyetech'''.split()
ASHBY = '''OpenAI anthropic ramp notion linear replit cursor vanta drata mercury
cohere perplexity together modal sentra cyera chainguard tines elevenlabs
wiz decagon harvey cognition retool vercel supabase railway huggingface'''.split()


def check(candidate):
    source, board = candidate
    url = {'greenhouse': f'https://boards-api.greenhouse.io/v1/boards/{board}/jobs',
           'lever': f'https://api.lever.co/v0/postings/{board}?mode=json&limit=1',
           'ashby': f'https://api.ashbyhq.com/posting-api/job-board/{board}'}[source]
    try:
        r = requests.get(url, timeout=(5, 15), headers={'User-Agent': 'CyberInternshipRadar board verification'})
        r.raise_for_status()
        data = r.json()
        jobs = data if source == 'lever' else data['jobs']
        if not isinstance(jobs, list) or not jobs:
            return None
        # Public board display identity can be reviewed alongside the API evidence.
        name = board
        if source == 'greenhouse':
            try:
                meta = requests.get(f'https://boards-api.greenhouse.io/v1/boards/{board}', timeout=(5, 10))
                if meta.ok:
                    name = meta.json().get('name') or board
            except requests.RequestException:
                pass
        return {'source': source, 'company': name, 'board': board,
                'verified_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'verification_url': url, 'observed_jobs': len(jobs)}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='config/companies.verified.json')
    args = parser.parse_args()
    candidates = [(s, b) for s, boards in [('greenhouse', GREENHOUSE), ('lever', LEVER), ('ashby', ASHBY)] for b in boards]
    with ThreadPoolExecutor(max_workers=8) as pool:
        verified = [r for r in pool.map(check, candidates) if r]
    # One board per employer, avoiding migration duplicates.
    unique = {}
    for entry in verified:
        unique.setdefault(entry['board'].lower(), entry)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({'seconds_between_boards': 0.2, 'letter_min_score': 80,
                                  'boards': list(unique.values())}, indent=2) + '\n', encoding='utf-8')
    print(f'{len(unique)} live verified employer boards saved to {output}')


if __name__ == '__main__':
    main()
