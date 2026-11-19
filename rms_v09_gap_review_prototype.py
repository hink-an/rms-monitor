#!/usr/bin/env python3
"""RMS v0.9 independent OFFLINE title-gap review; never a legal determination.

Reads previous HOLD title-review JSON. Adds review prompts for previously
no-signal article titles. All 477 candidates and all 114 articles are retained.
No HTTP code, no RMS access, no comparison or registration authorization.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

SOURCE_TOOL = 'rms_v09_title_review_prototype_v01'
ARTICLE_GROUPS = {'ARTICLE_SHAPE_PRESS_UNVERIFIED', 'ARTICLE_SHAPE_LEGACY_UNVERIFIED'}
# Deliberately broad: flags are human review prompts, not legal classifications.
REVIEW_CUES = {
    'PROPOSED_AREA_OR_PLAN_CHANGE': r'区域.{0,15}変更|計画.{0,15}変更|変更.{0,35}意見.{0,4}募集',
    'STATUTORY_PROCEDURE_OR_DECISION': r'裁決|大臣意見|環境影響評価|環境配慮書|準備書|行政処分|審査会',
    'INTERNATIONAL_RULE_OR_POLICY': r'条約|議定書|締約国|協定|国際会議|政府間会合|政策対話|ロードマップ',
    'ENVIRONMENTAL_BUSINESS_RELEVANCE': r'プラスチック|リサイクル|再資源化|循環型社会|脱炭素|省エネ|電池|化学|水セキュリティ|炭素市場',
}
PATTERNS = {k: re.compile(v) for k,v in REVIEW_CUES.items()}


def analyze(data):
    if not isinstance(data, dict) or data.get('tool') != SOURCE_TOOL:
        raise ValueError('UNEXPECTED_SOURCE')
    for key in ('diagnostic_status', 'comparison_allowed', 'complete_collection_verified',
                'legal_amendment_confirmed', 'rms_modified', 'network_accessed'):
        expected = 'HOLD' if key == 'diagnostic_status' else False
        if data.get(key) != expected or (key != 'diagnostic_status' and type(data.get(key)) is not bool):
            raise ValueError('UNSAFE_SOURCE_STATUS:'+key)
    all_items, articles = data.get('all_candidates'), data.get('article_review_candidates')
    if not isinstance(all_items,list) or not isinstance(articles,list):
        raise ValueError('MISSING_LISTS')
    if (type(data.get('original_candidate_count')) is not int or
        type(data.get('article_candidate_count')) is not int or
        len(all_items) != data['original_candidate_count'] or
        len(articles) != data['article_candidate_count'] or
        data.get('manual_review_required_count') != len(articles)):
        raise ValueError('COUNT_MISMATCH')
    seen=set(); source_articles={}
    for item in all_items:
        if not isinstance(item,dict): raise ValueError('BAD_INVENTORY_ENTRY')
        url=item.get('url')
        if (not isinstance(url,str) or not url.startswith('https://www.env.go.jp/')
            or url in seen or not isinstance(item.get('title'),str)
            or item.get('verified') is not False):
            raise ValueError('UNTRUSTED_INVENTORY')
        seen.add(url)
        if item.get('url_group') in ARTICLE_GROUPS: source_articles[url]=item
    if len(source_articles)!=len(articles): raise ValueError('ARTICLE_SET_MISMATCH')
    old_no_signal=0; out=[]; counts=Counter()
    seen_articles=set()
    for item in articles:
        if not isinstance(item,dict): raise ValueError('BAD_ARTICLE_ENTRY')
        url=item.get('url'); reference=source_articles.get(url)
        if url in seen_articles or reference is None: raise ValueError('ARTICLE_SET_MISMATCH')
        seen_articles.add(url)
        if (item.get('title') != reference['title'] or item.get('url_group') != reference['url_group']
            or item.get('original_queue') != reference.get('original_queue')
            or item.get('manual_review_required') is not True
            or item.get('legal_change_confirmed') is not False
            or not isinstance(item.get('review_signals'),list)
            or not all(isinstance(s,str) for s in item['review_signals'])):
            raise ValueError('ARTICLE_INCONSISTENT')
        no_signal=not item['review_signals']
        if no_signal: old_no_signal+=1
        cues=[label for label,p in PATTERNS.items() if p.search(item['title'])] if no_signal else []
        counts.update(cues)
        out.append({'url':url,'title':item['title'],'previous_no_signal':no_signal,
                    'new_review_cues':cues,'manual_review_required':True,
                    'legal_change_confirmed':False})
    if len(seen_articles)!=len(source_articles) or data.get('no_signal_count')!=old_no_signal:
        raise ValueError('NO_SIGNAL_OR_SET_MISMATCH')
    return {'tool':'rms_v09_gap_review_prototype_v01',
            'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'source_tool':SOURCE_TOOL, 'source_created_at_utc':data.get('created_at_utc'),
            'original_candidate_count':len(all_items),'article_candidate_count':len(out),
            'previous_no_signal_count':old_no_signal,
            'previous_no_signal_with_new_cues':sum(x['previous_no_signal'] and bool(x['new_review_cues']) for x in out),
            'previous_no_signal_still_without_cues':sum(x['previous_no_signal'] and not x['new_review_cues'] for x in out),
            'new_cue_counts_overlapping':dict(counts),
            'all_candidates':all_items,'article_reviews':out,
            'warnings':['TITLE_ONLY_HEURISTICS','NO_SIGNAL_DOES_NOT_MEAN_IRRELEVANT',
                        'NO_ARTICLE_BODY_OR_ATTACHMENTS_CHECKED','NO_LEGAL_CHANGE_CONFIRMED',
                        'FULL_COLLECTION_NOT_VERIFIED','ALL_ARTICLES_RETAINED_FOR_HUMAN_REVIEW'],
            'diagnostic_status':'HOLD','comparison_allowed':False,
            'complete_collection_verified':False,'legal_amendment_confirmed':False,
            'rms_modified':False,'network_accessed':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        if args.input.resolve()==args.output.resolve() or args.output.exists():
            raise ValueError('OUTPUT_MUST_BE_NEW_FILE')
        if args.input.stat().st_size>10*1024*1024:raise ValueError('INPUT_TOO_LARGE')
        result=analyze(json.loads(args.input.read_text(encoding='utf-8')))
        with args.output.open('x',encoding='utf-8') as f:
            json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
        print('HOLD / comparison prohibited; articles:',result['article_candidate_count'])
        return 1
    except (OSError,ValueError,TypeError,UnicodeError) as exc:
        print('FAIL-CLOSED:',type(exc).__name__,str(exc),file=sys.stderr)
        return 2

if __name__=='__main__':sys.exit(main())
