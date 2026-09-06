import math
import unittest

import model


class ModelTests(unittest.TestCase):
    def test_breakeven_snapshot(self):
        self.assertAlmostEqual(model.breakeven_turns(model.KIMI_K3, 0.0, 0.2), 2.5, places=6)
        self.assertAlmostEqual(model.breakeven_turns(model.KIMI_K3, 0.85, 0.2), 10.6382978723, places=6)

    def test_hermes_tail_budget_semantics(self):
        policy = model.CompressionPolicy(
            threshold=0.50,
            tail_ratio_of_threshold=0.20,
            summary_ratio_of_middle=0.20,
        )
        self.assertEqual(policy.trigger_tokens(1_000_000), 500_000)
        self.assertEqual(policy.tail_budget_tokens(1_000_000), 100_000)

    def test_cost_only_grid_does_not_invent_global_optimum(self):
        shape = model.SessionShape()
        results = model.grid_search(
            model.KIMI_K3,
            shape,
            thresholds=(0.05, 0.15),
            rho=0.0,
        )
        by_threshold = {r.threshold: r for r in results}
        self.assertLess(by_threshold[0.05].total_cost, by_threshold[0.15].total_cost)

    def test_no_compression_snapshot(self):
        result = model.simulate(model.KIMI_K3, model.SessionShape(), None, rho=0.0)
        self.assertAlmostEqual(result.total_cost, 115.83, places=2)
        self.assertEqual(result.compression_calls, 0)

    def test_nonlinear_long_context_pricing(self):
        low = model.OPENAI_GPT56_SOL.request_rates(272_000)
        high = model.OPENAI_GPT56_SOL.request_rates(272_001)
        self.assertEqual(low, (4.0, 0.4, 20.0))
        self.assertEqual(high, (8.0, 0.8, 30.0))

    def test_input_validation(self):
        with self.assertRaises(ValueError):
            model.CompressionPolicy(threshold=0)
        with self.assertRaises(ValueError):
            model.KIMI_K3.effective_input_rate(1.1)
        with self.assertRaises(ValueError):
            model.breakeven_turns(model.KIMI_K3, 0.5, 1.0)


if __name__ == "__main__":
    unittest.main()
