"""RMS v0.9: OFFLINE ONLY, experimental decision/effective-date notification planner.

Never fetches URLs, sends notices, writes files, or changes existing RMS data.
All results are advisory; human confirmation remains mandatory.
The only legal evidence accepted is explicitly reviewed, source-referenced input.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence
import hashlib
import json

PROTOTYPE_VERSION = "rms_v09_decision_notice_prototype_v01"


@dataclass(frozen=True)
class ConfirmedEvidence:
    """A human-reviewed primary-source determination, NOT inferred from a title."""

    official_source_url: str
    source_document_id: str
    reviewed_by_human: bool
    formally_decided: bool
    decision_date: str
    effective_date: Optional[str] = None
    effective_date_confirmed: bool = False
    withdrawn: bool = False


def _parse_date(value: Optional[str]) -> Optional[date]:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        result = date.fromisoformat(value)
    except ValueError:
        return None
    return result if result.isoformat() == value else None


def _evidence_issues(ev: ConfirmedEvidence) -> List[str]:
    issues: List[str] = []
    if not ev.reviewed_by_human:
        issues.append("NOT_HUMAN_REVIEWED")
    if not ev.official_source_url.startswith("https://") or not ev.source_document_id.strip():
        issues.append("PRIMARY_SOURCE_REFERENCE_INCOMPLETE")
    if not ev.formally_decided:
        issues.append("FORMAL_DECISION_NOT_CONFIRMED")
    if _parse_date(ev.decision_date) is None:
        issues.append("DECISION_DATE_INVALID_OR_MISSING")
    if ev.effective_date_confirmed and _parse_date(ev.effective_date) is None:
        issues.append("EFFECTIVE_DATE_UNVERIFIED")
    if ev.effective_date is not None and not ev.effective_date_confirmed:
        issues.append("EFFECTIVE_DATE_PRESENT_BUT_UNCONFIRMED")
    if ev.withdrawn:
        issues.append("WITHDRAWN_OR_CANCELLED_REQUIRES_MANUAL_REVIEW")
    return issues


def _event_id(case_id: str, kind: str, effective_date: Optional[str]) -> str:
    raw = json.dumps([case_id, kind, effective_date], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def plan_case(
    *,
    case_id: str,
    evidence: ConfirmedEvidence,
    previous_confirmed_effective_date: Optional[str] = None,
    initial_notice_recorded: bool = False,
    previously_notified_event_ids: Sequence[str] = (),
) -> Dict[str, Any]:
    """Plan suggested notifications from separately verified case state.

    Identifiers must be assigned to a specific legal amendment, not only a law name.
    Caller MUST validate continuity against original official documents. No message
    dispatch, persistence, RMS registration or legality determination happens here.

    To avoid missing delayed dates, caller supplies the last confirmed effective date
    (even when no notification was recorded). Unknown previous status -> HOLD.
    """
    base: Dict[str, Any] = {
        "tool": PROTOTYPE_VERSION,
        "case_id": case_id,
        "status": "HOLD",
        "comparison_allowed": False,
        "notification_sent": False,
        "rms_modified": False,
        "manual_approval_required": True,
        "suggested_events": [],
        "issues": [],
    }
    if not isinstance(case_id, str) or not case_id.strip():
        base["issues"].append("CASE_ID_REQUIRED")
        return base
    if not isinstance(evidence, ConfirmedEvidence):
        base["issues"].append("EVIDENCE_OBJECT_REQUIRED")
        return base
    base["issues"].extend(_evidence_issues(evidence))
    if previous_confirmed_effective_date is not None and _parse_date(previous_confirmed_effective_date) is None:
        base["issues"].append("PREVIOUS_EFFECTIVE_DATE_INVALID")
    if not isinstance(initial_notice_recorded, bool):
        base["issues"].append("INITIAL_NOTICE_STATUS_UNKNOWN")
    if not isinstance(previously_notified_event_ids, (list, tuple, set)) or not all(
        isinstance(x, str) for x in previously_notified_event_ids
    ):
        base["issues"].append("PREVIOUS_EVENT_IDS_INVALID")
    if base["issues"]:
        return base

    # Even with trusted evidence, this prototype ONLY suggests human-reviewed events.
    base["status"] = "REVIEW_REQUIRED"
    known = set(previously_notified_event_ids)
    current = evidence.effective_date if evidence.effective_date_confirmed else None
    def suggest(kind: str, when: Optional[str]) -> None:
        event_id = _event_id(case_id, kind, when)
        if event_id not in known:
            base["suggested_events"].append({
                "event_id": event_id,
                "kind": kind,
                "effective_date": when,
                "source_document_id": evidence.source_document_id,
                "official_source_url": evidence.official_source_url,
                "human_approval_required": True,
            })

    if not initial_notice_recorded:
        suggest("INITIAL_FORMAL_DECISION", current)
    else:
        if previous_confirmed_effective_date is None and current is not None:
            suggest("RENOTIFY_EFFECTIVE_DATE_CONFIRMED", current)
        elif previous_confirmed_effective_date is not None and current is None:
            base["issues"].append("DATE_DISAPPEARED_REQUIRES_MANUAL_REVIEW")
            base["status"] = "HOLD"
            base["suggested_events"] = []
        elif previous_confirmed_effective_date is not None and current != previous_confirmed_effective_date:
            suggest("RENOTIFY_EFFECTIVE_DATE_CHANGED", current)

    return base


def diagnostic_guard(source_diagnostic: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate upstream title/gap diagnostic flags; never treat titles as decisions."""
    issues = []
    if source_diagnostic.get("diagnostic_status") != "HOLD":
        issues.append("UPSTREAM_NOT_HOLD")
    if source_diagnostic.get("comparison_allowed") is not False:
        issues.append("UPSTREAM_COMPARISON_NOT_BLOCKED")
    if source_diagnostic.get("legal_amendment_confirmed") is not False:
        issues.append("UPSTREAM_LEGAL_CONFIRMATION_NOT_FALSE")
    if source_diagnostic.get("rms_modified") is not False:
        issues.append("UPSTREAM_RMS_MODIFICATION_NOT_FALSE")
    if source_diagnostic.get("network_accessed") is not False:
        issues.append("UPSTREAM_NETWORK_ACCESS_NOT_FALSE")
    if len(source_diagnostic.get("article_reviews", [])) != 114:
        issues.append("ARTICLE_REVIEW_COUNT_UNEXPECTED")
    return {
        "tool": PROTOTYPE_VERSION,
        "diagnostic_status": "HOLD",
        "comparison_allowed": False,
        "formal_decision_inferred": False,
        "notification_sent": False,
        "rms_modified": False,
        "upstream_issues": issues,
    }
