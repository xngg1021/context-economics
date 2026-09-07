#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parent

ac = root / "adaptive_control.py"
text = ac.read_text(encoding="utf-8")
old = '''    avoided_prefetches = sum(1 for row in prefetch_rows if row.avoided_miss is True)\n    total_prefetched = sum(row.prefetched_units for row in prefetch_rows)\n'''
new = '''    avoided_prefetches = sum(1 for row in prefetch_rows if row.avoided_miss is True)\n    labeled_prefetches = [row for row in prefetch_rows if row.avoided_miss is not None]\n    total_prefetched = sum(row.prefetched_units for row in prefetch_rows)\n'''
if old not in text:
    raise SystemExit("adaptive_control prefetch anchor not found")
text = text.replace(old, new, 1)
old = '''        "prefetch_observed_avoided_misses": avoided_prefetches,\n        "prefetch_units": total_prefetched,\n'''
new = '''        "prefetch_observed_avoided_misses": avoided_prefetches,\n        "prefetch_coverage": (\n            avoided_prefetches / len(miss_rows)\n            if miss_rows and labeled_prefetches\n            else None\n        ),\n        "prefetch_coverage_basis": (\n            "caller-labeled-avoided-misses-over-raw-misses"\n            if miss_rows and labeled_prefetches\n            else None\n        ),\n        "prefetch_units": total_prefetched,\n'''
if old not in text:
    raise SystemExit("adaptive_control coverage output anchor not found")
ac.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

test = root / "tests" / "test_adaptive_control.py"
text = test.read_text(encoding="utf-8")
anchor = '''    def test_unknown_fields_and_duplicate_ids_fail(self):\n'''
method = '''    def test_prefetch_coverage_requires_caller_labels_and_raw_misses(self):\n        events = [\n            ac.ContextAccessEvent("m1", "t1", "soft_miss", "a", avoidable=True),\n            ac.ContextAccessEvent("m2", "t2", "hard_miss", "b", avoidable=True),\n            ac.ContextAccessEvent("p1", "t1", "prefetch", "a", used=True,\n                                  avoided_miss=True, prefetched_units=1),\n        ]\n        report = ac.aggregate_access(events)\n        self.assertEqual(report["prefetch_coverage"], 0.5)\n        self.assertEqual(\n            report["prefetch_coverage_basis"],\n            "caller-labeled-avoided-misses-over-raw-misses",\n        )\n\n        unlabeled = ac.aggregate_access([\n            ac.ContextAccessEvent("m3", "t3", "soft_miss", "a", avoidable=True),\n        ])\n        self.assertIsNone(unlabeled["prefetch_coverage"])\n        self.assertIsNone(unlabeled["prefetch_coverage_basis"])\n\n'''
if anchor not in text:
    raise SystemExit("test insertion anchor not found")
test.write_text(text.replace(anchor, method + anchor, 1), encoding="utf-8", newline="\n")
