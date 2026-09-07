# -*- coding: utf-8 -*-
"""Task-level economics for context-policy experiments.

This module validates and aggregates observed run receipts. It deliberately does
not infer causality: callers are responsible for paired tasks, version pinning,
cache controls, and task scoring.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, fields
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping, Sequence


class ReceiptError(ValueError):
    """Structured receipt/schema error."""


def _text(value: object, name: str, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ReceiptError(f"{name} must be a non-empty string")
    return value


def _bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise ReceiptError(f"{name} must be boolean")
    return value


def _number(
    value: object,
    name: str,
    *,
    minimum: float | None = 0.0,
    maximum: float | None = None,
    allow_none: bool = False,
) -> float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReceiptError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ReceiptError(f"{name} must be finite")
    if minimum is not None and number < minimum:
        raise ReceiptError(f"{name} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise ReceiptError(f"{name} must be <= {maximum}")
    return number


def _integer(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReceiptError(f"{name} must be an integer")
    if value < minimum:
        raise ReceiptError(f"{name} must be >= {minimum}")
    return value


def _notes(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ReceiptError("notes must be a list of strings")
    out: list[str] = []
    for idx, item in enumerate(value):
        text = _text(item, f"notes[{idx}]")
        assert isinstance(text, str)
        out.append(text)
    return tuple(out)


@dataclass(frozen=True)
class RunReceipt:
    run_id: str
    task_id: str
    policy_id: str
    success: bool

    provider: str | None = None
    model: str | None = None
    model_revision: str | None = None
    harness_revision: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    task_score: float | None = None

    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0

    provider_bill_usd: float = 0.0
    provider_bill_source: str | None = None
    billing_status: str | None = None
    cost_ledger_version: int | None = None
    external_cost_usd: float = 0.0
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

    ttft_ms: float | None = None
    wall_time_ms: float = 0.0
    failure_class: str | None = None
    scorer_id: str | None = None
    scorer_version: str | None = None
    scoring_provenance: str | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self):
        version = self.cost_ledger_version
        if version is None:
            if self.reacquisition_cost_usd != 0 or self.retry_cost_usd != 0:
                raise ReceiptError("ambiguous classified costs: explicitly set cost_ledger_version=1 for legacy additive or migrate to 2")
            object.__setattr__(self, "cost_ledger_version", 2)
        elif type(version) is not int or version not in {1, 2}:
            raise ReceiptError("cost_ledger_version must be 1 or 2")

    @property
    def observed_cost_usd(self) -> float:
        return (
            self.provider_bill_usd
            + self.tool_cost_usd
            + self.external_cost_usd
            + (self.reacquisition_cost_usd + self.retry_cost_usd
               if self.cost_ledger_version == 1 else 0.0)
            + self.latency_cost_usd
            + self.failure_cost_usd
        )

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "RunReceipt":
        if not isinstance(row, Mapping):
            raise ReceiptError("run receipt must be an object")
        allowed = {f.name for f in fields(cls)}
        unknown = sorted(set(row) - allowed)
        if unknown:
            raise ReceiptError("unknown receipt fields: " + ", ".join(unknown))

        required = ("run_id", "task_id", "policy_id", "success")
        missing = [name for name in required if name not in row]
        if missing:
            raise ReceiptError("missing required receipt fields: " + ", ".join(missing))

        version = row.get("cost_ledger_version", 2)
        if type(version) is not int or version not in {1, 2}:
            raise ReceiptError("cost_ledger_version must be 1 (legacy additive) or 2 (attribution)")
        if "cost_ledger_version" not in row and any(row.get(k, 0) != 0 for k in ("reacquisition_cost_usd", "retry_cost_usd")):
            raise ReceiptError("ambiguous classified costs: explicitly set cost_ledger_version=1 for legacy additive or migrate to 2")

        strings = {}
        for name in (
            "provider",
            "model",
            "model_revision",
            "harness_revision",
            "started_at",
            "ended_at",
            "failure_class",
            "provider_bill_source",
            "billing_status",
            "scorer_id",
            "scorer_version",
            "scoring_provenance",
        ):
            strings[name] = _text(row.get(name), name, allow_none=True)

        if strings["billing_status"] not in {None, "observed", "estimated"}:
            raise ReceiptError("billing_status must be observed or estimated")
        if strings["scoring_provenance"] not in {
            None, "human", "automatic", "benchmark",
        }:
            raise ReceiptError(
                "scoring_provenance must be human, automatic, or benchmark"
            )

        task_score = _number(
            row.get("task_score"),
            "task_score",
            minimum=None,
            allow_none=True,
        )
        ttft_ms = _number(
            row.get("ttft_ms"),
            "ttft_ms",
            allow_none=True,
        )

        integer_names = (
            "input_tokens",
            "cached_input_tokens",
            "cache_write_tokens",
            "output_tokens",
            "tool_calls",
            "retrieval_calls",
            "reacquisition_calls",
            "retry_count",
            "compression_calls",
        )
        ints = {
            name: _integer(row.get(name, 0), name)
            for name in integer_names
        }
        if ints["cached_input_tokens"] > ints["input_tokens"]:
            raise ReceiptError(
                "cached_input_tokens cannot exceed input_tokens under this receipt schema"
            )
        if ints["reacquisition_calls"] > ints["retrieval_calls"]:
            raise ReceiptError(
                "reacquisition_calls cannot exceed retrieval_calls"
            )

        numeric_names = (
            "provider_bill_usd",
            "external_cost_usd",
            "tool_cost_usd",
            "reacquisition_cost_usd",
            "retry_cost_usd",
            "latency_cost_usd",
            "failure_cost_usd",
            "wall_time_ms",
        )
        nums = {
            name: _number(row.get(name, 0.0), name)
            for name in numeric_names
        }

        run_id = _text(row["run_id"], "run_id")
        task_id = _text(row["task_id"], "task_id")
        policy_id = _text(row["policy_id"], "policy_id")
        assert isinstance(run_id, str) and isinstance(task_id, str)
        assert isinstance(policy_id, str)

        return cls(
            run_id=run_id,
            task_id=task_id,
            policy_id=policy_id,
            success=_bool(row["success"], "success"),
            cost_ledger_version=version,
            task_score=task_score,
            ttft_ms=ttft_ms,
            notes=_notes(row.get("notes")),
            **strings,
            **ints,
            **nums,
        )


def load_receipts(path: str | Path) -> list[RunReceipt]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        unknown = sorted(set(payload) - {"schema_version", "note", "runs"})
        if unknown:
            raise ReceiptError("unknown receipt wrapper fields: " + ", ".join(unknown))
        if payload.get("schema_version") != 1:
            raise ReceiptError("receipt wrapper requires schema_version=1")
        rows = payload.get("runs")
    else:
        rows = payload

    if not isinstance(rows, list):
        raise ReceiptError("runs must be a list")

    out: list[RunReceipt] = []
    seen: set[str] = set()
    for raw in rows:
        row = RunReceipt.from_mapping(raw)
        if row.run_id in seen:
            raise ReceiptError(f"duplicate run_id: {row.run_id}")
        seen.add(row.run_id)
        out.append(row)
    return out


def _percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return ordered[lo]
    weight = position - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def aggregate(receipts: Iterable[RunReceipt]) -> dict:
    rows = list(receipts)
    if not rows:
        raise ReceiptError("at least one receipt is required")

    successes = sum(1 for row in rows if row.success)
    total_cost = sum(row.observed_cost_usd for row in rows)
    total_provider_bill = sum(row.provider_bill_usd for row in rows)
    total_input = sum(row.input_tokens for row in rows)
    total_cached = sum(row.cached_input_tokens for row in rows)
    scores = [row.task_score for row in rows if row.task_score is not None]
    ttfts = [row.ttft_ms for row in rows if row.ttft_ms is not None]
    walls = [row.wall_time_ms for row in rows]

    return {
        "runs": len(rows),
        "successes": successes,
        "success_rate": successes / len(rows),
        "mean_task_score": mean(scores) if scores else None,
        "total_observed_cost_usd": total_cost,
        "total_provider_bill_usd": total_provider_bill,
        "mean_observed_cost_usd": total_cost / len(rows),
        "cost_per_success_usd": (
            total_cost / successes if successes else math.inf
        ),
        "total_input_tokens": total_input,
        "total_cached_input_tokens": total_cached,
        "total_cache_write_tokens": sum(row.cache_write_tokens for row in rows),
        "total_output_tokens": sum(row.output_tokens for row in rows),
        "cache_hit_share": total_cached / total_input if total_input else None,
        "mean_tool_calls": mean(row.tool_calls for row in rows),
        "mean_retrieval_calls": mean(row.retrieval_calls for row in rows),
        "mean_reacquisition_calls": mean(row.reacquisition_calls for row in rows),
        "mean_retry_count": mean(row.retry_count for row in rows),
        "mean_compression_calls": mean(row.compression_calls for row in rows),
        "mean_wall_time_ms": mean(walls),
        "p50_wall_time_ms": _percentile(walls, 0.50),
        "p95_wall_time_ms": _percentile(walls, 0.95),
        "p50_ttft_ms": _percentile(ttfts, 0.50),
        "p95_ttft_ms": _percentile(ttfts, 0.95),
        "failure_classes": _failure_class_counts(rows),
    }


def _failure_class_counts(rows: Sequence[RunReceipt]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        if row.failure_class is None:
            continue
        out[row.failure_class] = out.get(row.failure_class, 0) + 1
    return dict(sorted(out.items()))


def aggregate_by_policy(receipts: Iterable[RunReceipt]) -> dict[str, dict]:
    groups: dict[str, list[RunReceipt]] = {}
    for row in receipts:
        groups.setdefault(row.policy_id, []).append(row)
    return {policy: aggregate(rows) for policy, rows in sorted(groups.items())}


def paired_task_report(
    receipts: Iterable[RunReceipt],
    control_policy: str,
    treatment_policy: str,
) -> dict:
    control_policy = _text(control_policy, "control_policy")
    treatment_policy = _text(treatment_policy, "treatment_policy")
    assert isinstance(control_policy, str) and isinstance(treatment_policy, str)
    if control_policy == treatment_policy:
        raise ReceiptError("control and treatment policies must differ")

    by_task: dict[str, dict[str, list[RunReceipt]]] = {}
    for row in receipts:
        if row.policy_id not in {control_policy, treatment_policy}:
            continue
        by_task.setdefault(row.task_id, {}).setdefault(row.policy_id, []).append(row)

    deltas: list[dict] = []
    paired_run_ids: list[str] = []
    omitted_missing_arm: list[str] = []
    omitted_duplicate_arm: list[str] = []

    for task_id, arms in sorted(by_task.items()):
        control = arms.get(control_policy, [])
        treatment = arms.get(treatment_policy, [])
        if not control or not treatment:
            omitted_missing_arm.append(task_id)
            continue
        if len(control) != 1 or len(treatment) != 1:
            omitted_duplicate_arm.append(task_id)
            continue

        c, t = control[0], treatment[0]
        paired_run_ids.extend((c.run_id, t.run_id))
        deltas.append(
            {
                "task_id": task_id,
                "cost_delta_usd": t.observed_cost_usd - c.observed_cost_usd,
                "provider_bill_delta_usd": (
                    t.provider_bill_usd - c.provider_bill_usd
                ),
                "success_delta": int(t.success) - int(c.success),
                "task_score_delta": (
                    t.task_score - c.task_score
                    if t.task_score is not None and c.task_score is not None
                    else None
                ),
                "input_token_delta": t.input_tokens - c.input_tokens,
                "cached_input_token_delta": (
                    t.cached_input_tokens - c.cached_input_tokens
                ),
                "cache_write_token_delta": (
                    t.cache_write_tokens - c.cache_write_tokens
                ),
                "output_token_delta": t.output_tokens - c.output_tokens,
                "tool_call_delta": t.tool_calls - c.tool_calls,
                "retrieval_call_delta": (
                    t.retrieval_calls - c.retrieval_calls
                ),
                "reacquisition_call_delta": (
                    t.reacquisition_calls - c.reacquisition_calls
                ),
                "retry_delta": t.retry_count - c.retry_count,
                "compression_call_delta": (
                    t.compression_calls - c.compression_calls
                ),
                "ttft_delta_ms": (
                    t.ttft_ms - c.ttft_ms
                    if t.ttft_ms is not None and c.ttft_ms is not None
                    else None
                ),
                "wall_time_delta_ms": t.wall_time_ms - c.wall_time_ms,
            }
        )

    candidate_tasks = len(by_task)
    return {
        "control_policy": control_policy,
        "treatment_policy": treatment_policy,
        "candidate_tasks": candidate_tasks,
        "paired_tasks": len(deltas),
        "paired_coverage": (
            len(deltas) / candidate_tasks if candidate_tasks else None
        ),
        "omitted_missing_arm": omitted_missing_arm,
        "omitted_duplicate_arm": omitted_duplicate_arm,
        "paired_run_ids": paired_run_ids,
        "paired_task_ids": [d["task_id"] for d in deltas],
        "deltas": deltas,
    }


def extract_exact_pairs(receipts, control, treatment):
    """Single pairing authority for aggregate gates and statistics."""
    rows = list(receipts)
    ids = [r.run_id for r in rows]
    if len(ids) != len(set(ids)):
        raise ReceiptError("duplicate run_id")
    report = paired_task_report(rows, control, treatment)
    paired_ids = set(report["paired_run_ids"])
    return report, [r for r in rows if r.run_id in paired_ids]


def paired_task_deltas(
    receipts: Iterable[RunReceipt],
    control_policy: str,
    treatment_policy: str,
) -> list[dict]:
    """Backward-compatible delta-only view over the explicit pairing report."""
    return paired_task_report(
        receipts, control_policy, treatment_policy
    )["deltas"]


def _json_safe(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and aggregate task-economics run receipts."
    )
    parser.add_argument("--receipts", required=True, help="JSON run-receipt file")
    parser.add_argument("--control", help="optional control policy id")
    parser.add_argument("--treatment", help="optional treatment policy id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rows = load_receipts(args.receipts)
        output: dict[str, object] = {
            "scope": "observed-run-receipts-not-causal-inference",
            "by_policy": aggregate_by_policy(rows),
        }
        if args.control or args.treatment:
            if not (args.control and args.treatment):
                raise ReceiptError(
                    "--control and --treatment must be supplied together"
                )
            output["paired"] = paired_task_report(
                rows, args.control, args.treatment
            )
        print(
            json.dumps(
                _json_safe(output),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    except (ReceiptError, json.JSONDecodeError, OSError, KeyError, TypeError) as exc:
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
