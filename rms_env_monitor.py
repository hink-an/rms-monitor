# RMS Environment Ministry Monitor
# Version 0.1 - Candidate extraction test
# Read-only. No RMS data is modified.

import urllib.request
import urllib.parse
from html.parser import HTMLParser
from datetime import datetime, timezone


SOURCE_URL = "https://www.env.go.jp/press/"

KEYWORDS = [
    "改正",
    "改定",
    "施行",
    "公布",
    "政令",
    "省令",
    "法令",
    "規則",
    "基準値",
    "規制基準",
]


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_url = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attributes = dict(attrs)
            self.current_url = attributes.get("href")
            self.current_text = []

    def handle_data(self, data):
        if self.current_url is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current_url:
            title = " ".join(
                "".join(self.current_text).split()
            )

            if title:
                self.links.append(
                    (title, self.current_url)
                )

            self.current_url = None
            self.current_text = []


def fetch_page():
    request = urllib.request.Request(
        SOURCE_URL,
        headers={
            "User-Agent": "RMS-Monitor/0.1"
        }
    )

    with urllib.request.urlopen(
        request, timeout=30
    ) as response:

        if response.status != 200:
            raise RuntimeError(
                f"HTTP error: {response.status}"
            )

        html = response.read().decode(
            "utf-8", errors="replace"
        )

    return html


def extract_candidates(html):
    parser = LinkParser()
    parser.feed(html)

    candidates = []
    seen = set()

    for title, href in parser.links:
        url = urllib.parse.urljoin(
            SOURCE_URL, href
        )

        parsed_url = urllib.parse.urlparse(url)

        if parsed_url.netloc != "www.env.go.jp":
            continue

        if not parsed_url.path.startswith("/press/"):
            continue

        if not any(word in title for word in KEYWORDS):
            continue

        if url in seen:
            continue

        seen.add(url)

        candidates.append({
            "title": title,
            "url": url,
            "status": "UNVERIFIED_CANDIDATE"
        })

    return candidates


def main():
    print("RMS Environment Ministry Monitor")
    print("Version: 0.1")
    print("UTC:", datetime.now(timezone.utc))
    print("Source:", SOURCE_URL)

    html = fetch_page()

    print("HTML received:", len(html), "characters")

    candidates = extract_candidates(html)

    print("Candidates found:", len(candidates))

    for index, item in enumerate(
        candidates[:30], start=1
    ):
        print("------------------------------")
        print("Candidate:", index)
        print("Title:", item["title"])
        print("URL:", item["url"])
        print("Status:", item["status"])

    print("------------------------------")
    print("Extraction test completed.")
    print("No legal changes have been verified.")
    print("No RMS data was modified.")


if __name__ == "__main__":
    main()
