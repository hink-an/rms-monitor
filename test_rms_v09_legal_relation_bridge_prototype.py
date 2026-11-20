"""Synthetic offline-only tests; never access network, disk, or RMS."""
import unittest
from dataclasses import replace
from rms_v09_legal_relation_bridge_prototype import DocumentEvidence, review_relation


def sample(**overrides):
    args = dict(
        source=DocumentEvidence('2022-DECREE-24', 'EFFECTIVE_DATE_DECREE', 'https://example.go.jp/decree', 'Kanpo example', True),
        target=DocumentEvidence('2021-LAW-60', 'NEW_ENACTMENT', 'https://example.go.jp/law', 'Kanpo example', True),
        relation_kind='SETS_EFFECTIVE_DATE_FOR',
        explicit_reference_human_checked=True,
        official_reference_text='Example reference text; NOT authenticated by software',
        effective_date='2022-04-01', source_page=5,
    )
    args.update(overrides)
    return review_relation(**args)


class BridgeSafetyTests(unittest.TestCase):
    def test_01_complete_candidate_still_hold(self):
        r = sample()
        self.assertEqual(r['status'], 'HOLD')
        self.assertIsNotNone(r['relation_candidate'])
        self.assertFalse(r['legal_link_confirmed'])

    def test_02_no_automation(self):
        r = sample()
        self.assertFalse(r['comparison_allowed'])
        self.assertFalse(r['notification_sent'])
        self.assertFalse(r['rms_modified'])
        self.assertTrue(r['human_approval_required'])

    def test_03_missing_reference_holds(self):
        self.assertIsNone(sample(official_reference_text='')['relation_candidate'])

    def test_04_unverified_reference_holds(self):
        self.assertIsNone(sample(explicit_reference_human_checked=False)['relation_candidate'])

    def test_05_unchecked_source_holds(self):
        doc = DocumentEvidence('2022-DECREE-24', 'EFFECTIVE_DATE_DECREE', 'https://example.go.jp/d', 'Kanpo', False)
        self.assertIsNone(sample(source=doc)['relation_candidate'])

    def test_06_wrong_kind_holds(self):
        doc = DocumentEvidence('2022-DECREE-24', 'AMENDMENT', 'https://example.go.jp/d', 'Kanpo', True)
        self.assertIn('RELATION_DOCUMENT_KINDS_MISMATCH', sample(source=doc)['issues'])

    def test_07_unknown_relation_holds(self):
        self.assertIsNone(sample(relation_kind='IDENTICAL_TO')['relation_candidate'])

    def test_08_invalid_date_holds(self):
        self.assertIsNone(sample(effective_date='2022-02-30')['relation_candidate'])

    def test_09_missing_page_holds(self):
        self.assertIsNone(sample(source_page=None)['relation_candidate'])

    def test_10_wrong_document_id_holds(self):
        doc = DocumentEvidence('UNKNOWN', 'NEW_ENACTMENT', 'https://example.go.jp/l', 'Kanpo', True)
        self.assertIsNone(sample(target=doc)['relation_candidate'])

    def test_11_self_reference_holds(self):
        doc = DocumentEvidence('2022-DECREE-24', 'NEW_ENACTMENT', 'https://example.go.jp/l', 'Kanpo', True)
        self.assertIsNone(sample(target=doc)['relation_candidate'])

    def test_12_new_enactment_not_amendment(self):
        self.assertIn('RELATION_DOCUMENT_KINDS_MISMATCH', sample(relation_kind='AMENDS')['issues'])

    def test_13_candidate_keeps_document_types(self):
        c = sample()['relation_candidate']
        self.assertEqual(c['source_document_kind'], 'EFFECTIVE_DATE_DECREE')
        self.assertEqual(c['target_document_kind'], 'NEW_ENACTMENT')


if __name__ == '__main__':
    unittest.main()
