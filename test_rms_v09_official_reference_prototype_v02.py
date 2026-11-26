"""Offline regression and safety tests for strict candidate prototype."""
import unittest
from rms_v09_official_reference_prototype_v02 import review_official_reference
from test_rms_v09_kanpo_consistency_diagnostic import META, DECREE_24, SYNTHETIC_COMPATIBLE, LAW_TITLE, DECREE_TITLE


class StrictReferenceTests(unittest.TestCase):
    def review(self, text=DECREE_24, verified=False, **overrides):
        result = review_official_reference(text, manually_verified_official_copy=verified, **(META | overrides))
        self.assertEqual(result['status'], 'HOLD')
        self.assertIs(result['human_approval_required'], True)
        for key in ('comparison_allowed', 'notification_sent', 'rms_modified', 'legal_link_confirmed'):
            self.assertIs(result[key], False)
        return result

    def suppressed(self, result):
        for key in ('proposed_law', 'proposed_decree', 'proposed_effective_date'):
            self.assertIsNone(result['evidence_candidate'][key])

    def test_01_single_decree(self):
        r = self.review()
        self.assertEqual(r['evidence_candidate']['proposed_effective_date'], '2022-04-01')
        self.assertEqual(r['evidence_candidate']['proposed_law'], '令和3年法律第60号')
        self.assertEqual(r['evidence_candidate']['proposed_decree'], '令和4年政令第24号')

    def test_02_missing_basis(self):
        self.suppressed(self.review(DECREE_24.replace('附則第一項', '')))

    def test_03_multiple_dates(self):
        for text in (DECREE_24, SYNTHETIC_COMPATIBLE):
            with self.subTest(text=text):
                r = self.review(text + '\n別の規定は令和四年五月一日から施行する。')
                self.suppressed(r)
                self.assertIn('MULTIPLE_DATE_MENTIONS', r['issues'])

    def test_04_cross_document(self):
        first = f'政令第二十四号\n{DECREE_TITLE}\n{LAW_TITLE}（令和三年法律第六十号）附則第1項の規定に基づく。'
        second = '政令第二十五号\n別の政令の本文。\n施行期日は、令和四年四月一日とする。'
        for text in (first, first + '\n' + second, DECREE_24 + '\n' + second):
            self.suppressed(self.review(text))
        self.assertIn('MULTIPLE_DECREE_IDENTIFIERS', self.review(first + '\n' + second)['issues'])

    def test_05_unknown_boundary(self):
        for text in (DECREE_24.replace('\n', ''), '別文書\n' + DECREE_24, DECREE_24 + '\n別文書', DECREE_24.replace('附則第一項', '附則第\n一項'), DECREE_24 + '\n' + DECREE_24):
            self.suppressed(self.review(text))

    def test_06_unverified(self):
        self.assertIn('OFFICIAL_COPY_NOT_HUMAN_VERIFIED', self.review()['issues'])

    def test_07_verified(self):
        r = self.review(verified=True)
        self.assertIn('LEGAL_LINK_REQUIRES_HUMAN_APPROVAL', r['issues'])
        self.assertIs(r['evidence_candidate']['source_verified_by_human_assertion_only'], True)

    def test_08_invalid_input(self):
        for text in (None, 42, [], '', ' '):
            self.suppressed(self.review(text))
        for overrides in ({'source_page': True}, {'source_page': 0}, {'source_type': None}, {'source_date': '2022-01-20'}):
            self.suppressed(self.review(**overrides))
        for flag in ('False', 1, None):
            self.suppressed(self.review(verified=flag))

    def test_09_unsupported_variants(self):
        self.suppressed(self.review(SYNTHETIC_COMPATIBLE))
        self.suppressed(self.review(DECREE_24.replace('四月一日', '五月一日')))
        self.suppressed(self.review(DECREE_24.replace('第二十四号', '第二十五号')))

    def test_10_line_endings(self):
        self.assertEqual(self.review(DECREE_24.replace('\n', '\r\n'))['evidence_candidate']['proposed_effective_date'], '2022-04-01')


if __name__ == '__main__':
    unittest.main()
