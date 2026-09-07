import random
import unittest
import context_runtime as rt
import runtime_experiment as rx
import task_economics as te
from tests.test_context_runtime import request, outcome
from tests.test_cost_ledger import tool

class InvariantTests(unittest.TestCase):
    def test_seeded_accounting_roundtrip(self):
        rng=random.Random(1234)
        for i in range(100):
            q=request();q['payload']['provider_bill_usd']=rng.randrange(100)/100
            q['payload']['cached_input_tokens']=rng.randrange(11)
            q['payload']['uncached_input_tokens']=10-q['payload']['cached_input_tokens']
            t=tool(bool(rng.randrange(2)),bool(rng.randrange(2)),rng.choice(['filesystem','search','database','web']))
            t['payload']['cost_usd']=rng.randrange(100)/100
            context={'event_id':'ctx','event_kind':'context','run_id':'r1','task_id':'t1','policy_id':'control','occurred_at':'2026-09-07T10:00:00.300Z','payload':{'kind':'context_hit','asset_id':'a'}}
            out=rt.normalize([rt.Envelope.parse(e) for e in (q,t,context,outcome())])
            r=te.RunReceipt.from_mapping(out['l5_receipts']['runs'][0])
            self.assertLessEqual(r.cached_input_tokens,r.input_tokens)
            self.assertLessEqual(r.reacquisition_calls,r.retrieval_calls)
            self.assertAlmostEqual(r.observed_cost_usd,q['payload']['provider_bill_usd']+t['payload']['cost_usd'])
            rx.ExperimentContextEvent.from_mapping(out['l6_context_events']['events'][0])
    def test_timestamp_and_identity_failures(self):
        for event in (outcome(),outcome(policy='wrong')):
            event['occurred_at']='2026-09-06T00:00:00Z'
            with self.assertRaises(rt.TelemetryError):rt.normalize([rt.Envelope.parse(x) for x in (request(),event)])
    def test_run_wall_includes_post_request_tool_and_outcome(self):
        t=tool();t['occurred_at']='2026-09-07T10:00:02Z';t['payload']['end']=t['occurred_at']
        o=outcome();o['occurred_at']='2026-09-07T10:00:03Z'
        result=rt.normalize([rt.Envelope.parse(x) for x in (request(),t,o)])
        self.assertEqual(result['l5_receipts']['runs'][0]['wall_time_ms'],3000)
