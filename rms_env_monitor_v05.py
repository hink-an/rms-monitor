"""RMS Environment Ministry Monitor v0.5 - candidate snapshot comparison.

Uses the v0.1/v0.2/v0.4 programs already in this GitHub repository.
Writes ONLY a separately named test JSON file. Never edits production RMS data.
A missing prior snapshot is a baseline, NOT evidence of newly published laws.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from rms_env_monitor import SOURCE_URL, extract_candidates, fetch_page
from rms_env_monitor_v02 import fetch_article
from rms_env_monitor_v04 import classify_title, date_evidence

VERSION = "0.5"
MAX_ARTICLES = 10
# The ministry's page layout must be checked before trusting this field.
# Dates collected here are UNVERIFIED publication-date candidates.
DATE_RE = re.compile(r"(?:20\d{2}年|令和(?:元|\d{1,2})年)\s*\d{1,2}月\s*\d{1,2}日")


def canonical_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "www.env.go.jp":
        raise ValueError("URL is not an allowed official HTTPS host")
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), parsed.path, "", ""))


def publication_date_candidates(text, meta_dates):
    """Conservative collection, not automatic confirmation of publication day."""
    result = []
    for raw in meta_dates[:5]:
        result.append({"value": raw, "evidence": "HTML metadata (not verified)"})
    # The v0.2 parser includes navigation and unrelated dates; limit this to
    # the beginning of the extracted page for *manual* inspection only.
    for match in list(DATE_RE.finditer(text[:800]))[:3]:
        result.append({
            "value": match.group(),
            "evidence": "Near beginning of extracted page (not verified)",
        })
    unique = []
    seen = set()
    for entry in result:
        if (entry["value"], entry["evidence"]) not in seen:
            unique.append(entry)
            seen.add((entry["value"], entry["evidence"]))
    return unique


def collect():
    records = []
    candidates = extract_candidates(fetch_page())[:MAX_ARTICLES]
    for item in candidates:
        url = canonical_url(item["url"])
        text, metadata_dates = fetch_article(url)
        if not text.strip():
            raise RuntimeError(f"Article empty: {url}")
        records.append({
            "id": url,  # Stable across repeated fetches; not a legal amendment ID.
            "title": item["title"],
            "source_url": url,
            "stage_candidate": classify_title(item["title"]),
            "publication_date": None,
            "publication_date_candidates": publication_date_candidates(text, metadata_dates),
            "explicit_date_evidence": date_evidence(text),
            "review_status": "UNVERIFIED",
        })
    return records


def read_previous(path):
    if path is None:
        return None
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Prior snapshot missing: {p}")
    previous = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(previous, dict) or not isinstance(previous.get("records"), list):
        raise ValueError("Invalid previous snapshot format")
    return previous


def compare(current, previous):
    if previous is None:
        return {"mode": "BASELINE", "new_candidate_ids": [], "unchanged_ids": [],
                "removed_from_current_list_ids": [], "note": "No prior snapshot; newness cannot be determined."}
    prior_ids = {entry["id"] for entry in previous["records"]}
    current_ids = {entry["id"] for entry in current}
    return {
        "mode": "COMPARED",
        "new_candidate_ids": sorted(current_ids - prior_ids),
        "unchanged_ids": sorted(current_ids & prior_ids),
        "removed_from_current_list_ids": sorted(prior_ids - current_ids),
        "note": "Removed from current list does not mean a legal change was repealed.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous", help="Path to a previous *test* snapshot JSON")
    parser.add_argument("--output", default="rms-env-monitor-v05-test.json",
                        help="Separate test JSON path (not production RMS JSON)")
    args = parser.parse_args()
    output = Path(args.output)
    forbidden = {"rms-monitor-results.json", "rms_運用データ.json"}
    if output.name.lower() in {name.lower() for name in forbidden}:
        parser.error("Refusing to overwrite an RMS production data file")
    if args.previous and output.resolve() == Path(args.previous).resolve():
        parser.error("Output must differ from prior snapshot")
    prior = read_previous(args.previous)
    records = collect()
    diff = compare(records, prior)
    snapshot = {
        "schema_version": 1,
        "monitor_version": VERSION,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_list": SOURCE_URL,
        "coverage": "Current press-list articles matching v0.1 keywords; incomplete",
        "legal_change_verified": False,
        "records": records,
        "comparison": diff,
    }
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Version:", VERSION)
    print("Candidates:", len(records))
    print("Comparison mode:", diff["mode"])
    print("New candidates since supplied snapshot:", len(diff["new_candidate_ids"]))
    print("Missing from current list:", len(diff["removed_from_current_list_ids"]))
    print("Saved test snapshot:", output)
    print("WARNING: No legal amendments, article publication dates, or applicability verified.")
    print("Production RMS files were not modified.")


if __name__ == "__main__":
    main()
