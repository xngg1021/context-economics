import unittest
from dataclasses import replace
import experiment_analysis as ea
import runtime_experiment as re
import task_economics as te
from tests.test_experiment_analysis import receipt

class PromotionTests(unittest.TestCase):
    def gate(self,rows,**kw):
        return ea.acceptance_gate(rows,{},'c','t',ea.GateConfig(min_paired_coverage=.5,min_cost_per_success_improvement=.1),**kw)
    def test_unmatched_expensive_failed_control_never_improves_gate(self):
        rows=[receipt('a','c'),receipt('a','t'),receipt('b','c',False,100)]
        out=self.gate(rows)
        self.assertEqual(out['cost_per_success_improvement'],0)
        self.assertFalse(out['performance_candidate'])
        self.assertEqual(out['paired_aggregates']['c']['success_rate'],1)
    def test_duplicate_arm_excluded(self):
        rows=[receipt('a','c'),receipt('a','t'),receipt('b','c',False,100),replace(receipt('b','c',False,100),run_id='duplicate'),receipt('b','t')]
        self.assertEqual(self.gate(rows)['paired_task_ids'],['a'])
        self.assertFalse(self.gate(rows)['performance_candidate'])
    def test_zero_pairs_and_low_coverage(self):
        self.assertFalse(self.gate([receipt('a','c'),receipt('b','t')])['candidate_for_promotion'])
        rows=[receipt('a','c',cost=2),receipt('a','t'),receipt('b','c'),receipt('z','c')]
        out=self.gate(rows)
        self.assertTrue(out['performance_candidate']);self.assertFalse(out['eligibility_checks']['paired_coverage'])
    def evidence(self,status='observed',evidence='runtime-A/B'):
        m=re.load_manifest('fixtures/runtime_experiment_manifest.json')
        m=replace(m,control_policy='c',treatment_policy='t',declared_evidence_class=evidence)
        records=re.load_receipt_records('fixtures/runtime_ab_receipts.json')
        old={m0.receipt.policy_id for m0 in records}; original=re.load_manifest('fixtures/runtime_experiment_manifest.json')
        mapping={original.control_policy:'c',original.treatment_policy:'t'}
        rows=[replace(x.receipt,policy_id=mapping[x.receipt.policy_id],billing_status=status,provider_bill_source='receipt@1',scorer_id='exact',scorer_version='1',scoring_provenance='benchmark') for x in records]
        events=[replace(e,policy_id=mapping[e.policy_id]) for e in re.load_experiment_events('fixtures/runtime_context_events.json')]
        return rows,dict(manifest=m,experiment_events=events,evidence_origin='real-provider',held_out_task_set_ref=m.task_set_ref)
    def test_structural_observed_and_estimated_paths(self):
        rows,kw=self.evidence();self.assertTrue(self.gate(rows,**kw)['evidence_eligible'])
        rows,kw=self.evidence('estimated');self.assertFalse(self.gate(rows,**kw)['evidence_eligible'])
        self.assertTrue(self.gate(rows,allow_estimated=True,**kw)['evidence_eligible'])
    def test_synthetic_loopback_missing_scorer_and_pin_mismatch(self):
        rows,kw=self.evidence(evidence='synthetic-contract')
        self.assertFalse(self.gate(rows,**kw)['evidence_eligible'])
        rows,kw=self.evidence();kw['evidence_origin']='loopback'
        self.assertFalse(self.gate(rows,**kw)['evidence_eligible'])
        rows,kw=self.evidence();rows[0]=replace(rows[0],scorer_id=None)
        self.assertFalse(self.gate(rows,**kw)['evidence_eligible'])
        rows,kw=self.evidence();rows[0]=replace(rows[0],model_revision='wrong')
        self.assertFalse(self.gate(rows,**kw)['evidence_eligible'])
