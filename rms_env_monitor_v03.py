# RMS Environment Ministry Monitor
# Version 0.3 - Evidence extraction test
# Read-only. No RMS data is modified.

import re
from datetime import datetime, timezone

from rms_env_monitor import (
    SOURCE_URL,
    fetch_page,
    extract_candidates,
)

from rms_env_monitor_v02 import fetch_article


VERSION = "0.3"
MAX_ARTICLES = 10

DATE_PATTERN = (
    r"(?:20\d{2}年|令和(?:元|\d{1,2})年)"
    r"\s*\d{1,2}月\s*\d{1,2}日"
)

STAGE_RULES = [
    ("意見募集", "PUBLIC_COMMENT"),
    ("パブリックコメント", "PUBLIC_COMMENT"),
    ("検討会", "DISCUSSION"),
    ("審議会", "DISCUSSION"),
    ("閣議決定", "CABINET_DECISION"),
    ("公布", "PUBLICATION_MENTIONED"),
    ("施行", "ENFORCEMENT_MENTIONED"),
    ("改正案", "DRAFT_MENTIONED"),
    ("改正", "AMENDMENT_MENTIONED"),
]

DATE_KEYWORDS = {
    "PUBLICATION_DATE": ["公布"],
    "ENFORCEMENT_DATE": ["施行"],
}


def classify_stage(title):

    for keyword, stage in STAGE_RULES:
        if keyword in title:
            return {
                "stage": stage,
                "evidence": keyword,
                "verified": False,
            }

    return {
        "stage": "UNKNOWN",
        "evidence": "",
        "verified": False,
    }


def extract_date_evidence(text):

    results = []
    seen = set()

    for match in re.finditer(DATE_PATTERN, text):

        date_value = match.group()

        start = max(0, match.start() - 100)
        end = min(len(text), match.end() + 100)

        context = text[start:end]
        context = " ".join(context.split())

        matched_types = []

        for date_type, keywords in DATE_KEYWORDS.items():

            if any(
                word in context
                for word in keywords
            ):
                matched_types.append(date_type)

        if not matched_types:
            matched_types = ["UNCLASSIFIED_DATE"]

        for date_type in matched_types:

            key = (date_value, date_type, context)

            if key in seen:
                continue

            seen.add(key)

            results.append({
                "date": date_value,
                "type_candidate": date_type,
                "evidence": context,
                "verified": False,
            })

    return results[:20]


def inspect_article(item):

    title = item["title"]
    url = item["url"]

    text, meta_dates = fetch_article(url)

    stage = classify_stage(title)

    dates = extract_date_evidence(text)

    return {
        "title": title,
        "url": url,
        "stage": stage,
        "date_evidence": dates,
        "metadata_dates": meta_dates,
        "text_length": len(text),
        "verification": "NOT_VERIFIED",
    }


def display_result(index, result):

    print("=" * 60)
    print("Candidate:", index)
    print("Title:", result["title"])
    print("URL:", result["url"])

    stage = result["stage"]

    print("Stage candidate:", stage["stage"])
    print("Stage evidence:", stage["evidence"])

    print("Article length:", result["text_length"])

    print("Published date metadata candidates:")

    if result["metadata_dates"]:

        for value in result["metadata_dates"][:5]:
            print(" -", value)

    else:
        print(" UNKNOWN")

    print("Date evidence:")

    dates = result["date_evidence"]

    if not dates:
        print(" No date evidence found.")

    for item in dates:

        print("-" * 40)
        print("Date:", item["date"])
        print("Type candidate:", item["type_candidate"])
        print("Evidence:", item["evidence"])
        print("Verified:", item["verified"])

    print("Verification:", result["verification"])


def main():

    print("RMS Environment Ministry Monitor")
    print("Version:", VERSION)
    print("UTC:", datetime.now(timezone.utc))
    print("Source:", SOURCE_URL)

    html = fetch_page()
    candidates = extract_candidates(html)

    print("Candidates found:", len(candidates))

    success_count = 0
    failure_count = 0

    for index, item in enumerate(
        candidates[:MAX_ARTICLES], start=1
    ):

        try:
            result = inspect_article(item)

            display_result(index, result)

            success_count += 1

        except Exception as error:

            failure_count += 1

            print("=" * 60)
            print("Candidate:", index)
            print("Article inspection FAILED")
            print("URL:", item["url"])
            print("Reason:", str(error))

    print("=" * 60)
    print("Inspection completed.")
    print("Successful:", success_count)
    print("Failed:", failure_count)

    print("All extracted information is unverified.")
    print("No RMS data was modified.")

    if failure_count > 0:
        raise RuntimeError(
            f"{failure_count} article inspections failed"
        )


if __name__ == "__main__":
    main()
