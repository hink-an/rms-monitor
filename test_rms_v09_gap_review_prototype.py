"""Synthetic-only offline tests for RMS v0.9 title-gap review."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import rms_v09_gap_review_prototype as m


def fixture():
    articles = [
        ('https://www.env.go.jp/press/press_00001.html','公園区域の変更に関する意見の募集',[]),
        ('https://www.env.go.jp/press/press_00002.html','表彰式のお知らせ',[]),
        ('https://www.env.go.jp/press/press_00003.html','法律改正案に関する検討会',['POSSIBLE_LEGAL_CHANGE_REVIEW']),
    ]
    all_items=[]; reviews=[]
    for u,t,flags in articles:
        all_items.append({'url':u,'title':t,'original_queue':'OTHER_UNVERIFIED',
                          'url_group':'ARTICLE_SHAPE_PRESS_UNVERIFIED','verified':False})
        reviews.append({'url':u,'title':t,'original_queue':'OTHER_UNVERIFIED',
                        'url_group':'ARTICLE_SHAPE_PRESS_UNVERIFIED','review_signals':flags,
                        'manual_review_required':True,'legal_change_confirmed':False})
    return {'tool':m.SOURCE_TOOL,'diagnostic_status':'HOLD','comparison_allowed':False,
            'complete_collection_verified':False,'legal_amendment_confirmed':False,
            'rms_modified':False,'network_accessed':False,'original_candidate_count':3,
            'article_candidate_count':3,'manual_review_required_count':3,'no_signal_count':2,
            'all_candidates':all_items,'article_review_candidates':reviews}

class GapSafetyTests(unittest.TestCase):
    def test_01_all_articles_retained(self):
        r=m.analyze(fixture());self.assertEqual(len(r['article_reviews']),3)
    def test_02_no_signal_review_kept(self):
        r=m.analyze(fixture());self.assertTrue(all(x['manual_review_required'] for x in r['article_reviews']))
    def test_03_change_proposal_review_only(self):
        r=m.analyze(fixture());self.assertIn('PROPOSED_AREA_OR_PLAN_CHANGE',r['article_reviews'][0]['new_review_cues']);self.assertFalse(r['legal_amendment_confirmed'])
    def test_04_no_signal_still_kept(self):
        r=m.analyze(fixture());self.assertEqual(r['previous_no_signal_still_without_cues'],1)
    def test_05_previous_flags_not_overwritten(self):
        r=m.analyze(fixture());self.assertEqual(r['article_reviews'][2]['new_review_cues'],[])
    def test_06_hold_comparison_prohibited(self):
        r=m.analyze(fixture());self.assertEqual(r['diagnostic_status'],'HOLD');self.assertFalse(r['comparison_allowed'])
    def test_07_source_unsafe_rejected(self):
        d=fixture();d['comparison_allowed']=True
        with self.assertRaises(ValueError):m.analyze(d)
    def test_08_count_mismatch_rejected(self):
        d=fixture();d['no_signal_count']=1
        with self.assertRaises(ValueError):m.analyze(d)
    def test_09_duplicate_rejected(self):
        d=fixture();d['article_review_candidates'][1]['url']=d['article_review_candidates'][0]['url']
        with self.assertRaises(ValueError):m.analyze(d)
    def test_10_title_inconsistency_rejected(self):
        d=fixture();d['article_review_candidates'][0]['title']='altered'
        with self.assertRaises(ValueError):m.analyze(d)
    def test_11_over_100_retained(self):
        d=fixture()
        for i in range(4,116):
            u=f'https://www.env.go.jp/press/press_{i:05d}.html';t='その他のお知らせ'
            d['all_candidates'].append({'url':u,'title':t,'original_queue':'OTHER_UNVERIFIED','url_group':'ARTICLE_SHAPE_PRESS_UNVERIFIED','verified':False})
            d['article_review_candidates'].append({'url':u,'title':t,'original_queue':'OTHER_UNVERIFIED','url_group':'ARTICLE_SHAPE_PRESS_UNVERIFIED','review_signals':[],'manual_review_required':True,'legal_change_confirmed':False})
        d.update(original_candidate_count=115,article_candidate_count=115,manual_review_required_count=115,no_signal_count=114)
        self.assertEqual(len(m.analyze(d)['article_reviews']),115)
    def test_12_input_unchanged(self):
        d=fixture();before=copy.deepcopy(d);m.analyze(d);self.assertEqual(d,before)
    def test_13_cli_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'src.json';b=Path(td)/'existing.json'
            a.write_text(json.dumps(fixture()));b.write_text('untouched')
            self.assertEqual(m.main(['--input',str(a),'--output',str(b)]),2)
            self.assertEqual(b.read_text(),'untouched')
    def test_14_cli_new_file_returns_hold(self):
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'src.json';b=Path(td)/'new.json'
            a.write_text(json.dumps(fixture()))
            self.assertEqual(m.main(['--input',str(a),'--output',str(b)]),1)
            self.assertEqual(json.loads(b.read_text())['diagnostic_status'],'HOLD')
    def test_15_no_network_functions_called(self):
        with patch('socket.socket.connect',side_effect=AssertionError('network call')):
            self.assertEqual(len(m.analyze(fixture())['article_reviews']),3)

if __name__=='__main__':unittest.main()
