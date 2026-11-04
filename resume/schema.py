"""Shared application schema for draft and approved candidate profiles.

Validation errors name fields, never candidate values. Draft validation does not
approve a profile. Unknown extension fields remain supported by the existing API.
"""
import json


def validate_profile(profile, *, require_approval=False):
    if not isinstance(profile, dict):
        raise ValueError('Candidate profile must be an object')
    if not isinstance(profile.get('education'), str) or not profile['education'].strip():
        raise ValueError('education must be a nonempty string')
    if not isinstance(profile.get('evidence'), list) or not profile['evidence']:
        raise ValueError('evidence must be a nonempty list')
    for index, entry in enumerate(profile['evidence']):
        if not isinstance(entry, dict) or not isinstance(entry.get('detail'), str) or not entry['detail'].strip():
            raise ValueError(f'evidence[{index}].detail must be a nonempty string')
        if not isinstance(entry.get('keywords', []), list) or not all(isinstance(k, str) and k.strip() for k in entry.get('keywords', [])):
            raise ValueError(f'evidence[{index}].keywords must contain nonempty strings')
    for key in ('skills', 'certifications', 'locations', 'coursework', 'missing_information', 'programming_languages', 'cybersecurity_tools'):
        if key in profile and (not isinstance(profile[key], list) or not all(isinstance(v, str) for v in profile[key])):
            raise ValueError(f'{key} must be a list of strings')
    for key in ('name', 'education_statement'):
        if key in profile and not isinstance(profile[key], str):
            raise ValueError(f'{key} must be a string')
    if 'certification_details' in profile:
        details = profile['certification_details']
        if not isinstance(details, list):
            raise ValueError('certification_details must be a list')
        for index, entry in enumerate(details):
            if (not isinstance(entry, dict) or not isinstance(entry.get('name'), str)
                    or entry.get('status') not in ('earned', 'scheduled', 'in_progress', 'planned')
                    or type(entry.get('earned')) is not bool
                    or entry['earned'] != (entry['status'] == 'earned')):
                raise ValueError(f'certification_details[{index}] has inconsistent name/status/earned fields')
    if 'projects' in profile:
        projects = profile['projects']
        if not isinstance(projects, list) or not all(isinstance(p, dict) and isinstance(p.get('id'), str) for p in projects):
            raise ValueError('projects must contain objects with string IDs')
        project_ids = [p['id'] for p in projects]
        if len(project_ids) != len(set(project_ids)):
            raise ValueError('projects must have unique IDs')
        if any(e.get('project_id') and e['project_id'] not in project_ids for e in profile['evidence']):
            raise ValueError('evidence references a project ID missing from projects')
    if 'category_evidence' in profile:
        categories = profile['category_evidence']
        evidence_ids = {e.get('id') for e in profile['evidence']}
        if not isinstance(categories, dict):
            raise ValueError('category_evidence must be an object')
        for group in categories.values():
            if not isinstance(group, dict) or not isinstance(group.get('evidence_ids'), list) or any(v not in evidence_ids for v in group['evidence_ids']):
                raise ValueError('category_evidence references an unknown evidence ID')
    if 'graduation_year' in profile and (type(profile['graduation_year']) is not int or not 1900 <= profile['graduation_year'] <= 2100):
        raise ValueError('graduation_year must be a four-digit integer')
    if 'approved' in profile and type(profile['approved']) is not bool:
        raise ValueError('approved must be a boolean')
    for key in ('email', 'phone', 'address', 'postal_code', 'contact', 'contact_information'):
        if key in profile:
            raise ValueError(f'{key} is unnecessary for cloud processing; remove it from the candidate profile')
    if len(json.dumps(profile, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > 40000:
        raise ValueError('Candidate profile exceeds the private secret size budget')
    if require_approval:
        from resume.process import validate_approval
        validate_approval(profile)
    return profile
