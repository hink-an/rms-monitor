#!/usr/bin/env python3
"""Standalone, read-only HTML link inventory for the Environment Ministry press page.

This is an investigative aid, NOT a verifier of collection completeness. It
never updates RMS, the monitor baseline, or comparison state. It cannot authorize
comparison or confirm legal amendments. Default operation is offline only.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlsplit, urlunsplit

SOURCE_URL = "https://www.env.go.jp/press/"
MAX_BYTES = 2 * 1024 * 1024
# Transcribed from v0.1 screenshot (review against actual code before equivalence claims).
LEGACY_KEYWORDS = ("改正", "改定", "施行", "公布", "政令", "省令", "法令", "規則", "基準値", "規制基準")
ARTICLE_PATH = re.compile(r"^/press/(?:\d+|[A-Za-z0-9_-]+)\.html$", re.IGNORECASE)


class AnchorCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self.active = []
        self.html_seen = False
        self.body_seen = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == 'html':
            self.html_seen = True
        if tag == 'body':
            self.body_seen = True
        if tag == 'a':
            attr = dict(attrs)
            self.active.append({'href': attr.get('href'), 'text': []})

    def handle_data(self, data):
        for anchor in self.active:
            anchor['text'].append(data)

    def handle_endtag(self, tag):
        if tag.lower() == 'a' and self.active:
            anchor = self.active.pop()
            anchor['title'] = ' '.join(''.join(anchor.pop('text')).split())
            self.anchors.append(anchor)

    def close(self):
        super().close()
        # Dangling anchors are deliberately excluded; this is logged as a risk.


def normalize_url(href, base):
    if not href or not isinstance(href, str):
        return None
    href = href.strip()
    try:
        absolute = urljoin(base, href)
        p = urlsplit(absolute)
        if p.scheme.lower() != 'https' or p.hostname is None:
            return None
        if p.username or p.password or p.port not in (None, 443):
            return None
        return urlunsplit(('https', p.hostname.lower(), p.path or '/', p.query, ''))
    except (ValueError, UnicodeError):
        return None


def classify(url):
    if url is None:
        return 'invalid_or_unsupported'
    p = urlsplit(url)
    if p.hostname != 'www.env.go.jp':
        return 'other_host'
    if not p.path.startswith('/press/'):
        return 'outside_press'
    # Matching an apparent URL pattern is NOT proof that a link is an article.
    if ARTICLE_PATH.fullmatch(p.path) and not p.query:
        return 'article_shape_unverified'
    return 'press_other_or_unknown'


def analyze_html(raw, source_url=SOURCE_URL):
    if len(raw) > MAX_BYTES:
        raise ValueError('HTML_SIZE_LIMIT_EXCEEDED')
    try:
        html = raw.decode('utf-8', errors='strict')
    except UnicodeDecodeError as exc:
        raise ValueError('INVALID_UTF8') from exc
    parser = AnchorCollector()
    parser.feed(html)
    parser.close()
    if not raw.strip() or not parser.html_seen or not parser.body_seen:
        raise ValueError('HTML_STRUCTURE_INVALID')
    records = []
    seen_press = set()
    duplicate_press = 0
    for i, link in enumerate(parser.anchors, start=1):
        url = normalize_url(link['href'], source_url)
        kind = classify(url)
        title = link['title'][:500]
        keyword_hit = any(k in title for k in LEGACY_KEYWORDS)
        is_press = kind in ('article_shape_unverified', 'press_other_or_unknown')
        duplicate = bool(is_press and url in seen_press)
        if duplicate:
            duplicate_press += 1
        if is_press:
            seen_press.add(url)
        records.append({'order': i, 'title': title, 'url': url, 'class': kind,
                        'keyword_match': keyword_hit, 'press_duplicate': duplicate})

    unique_press = [r for r in records if r['class'] in ('article_shape_unverified', 'press_other_or_unknown') and not r['press_duplicate']]
    # Approximation only: the legacy parser may differ in title extraction, ordering,
    # URL normalization and original keyword list.
    proxy_legacy = [r for r in unique_press if r['title'] and r['keyword_match']]
    return {
        'tool': 'rms_env_link_analysis_v01',
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_url': source_url,
        'mode': 'offline',
        'html_bytes': len(raw),
        'html_structure_basic': {'html_tag': parser.html_seen, 'body_tag': parser.body_seen},
        'counts': {
            'all_anchor_elements_closed': len(records),
            'classification_counts': dict(Counter(r['class'] for r in records)),
            'press_links_total': len([r for r in records if r['class'] in ('article_shape_unverified', 'press_other_or_unknown')]),
            'press_duplicate_occurrences': duplicate_press,
            'press_unique': len(unique_press),
            'press_unique_keyword_match': len(proxy_legacy),
            'press_unique_keyword_no_match': len(unique_press) - len(proxy_legacy),
            'article_shape_unverified_unique': len([r for r in unique_press if r['class'] == 'article_shape_unverified']),
            'press_other_or_unknown_unique': len([r for r in unique_press if r['class'] == 'press_other_or_unknown']),
            'legacy_10_limit_reached_proxy': len(proxy_legacy) >= 10,
            'legacy_10_proxy_not_examined': max(0, len(proxy_legacy) - 10),
        },
        'link_records': records,
        'warnings': [
            'OFFLINE_INPUT_NOT_AUTHENTICATED',
            'ARTICLE_LINK_CLASSIFICATION_IS_HEURISTIC',
            'LEGACY_EXTRACTION_EQUIVALENCE_NOT_VERIFIED',
            'SOURCE_COMPLETENESS_NOT_VERIFIED',
        ],
        'diagnostic_status': 'HOLD',
        'comparison_allowed': False,
        'complete_collection_verified': False,
        'legal_amendment_confirmed': False,
        'rms_modified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline-only read-only press link inventory')
    parser.add_argument('--offline-html', required=True, metavar='HTML_FILE')
    parser.add_argument('--output', required=True, metavar='NEW_JSON_FILE')
    args = parser.parse_args(argv)
    try:
        src = Path(args.offline_html)
        if not src.is_file():
            raise ValueError('INPUT_FILE_MISSING')
        if src.stat().st_size > MAX_BYTES:
            raise ValueError('HTML_SIZE_LIMIT_EXCEEDED')
        report = analyze_html(src.read_bytes())
        out = Path(args.output)
        # exclusive create prevents clobbering even if file appears simultaneously
        with out.open('x', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print('Diagnostic: HOLD')
        print('Comparison allowed: false')
        print('Report:', out)
        return 0  # Successful *inventory*, not permission for comparison.
    except (OSError, ValueError) as exc:
        print('FAIL-CLOSED: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
