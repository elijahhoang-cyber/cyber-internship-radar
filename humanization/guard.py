"""Conservative factual guard, not a semantic-equivalence or detector guarantee.

Qualification sentences must remain verbatim apart from case/spacing. Changes to
facts, new claims, numbers, negations or technical credentials fail closed.
"""
from collections import Counter
import re


def normalize(text):
    return re.sub(r'\s+', ' ', text).strip().casefold().rstrip('.')


def sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z])|\n\s*\n', text) if s.strip()]


def sanitize(letter, name=''):
    # Sign-off identity is restored locally, never sent to ToHuman.
    body = re.split(r'\n\s*Sincerely,?\s*\n', letter, flags=re.I)[0]
    if name:
        body = re.sub(re.escape(name), '', body, flags=re.I)
    body = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '', body)
    body = re.sub(r'https?://\S+|www\.\S+', '', body)
    body = re.sub(r'(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}(?!\d)', '', body)
    return body.strip()


def verify(original, rewritten, facts, company, title):
    if not isinstance(rewritten, str) or normalize(original) == normalize(rewritten):
        return False
    if sanitize(rewritten) != rewritten.strip() or re.search(r'(?:^|\n)\s*(?:Sincerely|Regards|Best(?: regards)?|Yours truly|Cheers)\s*,?\s*(?:\n|$)', rewritten, re.I):
        return False  # No newly invented identity, contact line or signature.
    if not all(normalize(v) in normalize(rewritten) for v in (company, title)):
        return False
    output_sentences = {normalize(s) for s in sentences(rewritten)}
    if any(normalize(s) not in output_sentences for f in facts for s in sentences(f)):
        return False
    if Counter(re.findall(r'\b\d+(?:[.,/]\d+)*(?:%)?', original)) != Counter(re.findall(r'\b\d+(?:[.,/]\d+)*(?:%)?', rewritten)):
        return False
    critical = r"\b(?:not|never|cannot|can't|don't|unable|lack|lacking|without|no|yet|scheduled|pursuing|earned|certified|certification|citizen|clearance|production)\b"
    if Counter(re.findall(critical, original.lower())) != Counter(re.findall(critical, rewritten.lower())):
        return False
    old_sentences = {normalize(s) for s in sentences(original)}
    claim = re.compile(r"\b(?:I (?:have|am|was|earned|led|managed|built|developed|worked|completed|possess|hold|specialize)|I'm (?:certified|experienced|pursuing)|my (?:experience|background|qualifications|degree|doctorate)|years? of experience|expertise|proficient|certified|graduated|deployed|investigated)\b", re.I)
    for sentence in sentences(rewritten):
        if claim.search(sentence) and normalize(sentence) not in old_sentences:
            return False
        if (re.match(r"(?:I\b|I'm\b|I've\b|My\b|As a\b|With my\b)", sentence, re.I)
                and normalize(sentence) not in old_sentences
                and not re.match(r"I(?:'d\b| would\b| want\b| hope\b| look\b| aim\b| plan\b|(?:'m| am) (?:interested|applying|eager|keen|looking)\b)", sentence, re.I)):
            return False
    from matching import SKILLS, contains
    if any(contains(rewritten, skill) and not contains(original, skill) for skill in SKILLS):
        return False
    return True
