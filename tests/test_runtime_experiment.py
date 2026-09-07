import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import runtime_experiment as rexp


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "fixtures" / "runtime_experiment_manifest.json"
RECEIPTS = ROOT / "fixtures" / "runtime_ab_receipts.json"
EVENTS = ROOT / "fixtures" / "runtime_context_events.json"


class RuntimeExperimentContractTests(unittest.TestCase):
    def setUp(self):
        self.manifest = rexp.load_manifest(MANIFEST)
        self.receipts = rexp.load_receipt_records(RECEIPTS)
        self.events = rexp.load_experiment_events(EVENTS)

    def test_synthetic_fixture_is_complete_but_not_promoted_to_runtime(self):
        report = rexp.build_joint_report(
            self.manifest, self.receipts, self.events, require_complete=True
        )
        self.assertTrue(report["structurally_complete"])
        self.assertFalse(report["runtime_design_structurally_ready"])
        self.assertEqual(report["declared_evidence_class"], "synthetic-contract")
        self.assertEqual(report["causal_claim"], "not inferred by this validator")
        self.assertEqual(report["paired_task_report"]["paired_coverage"], 1.0)
        self.assertEqual(set(report["by_policy_context_telemetry"]), {
            "baseline-context", "adaptive-shadow"
        })

    def test_runtime_label_can_only_upgrade_structural_readiness(self):
        manifest = replace(
            self.manifest,
            declared_evidence_class="runtime-A/B",
            assignment_method="randomized",
        )
        report = rexp.build_joint_report(
            manifest, self.receipts, self.events, require_complete=True
        )
        self.assertTrue(report["runtime_design_structurally_ready"])
        self.assertEqual(report["causal_claim"], "not inferred by this validator")

    def test_zero_success_report_serializes_without_nonstandard_infinity(self):
        failed = [
            rexp.ReceiptRecord(
                replace(row.receipt, success=False, task_score=0.0),
                row.explicit_fields,
            )
            for row in self.receipts
        ]
        report = rexp.build_joint_report(
            self.manifest, failed, self.events, require_complete=True
        )
        safe = rexp._json_safe(report)
        encoded = json.dumps(safe, allow_nan=False)
        self.assertIn('"cost_per_success_usd": null', encoded)

    def test_timestamp_order_and_timezone_are_validated(self):
        broken = list(self.receipts)
        broken[0] = rexp.ReceiptRecord(
            replace(
                broken[0].receipt,
                started_at="2026-09-07T00:00:10+00:00",
                ended_at="2026-09-07T00:00:00+00:00",
            ),
            broken[0].explicit_fields,
        )
        with self.assertRaises(rexp.ExperimentError):
            rexp.build_joint_report(self.manifest, broken, self.events)

        naive = list(self.receipts)
        naive[0] = rexp.ReceiptRecord(
            replace(naive[0].receipt, started_at="2026-09-07T00:00:00"),
            naive[0].explicit_fields,
        )
        with self.assertRaises(rexp.ExperimentError):
            rexp.build_joint_report(self.manifest, naive, self.events)

    def test_receipt_revision_mismatch_fails(self):
        broken = list(self.receipts)
        broken[0] = rexp.ReceiptRecord(
            replace(broken[0].receipt, model_revision="wrong-rev"),
            broken[0].explicit_fields,
        )
        with self.assertRaises(rexp.ExperimentError):
            rexp.build_joint_report(self.manifest, broken, self.events)

    def test_orphan_event_fails(self):
        broken = list(self.events)
        broken[0] = replace(broken[0], run_id="unknown-run")
        with self.assertRaises(rexp.ExperimentError):
            rexp.build_joint_report(self.manifest, self.receipts, broken)

    def test_event_policy_or_task_mismatch_fails(self):
        broken_policy = list(self.events)
        broken_policy[0] = replace(broken_policy[0], policy_id="adaptive-shadow")
        with self.assertRaises(rexp.ExperimentError):
            rexp.build_joint_report(self.manifest, self.receipts, broken_policy)

        broken_task = list(self.events)
        broken_task[0] = replace(
            broken_task[0],
            event=replace(broken_task[0].event, task_id="task-b"),
        )
        with self.assertRaises(rexp.ExperimentError):
            rexp.build_joint_report(self.manifest, self.receipts, broken_task)

    def test_missing_arm_is_disclosed_and_require_complete_fails(self):
        incomplete = [
            row for row in self.receipts if row.receipt.run_id != "t-b"
        ]
        events = [row for row in self.events if row.run_id != "t-b"]
        report = rexp.build_joint_report(
            self.manifest, incomplete, events, require_complete=False
        )
        self.assertFalse(report["structurally_complete"])
        self.assertIn(
            {"task_id": "task-b", "policy_id": "adaptive-shadow"},
            report["missing_arms"],
        )
        with self.assertRaises(rexp.ExperimentError):
            rexp.build_joint_report(
                self.manifest, incomplete, events, require_complete=True
            )

    def test_run_without_context_events_is_incomplete(self):
        events = [row for row in self.events if row.run_id != "t-b"]
        report = rexp.build_joint_report(
            self.manifest, self.receipts, events, require_complete=False
        )
        self.assertEqual(report["runs_without_context_events"], ["t-b"])
        self.assertFalse(report["structurally_complete"])

    def test_runtime_receipt_fields_must_be_explicit(self):
        payload = json.loads(RECEIPTS.read_text(encoding="utf-8"))
        del payload["runs"][0]["provider_bill_usd"]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "receipts.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(rexp.ExperimentError):
                rexp.load_receipt_records(path)

    def test_manifest_unknown_field_and_duplicate_tasks_fail(self):
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))["manifest"]
        bad = dict(payload)
        bad["typo"] = 1
        with self.assertRaises(rexp.ExperimentError):
            rexp.ExperimentManifest.from_mapping(bad)

        dup = dict(payload)
        dup["expected_task_ids"] = ["task-a", "task-a"]
        with self.assertRaises(rexp.ExperimentError):
            rexp.ExperimentManifest.from_mapping(dup)

    def test_experiment_event_unknown_field_fails(self):
        raw = {
            "run_id": "r",
            "policy_id": "p",
            "event_id": "e",
            "task_id": "t",
            "kind": "context_hit",
            "asset_id": "a",
            "typo": True,
        }
        with self.assertRaises(rexp.ExperimentError):
            rexp.ExperimentContextEvent.from_mapping(raw)


if __name__ == "__main__":
    unittest.main()
