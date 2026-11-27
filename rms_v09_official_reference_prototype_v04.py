"""Offline, case-specific, strict single-decree candidate prototype.

Only the reviewed synthetic case is supported. Limited punctuation-adjacent
spacing is allowed. Interior blank lines and controlled wraps require an
explicit human single-block assertion; unknown layouts suppress candidates.
Explicit number spellings are allowed only in known field contexts.
No source authentication, file/network/RMS I/O or automatic approval.
"""
from __future__ import annotations
import re
from typing import Any

VERSION = "rms_v09_official_reference_prototype_v04"
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


# Finite spelling alternatives for this case only; no global normalization.
# Each numeric token must use one consistent spelling system.
def _variants(sentence: str, slots: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    values = (sentence,)
    for slot in slots:
        values = tuple(value.replace(slot[0], alternative, 1)
                       for value in values for alternative in slot)
    return values


FIELD_VARIANTS = (
    _variants(HEADER, (("第二十四号", "第24号", "第２４号"),)),
    (DECREE_TITLE,),
    _variants(BASIS_SENTENCE, (("令和三年", "令和3年", "令和３年"),
                              ("法律第六十号", "法律第60号", "法律第６０号"),
                              ("附則第一項", "附則第1項", "附則第１項"))),
    _variants(DATE_SENTENCE, (("令和四年", "令和4年", "令和４年"),
                             ("四月", "4月", "４月"),
                             ("一日", "1日", "１日"))),
)


def review_official_reference(text: str, *, source_type: str, source_date: str,
                              source_issue: str, source_page: int,
                              manually_verified_official_copy: bool = False,
                              manually_verified_single_block: bool = False) -> dict[str, Any]:
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
    if type(manually_verified_single_block) is not bool:
        issues.append("SINGLE_BLOCK_FLAG_INVALID")
        return result
    # Preserve physical lines. Never remove whitespace inside identifiers.
    lines = [line.strip(" \t\u3000") for line in text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    if not lines:
        issues.append("SOURCE_TEXT_MISSING")
        return result
    # Only the two known sentences allow horizontal space after punctuation.
    def canonical(line: str) -> str:
        return re.sub(r"([、）])[ \t\u3000]+", r"\1", line)

    # Consume known fields in order, with no skipped nonblank text. A wrap is
    # permitted only immediately after a known comma or closing parenthesis,
    # inside a known sentence, and only with a human boundary assertion.
    expected = [HEADER, DECREE_TITLE, BASIS_SENTENCE, DATE_SENTENCE]
    pos = 0
    matched = []
    for index, alternatives in enumerate(FIELD_VARIANTS):
        if manually_verified_single_block and index:
            while pos < len(lines) and not lines[pos]:
                pos += 1
        if pos >= len(lines):
            break
        value = canonical(lines[pos]) if index >= 2 else lines[pos]
        pos += 1
        while (manually_verified_single_block and index >= 2
               and value not in alternatives and value and value[-1] in "、）"
               and any(target.startswith(value) for target in alternatives)
               and pos < len(lines) and lines[pos]):
            value += canonical(lines[pos])
            pos += 1
        if value not in alternatives:
            break
        matched.append(expected[index])
    exact_block = matched == expected and pos == len(lines)
    if not exact_block:
        issues.append("DOCUMENT_BOUNDARY_OR_LAYOUT_UNSUPPORTED")
        if not manually_verified_single_block:
            issues.append("SINGLE_BLOCK_ASSERTION_ABSENT")
    if len(DECREE_TOKEN.findall(text)) > 1:
        issues.append("MULTIPLE_DECREE_IDENTIFIERS")
    if len(DATE_TOKEN.findall(text)) > 1:
        issues.append("MULTIPLE_DATE_MENTIONS")
    if not exact_block or "MULTIPLE_DECREE_IDENTIFIERS" in issues or "MULTIPLE_DATE_MENTIONS" in issues:
        return result
    evidence.update(proposed_law="令和3年法律第60号", proposed_decree="令和4年政令第24号",
                    proposed_effective_date="2022-04-01",
                    source_verified_by_human_assertion_only=manually_verified_official_copy,
                     single_block_verified_by_human_assertion_only=manually_verified_single_block,
                    note="Candidate transcription only; verify original kanpo before decision.")
    return result
