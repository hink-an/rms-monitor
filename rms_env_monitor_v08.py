#!/usr/bin/env python3
"""RMS Monitor v0.8: offline HTML fixture safety gate (no network / no RMS writes).

This is a test harness, not a live source completeness verifier. A validated
fixture must carry an explicit manifest of expected candidate IDs. A missing
record or a capped extraction makes comparison unavailable (fail closed).
"""
import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

SOURCE = 'https://www.env.go.jp/press/'
MAX_HTML_BYTES = 2_000_000
MAX_CANDIDATES = 10

class CandidateParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.href = None
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'a' and self.href is None:
            self.href = dict(attrs).get('href')
            self.parts = []

    def handle_data(self, data):
        if self.href is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == 'a' and self.href is not None:
            self.links.append((self.href, ''.join(self.parts).strip()))
            self.href = None
            self.parts = []


def canonical_url(href):
    p = urlsplit(urljoin(SOURCE, href))
    if (p.scheme != 'https' or p.hostname != 'www.env.go.jp'
            or p.port not in (None, 443) or p.username is not None
            or p.password is not None or not p.path.startswith('/press/')):
        raise ValueError('out-of-scope URL')
    return urlunsplit(('https', 'www.env.go.jp', p.path, '', ''))


def load_json(path):
    raw = Path(path).read_bytes()
    if not raw or len(raw) > MAX_HTML_BYTES:
        raise ValueError('missing or oversized JSON')
    data = json.loads(raw.decode('utf-8-sig'))
    if type(data) is not dict:
        raise ValueError('JSON object required')
    return data


def validate_fixture(path):
    data = load_json(path)
    if data.get('schema_version') != 1 or data.get('fixture_only') is not True:
        raise ValueError('not a v0.8 offline fixture')
    if data.get('source_list') != SOURCE:
        raise ValueError('unexpected source list')
    if data.get('legal_change_verified') is not False:
        raise ValueError('unsafe verification flag')
    html = data.get('html')
    expected = data.get('expected_candidate_ids')
    if not isinstance(html, str) or not html.strip():
        raise ValueError('empty HTML')
    if len(html.encode('utf-8')) > MAX_HTML_BYTES:
        raise ValueError('HTML too large')
    if not isinstance(expected, list) or not expected:
        raise ValueError('no fixture manifest; cannot verify completeness')
    if not all(isinstance(x, str) for x in expected):
        raise ValueError('invalid manifest')
    if len(set(expected)) != len(expected):
        raise ValueError('duplicate manifest IDs')
    if len(expected) >= MAX_CANDIDATES:
        raise ValueError('candidate capacity reached; possible truncation')
    expected = set(canonical_url(x) for x in expected)
    if len(expected) == 0:
        raise ValueError('empty manifest')
    if '<html' not in html.lower() or '</html>' not in html.lower():
        raise ValueError('HTML document markers missing')
    parser = CandidateParser()
    parser.feed(html)
    parser.close()
    extracted = set()
    for href, title in parser.links:
        if not title or not href:
            continue
        try:
            link = canonical_url(href)
        except (ValueError, TypeError):
            continue
        if link in expected:
            extracted.add(link)
    if extracted != expected:
        raise ValueError('fixture HTML/manifest mismatch: completeness not established')
    return extracted


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline', required=True, help='v0.8 test fixture JSON')
    ap.add_argument('--current', required=True, help='v0.8 test fixture JSON')
    ap.add_argument('--output', required=True, help='fresh output JSON path')
    args = ap.parse_args()
    out = Path(args.output)
    if out.exists():
        ap.error('output already exists; refusing overwrite')
    if out.resolve() in (Path(args.baseline).resolve(), Path(args.current).resolve()):
        ap.error('output overlaps input')
    try:
        before = validate_fixture(args.baseline)
        after = validate_fixture(args.current)
        # No silent 'absent' conclusion even for valid fixtures: the test only
        # demonstrates ID math. A live monitor must separately verify coverage.
        result = {
            'schema_version': 1, 'monitor_version': '0.8-offline-prototype',
            'test_only': True, 'legal_change_verified': False,
            'coverage': 'INCOMPLETE', 'source_list': SOURCE,
            'baseline_count': len(before), 'current_count': len(after),
            'new_candidate_ids': sorted(after - before),
            'unchanged_ids': sorted(before & after),
            'absent_from_current_list_ids': sorted(before - after),
            'note': 'Offline fixture ID difference only; absence is not repeal.'
        }
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('PASS: offline fixture validated; candidate IDs compared; no legal decision')
        print(f"baseline={len(before)} current={len(after)} new={len(result['new_candidate_ids'])} unchanged={len(result['unchanged_ids'])} absent={len(result['absent_from_current_list_ids'])}")
    except (OSError, ValueError, json.JSONDecodeError, UnicodeError) as exc:
        ap.exit(1, f'FAIL-CLOSED: {exc}\n')

if __name__ == '__main__':
    main()
