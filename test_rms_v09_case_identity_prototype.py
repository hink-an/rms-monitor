"""Offline synthetic tests for experimental RMS amendment identity review."""
import unittest
from dataclasses import replace
from rms_v09_case_identity_prototype import Amendment, EffectiveDateEvidence, make_case_key, review_effective_date_updates


def amendment(doc="2026-LAW-17"):
    return Amendment("廃棄物処理法", doc, "2026-11-19", "https://example.go.jp/official/amend", True, True, "排出事業者の手続変更")


def effective(provision="section-1", date="2027-04-01", target="2026-LAW-17", source="2027-DECREE-2"):
    return EffectiveDateEvidence(source, "https://example.go.jp/official/decree", True, target, True, provision, date, True)


def review(items=None, prev=None, doc="2026-LAW-17", amendment_obj=None):
    return review_effective_date_updates(amendment=amendment_obj or amendment(), evidence=items or [effective()], previous_segments={} if prev is None else prev, previous_case_document_id=doc)


class SafetyTests(unittest.TestCase):
    def test_01_same_law_separate_amendments(self):
        self.assertNotEqual(make_case_key(amendment("2026-LAW-17"))["case_key"], make_case_key(amendment("2026-LAW-18"))["case_key"])

    def test_02_same_amendment_stable_identity(self):
        self.assertEqual(make_case_key(amendment())["case_key"], make_case_key(amendment())["case_key"])

    def test_03_unreviewed_amendment_holds(self):
        self.assertEqual(make_case_key(replace(amendment(), human_reviewed=False))["status"], "HOLD")

    def test_04_undecided_amendment_holds(self):
        self.assertEqual(make_case_key(replace(amendment(), formally_decided=False))["status"], "HOLD")

    def test_05_missing_doc_number_holds(self):
        self.assertEqual(make_case_key(replace(amendment(), amendment_document_id=""))["status"], "HOLD")

    def test_06_invalid_promulgation_date_holds(self):
        self.assertEqual(make_case_key(replace(amendment(), promulgation_date="2026-02-30"))["status"], "HOLD")

    def test_07_unofficial_url_holds(self):
        self.assertEqual(make_case_key(replace(amendment(), official_url="http://example.org"))["status"], "HOLD")

    def test_08_later_date_can_link_to_case(self):
        r = review()
        self.assertEqual(r["status"], "REVIEW_REQUIRED")
        self.assertEqual(r["proposed_changes"][0]["kind"], "EFFECTIVE_DATE_CONFIRMED")

    def test_09_different_amendment_target_holds(self):
        self.assertEqual(review(items=[effective(target="2026-LAW-18")])["status"], "HOLD")

    def test_10_reference_not_verified_holds(self):
        self.assertEqual(review(items=[replace(effective(), reference_confirmed_in_official_text=False)])["status"], "HOLD")

    def test_11_unreviewed_evidence_holds(self):
        self.assertEqual(review(items=[replace(effective(), human_reviewed=False)])["status"], "HOLD")

    def test_12_multiple_provisions_kept(self):
        r = review(items=[effective(), effective("section-2", "2028-04-01")])
        self.assertEqual(len(r["proposed_changes"]), 2)

    def test_13_date_change_is_separate_proposal(self):
        r = review(prev={"section-1": "2027-04-01"}, items=[effective(date="2027-05-01")])
        self.assertEqual(r["proposed_changes"][0]["kind"], "EFFECTIVE_DATE_CHANGED")

    def test_14_duplicate_same_date_no_proposal(self):
        r = review(prev={"section-1": "2027-04-01"})
        self.assertEqual(r["status"], "NO_CHANGE_REVIEWED")
        self.assertEqual(r["proposed_changes"], [])

    def test_15_duplicate_evidence_deduplicated(self):
        r = review(items=[effective(), effective()])
        self.assertEqual(len(r["proposed_changes"]), 1)

    def test_16_conflicting_dates_hold(self):
        r = review(items=[effective(), effective(date="2028-04-01")])
        self.assertEqual(r["status"], "HOLD")

    def test_17_missing_previous_segment_holds(self):
        r = review(prev={"section-1": "2027-04-01", "section-2": "2028-04-01"})
        self.assertEqual(r["status"], "HOLD")

    def test_18_unknown_previous_state_holds(self):
        r = review_effective_date_updates(amendment=amendment(), evidence=[effective()], previous_segments=None, previous_case_document_id="2026-LAW-17")
        self.assertEqual(r["status"], "HOLD")

    def test_19_previous_identity_mismatch_holds(self):
        self.assertEqual(review(doc="2026-LAW-99")["status"], "HOLD")

    def test_20_invalid_effective_date_holds(self):
        self.assertEqual(review(items=[effective(date="2027-02-30")])["status"], "HOLD")

    def test_21_missing_provision_holds(self):
        self.assertEqual(review(items=[effective(provision="")])["status"], "HOLD")

    def test_22_no_network_or_rms_changes(self):
        r = review()
        self.assertIs(r["notification_sent"], False)
        self.assertIs(r["rms_modified"], False)
        self.assertIs(r["comparison_allowed"], False)
        self.assertIs(r["human_approval_required"], True)

    def test_23_missing_evidence_holds(self):
        r = review_effective_date_updates(amendment=amendment(), evidence=[], previous_segments={}, previous_case_document_id="2026-LAW-17")
        self.assertEqual(r["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
