# -*- coding: utf-8 -*-
"""Deterministic paired experiment scheduling, statistics, and hard gates."""
from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass, fields
from pathlib import Path
from statistics import mean, median
from typing import Mapping, Sequence

import adaptive_control as ac
import task_economics as te


class AnalysisError(ValueError): pass


def counterbalanced_schedule(task_ids: Sequence[str], control: str, treatment: str) -> list[dict]:
    if not task_ids or len(set(task_ids)) != len(task_ids):
        raise AnalysisError("task_ids must be non-empty and unique")
    if control == treatment or not control or not treatment:
        raise AnalysisError("control and treatment must be distinct")
    return [
        {"task_id": task, "order": [control, treatment] if i % 2 == 0 else [treatment, control]}
        for i, task in enumerate(task_ids)
    ]


def _percentile(values: Sequence[float], q: float) -> float | None:
    if not values: return None
    ordered = sorted(values); pos = (len(ordered)-1)*q
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] if lo == hi else ordered[lo]*(hi-pos)+ordered[hi]*(pos-lo)


def describe(values: Sequence[float]) -> dict:
    if not values:
        return {"count": 0, "mean": None, "median": None, "p50": None, "p95": None,
                "min": None, "max": None, "wins": 0, "losses": 0, "ties": 0}
    return {"count": len(values), "mean": mean(values), "median": median(values),
            "p50": _percentile(values, .5), "p95": _percentile(values, .95),
            "min": min(values), "max": max(values),
            "wins": sum(x < 0 for x in values), "losses": sum(x > 0 for x in values),
            "ties": sum(x == 0 for x in values)}


def bootstrap_mean_ci(values: Sequence[float], *, seed: int = 0, samples: int = 2000, confidence: float = .95) -> dict:
    if not values:
        return {"status": "insufficient evidence", "n": 0}
    if samples < 100 or not 0 < confidence < 1:
        raise AnalysisError("bootstrap requires samples >= 100 and 0 < confidence < 1")
    rng = random.Random(seed); n = len(values)
    means = sorted(mean(rng.choice(values) for _ in range(n)) for _ in range(samples))
    alpha = (1-confidence)/2
    return {"status": "descriptive-only" if n < 20 else "interval-estimate",
            "n": n, "seed": seed, "samples": samples, "confidence": confidence,
            "low": _percentile(means, alpha), "high": _percentile(means, 1-alpha)}


METRICS = (
    "cost_delta_usd", "provider_bill_delta_usd", "success_delta", "task_score_delta",
    "input_token_delta", "cached_input_token_delta", "cache_write_token_delta",
    "output_token_delta", "tool_call_delta", "retrieval_call_delta",
    "reacquisition_call_delta", "retry_delta", "compression_call_delta",
    "ttft_delta_ms", "wall_time_delta_ms",
)


def paired_statistics(receipts: Sequence[te.RunReceipt], control: str, treatment: str, *, seed: int = 0) -> dict:
    pairing = te.paired_task_report(receipts, control, treatment)
    stats = {}
    for metric in METRICS:
        values = [float(row[metric]) for row in pairing["deltas"] if row[metric] is not None]
        stats[metric] = {**describe(values), "bootstrap_mean_ci": bootstrap_mean_ci(values, seed=seed)}
    return {"scope": "paired-descriptive-statistics-not-production-proof", **pairing, "statistics": stats}


@dataclass(frozen=True)
class GateConfig:
    quality_epsilon: float = 0.0
    min_cost_per_success_improvement: float = 0.0
    max_reacquisition_delta: float = 0.0
    max_treatment_p95_wall_time_ms: float = math.inf
    max_prefetch_pollution: float = 1.0
    max_stale_hit_rate: float = 1.0
    min_paired_coverage: float = 1.0

    @classmethod
    def parse(cls, value: Mapping[str, object]) -> "GateConfig":
        if not isinstance(value, Mapping): raise AnalysisError("gate config must be an object")
        allowed = {f.name for f in fields(cls)}
        if set(value) - allowed: raise AnalysisError("unknown gate fields: " + repr(sorted(set(value)-allowed)))
        kwargs = {}
        for name, raw in value.items():
            if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
                raise AnalysisError(f"{name} must be finite numeric")
            kwargs[name] = float(raw)
        cfg = cls(**kwargs)
        if min(cfg.quality_epsilon, cfg.min_cost_per_success_improvement, cfg.max_reacquisition_delta,
               cfg.max_treatment_p95_wall_time_ms, cfg.max_prefetch_pollution,
               cfg.max_stale_hit_rate, cfg.min_paired_coverage) < 0:
            raise AnalysisError("gate thresholds must be non-negative")
        return cfg


def acceptance_gate(receipts: Sequence[te.RunReceipt], context_by_policy: Mapping[str, Sequence[ac.ContextAccessEvent]], control: str, treatment: str, config: GateConfig) -> dict:
    by_policy = te.aggregate_by_policy(receipts)
    if control not in by_policy or treatment not in by_policy:
        raise AnalysisError("both policies require receipts")
    pair = te.paired_task_report(receipts, control, treatment)
    c, t = by_policy[control], by_policy[treatment]
    c_cps, t_cps = c["cost_per_success_usd"], t["cost_per_success_usd"]
    improvement = ((c_cps-t_cps)/c_cps if math.isfinite(c_cps) and c_cps > 0 else None)
    tctx = ac.aggregate_access(context_by_policy.get(treatment, []))
    checks = {
        "paired_coverage": pair["paired_coverage"] is not None and pair["paired_coverage"] >= config.min_paired_coverage,
        "quality_floor": t["success_rate"] >= c["success_rate"] - config.quality_epsilon,
        "cost_target": improvement is not None and improvement >= config.min_cost_per_success_improvement,
        "reacquisition_ceiling": t["mean_reacquisition_calls"] <= c["mean_reacquisition_calls"] + config.max_reacquisition_delta,
        "latency_ceiling": t["p95_wall_time_ms"] <= config.max_treatment_p95_wall_time_ms,
        "prefetch_pollution": tctx["prefetch_pollution_rate"] is None or tctx["prefetch_pollution_rate"] <= config.max_prefetch_pollution,
        "staleness": tctx["stale_hit_event_rate"] is None or tctx["stale_hit_event_rate"] <= config.max_stale_hit_rate,
    }
    return {"scope": "candidate-gate-only-no-auto-enable", "checks": checks,
            "candidate_for_promotion": all(checks.values()),
            "cost_per_success_improvement": improvement}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(); p.add_argument("--receipts", required=True)
    p.add_argument("--control", required=True); p.add_argument("--treatment", required=True)
    p.add_argument("--seed", type=int, default=0); args = p.parse_args(argv)
    try:
        print(json.dumps(paired_statistics(te.load_receipts(args.receipts), args.control, args.treatment, seed=args.seed), indent=2, allow_nan=False))
        return 0
    except (AnalysisError, te.ReceiptError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status":"ERROR", "error":type(exc).__name__, "message":str(exc)})); return 2


if __name__ == "__main__": raise SystemExit(main())
