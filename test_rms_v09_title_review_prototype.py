#!/usr/bin/env python3
"""Offline synthetic safety tests for RMS title review prototype."""
import copy
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from rms_v09_title_review_prototype import analyze, main


def sample(n=3):
    items = []
    for i in range(n):
        title = ['法律の改正案についての意見募集', '環境イベント開催', '廃棄物処理に係る指定'][i % 3]
        items.append({'url': f'https://www.env.go.jp/press/press_{i+10000}.html',
                      'title': title, 'original_queue': 'OTHER_UNVERIFIED',
                      'url_group': 'ARTICLE_SHAPE_PRESS_UNVERIFIED', 'verified': False})
    return {'tool': 'rms_v09_offline_inventory_classifier_v01', 'diagnostic_status': 'HOLD',
            'comparison_allowed': False, 'complete_collection_verified': False,
            'legal_amendment_confirmed': False, 'rms_modified': False,
            'network_accessed': False, 'all_candidates': items,
            'article_shape_candidates': list(items), 'original_candidate_count': n,
            'article_shape_count': n}


class SafetyTests(unittest.TestCase):
    def test_every_article_is_kept(self):
        result = analyze(sample())
        self.assertEqual(result['manual_review_required_count'], 3)
        self.assertTrue(all(x['manual_review_required'] for x in result['article_review_candidates']))

    def test_no_keyword_is_not_removed(self):
        result = analyze(sample())
        self.assertEqual(result['no_signal_count'], 1)
        self.assertEqual(len(result['article_review_candidates']), 3)

    def test_signals_are_overlapping_not_legal_status(self):
        result = analyze(sample())
        self.assertGreaterEqual(len(result['article_review_candidates'][0]['review_signals']), 2)
        self.assertTrue(all(not x['legal_change_confirmed'] for x in result['article_review_candidates']))

    def test_hold_no_compare_no_modification(self):
        r = analyze(sample())
        self.assertEqual(r['diagnostic_status'], 'HOLD')
        for field in ('comparison_allowed', 'complete_collection_verified', 'legal_amendment_confirmed', 'rms_modified', 'network_accessed'):
            self.assertIs(r[field], False)

    def test_more_than_100_retained(self):
        self.assertEqual(analyze(sample(114))['article_candidate_count'], 114)

    def test_dangerous_status_rejected(self):
        for field, val in [('comparison_allowed', True), ('rms_modified', True), ('diagnostic_status', 'OK')]:
            with self.subTest(field=field):
                bad = sample()
                bad[field] = val
                with self.assertRaises(ValueError):
                    analyze(bad)

    def test_count_mismatch_rejected(self):
        bad = sample()
        bad['article_shape_count'] = 10
        with self.assertRaises(ValueError):
            analyze(bad)

    def test_duplicate_rejected(self):
        bad = sample()
        bad['all_candidates'][1]['url'] = bad['all_candidates'][0]['url']
        with self.assertRaises(ValueError):
            analyze(bad)

    def test_missing_article_list_rejected(self):
        bad = sample()
        bad['article_shape_candidates'][0] = {'url': 'https://www.env.go.jp/press/unknown.html'}
        with self.assertRaises(ValueError):
            analyze(bad)

    def test_output_file_must_not_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            source, output = Path(td) / 'in.json', Path(td) / 'out.json'
            source.write_text(json.dumps(sample()), encoding='utf-8')
            output.write_text('KEEP', encoding='utf-8')
            self.assertEqual(main(['--input', str(source), '--output', str(output)]), 2)
            self.assertEqual(output.read_text(), 'KEEP')
            self.assertEqual(main(['--input', str(source), '--output', str(source)]), 2)

    def test_hold_exit_code_and_no_source_change(self):
        with tempfile.TemporaryDirectory() as td:
            source, output = Path(td) / 'in.json', Path(td) / 'out.json'
            source.write_text(json.dumps(sample()), encoding='utf-8')
            original = source.read_bytes()
            self.assertEqual(main(['--input', str(source), '--output', str(output)]), 1)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(json.loads(output.read_text())['diagnostic_status'], 'HOLD')

    def test_network_functions_not_used(self):
        with patch.object(socket, 'create_connection', side_effect=AssertionError('network attempted')):
            with patch.object(socket.socket, 'connect', side_effect=AssertionError('network attempted')):
                analyze(sample())


if __name__ == '__main__':
    unittest.main()
