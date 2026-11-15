#!/usr/bin/env python3
"""RMS v0.9 standalone, read-only environmental press-page probe.

Investigative output ONLY. Does not change RMS, baselines or comparison state.
A title or URL is never proof of a legal amendment. Collection completeness
is never established by this probe. Outputs are always HOLD/FAIL, never PASS.

Default is OFFLINE. Live network access requires explicit --live.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

SOURCE_URL = 'https://www.env.go.jp/press/'
HOST = 'www.env.go.jp'
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT = 30
LIMIT = 100
ARTICLE_PATH = re.compile(r'^/press/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.html$', re.I)
FORMAL_WORDS = ('公布', '施行', '指定', '指定の取消', '告示', '改正', '政令', '省令')
REFERENCE_WORDS = ('案', '審議会', '検討会', 'パブリックコメント', '意見募集', '諮問', '答申', '評価')


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.html_seen = False
        self.body_seen = False
        self.active = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'html':
            self.html_seen = True
        if tag == 'body':
            self.body_seen = True
        if tag == 'a':
            self.active.append({'href': dict(attrs).get('href'), 'text': []})

    def handle_data(self, data):
        for entry in self.active:
            entry['text'].append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.active:
            entry = self.active.pop()
            self.links.append({'href': entry['href'], 'title': ' '.join(''.join(entry['text']).split())})


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        p = urllib.parse.urlsplit(newurl)
        if self.count > MAX_REDIRECTS or p.scheme != 'https' or p.hostname != HOST or p.port not in (None, 443) or p.username or p.password:
            raise ValueError('UNSAFE_REDIRECT')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def normalize_article(href):
    if not href or not isinstance(href, str):
        return None
    candidate = urllib.parse.urljoin(SOURCE_URL, href.strip())
    p = urllib.parse.urlsplit(candidate)
    if p.scheme != 'https' or p.hostname != HOST or p.port not in (None, 443) or p.username or p.password:
        return None
    if not ARTICLE_PATH.fullmatch(p.path):
        return None
    # Fragments and query strings do not identify a distinct press article.
    return urllib.parse.urlunsplit(('https', HOST, p.path, '', ''))


def label_title(title):
    # Reference words have precedence; no legal-status determination is made.
    if any(word in title for word in REFERENCE_WORDS):
        return 'REFERENCE_CANDIDATE_UNVERIFIED'
    if any(word in title for word in FORMAL_WORDS):
        return 'FORMAL_REVIEW_CANDIDATE_UNVERIFIED'
    return 'OTHER_UNVERIFIED'


def analyze(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError('HTML_SIZE_LIMIT_EXCEEDED')
    html = raw.decode('utf-8', 'strict')
    parser = LinkParser()
    parser.feed(html)
    parser.close()
    if not raw.strip() or not parser.html_seen or not parser.body_seen:
        raise ValueError('HTML_STRUCTURE_INVALID')
    found = []
    seen = set()
    duplicates = 0
    for order, item in enumerate(parser.links, 1):
        url = normalize_article(item['href'])
        if not url:
            continue
        if url in seen:
            duplicates += 1
            continue
        seen.add(url)
        found.append({'order': order, 'url': url, 'title': item['title'],
                      'queue': label_title(item['title']), 'verified': False})
    if not found:
        raise ValueError('NO_ARTICLE_SHAPED_LINKS')
    # Do not truncate at 100: every detected article-shaped link is accounted for.
    counts = dict(Counter(x['queue'] for x in found))
    return {'source_url': SOURCE_URL, 'checked_at_utc': datetime.now(timezone.utc).isoformat(),
            'tool': 'rms_env_live_probe_v09', 'total_anchor_links': len(parser.links),
            'article_shape_candidates': len(found), 'duplicate_article_urls': duplicates,
            'candidate_limit': LIMIT, 'limit_exceeded': len(found) > LIMIT,
            'over_limit_count': max(0, len(found)-LIMIT), 'queue_counts': counts,
            'candidate_inventory': found,
            'warnings': ['SOURCE_COMPLETENESS_NOT_VERIFIED', 'URL_PATTERN_IS_HEURISTIC',
                         'TITLE_CLASSIFICATION_NOT_LEGAL_CONFIRMATION'] +
                        (['CANDIDATE_LIMIT_EXCEEDED_REVIEW_REQUIRED'] if len(found) > LIMIT else []),
            'diagnostic_status': 'HOLD', 'comparison_allowed': False,
            'complete_collection_verified': False, 'legal_amendment_confirmed': False,
            'rms_modified': False, 'network_fetch_article_bodies': False}


def live_fetch():
    redirect = SafeRedirect()
    opener = urllib.request.build_opener(redirect)
    req = urllib.request.Request(SOURCE_URL, headers={'User-Agent': 'RMS-ReadOnly-Probe-v0.9', 'Accept': 'text/html'})
    with opener.open(req, timeout=TIMEOUT) as resp:
        final = urllib.parse.urlsplit(resp.geturl())
        if final.scheme != 'https' or final.hostname != HOST or final.port not in (None, 443):
            raise ValueError('UNEXPECTED_FINAL_URL')
        if resp.status != 200:
            raise ValueError('UNEXPECTED_HTTP_STATUS')
        if 'text/html' not in resp.headers.get('Content-Type', '').lower():
            raise ValueError('UNEXPECTED_CONTENT_TYPE')
        raw = resp.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('HTML_SIZE_LIMIT_EXCEEDED')
        return raw, redirect.count


def main(argv=None):
    ap = argparse.ArgumentParser(description='RMS v0.9 isolated read-only site probe. OFFLINE by default.')
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--offline-html', type=Path, help='Local saved HTML; NO network')
    mode.add_argument('--live', action='store_true', help='Explicitly fetch only fixed env.go.jp press page')
    ap.add_argument('--output', type=Path, required=True, help='NEW JSON output; existing files never overwritten')
    args = ap.parse_args(argv)
    try:
        if args.offline_html:
            if not args.offline_html.is_file():
                raise ValueError('INPUT_NOT_FOUND')
            if args.offline_html.stat().st_size > MAX_BYTES:
                raise ValueError('HTML_SIZE_LIMIT_EXCEEDED')
            raw = args.offline_html.read_bytes()
            redirects = None
            mode_name = 'OFFLINE'
        else:
            raw, redirects = live_fetch()
            mode_name = 'LIVE_SINGLE_PAGE'
        result = analyze(raw)
        result['mode'] = mode_name
        result['redirect_count'] = redirects
        result['html_bytes'] = len(raw)
        # Exclusive creation protects baselines and any previous output.
        with args.output.open('x', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print('Diagnostic: HOLD; comparison allowed: false')
        print('Article-shaped candidates:', result['article_shape_candidates'])
        print('Limit exceeded:', str(result['limit_exceeded']).lower())
        print('Report:', args.output)
        return 1  # HOLD is never an authorization for the next pipeline step.
    except (OSError, UnicodeError, ValueError, urllib.error.URLError) as exc:
        print('FAIL-CLOSED:', type(exc).__name__, str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
