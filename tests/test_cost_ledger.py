import itertools
import unittest
import context_runtime as rt
import task_economics as te
from tests.test_context_runtime import request, outcome


def tool(reacq=False, retry=False, category='retrieval'):
    return {'event_id':'tool', 'event_kind':'tool', 'run_id':'r1', 'task_id':'t1',
            'policy_id':'control', 'occurred_at':'2026-09-07T10:00:00.200Z',
            'payload':{'tool_call_id':'tool', 'tool_name':'lookup', 'category':category,
                'start':'2026-09-07T10:00:00Z', 'end':'2026-09-07T10:00:00Z',
                'cost_usd':1, 'result_size_bytes':0, 'result_token_estimate':0,
                'retry':retry, 'error':False, 'whether_reacquisition':reacq,
                'reacquisition_reason':'reread' if reacq else None}}


class CostLedgerTests(unittest.TestCase):
    def test_classified_tool_spend_once_and_cost_per_success(self):
        for reacq, retry in itertools.product((False, True), repeat=2):
            with self.subTest(reacq=reacq, retry=retry):
                rows=[request(), tool(reacq,retry), outcome()]
                raw=rt.normalize([rt.Envelope.parse(r) for r in rows])['l5_receipts']['runs'][0]
                receipt=te.RunReceipt.from_mapping(raw)
                self.assertAlmostEqual(receipt.observed_cost_usd,1.001)
                self.assertAlmostEqual(te.aggregate([receipt])['cost_per_success_usd'],1.001)
                self.assertEqual(te.paired_task_deltas([receipt,te.RunReceipt('t','t1','t',True,provider_bill_usd=.001,tool_cost_usd=1)],'control','t')[0]['cost_delta_usd'],0)

    def test_ambiguous_legacy_requires_explicit_migration(self):
        r={'run_id':'r','task_id':'t','policy_id':'p','success':True,'reacquisition_cost_usd':1}
        with self.assertRaises(te.ReceiptError): te.RunReceipt.from_mapping(r)
        self.assertEqual(te.RunReceipt.from_mapping(dict(r,cost_ledger_version=1)).observed_cost_usd,1)
        self.assertEqual(te.RunReceipt.from_mapping(dict(r,cost_ledger_version=2,tool_cost_usd=1)).observed_cost_usd,1)

    def test_direct_constructor_requires_explicit_classified_ledger_version(self):
        with self.assertRaises(te.ReceiptError):
            te.RunReceipt('r','t','p',True,reacquisition_cost_usd=3,retry_cost_usd=2)
        legacy=te.RunReceipt('r','t','p',True,cost_ledger_version=1,reacquisition_cost_usd=3,retry_cost_usd=2)
        self.assertEqual(legacy.observed_cost_usd,5)
        modern=te.RunReceipt('r','t','p',True,cost_ledger_version=2,tool_cost_usd=3,reacquisition_cost_usd=3,retry_cost_usd=2)
        self.assertEqual(modern.observed_cost_usd,3)

    def test_legacy_positional_tool_cost_is_preserved(self):
        receipt=te.RunReceipt('r','t','p',True,None,None,None,None,None,None,None,
                              0,0,0,0,0,None,None,1)
        self.assertEqual(receipt.tool_cost_usd,1)
        self.assertEqual(receipt.observed_cost_usd,1)
        self.assertEqual(receipt.cost_ledger_version,2)
