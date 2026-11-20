"""Offline synthetic safety tests for candidate-only reference bridge adapter."""
import unittest
from copy import deepcopy
from rms_v09_reference_bridge_adapter_prototype import normalize_document_number, review_bridge


def evidence():
    return {
        'status': 'HOLD', 'legal_link_confirmed': False,
        'comparison_allowed': False, 'notification_sent': False, 'rms_modified': False,
        'evidence_candidate': {
            'source_type': '官報', 'source_date': '2022-01-19',
            'source_issue': '号外第13号', 'source_page': 5,
            'matches': {k: True for k in (
                'decree_number', 'decree_title', 'law_number',
                'explicit_law_reference', 'statutory_basis', 'effective_date')},
            'source_verified_by_human_assertion_only': True,
            'proposed_decree': '令和4年政令第24号',
            'proposed_law': '令和3年法律第60号',
            'proposed_effective_date': '2022-04-01',
        },
    }


def kwargs():
    return dict(
        source_official_url='https://www.example.go.jp/decree',
        target_official_url='https://www.example.go.jp/law',
        official_reference_text='令和3年法律第60号に基づく施行期日を定める',
        manually_verified_official_copy=True,
        source_human_checked=True, target_human_checked=True,
        explicit_reference_human_checked=True,
        source_document_kind='EFFECTIVE_DATE_DECREE',
        target_document_kind='NEW_ENACTMENT',
    )


class AdapterSafetyTests(unittest.TestCase):
    def test_01_good_candidate_stays_hold(self):
        result = review_bridge(evidence(), **kwargs())
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(result['issues'], ['LEGAL_RELATION_REQUIRES_AUTHORIZED_HUMAN_APPROVAL'])
        self.assertEqual(result['relation_candidate']['source_document_id'], '2022-DECREE-24')
        self.assertEqual(result['relation_candidate']['target_document_id'], '2021-LAW-60')

    def test_02_never_auto_modifies_or_notifies(self):
        r = review_bridge(evidence(), **kwargs())
        for k in ('comparison_allowed', 'notification_sent', 'rms_modified', 'legal_link_confirmed'):
            self.assertIs(r[k], False)
        self.assertIs(r['human_approval_required'], True)

    def test_03_invalid_object_holds(self):
        self.assertEqual(review_bridge(None, **kwargs())['status'], 'HOLD')

    def test_04_missing_candidate_holds(self):
        e = evidence(); del e['evidence_candidate']
        self.assertIn('EVIDENCE_CANDIDATE_MISSING', review_bridge(e, **kwargs())['issues'])

    def test_05_unexpected_approval_holds(self):
        e = evidence(); e['status'] = 'APPROVED'
        self.assertIn('OFFICIAL_RESULT_STATUS_UNEXPECTED', review_bridge(e, **kwargs())['issues'])

    def test_06_unsafe_flags_hold(self):
        e = evidence(); e['rms_modified'] = True
        self.assertIn('OFFICIAL_RESULT_SAFETY_FLAGS_UNEXPECTED', review_bridge(e, **kwargs())['issues'])

    def test_07_wrong_source_metadata_holds(self):
        e = evidence(); e['evidence_candidate']['source_page'] = 6
        self.assertIn('OFFICIAL_SOURCE_METADATA_UNEXPECTED', review_bridge(e, **kwargs())['issues'])

    def test_08_incomplete_text_checks_hold(self):
        e = evidence(); e['evidence_candidate']['matches']['law_number'] = False
        self.assertIn('OFFICIAL_TEXT_MATCHES_INCOMPLETE', review_bridge(e, **kwargs())['issues'])

    def test_09_human_verification_missing_holds(self):
        k = kwargs(); k['explicit_reference_human_checked'] = False
        self.assertIn('HUMAN_VERIFICATION_INCOMPLETE', review_bridge(evidence(), **k)['issues'])

    def test_10_document_kind_mismatch_holds(self):
        k = kwargs(); k['source_document_kind'] = 'AMENDMENT'
        self.assertIn('DOCUMENT_KIND_MISMATCH', review_bridge(evidence(), **k)['issues'])

    def test_11_no_official_reference_holds(self):
        k = kwargs(); k['official_reference_text'] = ''
        self.assertIn('OFFICIAL_REFERENCE_TEXT_MISSING', review_bridge(evidence(), **k)['issues'])

    def test_12_wrong_law_reference_holds(self):
        k = kwargs(); k['official_reference_text'] = '令和3年法律第61号に基づく'
        self.assertIn('TARGET_NUMBER_NOT_IN_REFERENCE_TEXT', review_bridge(evidence(), **k)['issues'])

    def test_13_wrong_or_missing_url_holds(self):
        k = kwargs(); k['source_official_url'] = 'http://example.com'
        self.assertIn('SOURCE_URL_INVALID', review_bridge(evidence(), **k)['issues'])

    def test_14_invalid_effective_date_holds(self):
        e = evidence(); e['evidence_candidate']['proposed_effective_date'] = '2022-02-30'
        self.assertIn('EFFECTIVE_DATE_INVALID', review_bridge(e, **kwargs())['issues'])

    def test_15_number_translation_and_reject_embedded_text(self):
        self.assertEqual(normalize_document_number('令和3年法律第60号')['internal_id'], '2021-LAW-60')
        self.assertEqual(normalize_document_number('令和4年政令第24号')['internal_id'], '2022-DECREE-24')
        self.assertEqual(normalize_document_number('本文：令和3年法律第60号')['status'], 'HOLD')

    def test_16_no_guessed_missing_number(self):
        e = evidence(); e['evidence_candidate']['proposed_decree'] = None
        self.assertIn('SOURCE_NUMBER_UNCONVERTIBLE', review_bridge(e, **kwargs())['issues'])

    def test_17_no_automatic_confirmation_from_assertion(self):
        r = review_bridge(evidence(), **kwargs())
        self.assertTrue(r['relation_candidate']['evidence_assertion_only'])
        self.assertFalse(r['legal_link_confirmed'])

    def test_18_missing_human_source_attestation_holds(self):
        e = evidence(); e['evidence_candidate']['source_verified_by_human_assertion_only'] = False
        self.assertIn('OFFICIAL_COPY_ATTESTATION_MISSING', review_bridge(e, **kwargs())['issues'])

if __name__ == '__main__':
    unittest.main()
