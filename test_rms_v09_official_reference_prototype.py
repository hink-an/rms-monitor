"""Synthetic offline-only tests; no network, disk writes or RMS modification."""
import unittest
from rms_v09_official_reference_prototype import review_official_reference

SAMPLE = """政令第二十四号
プラスチックに係る資源循環の促進等に関する法律の施行期日を定める政令
内閣は、プラスチックに係る資源循環の促進等に関する法律（令和三年法律第六十号）附則第一項
の規定に基づき、この政令を制定する。
プラスチックに係る資源循環の促進等に関する法律の施行期日は、令和四年四月一日とする。"""
META = {"source_type": "官報", "source_date": "2022-01-19", "source_issue": "号外第13号", "source_page": 5}

class SafetyTests(unittest.TestCase):
    def assert_safe(self, result):
        self.assertEqual(result["status"], "HOLD")
        self.assertTrue(result["human_approval_required"])
        self.assertFalse(result["comparison_allowed"])
        self.assertFalse(result["notification_sent"])
        self.assertFalse(result["rms_modified"])
        self.assertFalse(result["legal_link_confirmed"])

    def test_complete_candidate_still_hold(self):
        r = review_official_reference(SAMPLE, manually_verified_official_copy=True, **META)
        self.assert_safe(r)
        self.assertEqual(r["issues"], ["LEGAL_LINK_REQUIRES_HUMAN_APPROVAL"])
        self.assertTrue(all(r["evidence_candidate"]["matches"].values()))

    def test_no_human_source_check_hold(self):
        r = review_official_reference(SAMPLE, **META)
        self.assert_safe(r)
        self.assertIn("OFFICIAL_COPY_NOT_HUMAN_VERIFIED", r["issues"])

    def test_wrong_law_number_hold(self):
        r = review_official_reference(SAMPLE.replace("法律第六十号", "法律第六十一号"), **META)
        self.assert_safe(r)
        self.assertIn("EVIDENCE_EXPLICIT_LAW_REFERENCE_MISSING", r["issues"])

    def test_wrong_decree_number_hold(self):
        r = review_official_reference(SAMPLE.replace("政令第二十四号", "政令第二十五号"), **META)
        self.assert_safe(r)
        self.assertIn("EVIDENCE_DECREE_NUMBER_MISSING", r["issues"])

    def test_wrong_effective_date_hold(self):
        r = review_official_reference(SAMPLE.replace("令和四年四月一日", "令和四年五月一日"), **META)
        self.assert_safe(r)
        self.assertIn("EVIDENCE_EFFECTIVE_DATE_MISSING", r["issues"])

    def test_unrelated_metadata_hold(self):
        r = review_official_reference(SAMPLE, **{**META, "source_page": 6})
        self.assert_safe(r)
        self.assertIn("SOURCE_METADATA_UNVERIFIED_OR_UNEXPECTED", r["issues"])

    def test_empty_text_hold(self):
        self.assert_safe(review_official_reference("", **META))

    def test_non_numeric_page_hold(self):
        self.assert_safe(review_official_reference(SAMPLE, **{**META, "source_page": True}))

    def test_title_alone_not_enough(self):
        r = review_official_reference("プラスチックに係る資源循環の促進等に関する法律の施行期日を定める政令", **META)
        self.assert_safe(r)
        self.assertFalse(r["evidence_candidate"]["matches"]["explicit_law_reference"])

if __name__ == "__main__":
    unittest.main()
