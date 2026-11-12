#!/usr/bin/env python3
"""RMS v0.9 prototype: OFFLINE, standalone press-link candidate triage.

Investigative output only; never calls network, updates RMS, compares snapshots,
confirms a legal amendment, or claims complete ministry coverage.
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

SOURCE_URL = 'https://www.env.go.jp/press/'
MAX_HTML_BYTES = 2 * 1024 * 1024
DEFAULT_LIMIT = 100
MAX_LIMIT = 100
ARTICLE_PATH = re.compile(r'^/press/(?:[A-Za-z0-9_-]+)\.html$', re.I)
FORMAL_TERMS = ('公布', '施行', '指定', '指定の取消', '指定の取消し', '告示', '改正')
REFERENCE_TERMS = ('案', '審議会', '検討会', 'パブリックコメント', '意見募集', '諮問', '答申', '評価')

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.has_html = False
        self.has_body = False
        self.active = []
        self.links = []
    def handle_starttag(self, tag, attrs):
        if tag == 'html': self.has_html = True
        if tag == 'body': self.has_body = True
        if tag == 'a':
            self.active.append({'href': dict(attrs).get('href'), 'text': []})
    def handle_data(self, data):
        for a in self.active:
            a['text'].append(data)
    def handle_endtag(self, tag):
        if tag == 'a' and self.active:
            a = self.active.pop()
            self.links.append((a['href'], ' '.join(''.join(a['text']).split())[:500]))

def normalized_article_url(href):
    if not href: return None
    try:
        p = urlsplit(urljoin(SOURCE_URL, href))
        if p.scheme != 'https' or p.hostname != 'www.env.go.jp': return None
        if p.username or p.password or p.port not in (None, 443): return None
        if not ARTICLE_PATH.fullmatch(p.path): return None
        if p.query: return None
        return urlunsplit(('https', 'www.env.go.jp', p.path, '', ''))
    except ValueError:
        return None

def classify_title(title):
    """Unverified title-only *queue* label, not legal status determination."""
    if any(k in title for k in REFERENCE_TERMS):
        return 'REFERENCE_CANDIDATE_UNVERIFIED'
    if any(k in title for k in FORMAL_TERMS):
        return 'FORMAL_REVIEW_CANDIDATE_UNVERIFIED'
    return 'OTHER_UNVERIFIED'

def analyze(raw, limit=DEFAULT_LIMIT):
    if not 1 <= limit <= MAX_LIMIT: raise ValueError('INVALID_LIMIT')
    if len(raw) > MAX_HTML_BYTES: raise ValueError('HTML_SIZE_LIMIT_EXCEEDED')
    try: html = raw.decode('utf-8', 'strict')
    except UnicodeDecodeError as exc: raise ValueError('INVALID_UTF8') from exc
    parser = LinkParser()
    parser.feed(html)
    parser.close()
    if not raw.strip() or not parser.has_html or not parser.has_body or parser.active:
        raise ValueError('HTML_STRUCTURE_INVALID')
    found = []
    seen = set()
    duplicates = 0
    for order, (href, title) in enumerate(parser.links, 1):
        url = normalized_article_url(href)
        if not url or not title: continue
        if url in seen:
            duplicates += 1
            continue
        seen.add(url)
        found.append({'link_order': order, 'title': title, 'url': url,
                      'triage': classify_title(title), 'verification': 'NOT_VERIFIED'})
    # Preserve whole inventory in the offline diagnostic report. No first-N truncation.
    # A limit breach is a review trigger, NEVER treated as a complete collection.
    over_limit = len(found) > limit
    queues = Counter(x['triage'] for x in found)
    return {
        'tool': 'rms_env_collector_v09_prototype',
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_url': SOURCE_URL, 'mode': 'OFFLINE_ONLY',
        'html_bytes': len(raw), 'configured_candidate_limit': limit,
        'article_shape_candidates': len(found), 'duplicate_article_urls': duplicates,
        'queue_counts': dict(queues), 'limit_exceeded': over_limit,
        'unexamined_due_to_limit': max(0, len(found) - limit),
        'candidate_inventory': found,
        'warnings': ['SOURCE_COMPLETENESS_NOT_VERIFIED',
                     'ARTICLE_SHAPE_IS_HEURISTIC', 'TITLE_CLASSIFICATION_NOT_LEGAL_CONFIRMATION'] +
                    (['CANDIDATE_LIMIT_EXCEEDED_REVIEW_REQUIRED'] if over_limit else []),
        'diagnostic_status': 'HOLD', 'comparison_allowed': False,
        'complete_collection_verified': False, 'legal_amendment_confirmed': False,
        'rms_modified': False,
    }

def main(argv=None):
    ap = argparse.ArgumentParser(description='Offline v0.9 prototype - no RMS writes or live fetching')
    ap.add_argument('--offline-html', required=True)
    ap.add_argument('--output', required=True, help='New JSON path, NEVER overwritten')
    ap.add_argument('--limit', type=int, default=DEFAULT_LIMIT)
    args = ap.parse_args(argv)
    try:
        src = Path(args.offline_html)
        dest = Path(args.output)
        if src.resolve() == dest.resolve(): raise ValueError('OUTPUT_EQUALS_INPUT')
        if not src.is_file(): raise ValueError('INPUT_MISSING')
        if src.stat().st_size > MAX_HTML_BYTES: raise ValueError('HTML_SIZE_LIMIT_EXCEEDED')
        report = analyze(src.read_bytes(), args.limit)
        with dest.open('x', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print('Article-shape candidates:', report['article_shape_candidates'])
        print('Limit exceeded:', str(report['limit_exceeded']).lower())
        print('Queue counts:', report['queue_counts'])
        print('Diagnostic: HOLD; comparison allowed: false')
        print('Saved:', dest)
        return 0
    except (OSError, ValueError) as exc:
        print('FAIL-CLOSED:', exc, file=sys.stderr)
        return 1
if __name__ == '__main__':
    sys.exit(main())
