import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import adaptive_control as ac


class TelemetryTests(unittest.TestCase):
    def test_planned_and_prefetch_do_not_dilute_demand(self):
        events = [
            ac.ContextAccessEvent("h1", "t1", "context_hit", "a"),
            ac.ContextAccessEvent("m1", "t2", "soft_miss", "a", avoidable=True, extra_cost_units=4),
            ac.ContextAccessEvent("p1", "p-only", "prefetch", "a", used=False, prefetched_units=10),
            ac.ContextAccessEvent("r1", "r-only", "planned_retrieval", "a"),
        ]
        report = ac.aggregate_access(events)
        self.assertEqual(report["tasks"], 4)
        self.assertEqual(report["demand_tasks"], 2)
        self.assertEqual(report["by_asset"]["a"]["need_task_rate"], 1.0)
        self.assertEqual(report["raw_misses"], 1)
        self.assertEqual(report["planned_retrievals"], 1)

    def test_prefetch_coverage_requires_caller_labels_and_raw_misses(self):
        events = [
            ac.ContextAccessEvent("m1", "t1", "soft_miss", "a", avoidable=True),
            ac.ContextAccessEvent("m2", "t2", "hard_miss", "b", avoidable=True),
            ac.ContextAccessEvent("p1", "t1", "prefetch", "a", used=True,
                                  avoided_miss=True, prefetched_units=1),
        ]
        report = ac.aggregate_access(events)
        self.assertEqual(report["prefetch_coverage"], 0.5)
        self.assertEqual(
            report["prefetch_coverage_basis"],
            "caller-labeled-avoided-misses-over-raw-misses",
        )

        unlabeled = ac.aggregate_access([
            ac.ContextAccessEvent("m3", "t3", "soft_miss", "a", avoidable=True),
        ])
        self.assertIsNone(unlabeled["prefetch_coverage"])
        self.assertIsNone(unlabeled["prefetch_coverage_basis"])

    def test_unknown_fields_and_duplicate_ids_fail(self):
        with self.assertRaises(ac.ControlError):
            ac.ContextAccessEvent.from_mapping({
                "event_id": "x", "task_id": "t", "kind": "context_hit",
                "asset_id": "a", "avoidble": True,
            })
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "events.json"
            path.write_text(json.dumps({
                "schema_version": 1,
                "events": [
                    {"event_id": "x", "task_id": "t1", "kind": "context_hit", "asset_id": "a"},
                    {"event_id": "x", "task_id": "t2", "kind": "context_hit", "asset_id": "a"},
                ],
            }), encoding="utf-8")
            with self.assertRaises(ac.ControlError):
                ac.load_events(path)

    def test_prefetch_metrics_are_explicit(self):
        events = [
            ac.ContextAccessEvent("p1", "t1", "prefetch", "a", used=True, avoided_miss=True,
                                  avoided_cost_units=5, extra_cost_units=1, prefetched_units=10),
            ac.ContextAccessEvent("p2", "t2", "prefetch", "a", used=False, avoided_miss=False,
                                  avoided_cost_units=0, extra_cost_units=1, prefetched_units=20),
        ]
        report = ac.aggregate_access(events)
        self.assertEqual(report["demand_tasks"], 0)
        self.assertEqual(report["prefetch_accuracy"], 0.5)
        self.assertAlmostEqual(report["prefetch_pollution_rate"], 20 / 30)
        self.assertEqual(report["prefetch_net_value_units"], 3)


class ResidencyTests(unittest.TestCase):
    def _demands(self, ids):
        events = []
        for task in ("t1", "t2", "t3"):
            for asset in ids:
                events.append(ac.ContextAccessEvent(
                    f"{task}:{asset}", task, "context_hit", asset
                ))
        return events

    def test_resident_hit_without_counterfactual_value_is_protected_for_review(self):
        events = self._demands(["resident"])
        assets = {
            "resident": ac.ContextAsset(
                "resident", "history", 5, 0.1, currently_resident=True
            )
        }
        report = ac.recommend_residency(
            events, assets, 5, min_demand_tasks=3, min_asset_demands=2
        )
        decision = report["decisions"][0]
        self.assertEqual(decision["action"], "keep-protected")
        self.assertFalse(decision["counterfactual_value_available"])

    def test_observed_avoidable_miss_can_admit(self):
        events = [
            ac.ContextAccessEvent("m1", "t1", "soft_miss", "a", avoidable=True, extra_cost_units=8),
            ac.ContextAccessEvent("m2", "t2", "soft_miss", "a", avoidable=True, extra_cost_units=8),
            ac.ContextAccessEvent("m3", "t3", "soft_miss", "a", avoidable=True, extra_cost_units=8),
        ]
        assets = {"a": ac.ContextAsset("a", "document", 3, 1.0)}
        report = ac.recommend_residency(
            events, assets, 3, min_demand_tasks=3, min_asset_demands=2
        )
        self.assertEqual(report["selected"], ["a"])
        self.assertEqual(report["decisions"][0]["action"], "admit")

    def test_unavoidable_miss_does_not_create_value(self):
        events = [
            ac.ContextAccessEvent("m1", "t1", "hard_miss", "a", extra_cost_units=100),
            ac.ContextAccessEvent("m2", "t2", "hard_miss", "a", extra_cost_units=100),
            ac.ContextAccessEvent("m3", "t3", "hard_miss", "a", extra_cost_units=100),
        ]
        assets = {"a": ac.ContextAsset("a", "document", 3, 0.1)}
        report = ac.recommend_residency(
            events, assets, 3, min_demand_tasks=3, min_asset_demands=2
        )
        self.assertEqual(report["selected"], [])
        self.assertEqual(report["decisions"][0]["action"], "review-insufficient-evidence")

    def test_exact_packing_beats_density_greedy(self):
        events = self._demands(["a", "b", "c"])
        assets = {
            "a": ac.ContextAsset("a", "document", 6, 1.0, counterfactual_miss_cost_units=10),
            "b": ac.ContextAsset("b", "document", 5, 1.0, counterfactual_miss_cost_units=8),
            "c": ac.ContextAsset("c", "document", 5, 1.0, counterfactual_miss_cost_units=8),
        }
        report = ac.recommend_residency(
            events, assets, 10, min_demand_tasks=3, min_asset_demands=2
        )
        self.assertEqual(set(report["selected"]), {"b", "c"})

    def test_stale_penalty_can_make_residency_negative(self):
        events = [
            ac.ContextAccessEvent("s1", "t1", "stale_hit", "a", extra_cost_units=10),
            ac.ContextAccessEvent("s2", "t2", "stale_hit", "a", extra_cost_units=10),
            ac.ContextAccessEvent("s3", "t3", "context_hit", "a"),
        ]
        assets = {
            "a": ac.ContextAsset(
                "a", "memory", 2, 0.1, currently_resident=True,
                counterfactual_miss_cost_units=2,
            )
        }
        report = ac.recommend_residency(
            events, assets, 2, min_demand_tasks=3, min_asset_demands=2
        )
        decision = report["decisions"][0]
        self.assertEqual(decision["action"], "evict")
        self.assertLess(decision["net_residency_value_units_per_task"], 0)


class LocatorPrefetchAndBudgetTests(unittest.TestCase):
    def test_locator_economics(self):
        report = ac.locator_economics(
            locator_units=20,
            locator_carry_cost_units_per_task=0.2,
            fetch_probability=0.5,
            search_avoided_units=10,
            fetch_cost_units=1,
        )
        self.assertAlmostEqual(report["net_locator_value_units_per_task"], 4.3)
        self.assertGreater(report["benefit_cost_ratio"], 1)

    def test_prefetch_uses_demand_cooccurrence_not_prefetch_history(self):
        events = [
            ac.ContextAccessEvent("s1", "t1", "context_hit", "seed"),
            ac.ContextAccessEvent("a1", "t1", "soft_miss", "a", avoidable=True, extra_cost_units=5),
            ac.ContextAccessEvent("s2", "t2", "context_hit", "seed"),
            ac.ContextAccessEvent("a2", "t2", "soft_miss", "a", avoidable=True, extra_cost_units=5),
            ac.ContextAccessEvent("fake", "t3", "prefetch", "b", used=True, avoided_miss=True,
                                  avoided_cost_units=100, prefetched_units=1),
        ]
        assets = {
            "seed": ac.ContextAsset("seed", "repo_map", 1, 0.1, currently_resident=True),
            "a": ac.ContextAsset("a", "document", 2, 0.1, locator="a.py",
                                 prefetch_units=1, prefetch_cost_units=0.1,
                                 prefetch_value_units=3),
            "b": ac.ContextAsset("b", "document", 2, 0.1, locator="b.py",
                                 prefetch_units=1, prefetch_cost_units=0.1,
                                 prefetch_value_units=100),
        }
        report = ac.recommend_prefetch(
            events, assets, ["seed"], 2, min_seed_demands=2, min_joint_tasks=2
        )
        self.assertEqual(report["selected"], ["a"])
        self.assertNotIn("b", [x["asset_id"] for x in report["candidates"]])
        with self.assertRaises(ac.ControlError):
            ac.recommend_prefetch(events, assets, ["missing"], 2)

    def test_budget_grows_under_miss_pressure_and_shrinks_under_pressure(self):
        current = ac.ContextBudget(100, 100, 100, 100, 100, 100, 0.5)
        bounds = ac.BudgetBounds(
            ac.ContextBudget(50, 50, 50, 50, 50, 0, 0.2),
            ac.ContextBudget(200, 200, 200, 200, 200, 200, 0.9),
        )
        grow = ac.suggest_budget(
            current, bounds,
            ac.ControllerObservation(0.4, 0.2, 5, 6, 0.9, 0.2, 500, 0.1, 0.01),
        )
        self.assertGreater(grow["proposed"]["retrieval_units"], 100)
        self.assertGreater(grow["proposed"]["repo_map_units"], 100)

        shrink = ac.suggest_budget(
            current, bounds,
            ac.ControllerObservation(0.01, 0.0, 0.0, 1, 0.2, 0.99, 5000, 0.9, 0.3),
        )
        self.assertLess(shrink["proposed"]["history_units"], 100)
        self.assertLess(shrink["proposed"]["prefetch_units"], 100)
        self.assertLess(shrink["proposed"]["compression_retained_ratio"], 0.5)


class AmplificationAndSharingTests(unittest.TestCase):
    def test_mutation_amplification(self):
        report = ac.mutation_amplification(
            ac.MutationReceipt("m", 2, 20, 10, 30, 40, 5)
        )
        self.assertEqual(report["storage_amplification"], 10)
        self.assertEqual(report["cache_invalidation_amplification"], 20)
        self.assertEqual(report["derived_write_fanout"], 5)

    def test_shared_immutable_base(self):
        report = ac.shared_immutable_context_economics(
            base_units=100, consumers=3, private_delta_units_per_consumer=10
        )
        self.assertEqual(report["duplicated_units"], 330)
        self.assertEqual(report["shared_base_plus_private_delta_units"], 130)
        self.assertEqual(report["saved_units"], 200)
        self.assertIn("private deltas remain isolated", report["boundary"])


class CLITests(unittest.TestCase):
    def test_cli_structured_error(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.json"
            bad.write_text('{"schema_version":1,"events":[{"event_id":"x","task_id":"t","kind":"context_hit","asset_id":"a","typo":1}]}', encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(Path(ac.__file__)), "telemetry", "--events", str(bad)],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            self.assertEqual(proc.returncode, 2)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["status"], "ERROR")


if __name__ == "__main__":
    unittest.main()
