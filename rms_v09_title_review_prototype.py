#!/usr/bin/env python3
"""Offline-only title review prototype for RMS v0.9 inventory diagnostics.

Heuristic review flags are NOT legal classifications. Every article candidate is
retained for review, including those with no matching keyword. No network access,
no RMS modification, and no comparison/registration approval.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

EXPECTED_TOOL = 'rms_v09_offline_inventory_classifier_v01'
GROUPS = {'ARTICLE_SHAPE_PRESS_UNVERIFIED', 'ARTICLE_SHAPE_LEGACY_UNVERIFIED'}
QUEUES = {'FORMAL_REVIEW_CANDIDATE_UNVERIFIED', 'REFERENCE_CANDIDATE_UNVERIFIED', 'OTHER_UNVERIFIED'}
# These broad expressions generate reasons for HUMAN REVIEW, never approvals.
SIGNALS = {
    'POSSIBLE_LEGAL_CHANGE_REVIEW': r'法令|法律|政令|省令|条例|施行規則|告示|改正|改定|制定|廃止|施行|公布|規制|基準|指定解除|指定の解除|指定|規則',
    'POSSIBLE_ADMINISTRATIVE_ACTION_REVIEW': r'認定|認証|許可|承認|登録|指定|解除|区域変更|区域の変更',
    'POSSIBLE_PROPOSAL_OR_CONSULTATION_REVIEW': r'意見募集|パブリックコメント|改正案|検討会|審議会|答申|諮問|案について',
    'POSSIBLE_ENVIRONMENTAL_COMPLIANCE_REVIEW': r'廃棄物|資源循環|化学物質|有害|排出|温室効果ガス|石綿|アスベスト|PCB|水質|大気|土壌|フロン|リチウムイオン電池',
}
PATTERNS = {key: re.compile(value) for key, value in SIGNALS.items()}


def analyze(data):
    if not isinstance(data, dict) or data.get('tool') != EXPECTED_TOOL:
        raise ValueError('UNEXPECTED_SOURCE_TOOL')
    for key in ('diagnostic_status', 'comparison_allowed', 'complete_collection_verified',
                'legal_amendment_confirmed', 'rms_modified', 'network_accessed'):
        expected = 'HOLD' if key == 'diagnostic_status' else False
        if data.get(key) != expected or (key != 'diagnostic_status' and type(data.get(key)) is not bool):
            raise ValueError('UNSAFE_SOURCE_STATUS:' + key)
    inventory = data.get('all_candidates')
    articles = data.get('article_shape_candidates')
    if not isinstance(inventory, list) or not isinstance(articles, list) or not inventory:
        raise ValueError('MISSING_INVENTORY')
    if len(inventory) != data.get('original_candidate_count') or len(articles) != data.get('article_shape_count'):
        raise ValueError('COUNT_MISMATCH')
    seen = set()
    article_urls = set()
    reviewed = []
    for item in inventory:
        if not isinstance(item, dict):
            raise ValueError('BAD_CANDIDATE')
        url, title, group, queue = (item.get(k) for k in ('url', 'title', 'url_group', 'original_queue'))
        if (not isinstance(url, str) or not url.startswith('https://www.env.go.jp/')
                or not isinstance(title, str) or not isinstance(group, str)
                or queue not in QUEUES or item.get('verified') is not False or url in seen):
            raise ValueError('BAD_OR_DUPLICATE_CANDIDATE')
        seen.add(url)
        if group in GROUPS:
            article_urls.add(url)
            flags = [name for name, pattern in PATTERNS.items() if pattern.search(title)]
            reviewed.append({'url': url, 'title': title, 'original_queue': queue,
                             'url_group': group, 'review_signals': flags,
                             'manual_review_required': True,
                             'legal_change_confirmed': False})
    if len(article_urls) != len(articles) or any(
            not isinstance(item, dict) or item.get('url') not in article_urls for item in articles):
        raise ValueError('ARTICLE_SET_MISMATCH')
    if len({item['url'] for item in articles}) != len(articles):
        raise ValueError('DUPLICATE_ARTICLE_LIST')
    # Retain the full input inventory unchanged in the output for auditability.
    counts = Counter(flag for item in reviewed for flag in item['review_signals'])
    return {
        'tool': 'rms_v09_title_review_prototype_v01',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_tool': EXPECTED_TOOL,
        'source_created_at_utc': data.get('created_at_utc'),
        'original_candidate_count': len(inventory), 'article_candidate_count': len(reviewed),
        'manual_review_required_count': len(reviewed),
        'no_signal_count': sum(not x['review_signals'] for x in reviewed),
        'review_signal_counts_overlapping': dict(counts),
        'all_candidates': inventory, 'article_review_candidates': reviewed,
        'warnings': ['HEURISTIC_TITLE_SIGNALS_ONLY', 'NO_SIGNAL_IS_NOT_IRRELEVANT',
                     'NO_ARTICLE_BODY_OR_ATTACHMENTS_CHECKED', 'NO_LEGAL_CHANGE_CONFIRMED',
                     'NO_COLLECTION_COMPLETENESS_CLAIM', 'ALL_ARTICLES_REQUIRE_MANUAL_REVIEW',
                     'NO_CANDIDATES_DROPPED_FOR_100_ITEM_LIMIT'],
        'diagnostic_status': 'HOLD', 'comparison_allowed': False,
        'complete_collection_verified': False, 'legal_amendment_confirmed': False,
        'rms_modified': False, 'network_accessed': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.input.resolve() == args.output.resolve() or args.output.exists():
            raise ValueError('OUTPUT_MUST_BE_NEW_FILE')
        if args.input.stat().st_size > 10 * 1024 * 1024:
            raise ValueError('INPUT_TOO_LARGE')
        result = analyze(json.loads(args.input.read_text(encoding='utf-8')))
        with args.output.open('x', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write('\n')
        print('HOLD / comparison prohibited; articles:', result['article_candidate_count'])
        return 1  # HOLD, not permission to automate comparison or registration
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        print('FAIL-CLOSED:', type(exc).__name__, str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
