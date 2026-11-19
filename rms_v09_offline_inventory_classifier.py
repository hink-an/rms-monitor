#!/usr/bin/env python3
"""RMS offline inventory diagnostic v0.1.

Reads an EXISTING v0.9 Live Probe JSON. Never accesses network, writes RMS
state, determines legal status, or authorizes comparison. Outputs HOLD only.
URL shape is heuristic; uncertain shapes are retained for human review.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ARTICLE_PRESS = re.compile(r"/press/press_[0-9]+\.html\Z")
ARTICLE_LEGACY = re.compile(r"/press/[0-9]+_[0-9]+\.html\Z")
ARCHIVE_MONTH = re.compile(r"/press/([0-9]{4})(0[1-9]|1[0-2])\.html\Z")
ARCHIVE_TOP = "/press/index.html"
QUEUES = {"FORMAL_REVIEW_CANDIDATE_UNVERIFIED", "REFERENCE_CANDIDATE_UNVERIFIED", "OTHER_UNVERIFIED"}


def group_url(url):
    if not isinstance(url, str):
        return "UNRECOGNIZED_REVIEW_REQUIRED"
    u = urlsplit(url)
    if u.scheme != 'https' or u.hostname != 'www.env.go.jp' or u.port not in (None, 443) or u.username or u.password or u.query or u.fragment:
        return "UNRECOGNIZED_REVIEW_REQUIRED"
    p = u.path
    if p == ARCHIVE_TOP:
        return "INDEX_TOP"
    if ARCHIVE_MONTH.fullmatch(p):
        return "ARCHIVE_MONTH"
    if ARTICLE_PRESS.fullmatch(p):
        return "ARTICLE_SHAPE_PRESS_UNVERIFIED"
    if ARTICLE_LEGACY.fullmatch(p):
        return "ARTICLE_SHAPE_LEGACY_UNVERIFIED"
    return "UNRECOGNIZED_REVIEW_REQUIRED"


def diagnose(data):
    if not isinstance(data, dict) or data.get('tool') != 'rms_env_live_probe_v09' or data.get('diagnostic_status') != 'HOLD' or data.get('comparison_allowed') is not False or data.get('complete_collection_verified') is not False or data.get('legal_amendment_confirmed') is not False or data.get('rms_modified') is not False:
        raise ValueError('UNSAFE_OR_UNEXPECTED_INPUT_REPORT')
    inventory = data.get('candidate_inventory')
    if not isinstance(inventory, list) or not inventory or len(inventory) != data.get('article_shape_candidates'):
        raise ValueError('INVENTORY_COUNT_MISMATCH')
    classified = []
    urls = set()
    for item in inventory:
        if not isinstance(item, dict) or not isinstance(item.get('url'), str) or not isinstance(item.get('title'), str) or item.get('queue') not in QUEUES or item.get('verified') is not False:
            raise ValueError('INVALID_CANDIDATE_ENTRY')
        url = item['url']
        if url in urls:
            raise ValueError('DUPLICATE_URL_IN_INPUT')
        urls.add(url)
        classified.append({'url': url, 'title': item['title'], 'original_queue': item['queue'], 'url_group': group_url(url), 'verified': False})
    groups = dict(Counter(x['url_group'] for x in classified))
    articles = [x for x in classified if x['url_group'].startswith('ARTICLE_SHAPE_')]
    archives = [x for x in classified if x['url_group'] in ('INDEX_TOP', 'ARCHIVE_MONTH')]
    unknown = [x for x in classified if x['url_group'] == 'UNRECOGNIZED_REVIEW_REQUIRED']
    return {
        'tool': 'rms_v09_offline_inventory_classifier_v01',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_tool': data['tool'], 'source_checked_at_utc': data.get('checked_at_utc'),
        'original_candidate_count': len(classified), 'url_group_counts': groups,
        'article_shape_count': len(articles), 'archive_index_count': len(archives), 'unknown_shape_count': len(unknown),
        'article_shape_queue_counts': dict(Counter(x['original_queue'] for x in articles)),
        'article_shape_over_100': len(articles) > 100,
        'all_candidates': classified, 'article_shape_candidates': articles,
        'archive_index_candidates': archives, 'unknown_shape_candidates': unknown,
        'warnings': ['URL_SHAPES_ARE_HEURISTICS_NOT_PAGE_TYPE_PROOF', 'TITLE_CLASSIFICATIONS_ARE_UNVERIFIED',
                     'ARTICLE_BODY_AND_ATTACHMENTS_NOT_FETCHED', 'SOURCE_COMPLETENESS_NOT_VERIFIED',
                     'NEVER_EXCLUDE_UNCLASSIFIED_INFORMATION_AS_LEGALLY_IRRELEVANT'],
        'diagnostic_status': 'HOLD', 'comparison_allowed': False,
        'complete_collection_verified': False, 'legal_amendment_confirmed': False,
        'rms_modified': False, 'network_accessed': False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description='Offline-only inspection of a v0.9 Live Probe JSON; never changes RMS.')
    p.add_argument('--input', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args(argv)
    try:
        if args.input.resolve() == args.output.resolve():
            raise ValueError('INPUT_OUTPUT_MUST_DIFFER')
        if args.input.stat().st_size > 10 * 1024 * 1024:
            raise ValueError('INPUT_TOO_LARGE')
        result = diagnose(json.loads(args.input.read_text(encoding='utf-8')))
        with args.output.open('x', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print('Diagnostic: HOLD / comparison disabled')
        print('URL groups:', result['url_group_counts'])
        print('Article-shaped:', result['article_shape_count'])
        print('Unrecognized:', result['unknown_shape_count'])
        return 1  # HOLD is NOT approval for automatic comparison/registration
    except (OSError, ValueError, UnicodeError, TypeError, json.JSONDecodeError) as exc:
        print('FAIL-CLOSED:', type(exc).__name__, str(exc), file=sys.stderr)
        return 2

if __name__ == '__main__':
    sys.exit(main())
