"""python -m resume.process extract resume.pdf; review draft, then approve."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def extract_profile(text):
    from matching import SKILLS, contains
    sections = {'education': [], 'skills': [], 'certifications': [], 'projects': [], 'experience': [], 'accomplishments': []}
    current = None
    for line in text.splitlines():
        line = line.strip()
        heading = re.sub(r'[^a-z ]', '', line.lower()).strip()
        aliases = {'technical skills': 'skills', 'work experience': 'experience', 'professional experience': 'experience',
                   'academic projects': 'projects', 'awards': 'accomplishments', 'certificates': 'certifications'}
        heading = aliases.get(heading, heading)
        if heading in sections:
            current = heading
        elif current and line:
            sections[current].append(line)
    evidence = [{'label': section, 'detail': line, 'keywords': [s for s in SKILLS if contains(line, s)]}
                for section in ('projects', 'experience', 'accomplishments') for line in sections[section]]
    return {'approved': False, 'education': ' '.join(sections['education']),
            'skills': [s for s in SKILLS if contains(' '.join(sections['skills']), s)],
            'certifications': sections['certifications'], 'evidence': evidence,
            'extracted_sections': sections,
            'review_notes': 'Review every field. PDF extraction is heuristic. Keep pending certifications labeled; rewrite evidence in your own first person. Add name, locations and graduation_year if desired.'}


def digest(profile):
    data = {k: v for k, v in profile.items() if k not in ('approved', 'approval_sha256')}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def validate_approval(profile):
    if not profile.get('approved') or profile.get('approval_sha256') != digest(profile):
        raise ValueError('Candidate profile must be reviewed and approved again after edits')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['extract', 'approve', 'export'])
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'extract':
        from pypdf import PdfReader
        text = '\n'.join(page.extract_text() or '' for page in PdfReader(args.input).pages)
        if not text.strip():
            parser.error('No selectable text found. OCR the PDF locally before importing.')
        profile = extract_profile(text)
        target = args.output or Path('private/profile.draft.json')
    else:
        profile = json.loads(args.input.read_text(encoding='utf-8'))
        if args.action == 'approve':
            if not profile.get('education') or not profile.get('evidence'):
                parser.error('Education and at least one verified evidence entry are required')
            profile['approved'] = True
            profile['approval_sha256'] = digest(profile)
            target = args.output or Path('private/profile.approved.json')
        else:
            validate_approval(profile)
            # Export a small payload suitable for gh secret set --body-file via stdin.
            print(json.dumps(profile, separators=(',', ':')))
            return
    if not target.resolve().is_relative_to(Path('private').resolve()):
        parser.error('Profile output must stay inside the ignored private/ directory')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(profile, indent=2) + '\n', encoding='utf-8')
    print(f'Saved locally: {target}')


if __name__ == '__main__':
    main()
