"""RMS Monitor v0.9: OFFLINE-ONLY experimental legal amendment identity review.

Pure in-memory functions. No network, disk I/O, notifications, or RMS edits.
Evidence is a human-reviewed assertion, NOT a machine determination of legal facts.
A later effective-date instrument may be linked only when its explicit official
source reference to an amendment is human confirmed. All results require review.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional, Sequence, Tuple
import hashlib
import json
import re

VERSION = "rms_v09_case_identity_prototype_v01"
_DOC_RE = re.compile(r"^[A-Za-z0-9_./:-]{3,120}$")


@dataclass(frozen=True)
class Amendment:
    law_name: str
    amendment_document_id: str  # official promulgation / notification identifier
    promulgation_date: str
    official_url: str
    human_reviewed: bool
    formally_decided: bool
    amendment_scope: str  # description; not a machine-extracted identity key


@dataclass(frozen=True)
class EffectiveDateEvidence:
    source_document_id: str  # later decree etc. can have its OWN number
    official_url: str
    human_reviewed: bool
    amendment_document_id_referenced: str  # must explicitly link to amendment
    reference_confirmed_in_official_text: bool
    provision_key: str  # explicit clause / applicability segment identifier
    effective_date: str
    effective_date_confirmed: bool


def _valid_date(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _valid_doc(value: Any) -> bool:
    return isinstance(value, str) and bool(_DOC_RE.fullmatch(value))


def _valid_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("https://") and len(value) > 12


def _hold(*issues: str) -> Dict[str, Any]:
    return {
        "tool": VERSION,
        "status": "HOLD",
        "comparison_allowed": False,
        "notification_sent": False,
        "rms_modified": False,
        "human_approval_required": True,
        "case_key": None,
        "proposed_changes": [],
        "issues": list(issues),
    }


def make_case_key(amendment: Amendment) -> Dict[str, Any]:
    """Assign candidate key from reviewed amendment instrument, not law name/date alone."""
    if not isinstance(amendment, Amendment):
        return _hold("AMENDMENT_OBJECT_REQUIRED")
    issues = []
    if not amendment.human_reviewed or not amendment.formally_decided:
        issues.append("FORMAL_DECISION_NOT_HUMAN_CONFIRMED")
    if not _valid_doc(amendment.amendment_document_id):
        issues.append("AMENDMENT_DOCUMENT_ID_INVALID")
    if not _valid_date(amendment.promulgation_date):
        issues.append("PROMULGATION_DATE_INVALID")
    if not _valid_url(amendment.official_url):
        issues.append("OFFICIAL_URL_INVALID")
    if not isinstance(amendment.law_name, str) or not amendment.law_name.strip():
        issues.append("LAW_NAME_MISSING")
    if not isinstance(amendment.amendment_scope, str) or not amendment.amendment_scope.strip():
        issues.append("AMENDMENT_SCOPE_MISSING")
    if issues:
        return _hold(*issues)
    # Scope and date retained as evidence, not silently coalesced by law name.
    raw = json.dumps([amendment.amendment_document_id, amendment.promulgation_date], ensure_ascii=False)
    key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return {
        "tool": VERSION,
        "status": "REVIEW_REQUIRED",
        "comparison_allowed": False,
        "notification_sent": False,
        "rms_modified": False,
        "human_approval_required": True,
        "case_key": key,
        "proposed_changes": [],
        "issues": [],
        "source_document_id": amendment.amendment_document_id,
        "official_url": amendment.official_url,
    }


def review_effective_date_updates(
    *,
    amendment: Amendment,
    evidence: Sequence[EffectiveDateEvidence],
    previous_segments: Optional[Dict[str, str]],
    previous_case_document_id: Optional[str],
) -> Dict[str, Any]:
    """Review date segments without automatically merging, saving or notifying.

    previous_segments is a fully confirmed snapshot mapping provision key -> ISO date.
    The empty dict means confirmed no dates yet; None means unknown and MUST HOLD.
    An omitted previously known segment is considered a conflict, never a deletion.
    """
    identity = make_case_key(amendment)
    if identity["status"] == "HOLD":
        return identity
    if previous_segments is None or previous_case_document_id is None:
        return _hold("PREVIOUS_CASE_STATE_UNKNOWN")
    if previous_case_document_id != amendment.amendment_document_id:
        return _hold("PREVIOUS_CASE_IDENTITY_MISMATCH")
    if not isinstance(previous_segments, dict) or any(
        not isinstance(k, str) or not k.strip() or not _valid_date(v)
        for k, v in previous_segments.items()
    ):
        return _hold("PREVIOUS_SEGMENTS_INVALID")
    if not isinstance(evidence, (list, tuple)):
        return _hold("EVIDENCE_SEQUENCE_INVALID")
    if not evidence:
        return _hold("NO_NEW_EVIDENCE")
    issues = []
    current: Dict[str, str] = {}
    seen_sources = set()
    for item in evidence:
        if not isinstance(item, EffectiveDateEvidence):
            issues.append("EVIDENCE_OBJECT_INVALID")
            continue
        if not item.human_reviewed or not item.reference_confirmed_in_official_text:
            issues.append("EXPLICIT_LINK_NOT_HUMAN_CONFIRMED")
        if item.amendment_document_id_referenced != amendment.amendment_document_id:
            issues.append("TARGET_AMENDMENT_MISMATCH")
        if not _valid_doc(item.source_document_id) or not _valid_url(item.official_url):
            issues.append("SOURCE_REFERENCE_INVALID")
        if not item.effective_date_confirmed or not _valid_date(item.effective_date):
            issues.append("EFFECTIVE_DATE_NOT_CONFIRMED")
        if not isinstance(item.provision_key, str) or not item.provision_key.strip():
            issues.append("PROVISION_KEY_MISSING")
            continue
        source_key = (item.source_document_id, item.provision_key, item.effective_date)
        if source_key in seen_sources:
            continue  # exact duplicate evidence, no new event
        seen_sources.add(source_key)
        if item.provision_key in current and current[item.provision_key] != item.effective_date:
            issues.append("CONFLICTING_EFFECTIVE_DATES_FOR_PROVISION")
        current[item.provision_key] = item.effective_date
    if issues:
        return _hold(*sorted(set(issues)))
    # This input must be a full current snapshot for tracked provisions; refuse losses.
    if set(previous_segments) - set(current):
        return _hold("PREVIOUS_PROVISION_MISSING_FROM_CURRENT_SNAPSHOT")
    changes = []
    for provision, new_date in sorted(current.items()):
        old_date = previous_segments.get(provision)
        if old_date == new_date:
            continue
        changes.append({
            "provision_key": provision,
            "kind": "EFFECTIVE_DATE_CONFIRMED" if old_date is None else "EFFECTIVE_DATE_CHANGED",
            "previous_date": old_date,
            "effective_date": new_date,
            "human_approval_required": True,
        })
    identity["proposed_changes"] = changes
    identity["status"] = "REVIEW_REQUIRED" if changes else "NO_CHANGE_REVIEWED"
    return identity
