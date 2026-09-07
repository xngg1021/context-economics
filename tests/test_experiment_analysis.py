import math
import unittest

import adaptive_control as ac
import experiment_analysis as ea
import task_economics as te


def receipt(task, policy, success=True, cost=1.0, wall=100.0, reacq=0):
    return te.RunReceipt(run_id=f"{task}-{policy}", task_id=task, policy_id=policy,
        success=success, provider_bill_usd=cost, wall_time_ms=wall,
        retrieval_calls=reacq, reacquisition_calls=reacq)


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.rows = [receipt("a","c",cost=2), receipt("a","t",cost=1),
                     receipt("b","c",cost=2), receipt("b","t",cost=1)]

    def test_counterbalanced_ab_ba(self):
        schedule = ea.counterbalanced_schedule(["a","b","c"], "c", "t")
        self.assertEqual(schedule[0]["order"], ["c","t"])
        self.assertEqual(schedule[1]["order"], ["t","c"])

    def test_statistics_and_deterministic_bootstrap(self):
        a = ea.paired_statistics(self.rows, "c", "t", seed=42)
        b = ea.paired_statistics(self.rows, "c", "t", seed=42)
        self.assertEqual(a, b)
        self.assertEqual(a["statistics"]["provider_bill_delta_usd"]["wins"], 2)
        self.assertEqual(a["statistics"]["provider_bill_delta_usd"]["bootstrap_mean_ci"]["status"], "descriptive-only")

    def test_gate_passes_and_never_auto_enables(self):
        out = ea.acceptance_gate(self.rows, {"t": []}, "c", "t", ea.GateConfig())
        self.assertTrue(out["candidate_for_promotion"])
        self.assertIn("no-auto-enable", out["scope"])

    def test_zero_success_fails_cost_gate(self):
        rows = [receipt("a","c",True,2), receipt("a","t",False,1)]
        out = ea.acceptance_gate(rows, {"t": []}, "c", "t", ea.GateConfig(quality_epsilon=1))
        self.assertFalse(out["checks"]["cost_target"])

    def test_bad_gate_and_missing_pair(self):
        with self.assertRaises(ea.AnalysisError): ea.GateConfig.parse({"typo": 1})
        stats = ea.paired_statistics([receipt("a","c")], "c", "t")
        self.assertEqual(stats["paired_tasks"], 0)


if __name__ == "__main__": unittest.main()
