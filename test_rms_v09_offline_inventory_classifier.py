#!/usr/bin/env python3
"""Offline, non-destructive safety tests for rms_v09_offline_inventory_classifier.py.

Place this file next to the diagnostic program. Runs only synthetic fixtures;
never downloads content or writes RMS files. A test success is NOT evidence
that legal changes were comprehensively discovered.
"""
import copy
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

TARGET = Path(__file__).with_name('rms_v09_offline_inventory_classifier.py')


def load_target():
    if not TARGET.is_file():
        raise FileNotFoundError('Place rms_v09_offline_inventory_classifier.py next to this test file')
    spec = importlib.util.spec_from_file_location('rms_inventory_classifier_under_test', TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def item(path, queue='OTHER_UNVERIFIED'):
    return {'url': 'https://www.env.go.jp' + path, 'title': 'Synthetic test only',
            'queue': queue, 'verified': False}


def report(items):
    return {'tool': 'rms_env_live_probe_v09', 'diagnostic_status': 'HOLD',
            'comparison_allowed': False, 'complete_collection_verified': False,
            'legal_amendment_confirmed': False, 'rms_modified': False,
            'article_shape_candidates': len(items), 'candidate_inventory': items}


class OfflineInventorySafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = load_target()

    def test_01_url_categories_are_only_shapes(self):
        cases = [('/press/press_123.html', 'ARTICLE_SHAPE_PRESS_UNVERIFIED'),
                 ('/press/123_456.html', 'ARTICLE_SHAPE_LEGACY_UNVERIFIED'),
                 ('/press/202611.html', 'ARCHIVE_MONTH'),
                 ('/press/index.html', 'INDEX_TOP'),
                 ('/unknown.html', 'UNRECOGNIZED_REVIEW_REQUIRED'),
                 ('/press/202613.html', 'UNRECOGNIZED_REVIEW_REQUIRED')]
        for path, expected in cases:
            with self.subTest(path=path):
                self.assertEqual(self.app.group_url('https://www.env.go.jp' + path), expected)

    def test_02_untrusted_urls_are_not_recognized(self):
        urls = ['http://www.env.go.jp/press/press_1.html',
                'https://www.env.go.jp.evil.test/press/press_1.html',
                'https://www.env.go.jp/press/press_1.html?x=1',
                'https://www.env.go.jp/press/press_1.html#section',
                'https://u:p@www.env.go.jp/press/press_1.html',
                'https://www.env.go.jp:444/press/press_1.html',
                'https://www.env.go.jp/press/press_1.html/extra']
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.app.group_url(url), 'UNRECOGNIZED_REVIEW_REQUIRED')

    def test_03_all_candidates_retained_and_unclassified_reviewed(self):
        entries = [item('/press/press_1.html', 'FORMAL_REVIEW_CANDIDATE_UNVERIFIED'),
                   item('/press/12_34.html', 'REFERENCE_CANDIDATE_UNVERIFIED'),
                   item('/press/202611.html'), item('/press/index.html'),
                   item('/something_new.html')]
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('network used')), \
             patch.object(socket, 'create_connection', side_effect=AssertionError('network used')):
            out = self.app.diagnose(report(entries))
        self.assertEqual(out['original_candidate_count'], 5)
        self.assertEqual(out['article_shape_count'], 2)
        self.assertEqual(out['archive_index_count'], 2)
        self.assertEqual(out['unknown_shape_count'], 1)
        self.assertEqual(len(out['all_candidates']), 5)
        self.assertEqual(len({x['url'] for x in out['all_candidates']}), 5)
        self.assertEqual(out['unknown_shape_candidates'][0]['url'], entries[-1]['url'])
        self.assertTrue(all(x['verified'] is False for x in out['all_candidates']))

    def test_04_unsafe_input_flags_rejected(self):
        base = report([item('/press/press_1.html')])
        for key, value in [('tool', 'other'), ('diagnostic_status', 'OK'),
                           ('comparison_allowed', True), ('comparison_allowed', 0),
                           ('complete_collection_verified', True),
                           ('legal_amendment_confirmed', True), ('rms_modified', True)]:
            with self.subTest(key=key, value=value):
                altered = copy.deepcopy(base)
                altered[key] = value
                with self.assertRaises(ValueError):
                    self.app.diagnose(altered)

    def test_05_bad_inventory_count_or_entries_rejected(self):
        base = report([item('/press/press_1.html')])
        bad = []
        missing = copy.deepcopy(base)
        missing['candidate_inventory'] = []
        bad.append(missing)
        mismatch = copy.deepcopy(base)
        mismatch['article_shape_candidates'] = 99
        bad.append(mismatch)
        duplicate = report([item('/press/press_1.html'), item('/press/press_1.html')])
        bad.append(duplicate)
        verified = copy.deepcopy(base)
        verified['candidate_inventory'][0]['verified'] = True
        bad.append(verified)
        wrong_queue = copy.deepcopy(base)
        wrong_queue['candidate_inventory'][0]['queue'] = 'APPROVED'
        bad.append(wrong_queue)
        for i, altered in enumerate(bad):
            with self.subTest(case=i), self.assertRaises(ValueError):
                self.app.diagnose(altered)

    def test_06_hard_safety_flags_and_warnings_remain(self):
        out = self.app.diagnose(report([item('/press/press_1.html')]))
        self.assertEqual(out['diagnostic_status'], 'HOLD')
        for flag in ('comparison_allowed', 'complete_collection_verified',
                     'legal_amendment_confirmed', 'rms_modified', 'network_accessed'):
            self.assertIs(out[flag], False, flag)
        self.assertIn('SOURCE_COMPLETENESS_NOT_VERIFIED', out['warnings'])
        self.assertIn('NEVER_EXCLUDE_UNCLASSIFIED_INFORMATION_AS_LEGALLY_IRRELEVANT', out['warnings'])

    def test_07_over_100_still_hold_and_no_truncation(self):
        entries = [item('/press/press_%d.html' % i) for i in range(101)]
        out = self.app.diagnose(report(entries))
        self.assertEqual(out['article_shape_count'], 101)
        self.assertEqual(len(out['all_candidates']), 101)
        self.assertTrue(out['article_shape_over_100'])
        self.assertIs(out['comparison_allowed'], False)

    def test_08_cli_creates_only_new_output_and_returns_hold_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.json'
            output = root / 'diagnostic.json'
            source.write_text(json.dumps(report([item('/press/press_1.html')])), encoding='utf-8')
            before = source.read_bytes()
            with patch.object(socket.socket, 'connect', side_effect=AssertionError('network used')), \
                 patch.object(socket, 'create_connection', side_effect=AssertionError('network used')):
                code = self.app.main(['--input', str(source), '--output', str(output)])
            self.assertEqual(code, 1)  # HOLD deliberately is not success/approval
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['diagnostic_status'], 'HOLD')
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['diagnostic.json', 'source.json'])

    def test_09_cli_refuses_overwrite_and_same_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.json'
            output = root / 'existing.json'
            source.write_text(json.dumps(report([item('/press/press_1.html')])), encoding='utf-8')
            output.write_text('DO NOT REPLACE', encoding='utf-8')
            self.assertEqual(self.app.main(['--input', str(source), '--output', str(output)]), 2)
            self.assertEqual(output.read_text(encoding='utf-8'), 'DO NOT REPLACE')
            before = source.read_bytes()
            self.assertEqual(self.app.main(['--input', str(source), '--output', str(source)]), 2)
            self.assertEqual(source.read_bytes(), before)

    def test_10_cli_rejects_malformed_and_oversized_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'bad.json'
            output = root / 'new.json'
            source.write_text('{ invalid json', encoding='utf-8')
            self.assertEqual(self.app.main(['--input', str(source), '--output', str(output)]), 2)
            self.assertFalse(output.exists())
            source.write_bytes(b' ' * (10 * 1024 * 1024 + 1))
            self.assertEqual(self.app.main(['--input', str(source), '--output', str(output)]), 2)
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
