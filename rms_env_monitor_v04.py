"""RMS Environment Ministry Monitor v0.4 (read-only, candidate inspection).

Dependencies: rms_env_monitor.py (v0.1), rms_env_monitor_v02.py (v0.2).
Does NOT update rms-monitor-results.json or other RMS data.
This is a *partial* monitor of the current Ministry of the Environment press list,
not a comprehensive legal-change detection system.
"""

import hashlib
import re
from datetime import datetime, timezone
from html import unescape

from rms_env_monitor import SOURCE_URL, extract_candidates, fetch_page
from rms_env_monitor_v02 import fetch_article

VERSION = "0.4"
MAX_ARTICLES = 10

# A title is evidence of a *topic or procedural stage*, not proof of enactment.
STAGE_RULES = [
    ("PUBLIC_COMMENT", ("意見募集", "パブリックコメント", "意見の募集")),
    ("DISCUSSION", ("検討会", "審議会", "検討部会")),
    ("DRAFT", ("改正案", "政令案", "省令案", "法律案", "答申案")),
    ("CABINET_DECISION", ("閣議決定",)),
    ("PROMULGATION_MENTIONED", ("公布",)),
    ("ENFORCEMENT_MENTIONED", ("施行",)),
    ("AMENDMENT_MENTIONED", ("改正", "改定")),
]

YEAR = r"(?:20\d{2}年|令和(?:元|\d{1,2})年)"
DATE = rf"{YEAR}\s*\d{{1,2}}月\s*\d{{1,2}}日"
# Match *explicit phrases* where a date is grammatically linked with an action.
DATE_RELATIONS = [
    ("PROMULGATION_DATE_CANDIDATE", re.compile(rf"({DATE})\s*(?:に|付で|付けで)?\s*公布")),
    ("PROMULGATION_DATE_CANDIDATE", re.compile(rf"公布(?:日|期日)?\s*(?:は|：|:|を)?\s*({DATE})")),
    ("ENFORCEMENT_DATE_CANDIDATE", re.compile(rf"({DATE})\s*(?:から|より|に|をもって)?\s*施行")),
    ("ENFORCEMENT_DATE_CANDIDATE", re.compile(rf"施行(?:日|期日)?\s*(?:は|：|:|を)?\s*({DATE})")),
]
DATE_FINDER = re.compile(DATE)


def classify_title(title):
    for stage, expressions in STAGE_RULES:
        for expression in expressions:
            if expression in title:
                return {"stage_candidate": stage, "trigger": expression, "verified": False}
    return {"stage_candidate": "UNKNOWN", "trigger": None, "verified": False}


def evidence_excerpt(text, start, end, width=65):
    # v0.2 returns text joined with newlines, which may include page navigation.
    left = max(0, start - width)
    right = min(len(text), end + width)
    return " ".join(text[left:right].split())


def date_evidence(text):
    candidates = []
    seen = set()
    for kind, pattern in DATE_RELATIONS:
        for match in pattern.finditer(text):
            date = match.group(1)
            key = (kind, date, match.start())
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "date": date,
                "type_candidate": kind,
                "matched_phrase": match.group(0),
                "evidence": evidence_excerpt(text, match.start(), match.end()),
                "verified": False,
            })
    # Dates without explicit linked phrases are deliberately not typed.
    return candidates[:20]


def inspect(item):
    url = item["url"]
    text, meta_dates = fetch_article(url)
    if not text.strip():
        raise ValueError("Article text was empty")
    dates = date_evidence(text)
    return {
        "event_key_candidate": "env-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:16],
        "title": unescape(item["title"]),
        "url": url,
        "stage": classify_title(item["title"]),
        "publication_date": "UNKNOWN",  # v0.2 metadata is not reliable enough to confirm it
        "publication_date_metadata_candidates": meta_dates[:5],
        "explicit_date_evidence": dates,
        "unclassified_date_count": len(DATE_FINDER.findall(text)),
        "article_text_length": len(text),
        "verification": "NOT_VERIFIED",
    }


def main():
    print(f"RMS Environment Ministry Monitor v{VERSION}")
    print("UTC:", datetime.now(timezone.utc).isoformat())
    print("Source:", SOURCE_URL)
    print("Coverage: only current press-list links with v0.1 keywords")
    print("WARNING: 0 candidates does NOT mean 0 legal changes")
    print("Read-only: no RMS or repository files are written")
    candidates = extract_candidates(fetch_page())
    print("Candidates in current list:", len(candidates))
    success = 0
    failed = 0
    for number, item in enumerate(candidates[:MAX_ARTICLES], 1):
        print("=" * 60)
        print("Candidate:", number)
        try:
            result = inspect(item)
            success += 1
            print("Event key candidate:", result["event_key_candidate"])
            print("Title:", result["title"])
            print("URL:", result["url"])
            print("Stage candidate:", result["stage"])
            print("Publication date: UNKNOWN (not automatically verified)")
            print("Publication metadata date candidates:", result["publication_date_metadata_candidates"])
            print("All date mentions:", result["unclassified_date_count"])
            print("Explicit date relation candidates:", len(result["explicit_date_evidence"]))
            for evidence in result["explicit_date_evidence"]:
                print("Date:", evidence["date"])
                print("Type candidate:", evidence["type_candidate"])
                print("Matched phrase:", evidence["matched_phrase"])
                print("Evidence:", evidence["evidence"])
                print("Verified: False")
            print("Verification: NOT_VERIFIED")
        except Exception as error:
            failed += 1
            print("Article inspection FAILED:", type(error).__name__, str(error))
            print("URL:", item["url"])
    print("=" * 60)
    print("Successful:", success)
    print("Failed:", failed)
    print("No RMS data was modified")
    if failed:
        raise RuntimeError(f"{failed} article inspections failed")


if __name__ == "__main__":
    main()
