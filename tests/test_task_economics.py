import math
import unittest

import task_economics


class TaskEconomicsTests(unittest.TestCase):
    def test_observed_cost_sums_components(self):
        receipt = task_economics.RunReceipt(
            run_id="r",
            task_id="t",
            policy_id="p",
            success=True,
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
            task_economics.RunReceipt("1", "a", "p", True, provider_bill_usd=1.0),
            task_economics.RunReceipt("2", "b", "p", False, provider_bill_usd=1.0),
        ]
        agg = task_economics.aggregate(rows)
        self.assertEqual(agg["success_rate"], 0.5)
        self.assertEqual(agg["cost_per_success_usd"], 2.0)

    def test_no_success_is_infinite(self):
        agg = task_economics.aggregate(
            [task_economics.RunReceipt("1", "a", "p", False, provider_bill_usd=1.0)]
        )
        self.assertTrue(math.isinf(agg["cost_per_success_usd"]))

    def test_paired_deltas(self):
        rows = [
            task_economics.RunReceipt("c", "task", "control", True, provider_bill_usd=1.0, reacquisition_calls=0),
            task_economics.RunReceipt("t", "task", "treatment", True, provider_bill_usd=0.8, reacquisition_cost_usd=0.3, reacquisition_calls=2),
        ]
        delta = task_economics.paired_task_deltas(rows, "control", "treatment")[0]
        self.assertAlmostEqual(delta["cost_delta_usd"], 0.1)
        self.assertEqual(delta["reacquisition_call_delta"], 2)


if __name__ == "__main__":
    unittest.main()
