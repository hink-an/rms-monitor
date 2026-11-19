"""Offline-only regression checks for the unapproved 2021 plastic law evidence fixture.

Never treats a historical example as a verified legal determination. Does not
perform network calls, send notices, or mutate the RMS application.
"""
import json
import unittest
from pathlib import Path

from rms_v09_case_identity_prototype import (
    Amendment,
    EffectiveDateEvidence,
    make_case_key,
    review_effective_date_updates,
)

FIXTURE = Path(__file__).with_name("rms_v09_case_identity_real_example_2021_plastic_law.json")


class RealExampleOfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def amendment(self):
        fields = Amendment.__dataclass_fields__
        return Amendment(**{k: self.fixture["amendment"][k] for k in fields})

    def evidence(self):
        fields = EffectiveDateEvidence.__dataclass_fields__
        return [EffectiveDateEvidence(**{k: item[k] for k in fields})
                for item in self.fixture["effective_date_evidence"]]

    def evaluate(self):
        p = self.fixture["prototype_preconditions"]
        return review_effective_date_updates(
            amendment=self.amendment(), evidence=self.evidence(),
            previous_segments=p["previous_segments"],
            previous_case_document_id=p["previous_case_document_id"],
        )

    def test_01_evidence_is_explicitly_unapproved(self):
        self.assertEqual(self.fixture["review_state"], "HOLD_PENDING_HUMAN_REVIEW")
        self.assertFalse(self.fixture["amendment"]["human_reviewed"])
        self.assertFalse(self.fixture["effective_date_evidence"][0]["human_reviewed"])
        self.assertFalse(self.fixture["effective_date_evidence"][0]["reference_confirmed_in_official_text"])

    def test_02_fixture_identifiers_preserved(self):
        self.assertEqual(self.fixture["amendment"]["official_document_number"], "令和3年法律第60号")
        self.assertEqual(self.fixture["effective_date_evidence"][0]["official_document_number"], "令和4年政令第24号")
        self.assertEqual(self.fixture["effective_date_evidence"][0]["amendment_document_id_referenced"],
                         self.fixture["amendment"]["amendment_document_id"])

    def test_03_new_enactment_limitation_is_documented(self):
        self.assertIn("NEW ENACTMENT", self.fixture["important_limitation"])

    def test_04_unreviewed_amendment_key_must_hold(self):
        result = make_case_key(self.amendment())
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["comparison_allowed"])
        self.assertIsNone(result["case_key"])

    def test_05_full_example_must_hold_without_changes(self):
        result = self.evaluate()
        self.assertEqual(result["status"], self.fixture["expected_current_result"]["status"])
        self.assertFalse(result["comparison_allowed"])
        self.assertFalse(result["notification_sent"])
        self.assertFalse(result["rms_modified"])
        self.assertEqual(result["proposed_changes"], [])

    def test_06_no_effective_date_proposal_without_human_review(self):
        self.assertFalse(self.evaluate()["proposed_changes"])

    def test_07_offline_only_policy(self):
        self.assertTrue(self.fixture["no_network_requests_during_test"])
        self.assertTrue(self.fixture["no_notification"])
        self.assertTrue(self.fixture["no_rms_updates"])


if __name__ == "__main__":
    unittest.main()
