"""RMS v0.9 offline, candidate-only official reference to legal relation adapter.

No network, filesystem, notifications, RMS writes, or imports from earlier prototypes.
All supplied evidence is an untrusted assertion. Never authenticate legal facts.
"""
from __future__ import annotations

from datetime import date
import re
from typing import Any, Mapping

VERSION = 'rms_v09_reference_bridge_adapter_prototype_v01'
_JP_ID = re.compile(r'^(令和|平成|昭和)(元|[1-9][0-9]*)年(法律|政令)第([1-9][0-9]*)号$')
_INTERNAL_ID = re.compile(r'^(\d{4})-(LAW|DECREE)-([1-9][0-9]*)$')
_ERA_START = {'令和': 2019, '平成': 1989, '昭和': 1926}
_KINDS = {'LAW': 'NEW_ENACTMENT', 'DECREE': 'EFFECTIVE_DATE_DECREE'}
_EXPECTED_CHECKS = ('decree_number', 'decree_title', 'law_number', 'explicit_law_reference', 'statutory_basis', 'effective_date')


def _hold(*issues: str, candidate: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        'tool': VERSION, 'status': 'HOLD', 'human_approval_required': True,
        'legal_link_confirmed': False, 'comparison_allowed': False,
        'notification_sent': False, 'rms_modified': False,
        'issues': sorted(set(issues)),
        'relation_candidate': dict(candidate) if candidate is not None else None,
    }


def normalize_document_number(value: Any) -> dict[str, Any]:
    """Convert only fully matched Japanese statute/decree numbers, never free text."""
    if not isinstance(value, str):
        return {'status': 'HOLD', 'issues': ['DOCUMENT_NUMBER_NOT_TEXT']}
    m = _JP_ID.fullmatch(value)
    if not m:
        return {'status': 'HOLD', 'issues': ['DOCUMENT_NUMBER_FORMAT_INVALID']}
    era, era_year, jp_kind, serial = m.groups()
    n = 1 if era_year == '元' else int(era_year)
    year = _ERA_START[era] + n - 1
    # Restrict to era boundaries; historical conversion is not authenticity verification.
    if (era == '令和' and year < 2019) or (era == '平成' and not 1989 <= year <= 2019) or (era == '昭和' and not 1926 <= year <= 1989):
        return {'status': 'HOLD', 'issues': ['ERA_YEAR_INVALID']}
    kind = 'LAW' if jp_kind == '法律' else 'DECREE'
    internal = f'{year:04d}-{kind}-{int(serial)}'
    if not _INTERNAL_ID.fullmatch(internal):
        return {'status': 'HOLD', 'issues': ['INTERNAL_NUMBER_INVALID']}
    return {'status': 'CANDIDATE_ONLY', 'internal_id': internal, 'kind': kind,
            'original': value, 'human_approval_required': True}


def review_bridge(
    official_result: Any,
    *,
    source_official_url: Any = None,
    target_official_url: Any = None,
    official_reference_text: Any = None,
    manually_verified_official_copy: bool = False,
    source_human_checked: bool = False,
    target_human_checked: bool = False,
    explicit_reference_human_checked: bool = False,
    source_document_kind: Any = None,
    target_document_kind: Any = None,
) -> dict[str, Any]:
    """Return a HOLD candidate only with consistent explicitly supplied evidence.

    No bridge approval or legal-effect conclusion. Input must be the unmodified
    output shape of rms_v09_official_reference_prototype.review_official_reference.
    """
    if not isinstance(official_result, Mapping):
        return _hold('OFFICIAL_RESULT_INVALID')
    issues: list[str] = []
    if official_result.get('status') != 'HOLD' or official_result.get('legal_link_confirmed') is not False:
        issues.append('OFFICIAL_RESULT_STATUS_UNEXPECTED')
    if any(official_result.get(k) is not False for k in ('comparison_allowed', 'notification_sent', 'rms_modified')):
        issues.append('OFFICIAL_RESULT_SAFETY_FLAGS_UNEXPECTED')
    evidence = official_result.get('evidence_candidate')
    if not isinstance(evidence, Mapping):
        return _hold(*(issues + ['EVIDENCE_CANDIDATE_MISSING']))
    if evidence.get('source_type') != '官報' or evidence.get('source_date') != '2022-01-19' or evidence.get('source_issue') != '号外第13号' or evidence.get('source_page') != 5:
        issues.append('OFFICIAL_SOURCE_METADATA_UNEXPECTED')
    checks = evidence.get('matches')
    if not isinstance(checks, Mapping) or any(checks.get(k) is not True for k in _EXPECTED_CHECKS):
        issues.append('OFFICIAL_TEXT_MATCHES_INCOMPLETE')
    if not all((manually_verified_official_copy is True,
                source_human_checked is True, target_human_checked is True,
                explicit_reference_human_checked is True)):
        issues.append('HUMAN_VERIFICATION_INCOMPLETE')
    if evidence.get('source_verified_by_human_assertion_only') is not True:
        issues.append('OFFICIAL_COPY_ATTESTATION_MISSING')
    if source_document_kind != 'EFFECTIVE_DATE_DECREE' or target_document_kind != 'NEW_ENACTMENT':
        issues.append('DOCUMENT_KIND_MISMATCH')
    for key, value in (('SOURCE', source_official_url), ('TARGET', target_official_url)):
        if not isinstance(value, str) or not value.startswith('https://') or len(value) <= len('https://'):
            issues.append(f'{key}_URL_INVALID')
    source = normalize_document_number(evidence.get('proposed_decree'))
    target = normalize_document_number(evidence.get('proposed_law'))
    if source['status'] != 'CANDIDATE_ONLY':
        issues.append('SOURCE_NUMBER_UNCONVERTIBLE')
    if target['status'] != 'CANDIDATE_ONLY':
        issues.append('TARGET_NUMBER_UNCONVERTIBLE')
    if isinstance(official_reference_text, str) and official_reference_text.strip() and target['status'] == 'CANDIDATE_ONLY':
        # Require exact Japanese identifier, with boundary after the number.
        pattern = re.escape(target['original']) + r'(?![0-9０-９])'
        if not re.search(pattern, official_reference_text):
            issues.append('TARGET_NUMBER_NOT_IN_REFERENCE_TEXT')
    else:
        issues.append('OFFICIAL_REFERENCE_TEXT_MISSING')
    raw_date = evidence.get('proposed_effective_date')
    try:
        if not isinstance(raw_date, str) or date.fromisoformat(raw_date).isoformat() != raw_date:
            raise ValueError
    except ValueError:
        issues.append('EFFECTIVE_DATE_INVALID')
    if issues:
        return _hold(*issues)
    candidate = {
        'source_document_id': source['internal_id'],
        'source_original_number': source['original'],
        'source_document_kind': source_document_kind,
        'source_official_url_asserted': source_official_url,
        'target_document_id': target['internal_id'],
        'target_original_number': target['original'],
        'target_document_kind': target_document_kind,
        'target_official_url_asserted': target_official_url,
        'relation_kind': 'SETS_EFFECTIVE_DATE_FOR',
        'effective_date': raw_date,
        'source_label': '官報 2022-01-19 号外第13号 5ページ',
        'source_page': 5,
        'reference_text_supplied': True,
        'evidence_assertion_only': True,
    }
    return _hold('LEGAL_RELATION_REQUIRES_AUTHORIZED_HUMAN_APPROVAL', candidate=candidate)
