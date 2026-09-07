import json
import math
import tempfile
import unittest
from pathlib import Path

import task_economics as te


class TaskEconomicsTests(unittest.TestCase):
    def test_observed_cost_sums_components(self):
        receipt = te.RunReceipt(
            run_id="r",
            task_id="t",
            policy_id="p",
            success=True,
            cost_ledger_version=1,
            provider_bill_usd=1.0,
            tool_cost_usd=0.1,
            reacquisition_cost_usd=0.2,
            retry_cost_usd=0.3,
            latency_cost_usd=0.4,
            failure_cost_usd=0.5,
        )
        self.assertAlmostEqual(receipt.observed_cost_usd, 2.5)

    def test_cost_per_success_penalizes_failures(self):
        rows = [
            te.RunReceipt("1", "a", "p", True, provider_bill_usd=1.0),
            te.RunReceipt("2", "b", "p", False, provider_bill_usd=1.0),
        ]
        agg = te.aggregate(rows)
        self.assertEqual(agg["success_rate"], 0.5)
        self.assertEqual(agg["cost_per_success_usd"], 2.0)

    def test_no_success_is_infinite(self):
        agg = te.aggregate(
            [te.RunReceipt("1", "a", "p", False, provider_bill_usd=1.0)]
        )
        self.assertTrue(math.isinf(agg["cost_per_success_usd"]))

    def test_string_false_is_rejected(self):
        with self.assertRaises(te.ReceiptError):
            te.RunReceipt.from_mapping({
                "run_id": "r", "task_id": "t", "policy_id": "p", "success": "false"
            })

    def test_unknown_field_is_rejected(self):
        with self.assertRaises(te.ReceiptError):
            te.RunReceipt.from_mapping({
                "run_id": "r", "task_id": "t", "policy_id": "p",
                "success": True, "provider_bil_usd": 1.0
            })

    def test_token_and_reacquisition_invariants(self):
        with self.assertRaises(te.ReceiptError):
            te.RunReceipt.from_mapping({
                "run_id": "r", "task_id": "t", "policy_id": "p",
                "success": True, "input_tokens": 10, "cached_input_tokens": 11
            })
        with self.assertRaises(te.ReceiptError):
            te.RunReceipt.from_mapping({
                "run_id": "r", "task_id": "t", "policy_id": "p",
                "success": True, "retrieval_calls": 1, "reacquisition_calls": 2
            })

    def test_duplicate_run_id_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "r.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "runs": [
                    {"run_id":"x","task_id":"a","policy_id":"p","success":True},
                    {"run_id":"x","task_id":"b","policy_id":"p","success":False},
                ]
            }), encoding="utf-8")
            with self.assertRaises(te.ReceiptError):
                te.load_receipts(path)

    def test_aggregate_cache_latency_and_score(self):
        rows = [
            te.RunReceipt("1","a","p",True,task_score=1.0,input_tokens=100,cached_input_tokens=80,
                          cache_write_tokens=20,output_tokens=10,ttft_ms=100,wall_time_ms=1000),
            te.RunReceipt("2","b","p",False,task_score=0.0,input_tokens=100,cached_input_tokens=20,
                          cache_write_tokens=0,output_tokens=20,ttft_ms=300,wall_time_ms=3000,
                          failure_class="tool"),
        ]
        agg=te.aggregate(rows)
        self.assertEqual(agg["cache_hit_share"],0.5)
        self.assertEqual(agg["mean_task_score"],0.5)
        self.assertEqual(agg["p50_ttft_ms"],200)
        self.assertEqual(agg["p95_wall_time_ms"],2900)
        self.assertEqual(agg["failure_classes"],{"tool":1})

    def test_pairing_report_discloses_omitted_tasks(self):
        rows=[
            te.RunReceipt("c1","paired","c",True),
            te.RunReceipt("t1","paired","t",True),
            te.RunReceipt("c2","missing","c",True),
            te.RunReceipt("c3","dup","c",True),
            te.RunReceipt("c4","dup","c",True),
            te.RunReceipt("t4","dup","t",True),
        ]
        report=te.paired_task_report(rows,"c","t")
        self.assertEqual(report["paired_tasks"],1)
        self.assertIn("missing",report["omitted_missing_arm"])
        self.assertIn("dup",report["omitted_duplicate_arm"])
        self.assertAlmostEqual(report["paired_coverage"],1/3)

    def test_paired_deltas_backward_compatible(self):
        rows = [
            te.RunReceipt("c", "task", "control", True, provider_bill_usd=1.0, reacquisition_calls=0),
            te.RunReceipt("t", "task", "treatment", True, provider_bill_usd=0.8,
                          cost_ledger_version=2, external_cost_usd=0.3, reacquisition_cost_usd=0.3, retrieval_calls=2, reacquisition_calls=2),
        ]
        delta = te.paired_task_deltas(rows, "control", "treatment")[0]
        self.assertAlmostEqual(delta["cost_delta_usd"], 0.1)
        self.assertEqual(delta["reacquisition_call_delta"], 2)


if __name__ == "__main__":
    unittest.main()
