"""Offline, case-specific, strict single-decree candidate prototype.

Only the reviewed synthetic transcription structure is supported. Unknown
layouts, extra text and ambiguous boundaries suppress all candidates.
No source authentication, file/network/RMS I/O or automatic approval.
"""
from __future__ import annotations
import re
from typing import Any

VERSION = "rms_v09_official_reference_prototype_v02"
LAW_TITLE = "プラスチックに係る資源循環の促進等に関する法律"
DECREE_TITLE = LAW_TITLE + "の施行期日を定める政令"
HEADER = "政令第二十四号"
BASIS_SENTENCE = (
    f"内閣は、{LAW_TITLE}（令和三年法律第六十号）"
    "附則第一項の規定に基づき、この政令を制定する。"
)
DATE_SENTENCE = f"{LAW_TITLE}の施行期日は、令和四年四月一日とする。"
DATE_TOKEN = re.compile(r"(?:明治|大正|昭和|平成|令和)[元〇零一二三四五六七八九十百0-9０-９]+年[〇零一二三四五六七八九十0-9０-９]+月[〇零一二三四五六七八九十0-9０-９]+日|[0-9０-９]{4}年[0-9０-９]{1,2}月[0-9０-９]{1,2}日")
DECREE_TOKEN = re.compile(r"政令第[ \t\u3000]*[〇零一二三四五六七八九十百千0-9０-９]+[ \t\u3000]*号")


def review_official_reference(text: str, *, source_type: str, source_date: str,
                              source_issue: str, source_page: int,
                              manually_verified_official_copy: bool = False) -> dict[str, Any]:
    issues = []
    evidence = {"proposed_law": None, "proposed_decree": None,
                "proposed_effective_date": None}
    result = {"tool": VERSION, "status": "HOLD", "human_approval_required": True,
              "comparison_allowed": False, "notification_sent": False,
              "rms_modified": False, "legal_link_confirmed": False,
              "issues": issues, "evidence_candidate": evidence}
    issues.append("LEGAL_LINK_REQUIRES_HUMAN_APPROVAL")
    if type(manually_verified_official_copy) is not bool:
        issues.append("SOURCE_VERIFICATION_FLAG_INVALID")
    if manually_verified_official_copy is not True:
        issues.append("OFFICIAL_COPY_NOT_HUMAN_VERIFIED")
    if (type(source_type) is not str or type(source_date) is not str
            or type(source_issue) is not str or type(source_page) is not int
            or source_page < 1):
        issues.append("SOURCE_METADATA_INVALID")
        return result
    if (source_type, source_date, source_issue, source_page) != ("官報", "2022-01-19", "号外第13号", 5):
        issues.append("SOURCE_METADATA_UNVERIFIED_OR_UNEXPECTED")
        return result
    if type(text) is not str or not text.strip():
        issues.append("SOURCE_TEXT_MISSING")
        return result
    if type(manually_verified_official_copy) is not bool:
        return result
    # Preserve line boundaries; never concatenate fragments across lines.
    lines = text.replace("\r\n", "\n").strip("\n").split("\n")
    lines = [line.strip(" \t\u3000") for line in lines]
    if len(DECREE_TOKEN.findall(text)) > 1:
        issues.append("MULTIPLE_DECREE_IDENTIFIERS")
    if len(DATE_TOKEN.findall(text)) > 1:
        issues.append("MULTIPLE_DATE_MENTIONS")
    if len(lines) != 4 or lines[0] != HEADER or lines[1] != DECREE_TITLE:
        issues.append("DOCUMENT_BOUNDARY_OR_LAYOUT_UNSUPPORTED")
    if len(lines) != 4 or lines[2] != BASIS_SENTENCE:
        issues.append("STATUTORY_BASIS_CONTEXT_UNSUPPORTED")
    if len(lines) != 4 or lines[3] != DATE_SENTENCE:
        issues.append("EFFECTIVE_DATE_CONTEXT_UNSUPPORTED")
    # Exact whole-block match is deliberately restrictive. Even a matching
    # transcription cannot establish its authenticity or actual provenance.
    if lines != [HEADER, DECREE_TITLE, BASIS_SENTENCE, DATE_SENTENCE]:
        return result
    evidence.update(proposed_law="令和3年法律第60号", proposed_decree="令和4年政令第24号",
                    proposed_effective_date="2022-04-01",
                    source_verified_by_human_assertion_only=manually_verified_official_copy,
                    note="Candidate transcription only; verify original kanpo before decision.")
    return result
