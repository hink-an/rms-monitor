#!/usr/bin/env python3
"""RMS environmental source diagnostics v0.1 (read-only, standalone).

This tool does NOT update RMS, previous baselines, or any comparison state.
PASS means only that the limited diagnostics found no anomaly; it is NOT
proof of a complete collection and NEVER authorizes an automatic comparison.
"""

import argparse
import hashlib
from html.parser import HTMLParser
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

SOURCE_URL = "https://www.env.go.jp/press/"
MAX_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 30
MAX_REDIRECTS = 3
COLLECTOR_LIMIT = 10  # Known limit of the separate v0.5 collector; not this script.


class PageInspector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.html_seen = False
        self.body_seen = False
        self.links = []
        self.title_seen = False
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "html":
            self.html_seen = True
        elif tag == "body":
            self.body_seen = True
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title and data.strip():
            self.title_seen = True


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, original_host):
        self.original_host = original_host
        self.redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.redirect_count += 1
        parsed = urllib.parse.urlsplit(newurl)
        if (self.redirect_count > MAX_REDIRECTS or parsed.scheme != "https"
                or parsed.hostname != self.original_host):
            raise ValueError("Unexpected or excessive redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def inspect_html(raw, url, report):
    report["html_bytes"] = len(raw)
    report["sha256"] = hashlib.sha256(raw).hexdigest()
    if not raw:
        report["errors"].append("EMPTY_HTML")
        return
    try:
        html = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        report["errors"].append("INVALID_UTF8")
        return
    if "\ufffd" in html:
        report["warnings"].append("REPLACEMENT_CHARACTER_PRESENT")
    parser = PageInspector()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        report["errors"].append("HTML_PARSE_ERROR")
        return
    report["html_structure"] = {
        "html_tag_seen": parser.html_seen,
        "body_tag_seen": parser.body_seen,
        "title_text_seen": parser.title_seen,
    }
    if not parser.html_seen or not parser.body_seen:
        report["errors"].append("MISSING_HTML_OR_BODY")
    report["all_links_count"] = len(parser.links)
    press_links = set()
    for href in parser.links:
        target = urllib.parse.urlsplit(urllib.parse.urljoin(url, href))
        if (target.scheme == "https" and target.hostname == "www.env.go.jp"
                and (target.path.startswith("/press/") or target.path.startswith("/press_"))
                and target.path.rstrip("/") != "/press"):
            press_links.add(urllib.parse.urlunsplit((target.scheme, target.netloc,
                                                     target.path, "", "")))
    report["press_link_candidates_count"] = len(press_links)
    report["candidate_count_is_heuristic"] = True
    if not press_links:
        report["warnings"].append("ZERO_PRESS_LINK_CANDIDATES")
    if len(press_links) >= COLLECTOR_LIMIT:
        report["warnings"].append("V05_COLLECTION_LIMIT_RISK")
    # No prior expected IDs or complete site structure are verified here.
    report["warnings"].append("SOURCE_COMPLETENESS_NOT_VERIFIED")


def fetch(url, report):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "www.env.go.jp":
        raise ValueError("Only https://www.env.go.jp is allowed")
    redirect_handler = SameHostRedirect(parsed.hostname)
    opener = urllib.request.build_opener(redirect_handler)
    request = urllib.request.Request(url, headers={"User-Agent": "RMS-Monitor-Diagnostic/0.1",
                                                    "Accept": "text/html"})
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        report["http_status"] = response.status
        report["final_url"] = response.geturl()
        report["content_type"] = response.headers.get("Content-Type", "")
        report["redirect_count"] = redirect_handler.redirect_count
        if response.status != 200:
            raise ValueError("Unexpected HTTP status")
        if "text/html" not in report["content_type"].lower():
            report["errors"].append("UNEXPECTED_CONTENT_TYPE")
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            report["errors"].append("HTML_SIZE_LIMIT_EXCEEDED")
            report["html_bytes"] = len(raw)
            return
    inspect_html(raw, report["final_url"], report)


def run(args):
    now = datetime.now(timezone.utc)
    report = {
        "tool": "rms_env_diagnostic_v01", "checked_at_utc": now.isoformat(),
        "requested_url": args.url, "mode": "offline" if args.offline_html else "online",
        "http_status": None, "final_url": None, "content_type": None,
        "redirect_count": None, "html_bytes": None, "sha256": None,
        "html_structure": None, "all_links_count": None,
        "press_link_candidates_count": None, "candidate_count_is_heuristic": True,
        "collector_limit_v05": COLLECTOR_LIMIT, "errors": [], "warnings": [],
        "diagnostic_status": "FAIL", "comparison_allowed": False,
        "complete_collection_verified": False, "rms_modified": False,
    }
    try:
        if args.offline_html:
            p = Path(args.offline_html)
            if p.stat().st_size > MAX_BYTES:
                report["errors"].append("HTML_SIZE_LIMIT_EXCEEDED")
                report["html_bytes"] = p.stat().st_size
            else:
                inspect_html(p.read_bytes(), args.url, report)
        else:
            fetch(args.url, report)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        report["errors"].append("FETCH_OR_INPUT_ERROR")
        report["error_type"] = type(exc).__name__  # Avoid logging sensitive response content.
    # Even error-free diagnostics cannot establish completeness.
    report["diagnostic_status"] = ("FAIL" if report["errors"] else
                                   "HOLD" if report["warnings"] else "PASS")
    output = Path(args.output) if args.output else Path(
        "rms-env-diagnostic-" + now.strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    try:
        # Exclusive create: no overwrite of any existing file, including state and RMS data.
        with output.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except OSError as exc:
        print("Cannot create diagnostic JSON: " + str(exc), file=sys.stderr)
        return 2
    print("Diagnostic:", report["diagnostic_status"])
    print("Comparison allowed: false")
    print("Report:", output)
    # HOLD and FAIL both exit nonzero to prevent accidental pipeline continuation.
    return 0 if report["diagnostic_status"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser(description="Standalone RMS source diagnostics; never modifies RMS")
    parser.add_argument("--url", default=SOURCE_URL, help="Official page (restricted to env.go.jp online)")
    parser.add_argument("--offline-html", metavar="FILE", help="Analyze local HTML without network access")
    parser.add_argument("--output", metavar="FILE", help="New JSON report; existing file never overwritten")
    args = parser.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
