"""RMS v0.9 offline integration safety tests using synthetic assertions only.

This test never establishes legal facts or human verification. The caller must
explicitly supply each attestation; no missing attestation becomes True.
No network access, notifications, or RMS changes are performed by this file.
"""

import unittest

from rms_v09_official_reference_prototype import (
    DECREE_TITLE,
    LAW_TITLE,
    review_official_reference,
)
from rms_v09_reference_bridge_adapter_prototype import review_bridge
from rms_v09_legal_relation_bridge_prototype import DocumentEvidence, review_relation


# Deliberately synthetic text matching the case-specific prototype patterns.
# It is NOT a transcription authenticated against the actual Kanpo PDF.
SYNTHETIC_TEXT = (
    f"{DECREE_TITLE} "
    "政令第二十四号 "
    f"{LAW_TITLE}（令和三年法律第六十号） "
    "附則第一項 "
    "施行期日は、令和四年四月一日とする"
)
REFERENCE_TEXT = f"{LAW_TITLE}（令和3年法律第60号）"
# Placeholders only, NOT official government URLs verified by a human.
SOURCE_URL = "https://example.invalid/decree"
TARGET_URL = "https://example.invalid/law"


def official_stage(*, text=SYNTHETIC_TEXT, official_copy_checked=False):
    return review_official_reference(
        text,
        source_type="官報",
        source_date="2022-01-19",
        source_issue="号外第13号",
        source_page=5,
        manually_verified_official_copy=official_copy_checked,
    )


def adapter_stage(
    official,
    *,
    official_copy_checked=False,
    source_checked=False,
    target_checked=False,
    reference_checked=False,
    reference_text=REFERENCE_TEXT,
):
    # The caller supplies attestations explicitly; never infer them from HOLD
    # or from the mere presence of an evidence candidate.
    return review_bridge(
        official,
        source_official_url=SOURCE_URL,
        target_official_url=TARGET_URL,
        official_reference_text=reference_text,
        manually_verified_official_copy=official_copy_checked,
        source_human_checked=source_checked,
        target_human_checked=target_checked,
        explicit_reference_human_checked=reference_checked,
        source_document_kind="EFFECTIVE_DATE_DECREE",
        target_document_kind="NEW_ENACTMENT",
    )


def relation_stage(
    adapter,
    *,
    source_checked=False,
    target_checked=False,
    reference_checked=False,
    reference_text=REFERENCE_TEXT,
):
    # No candidate: fail closed. Never fabricate source/target evidence.
    candidate = adapter.get("relation_candidate") if isinstance(adapter, dict) else None
    if not isinstance(candidate, dict):
        return None
    source = DocumentEvidence(
        document_id=candidate["source_document_id"],
        document_kind=candidate["source_document_kind"],
        official_url=candidate["source_official_url_asserted"],
        source_label=candidate["source_label"],
        human_source_checked=source_checked,
    )
    target = DocumentEvidence(
        document_id=candidate["target_document_id"],
        document_kind=candidate["target_document_kind"],
        official_url=candidate["target_official_url_asserted"],
        source_label=candidate["source_label"],
        human_source_checked=target_checked,
    )
    return review_relation(
        source=source,
        target=target,
        relation_kind=candidate["relation_kind"],
        explicit_reference_human_checked=reference_checked,
        official_reference_text=reference_text,
        effective_date=candidate["effective_date"],
        source_page=candidate["source_page"],
    )


def asserted_fixture():
    """Explicit synthetic TRUE flags for positive-path testing only.

    These flags are *test assertions*, NOT genuine verification records.
    """
    return {
        "official_copy_checked": True,
        "source_checked": True,
        "target_checked": True,
        "reference_checked": True,
    }


def asserted_pipeline():
    flags = asserted_fixture()
    official = official_stage(official_copy_checked=flags["official_copy_checked"])
    bridge = adapter_stage(official, **flags)
    relation = relation_stage(
        bridge,
        source_checked=flags["source_checked"],
        target_checked=flags["target_checked"],
        reference_checked=flags["reference_checked"],
    )
    return official, bridge, relation


class IntegrationSafetyTests(unittest.TestCase):
    def assert_safe_hold(self, result):
        self.assertIsInstance(result, dict)
        self.assertEqual(result["status"], "HOLD")
        self.assertIs(result["human_approval_required"], True)
        for key in ("legal_link_confirmed", "comparison_allowed", "notification_sent", "rms_modified"):
            self.assertIs(result[key], False)

    def test_01_official_defaults_to_unverified_hold(self):
        official = official_stage()
        self.assert_safe_hold(official)
        self.assertFalse(official["evidence_candidate"]["source_verified_by_human_assertion_only"])

    def test_02_official_synthetic_pattern_matches_are_not_approval(self):
        official = official_stage(official_copy_checked=True)
        self.assert_safe_hold(official)
        self.assertTrue(all(official["evidence_candidate"]["matches"].values()))
        self.assertEqual(official["evidence_candidate"]["proposed_law"], "令和3年法律第60号")
        self.assertEqual(official["evidence_candidate"]["proposed_decree"], "令和4年政令第24号")

    def test_03_adapter_defaults_to_no_candidate(self):
        official = official_stage()
        bridge = adapter_stage(official)
        self.assert_safe_hold(bridge)
        self.assertIsNone(bridge["relation_candidate"])

    def test_04_explicit_test_assertions_allow_candidate_but_not_approval(self):
        official, bridge, relation = asserted_pipeline()
        for stage in (official, bridge, relation):
            self.assert_safe_hold(stage)
        self.assertIsNotNone(bridge["relation_candidate"])
        self.assertIsNotNone(relation["relation_candidate"])

    def test_05_identifiers_preserved_across_two_bridges(self):
        _, bridge, relation = asserted_pipeline()
        self.assertEqual(bridge["relation_candidate"]["source_document_id"], "2022-DECREE-24")
        self.assertEqual(bridge["relation_candidate"]["target_document_id"], "2021-LAW-60")
        for key in ("source_document_id", "target_document_id", "relation_kind", "effective_date", "source_page"):
            self.assertEqual(bridge["relation_candidate"][key], relation["relation_candidate"][key])

    def test_06_official_copy_flag_not_inferred_from_text(self):
        flags = asserted_fixture()
        official = official_stage(official_copy_checked=False)
        bridge = adapter_stage(official, **flags)
        self.assert_safe_hold(bridge)
        self.assertIsNone(bridge["relation_candidate"])

    def test_07_adapter_does_not_infer_missing_attestation(self):
        flags = asserted_fixture()
        official = official_stage(official_copy_checked=True)
        flags["official_copy_checked"] = False
        bridge = adapter_stage(official, **flags)
        self.assert_safe_hold(bridge)
        self.assertIsNone(bridge["relation_candidate"])

    def test_08_missing_source_check_blocks_adapter(self):
        flags = asserted_fixture()
        flags["source_checked"] = False
        bridge = adapter_stage(official_stage(official_copy_checked=True), **flags)
        self.assert_safe_hold(bridge)
        self.assertIsNone(bridge["relation_candidate"])

    def test_09_missing_target_check_blocks_adapter(self):
        flags = asserted_fixture()
        flags["target_checked"] = False
        bridge = adapter_stage(official_stage(official_copy_checked=True), **flags)
        self.assert_safe_hold(bridge)
        self.assertIsNone(bridge["relation_candidate"])

    def test_10_missing_reference_check_blocks_adapter(self):
        flags = asserted_fixture()
        flags["reference_checked"] = False
        bridge = adapter_stage(official_stage(official_copy_checked=True), **flags)
        self.assert_safe_hold(bridge)
        self.assertIsNone(bridge["relation_candidate"])

    def test_11_incorrect_reference_blocks_adapter(self):
        flags = asserted_fixture()
        bridge = adapter_stage(official_stage(official_copy_checked=True),
                               reference_text="別の法律についての記載", **flags)
        self.assert_safe_hold(bridge)
        self.assertIsNone(bridge["relation_candidate"])

    def test_12_relation_does_not_infer_source_verification(self):
        _, bridge, _ = asserted_pipeline()
        result = relation_stage(bridge, source_checked=False, target_checked=True, reference_checked=True)
        self.assert_safe_hold(result)
        self.assertIsNone(result["relation_candidate"])

    def test_13_relation_does_not_infer_target_verification(self):
        _, bridge, _ = asserted_pipeline()
        result = relation_stage(bridge, source_checked=True, target_checked=False, reference_checked=True)
        self.assert_safe_hold(result)
        self.assertIsNone(result["relation_candidate"])

    def test_14_relation_does_not_infer_reference_verification(self):
        _, bridge, _ = asserted_pipeline()
        result = relation_stage(bridge, source_checked=True, target_checked=True, reference_checked=False)
        self.assert_safe_hold(result)
        self.assertIsNone(result["relation_candidate"])

    def test_15_absent_bridge_candidate_does_not_reach_relation(self):
        bridge = adapter_stage(official_stage())
        self.assertIsNone(relation_stage(bridge))

    def test_16_missing_official_identifiers_prevent_bridge_candidate(self):
        flags = asserted_fixture()
        official = official_stage(text="関係のない合成文章", official_copy_checked=True)
        bridge = adapter_stage(official, **flags)
        self.assert_safe_hold(bridge)
        self.assertIsNone(bridge["relation_candidate"])


if __name__ == "__main__":
    unittest.main()
