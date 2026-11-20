"""RMS v0.9: offline-only official-text reference evidence prototype.

This module examines a *human-supplied transcription* of an official text.
It cannot authenticate source documents, determine legal applicability, or approve
links. Every result requires a human and remains HOLD; no file/network/RMS I/O.
"""
from __future__ import annotations

import re
from typing import Any

VERSION = "rms_v09_official_reference_prototype_v01"
LAW_TITLE = "プラスチックに係る資源循環の促進等に関する法律"
DECREE_TITLE = LAW_TITLE + "の施行期日を定める政令"

# Conservative, case-specific patterns only. Never infer from a document title.
DECREE_NUMBER = re.compile(r"政令第\s*二十四\s*号")
LAW_NUMBER = re.compile(r"令和\s*三\s*年\s*法律第\s*六十\s*号")
BASIS = re.compile(r"附則第\s*一\s*項")
DATE = re.compile(r"施行期日は[、，\s]*令和\s*四\s*年\s*四\s*月\s*一\s*日とする")
REFERENCE_CONTEXT = re.compile(re.escape(LAW_TITLE) + r"[（(]\s*令和\s*三\s*年\s*法律第\s*六十\s*号\s*[）)]")


def _hold(issues: list[str], evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "tool": VERSION,
        "status": "HOLD",
        "human_approval_required": True,
        "comparison_allowed": False,
        "notification_sent": False,
        "rms_modified": False,
        "legal_link_confirmed": False,
        "issues": issues,
        "evidence_candidate": evidence or {},
    }


def review_official_reference(
    text: str,
    *,
    source_type: str,
    source_date: str,
    source_issue: str,
    source_page: int,
    manually_verified_official_copy: bool = False,
) -> dict[str, Any]:
    """Locate case-specific explicit identifiers in a transcription.

    All fields are untrusted unless compared to an authentic official document
    by a human. Even a complete match is HOLD pending human approval.
    """
    if not isinstance(text, str) or not text.strip():
        return _hold(["SOURCE_TEXT_MISSING"])
    if not isinstance(source_type, str) or not isinstance(source_date, str) or not isinstance(source_issue, str):
        return _hold(["SOURCE_METADATA_INVALID"])
    if not isinstance(source_page, int) or isinstance(source_page, bool) or source_page < 1:
        return _hold(["SOURCE_PAGE_INVALID"])

    # Prevent deceptive partial matching due to arbitrary whitespace in long text.
    normalized = re.sub(r"\s+", "", text)
    checks = {
        "decree_number": bool(DECREE_NUMBER.search(normalized)),
        "decree_title": DECREE_TITLE in normalized,
        "law_number": bool(LAW_NUMBER.search(normalized)),
        "explicit_law_reference": bool(REFERENCE_CONTEXT.search(normalized)),
        "statutory_basis": bool(BASIS.search(normalized)),
        "effective_date": bool(DATE.search(normalized)),
    }
    issues = [f"EVIDENCE_{name.upper()}_MISSING" for name, found in checks.items() if not found]
    if source_type != "官報" or source_date != "2022-01-19" or source_issue != "号外第13号" or source_page != 5:
        issues.append("SOURCE_METADATA_UNVERIFIED_OR_UNEXPECTED")
    if not manually_verified_official_copy:
        issues.append("OFFICIAL_COPY_NOT_HUMAN_VERIFIED")
    # Even when all gates pass, the program cannot authenticate legality.
    issues.append("LEGAL_LINK_REQUIRES_HUMAN_APPROVAL")
    evidence = {
        "source_type": source_type,
        "source_date": source_date,
        "source_issue": source_issue,
        "source_page": source_page,
        "matches": checks,
        "source_verified_by_human_assertion_only": bool(manually_verified_official_copy),
        "proposed_law": "令和3年法律第60号" if checks["explicit_law_reference"] else None,
        "proposed_decree": "令和4年政令第24号" if checks["decree_number"] else None,
        "proposed_effective_date": "2022-04-01" if checks["effective_date"] else None,
        "note": "Candidate transcription only; verify original kanpo before decision.",
    }
    return _hold(issues, evidence)
