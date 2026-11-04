"""Explainable ranking; unknown candidate qualifications never count as matches."""
import re

SKILLS = ('python', 'linux', 'windows', 'sql', 'splunk', 'siem', 'wireshark', 'aws', 'azure',
          'networking', 'incident response', 'penetration testing', 'vulnerability management',
          'iam', 'grc', 'security+', 'cissp', 'javascript', 'powershell', 'digital forensics',
          'bash', 'hardware security', 'firmware', 'bmcs', 'tpms', 'secure boot',
          'remote attestation', 'confidential computing', 'computer architecture', 'embedded systems')


def contains(text, term):
    return bool(re.search(r'(?<!\w)' + re.escape(term) + r'(?!\w)', text, re.I))


def rank(job, profile=None):
    from tracker import score_job
    relevance = score_job(job)
    if not relevance:
        return {'score': 0, 'category': 'Low priority', 'matched': [], 'missing': [], 'unknown': ['Not a relevant student role']}
    text = (job.get('title', '') + ' ' + job.get('description', '')).lower()
    earned_certs = [c for c in (profile or {}).get('certifications', [])
                    if not re.search(r'pursu|in[ -]?progress|studying|planned|expected|candidate|scheduled|prepar', c, re.I)]
    facts = ' '.join([str((profile or {}).get('education', ''))] +
                     list((profile or {}).get('skills', [])) + earned_certs +
                     [e['detail'] for e in (profile or {}).get('evidence', [])]).lower()
    requested = [s for s in SKILLS if contains(text, s)]
    aliases = {'networking': ('tcp/ip', 'network analysis', 'network telemetry'), 'siem': ('splunk',)}
    matched = [s for s in requested if contains(facts, s) or any(contains(facts, alias) for alias in aliases.get(s, ()))]
    # "languages such as Python, JavaScript, or similar" is an alternatives list.
    # A satisfied alternative is not evidence that the candidate knows the others.
    for group in re.findall(r'(?:such as|for example)\s+([^.!?]{1,180})', text):
        options = [s for s in requested if contains(group, s)]
        if re.search(r'\bor\b', group) and any(s in matched for s in options):
            requested = [s for s in requested if s not in options or s in matched]
    missing = [s for s in requested if s not in matched]
    # 60 points for relevance + student role; 40 depend on actual candidate evidence.
    score = 60 if relevance >= 75 else 45
    unknown = []
    if '2027' in text and ('summer' in text or 'co-op' in text):
        score += 5
    if profile:
        score += round(15 * len(matched) / len(requested)) if requested else 0
        evidence = [e for e in profile.get('evidence', []) if any(contains(text, str(k)) for k in e.get('keywords', []))]
        score += min(10, len(evidence) * 5)
        degree_required = re.search(r"bachelor|b\.s\.|undergraduate|university|college", text)
        if degree_required and re.search(r"bachelor|b\.s\.|university|college", profile.get('education', ''), re.I):
            score += 5
        prefs = profile.get('locations', [])
        if prefs and any(contains(job.get('location', ''), loc) for loc in prefs):
            score += 3
        elif prefs:
            unknown.append('Location/remote eligibility needs review')
        else:
            unknown.append('Location, relocation and remote eligibility have not been confirmed')
        if re.search(r'(?:us|u\.s\.)\s+security\s+clearance|(?:obtain|hold)\s+(?:a\s+)?(?:us\s+)?security\s+clearance', text):
            unknown.append('Security-clearance eligibility and willingness require review')
        if re.search(r'scholarship.for.service|\bSFS\b', text, re.I):
            unknown.append('Scholarship for Service program eligibility has not been confirmed')
        years = re.findall(r'(?:graduat\w*|class of)[^.!?]{0,50}?(20\d\d)', text)
        if years and str(profile.get('graduation_year', '')) in years:
            score += 2
        elif years:
            missing.append('Graduation year: ' + ', '.join(years))
    else:
        unknown.append('Candidate profile unavailable; score measures opportunity relevance only')
    if not job.get('description'):
        unknown.append('Description missing; qualifications require review')
    score = min(100, score)
    if profile and re.search(r'\bph\.?d\b', job.get('title', ''), re.I) and not re.search(r'ph\.?d|doctor', profile.get('education', ''), re.I):
        missing.append('PhD enrollment required by the role title')
        score = min(score, 59)
    category = next(label for threshold, label in ((90, 'Excellent match'), (80, 'Strong match'), (70, 'Good match'), (60, 'Possible match'), (0, 'Low priority')) if score >= threshold)
    return {'score': score, 'category': category, 'matched': matched, 'missing': missing, 'unknown': unknown}
