"""RMS v0.9 experimental offline document-relation bridge.

This is a *candidate-only*, fail-closed adapter. It never confirms legal
relationships, checks authentic sources, sends notifications, or writes RMS data.
No imports of, or changes to, earlier RMS prototypes are required.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import re

VERSION = 'rms_v09_legal_relation_bridge_prototype_v01'
KINDS = frozenset({'NEW_ENACTMENT', 'AMENDMENT', 'EFFECTIVE_DATE_DECREE', 'EFFECTIVE_DATE_AMENDMENT'})
RELATIONS = frozenset({'SETS_EFFECTIVE_DATE_FOR', 'AMENDS', 'CHANGES_EFFECTIVE_DATE_FOR'})
DOC_NUMBER = re.compile(r'^\d{4}-(LAW|DECREE)-\d+$')
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


@dataclass(frozen=True)
class DocumentEvidence:
    document_id: str
    document_kind: str
    official_url: str
    source_label: str
    human_source_checked: bool


def _hold(*issues: str, candidate: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        'tool': VERSION,
        'status': 'HOLD',
        'legal_link_confirmed': False,
        'human_approval_required': True,
        'comparison_allowed': False,
        'notification_sent': False,
        'rms_modified': False,
        'issues': sorted(set(issues)),
        'relation_candidate': dict(candidate) if candidate else None,
    }


def review_relation(
    *,
    source: DocumentEvidence,
    target: DocumentEvidence,
    relation_kind: str,
    explicit_reference_human_checked: bool,
    official_reference_text: str,
    effective_date: str | None = None,
    source_page: int | None = None,
) -> dict[str, Any]:
    """Return a *non-approved* document-relation candidate, or HOLD without one.

    Caller supplies human-reviewed evidence assertions. The routine cannot
    verify URLs, official text, or statutory effect; it only checks structure.
    """
    if not isinstance(source, DocumentEvidence) or not isinstance(target, DocumentEvidence):
        return _hold('DOCUMENT_EVIDENCE_OBJECT_REQUIRED')
    issues: list[str] = []
    for label, doc in (('SOURCE', source), ('TARGET', target)):
        if not isinstance(doc.document_id, str) or not DOC_NUMBER.fullmatch(doc.document_id):
            issues.append(f'{label}_DOCUMENT_ID_INVALID')
        if doc.document_kind not in KINDS:
            issues.append(f'{label}_KIND_INVALID')
        if not isinstance(doc.official_url, str) or not doc.official_url.startswith('https://'):
            issues.append(f'{label}_OFFICIAL_URL_INVALID')
        if not isinstance(doc.source_label, str) or not doc.source_label.strip():
            issues.append(f'{label}_SOURCE_LABEL_MISSING')
        if doc.human_source_checked is not True:
            issues.append(f'{label}_HUMAN_SOURCE_CHECK_MISSING')
    if relation_kind not in RELATIONS:
        issues.append('RELATION_KIND_UNRECOGNIZED')
    elif relation_kind == 'SETS_EFFECTIVE_DATE_FOR' and not (
        source.document_kind == 'EFFECTIVE_DATE_DECREE' and target.document_kind == 'NEW_ENACTMENT'
    ):
        issues.append('RELATION_DOCUMENT_KINDS_MISMATCH')
    elif relation_kind == 'AMENDS' and source.document_kind != 'AMENDMENT':
        issues.append('RELATION_DOCUMENT_KINDS_MISMATCH')
    elif relation_kind == 'CHANGES_EFFECTIVE_DATE_FOR' and source.document_kind != 'EFFECTIVE_DATE_AMENDMENT':
        issues.append('RELATION_DOCUMENT_KINDS_MISMATCH')
    if source.document_id == target.document_id:
        issues.append('SELF_REFERENCE_FORBIDDEN')
    if explicit_reference_human_checked is not True:
        issues.append('EXPLICIT_REFERENCE_NOT_HUMAN_CHECKED')
    if not isinstance(official_reference_text, str) or not official_reference_text.strip():
        issues.append('OFFICIAL_REFERENCE_TEXT_MISSING')
    if source_page is None or type(source_page) is not int or source_page < 1:
        issues.append('SOURCE_PAGE_INVALID')
    if relation_kind in ('SETS_EFFECTIVE_DATE_FOR', 'CHANGES_EFFECTIVE_DATE_FOR'):
        if not isinstance(effective_date, str) or not DATE.fullmatch(effective_date):
            issues.append('EFFECTIVE_DATE_FORMAT_INVALID')
        else:
            from datetime import date
            try:
                date.fromisoformat(effective_date)
            except ValueError:
                issues.append('EFFECTIVE_DATE_INVALID')
    if issues:
        return _hold(*issues)
    candidate = {
        'source_document_id': source.document_id,
        'source_document_kind': source.document_kind,
        'target_document_id': target.document_id,
        'target_document_kind': target.document_kind,
        'relation_kind': relation_kind,
        'effective_date': effective_date,
        'source_page': source_page,
        'reference_text_supplied': True,
        'evidence_assertion_only': True,
    }
    return _hold('LEGAL_RELATION_REQUIRES_AUTHORIZED_HUMAN_APPROVAL', candidate=candidate)
