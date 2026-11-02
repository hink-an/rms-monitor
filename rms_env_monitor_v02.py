# RMS Environment Ministry Monitor
# Version 0.2 - Article inspection test
# Read-only. No RMS data is modified.

import re
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from datetime import datetime, timezone

from rms_env_monitor import (
    SOURCE_URL,
    fetch_page,
    extract_candidates,
)

VERSION = "0.2"
MAX_ARTICLES = 10


class ArticleParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.skip_depth = 0
        self.meta_dates = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in ("script", "style", "noscript"):
            self.skip_depth += 1

        if tag == "meta":
            key = (
                attrs.get("property", "")
                or attrs.get("name", "")
            ).lower()

            if key in (
                "article:published_time",
                "date",
                "dc.date",
                "dc.date.issued",
            ):
                value = attrs.get("content", "")
                if value:
                    self.meta_dates.append(value)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip_depth = max(
                0, self.skip_depth - 1
            )

    def handle_data(self, data):
        if self.skip_depth == 0:
            text = " ".join(data.split())
            if text:
                self.text_parts.append(text)

    def get_text(self):
        return "\n".join(self.text_parts)


def fetch_article(url):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "RMS-Monitor/0.2"
        }
    )

    with urllib.request.urlopen(
        request, timeout=30
    ) as response:

        if response.status != 200:
            raise RuntimeError(
                f"HTTP status: {response.status}"
            )

        charset = response.headers.get_content_charset()
        charset = charset or "utf-8"

        html = response.read().decode(
            charset, errors="replace"
        )

    parser = ArticleParser()
    parser.feed(html)

    return parser.get_text(), parser.meta_dates


def find_date_candidates(text, meta_dates):

    results = []

    for value in meta_dates:
        results.append({
            "value": value,
            "source": "HTML metadata",
        })

    patterns = [
        r"20\d{2}年\s*\d{1,2}月\s*\d{1,2}日",
        r"令和\d{1,2}年\s*\d{1,2}月\s*\d{1,2}日",
        r"令和元年\s*\d{1,2}月\s*\d{1,2}日",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text)

        for value in matches[:5]:
            results.append({
                "value": value,
                "source": "Article text",
            })

    unique = []
    seen = set()

    for item in results:
        key = item["value"]

        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique[:10]


def classify_stage(title):

    if "意見募集" in title:
        return "PUBLIC_COMMENT"

    if "検討会" in title or "審議会" in title:
        return "DISCUSSION"

    if "閣議決定" in title:
        return "CABINET_DECISION"

    if "公布" in title:
        return "PUBLICATION_MENTIONED"

    if "施行" in title:
        return "ENFORCEMENT_MENTIONED"

    if "改正案" in title:
        return "DRAFT_MENTIONED"

    if "改正" in title:
        return "AMENDMENT_MENTIONED"

    return "UNKNOWN"


def inspect_article(item):

    title = item["title"]
    url = item["url"]

    text, meta_dates = fetch_article(url)

    date_candidates = find_date_candidates(
        text, meta_dates
    )

    stage = classify_stage(title)

    return {
        "title": title,
        "url": url,
        "stage_candidate": stage,
        "date_candidates": date_candidates,
        "text_length": len(text),
        "verification": "NOT_VERIFIED",
    }


def main():

    print("RMS Environment Ministry Monitor")
    print("Version:", VERSION)
    print("UTC:", datetime.now(timezone.utc))
    print("Source:", SOURCE_URL)

    html = fetch_page()
    candidates = extract_candidates(html)

    print("Candidates found:", len(candidates))

    for index, item in enumerate(
        candidates[:MAX_ARTICLES], start=1
    ):

        print("=" * 50)
        print("Candidate:", index)

        try:
            result = inspect_article(item)

            print("Title:", result["title"])
            print("URL:", result["url"])

            print(
                "Stage candidate:",
                result["stage_candidate"]
            )

            print(
                "Article text length:",
                result["text_length"]
            )

            dates = result["date_candidates"]

            if dates:
                print("Date candidates:")

                for date in dates:
                    print(
                        " ",
                        date["value"],
                        "/",
                        date["source"]
                    )
            else:
                print("Date candidates: UNKNOWN")

            print(
                "Verification:",
                result["verification"]
            )

        except Exception as error:
            print("Article inspection failed")
            print("Reason:", str(error))

    print("=" * 50)
    print("Inspection test completed.")
    print("Dates and stages require verification.")
    print("No RMS data was modified.")


if __name__ == "__main__":
    main()
