#!/usr/bin/env python3
"""Preview a no-cost cover letter entirely on your machine (never in CI)."""
import argparse
import json
from pathlib import Path

from cover_letters import local_letter


def main() -> None:
    p = argparse.ArgumentParser(description='Preview a cover-letter draft locally')
    p.add_argument('--profile', default='private/profile.approved.json')
    p.add_argument('--company', required=True)
    p.add_argument('--title', required=True)
    p.add_argument('--description', default='')
    p.add_argument('--output', default='letters/cover_letter_preview.txt')
    args = p.parse_args()
    profile = json.loads(Path(args.profile).read_text(encoding='utf-8'))
    from resume.process import validate_approval
    validate_approval(profile)
    letter = local_letter({'company': args.company, 'title': args.title, 'description': args.description}, profile)
    if args.output:
        target = Path(args.output).resolve()
        if not any(target.is_relative_to(Path(root).resolve()) for root in ('private', 'letters')):
            p.error('Generated letters must stay inside private/ or letters/')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(letter + '\n', encoding='utf-8')
        print('Saved private draft to:', args.output)
    else:
        print(letter)


if __name__ == '__main__':
    main()
