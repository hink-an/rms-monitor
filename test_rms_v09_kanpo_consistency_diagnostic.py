"""RMS v0.9 Kanpo consistency diagnostic.

Offline diagnostic using synthetic text derived from a reviewed
Kanpo example. No network, notifications, or RMS modifications.

Passing tests demonstrate detection of known limitations.
They do NOT establish legal authenticity or correctness.
"""

import unittest

from rms_v09_official_reference_prototype import (
    LAW_TITLE,
    DECREE_TITLE,
    review_official_reference,
)


META = {
    "source_type": "官報",
    "source_date": "2022-01-19",
    "source_issue": "号外第13号",
    "source_page": 5,
}

DECREE_24 = (
    "政令第二十四号\n"
    f"{DECREE_TITLE}\n"
    f"内閣は、{LAW_TITLE}（令和三年法律第六十号）"
    "附則第一項の規定に基づき、この政令を制定する。\n"
    f"{LAW_TITLE}の施行期日は、令和四年四月一日とする。"
)

# This is intentionally different from the Kanpo wording.
SYNTHETIC_COMPATIBLE = DECREE_24.replace(
    "附則第一項", "附則第1項"
)


def review(text):
    return review_official_reference(
        text,
        manually_verified_official_copy=False,
        **META,
    )


class KanpoConsistencyDiagnostics(unittest.TestCase):

    def assert_safe(self, result):
        self.assertEqual(result["status"], "HOLD")
        self.assertTrue(result["human_approval_required"])
        self.assertFalse(result["comparison_allowed"])
        self.assertFalse(result["notification_sent"])
        self.assertFalse(result["rms_modified"])
        self.assertFalse(result["legal_link_confirmed"])

    def test_01_kanpo_basis_wording_detected(self):
        result = review(DECREE_24)
        self.assert_safe(result)

        checks = result["evidence_candidate"]["matches"]

        # Confirm that the Kanpo-style statutory basis
        # is recognized by the present prototype.
        self.assertTrue(checks["statutory_basis"])
        self.assertNotIn(
            "EVIDENCE_STATUTORY_BASIS_MISSING",
            result["issues"],
        )

   def test_02_synthetic_basis_is_not_detected(self):
        result = review(SYNTHETIC_COMPATIBLE)
        self.assert_safe(result)

        checks = result["evidence_candidate"]["matches"]
       self.assertFalse(checks["statutory_basis"])

        # Recognition must never mean legal approval.
        self.assertFalse(result["legal_link_confirmed"])

    def test_03_multiple_dates_are_not_resolved(self):
        text = (
            SYNTHETIC_COMPATIBLE
            + "\n別の規定は令和四年五月一日から施行する。"
        )
        result = review(text)
        self.assert_safe(result)

        evidence = result["evidence_candidate"]

        # The prototype still returns a fixed candidate.
        self.assertTrue(evidence["matches"]["effective_date"])
        self.assertEqual(
            evidence["proposed_effective_date"],
            "2022-04-01",
        )

        # Record the ambiguity, rather than approving it.
        self.assertIn("令和四年四月一日", text)
        self.assertIn("令和四年五月一日", text)

    def test_04_cross_document_contamination(self):
        first = (
            "政令第二十四号\n"
            f"{DECREE_TITLE}\n"
            f"{LAW_TITLE}（令和三年法律第六十号）"
            "附則第1項の規定に基づく。"
        )

        second = (
            "政令第二十五号\n"
            "別の政令の本文。\n"
            "施行期日は、令和四年四月一日とする。"
        )

        first_result = review(first)
        joined_result = review(first + "\n" + second)

        self.assert_safe(first_result)
        self.assert_safe(joined_result)

        self.assertFalse(
            first_result["evidence_candidate"]
            ["matches"]["effective_date"]
        )

        # Joining document fragments can satisfy checks
        # even when one document alone cannot.
        self.assertTrue(
            joined_result["evidence_candidate"]
            ["matches"]["effective_date"]
        )

        # The merged text must still remain HOLD.
        self.assertFalse(
            joined_result["legal_link_confirmed"]
        )

    def test_05_unverified_source_never_approves(self):
        result = review(SYNTHETIC_COMPATIBLE)
        self.assert_safe(result)

        self.assertIn(
            "OFFICIAL_COPY_NOT_HUMAN_VERIFIED",
            result["issues"],
        )


if __name__ == "__main__":
    unittest.main()
