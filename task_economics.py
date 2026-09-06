# -*- coding: utf-8 -*-
"""Task-level economics for context-policy experiments.

This module aggregates observed run receipts. It deliberately does not infer
causality: callers are responsible for experimental design (paired tasks,
version pinning, cache controls, etc.).
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable, Sequence


@dataclass(frozen=True)
class RunReceipt:
    run_id: str
    task_id: str
    policy_id: str
    success: bool
    provider_bill_usd: float = 0.0
    tool_cost_usd: float = 0.0
    reacquisition_cost_usd: float = 0.0
    retry_cost_usd: float = 0.0
    latency_cost_usd: float = 0.0
    failure_cost_usd: float = 0.0
    tool_calls: int = 0
    retrieval_calls: int = 0
    reacquisition_calls: int = 0
    retry_count: int = 0
    compression_calls: int = 0
    wall_time_ms: float = 0.0

    @property
    def observed_cost_usd(self) -> float:
        return (
            self.provider_bill_usd
            + self.tool_cost_usd
            + self.reacquisition_cost_usd
            + self.retry_cost_usd
            + self.latency_cost_usd
            + self.failure_cost_usd
        )

    @classmethod
    def from_mapping(cls, row: dict) -> "RunReceipt":
        fields = {
            "run_id": str(row["run_id"]),
            "task_id": str(row["task_id"]),
            "policy_id": str(row["policy_id"]),
            "success": bool(row["success"]),
        }
        for name in (
            "provider_bill_usd",
            "tool_cost_usd",
            "reacquisition_cost_usd",
            "retry_cost_usd",
            "latency_cost_usd",
            "failure_cost_usd",
            "wall_time_ms",
        ):
            fields[name] = float(row.get(name, 0.0) or 0.0)
        for name in (
            "tool_calls",
            "retrieval_calls",
            "reacquisition_calls",
            "retry_count",
            "compression_calls",
        ):
            fields[name] = int(row.get(name, 0) or 0)
        return cls(**fields)


def load_receipts(path: str | Path) -> list[RunReceipt]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload["runs"] if isinstance(payload, dict) else payload
    return [RunReceipt.from_mapping(row) for row in rows]


def aggregate(receipts: Iterable[RunReceipt]) -> dict:
    rows = list(receipts)
    if not rows:
        raise ValueError("at least one receipt is required")

    successes = sum(1 for row in rows if row.success)
    total_cost = sum(row.observed_cost_usd for row in rows)
    total_provider_bill = sum(row.provider_bill_usd for row in rows)

    return {
        "runs": len(rows),
        "successes": successes,
        "success_rate": successes / len(rows),
        "total_observed_cost_usd": total_cost,
        "total_provider_bill_usd": total_provider_bill,
        "mean_observed_cost_usd": total_cost / len(rows),
        "cost_per_success_usd": (
            total_cost / successes if successes else math.inf
        ),
        "mean_tool_calls": mean(row.tool_calls for row in rows),
        "mean_retrieval_calls": mean(row.retrieval_calls for row in rows),
        "mean_reacquisition_calls": mean(
            row.reacquisition_calls for row in rows
        ),
        "mean_retry_count": mean(row.retry_count for row in rows),
        "mean_compression_calls": mean(
            row.compression_calls for row in rows
        ),
        "mean_wall_time_ms": mean(row.wall_time_ms for row in rows),
    }


def aggregate_by_policy(receipts: Iterable[RunReceipt]) -> dict[str, dict]:
    groups: dict[str, list[RunReceipt]] = {}
    for row in receipts:
        groups.setdefault(row.policy_id, []).append(row)
    return {policy: aggregate(rows) for policy, rows in sorted(groups.items())}


def paired_task_deltas(
    receipts: Iterable[RunReceipt],
    control_policy: str,
    treatment_policy: str,
) -> list[dict]:
    """Return per-task treatment-control deltas for tasks with exactly one each.

    Ambiguous tasks (duplicates or missing arms) are skipped rather than silently
    averaged. Large experiments should use a richer statistical pipeline.
    """
    by_task: dict[str, dict[str, list[RunReceipt]]] = {}
    for row in receipts:
        if row.policy_id not in {control_policy, treatment_policy}:
            continue
        by_task.setdefault(row.task_id, {}).setdefault(row.policy_id, []).append(row)

    out: list[dict] = []
    for task_id, arms in sorted(by_task.items()):
        control = arms.get(control_policy, [])
        treatment = arms.get(treatment_policy, [])
        if len(control) != 1 or len(treatment) != 1:
            continue
        c, t = control[0], treatment[0]
        out.append(
            {
                "task_id": task_id,
                "cost_delta_usd": t.observed_cost_usd - c.observed_cost_usd,
                "provider_bill_delta_usd": t.provider_bill_usd - c.provider_bill_usd,
                "success_delta": int(t.success) - int(c.success),
                "reacquisition_call_delta": (
                    t.reacquisition_calls - c.reacquisition_calls
                ),
                "retry_delta": t.retry_count - c.retry_count,
                "wall_time_delta_ms": t.wall_time_ms - c.wall_time_ms,
            }
        )
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate task-economics run receipts."
    )
    parser.add_argument("--receipts", required=True, help="JSON run-receipt file")
    parser.add_argument("--control", help="optional control policy id")
    parser.add_argument("--treatment", help="optional treatment policy id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rows = load_receipts(args.receipts)
    print(json.dumps(aggregate_by_policy(rows), indent=2, ensure_ascii=False))

    if args.control or args.treatment:
        if not (args.control and args.treatment):
            raise SystemExit("--control and --treatment must be supplied together")
        deltas = paired_task_deltas(rows, args.control, args.treatment)
        print("\npaired task deltas:")
        print(json.dumps(deltas, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
