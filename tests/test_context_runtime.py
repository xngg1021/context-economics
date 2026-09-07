import json
import math
import tempfile
import unittest
from pathlib import Path

import context_runtime as rt


def request(event_id="e1", run="r1", task="t1", policy="control", seq=0):
    return {
        "event_id": event_id, "event_kind": "request", "run_id": run,
        "task_id": task, "policy_id": policy, "occurred_at": "2026-09-07T10:00:00Z",
        "payload": {
            "request_id": "q" + event_id, "sequence_index": seq,
            "provider": "fake-http", "model": "deterministic", "model_revision": "v1",
            "request_start": "2026-09-07T10:00:00Z", "request_end": "2026-09-07T10:00:00.100Z",
            "input_tokens": 10, "cached_input_tokens": 4, "uncached_input_tokens": 6,
            "cache_write_tokens": 2, "output_tokens": 3, "provider_bill_usd": 0.001,
            "provider_bill_source": "fake-receipt", "billing_status": "estimated",
            "ttft_ms": 10.0, "request_wall_time_ms": 100.0,
            "context_length_before": 10, "context_length_after": 13,
            "compression_triggered": False, "provider_metadata": {"route": "local"},
        },
    }


def outcome(event_id="e2", run="r1", task="t1", policy="control"):
    return {
        "event_id": event_id, "event_kind": "outcome", "run_id": run,
        "task_id": task, "policy_id": policy, "occurred_at": "2026-09-07T10:00:01Z",
        "payload": {"success": True, "task_score": 1.0, "scorer_id": "exact",
                    "scorer_version": "v1", "scoring_provenance": "benchmark",
                    "harness_revision": "h1"},
    }


class RuntimeTests(unittest.TestCase):
    def normalized(self, rows=None):
        return rt.normalize([rt.Envelope.parse(x) for x in (rows or [request(), outcome()])])

    def test_normalizes_to_l5_receipt(self):
        out = self.normalized()
        receipt = out["l5_receipts"]["runs"][0]
        self.assertEqual(receipt["input_tokens"], 10)
        self.assertEqual(receipt["billing_status"], "estimated")
        self.assertEqual(receipt["scoring_provenance"], "benchmark")

    def test_unknown_typo_fails(self):
        row = request()
        row["payload"]["input_token"] = row["payload"].pop("input_tokens")
        with self.assertRaises(rt.TelemetryError): self.normalized([row, outcome()])

    def test_token_total_and_nonfinite_fail(self):
        row = request(); row["payload"]["uncached_input_tokens"] = 7
        with self.assertRaises(rt.TelemetryError): self.normalized([row, outcome()])
        row = request(); row["payload"]["provider_bill_usd"] = math.inf
        with self.assertRaises(rt.TelemetryError): self.normalized([row, outcome()])

    def test_cross_policy_and_nonmonotonic_fail(self):
        with self.assertRaises(rt.TelemetryError):
            self.normalized([request(), outcome(policy="treatment")])
        a = request(seq=1); b = request("e3", seq=0)
        with self.assertRaises(rt.TelemetryError): self.normalized([a, b, outcome()])

    def test_private_provider_metadata_fails(self):
        row = request(); row["payload"]["provider_metadata"] = {"Authorization": "secret"}
        with self.assertRaises(rt.TelemetryError): self.normalized([row, outcome()])

    def test_prefetch_requires_caller_label(self):
        prefetch = {"event_id":"pf1","event_kind":"context","run_id":"r1",
            "task_id":"t1","policy_id":"control","occurred_at":"2026-09-07T10:00:00Z",
            "payload":{"kind":"prefetch","asset_id":"a","used":True}}
        result = self.normalized([request(), prefetch, outcome()])
        event = result["l6_context_events"]["events"][0]
        self.assertIsNone(event["avoided_miss"])
        self.assertEqual(event["kind"], "prefetch")

    def test_collector_duplicate_and_cli(self):
        c = rt.Collector(rt.CanonicalAdapter()); c.capture(request())
        with self.assertRaises(rt.TelemetryError): c.capture(request())
        c.capture(outcome())
        with tempfile.TemporaryDirectory() as td:
            src, dst = Path(td)/"raw.json", Path(td)/"out.json"
            src.write_text(json.dumps(c.bundle()), encoding="utf-8")
            self.assertEqual(rt.main(["--input", str(src), "--output", str(dst)]), 0)
            self.assertEqual(json.loads(dst.read_text())["schema_version"], 1)


if __name__ == "__main__": unittest.main()
