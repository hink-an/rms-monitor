"""Synthetic, offline-only test cases; no legal assertions or live network."""
import unittest
from rms_v09_decision_notice_prototype import ConfirmedEvidence, plan_case, diagnostic_guard


def ev(**changes):
    base = dict(official_source_url="https://www.example.go.jp/notice/123",
                source_document_id="official-example-123", reviewed_by_human=True,
                formally_decided=True, decision_date="2026-11-19",
                effective_date=None, effective_date_confirmed=False, withdrawn=False)
    base.update(changes)
    return ConfirmedEvidence(**base)


class SafetyTests(unittest.TestCase):
    def plan(self, evidence=None, **kwargs):
        return plan_case(case_id="law-2026-amendment-001", evidence=evidence or ev(), **kwargs)

    def test_no_date_initial_notification(self):
        p=self.plan()
        self.assertEqual(p['status'], 'REVIEW_REQUIRED')
        self.assertEqual(p['suggested_events'][0]['kind'], 'INITIAL_FORMAL_DECISION')
        self.assertIsNone(p['suggested_events'][0]['effective_date'])

    def test_known_date_initial_notification(self):
        p=self.plan(ev(effective_date='2027-04-01', effective_date_confirmed=True))
        self.assertEqual(p['suggested_events'][0]['kind'], 'INITIAL_FORMAL_DECISION')

    def test_later_date_confirmation_re_notifies(self):
        p=self.plan(ev(effective_date='2027-04-01',effective_date_confirmed=True),initial_notice_recorded=True)
        self.assertEqual([e['kind'] for e in p['suggested_events']], ['RENOTIFY_EFFECTIVE_DATE_CONFIRMED'])

    def test_date_change_re_notifies(self):
        p=self.plan(ev(effective_date='2027-06-01',effective_date_confirmed=True),initial_notice_recorded=True,
                    previous_confirmed_effective_date='2027-04-01')
        self.assertEqual(p['suggested_events'][0]['kind'], 'RENOTIFY_EFFECTIVE_DATE_CHANGED')

    def test_same_date_no_re_notifies(self):
        p=self.plan(ev(effective_date='2027-04-01',effective_date_confirmed=True),initial_notice_recorded=True,
                    previous_confirmed_effective_date='2027-04-01')
        self.assertEqual(p['suggested_events'], [])

    def test_duplicate_event_id_is_suppressed(self):
        p=self.plan()
        q=self.plan(previously_notified_event_ids=[p['suggested_events'][0]['event_id']])
        self.assertEqual(q['suggested_events'], [])

    def test_unreviewed_evidence_holds(self):
        self.assertEqual(self.plan(ev(reviewed_by_human=False))['status'],'HOLD')

    def test_undecided_holds(self):
        self.assertEqual(self.plan(ev(formally_decided=False))['suggested_events'],[])

    def test_missing_official_reference_holds(self):
        self.assertEqual(self.plan(ev(official_source_url=''))['status'],'HOLD')

    def test_invalid_decision_date_holds(self):
        self.assertEqual(self.plan(ev(decision_date='2026-02-30'))['status'],'HOLD')

    def test_unconfirmed_effective_date_holds(self):
        self.assertEqual(self.plan(ev(effective_date='2027-04-01'))['status'],'HOLD')

    def test_invalid_effective_date_holds(self):
        self.assertEqual(self.plan(ev(effective_date='2027-02-30',effective_date_confirmed=True))['status'],'HOLD')

    def test_withdrawn_holds(self):
        self.assertEqual(self.plan(ev(withdrawn=True))['status'],'HOLD')

    def test_disappeared_effective_date_holds(self):
        p=self.plan(initial_notice_recorded=True,previous_confirmed_effective_date='2027-04-01')
        self.assertEqual(p['status'],'HOLD')
        self.assertEqual(p['suggested_events'],[])

    def test_unknown_initial_notice_state_holds(self):
        self.assertEqual(self.plan(initial_notice_recorded=None)['status'],'HOLD')

    def test_invalid_case_id_holds(self):
        self.assertEqual(plan_case(case_id='',evidence=ev())['status'],'HOLD')

    def test_never_dispatches_or_modifies_rms(self):
        p=self.plan()
        self.assertFalse(p['notification_sent'])
        self.assertFalse(p['rms_modified'])
        self.assertFalse(p['comparison_allowed'])
        self.assertTrue(p['manual_approval_required'])

    def test_upstream_guard_retains_hold(self):
        d=dict(diagnostic_status='HOLD',comparison_allowed=False,
               legal_amendment_confirmed=False,rms_modified=False,network_accessed=False,
               article_reviews=[{}]*114)
        result=diagnostic_guard(d)
        self.assertEqual(result['upstream_issues'],[])
        self.assertEqual(result['diagnostic_status'],'HOLD')

    def test_upstream_unsafe_flags_reported(self):
        d=dict(diagnostic_status='READY',comparison_allowed=True,
               legal_amendment_confirmed=True,rms_modified=True,network_accessed=True,
               article_reviews=[])
        self.assertEqual(len(diagnostic_guard(d)['upstream_issues']),6)


if __name__=='__main__':
    unittest.main(verbosity=2)
