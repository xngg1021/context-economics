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
import runtime_experiment as re
from dataclasses import asdict


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


def acceptance_gate(receipts: Sequence[te.RunReceipt], context_by_policy: Mapping[str, Sequence[ac.ContextAccessEvent]], control: str, treatment: str, config: GateConfig, *, manifest=None, experiment_events=(), target="task-economic", allow_estimated=False, evidence_origin="unknown", held_out_task_set_ref=None) -> dict:
    if target not in {"runtime-A/B", "task-economic"} or type(allow_estimated) is not bool:
        raise AnalysisError("invalid promotion target/allow_estimated")
    pair, paired = te.extract_exact_pairs(receipts, control, treatment)
    paired_tasks = set(pair["paired_task_ids"])
    paired_ids = set(pair["paired_run_ids"])
    groups = te.aggregate_by_policy(paired)
    improvement = None
    checks = {name: False for name in ("quality_floor", "cost_target", "reacquisition_ceiling", "latency_ceiling", "prefetch_pollution", "staleness")}
    if paired:
        c, t = groups[control], groups[treatment]
        c_cps, t_cps = c["cost_per_success_usd"], t["cost_per_success_usd"]
        improvement = ((c_cps-t_cps)/c_cps if math.isfinite(c_cps) and math.isfinite(t_cps) and c_cps > 0 else None)
        # Wrapped runtime events are authoritative when supplied.
        t_events = ([e.event for e in experiment_events if e.run_id in paired_ids and e.policy_id == treatment]
                    if experiment_events else [e for e in context_by_policy.get(treatment, []) if e.task_id in paired_tasks])
        tctx = ac.aggregate_access(t_events)
        checks = {
            "quality_floor": t["success_rate"] >= c["success_rate"] - config.quality_epsilon,
            "cost_target": improvement is not None and improvement >= config.min_cost_per_success_improvement,
            "reacquisition_ceiling": t["mean_reacquisition_calls"] <= c["mean_reacquisition_calls"] + config.max_reacquisition_delta,
            "latency_ceiling": t["p95_wall_time_ms"] <= config.max_treatment_p95_wall_time_ms,
            "prefetch_pollution": tctx["prefetch_pollution_rate"] is None or tctx["prefetch_pollution_rate"] <= config.max_prefetch_pollution,
            "staleness": tctx["stale_hit_event_rate"] is None or tctx["stale_hit_event_rate"] <= config.max_stale_hit_rate,
        }
    coverage = pair["paired_coverage"]
    eligibility = {
        "paired_cohort": bool(paired),
        "paired_coverage": coverage is not None and coverage >= config.min_paired_coverage,
        "manifest_valid": False,
        "scorer_provenance": bool(paired) and all(r.scorer_id and r.scorer_version and r.scoring_provenance in {"human", "automatic", "benchmark"} and r.task_score is not None for r in paired),
        "billing_provenance": bool(paired) and all(r.provider_bill_source and (r.billing_status == "observed" or (allow_estimated and r.billing_status == "estimated")) and r.cost_ledger_version == 2 for r in paired),
        "evidence_class": False,
        "real_execution": evidence_origin == "real-provider",
        "held_out_tasks": False,
    }
    reason = None
    if manifest is not None:
        try:
            m = re.ExperimentManifest.from_mapping(dict(asdict(manifest), expected_task_ids=list(manifest.expected_task_ids))) if isinstance(manifest, re.ExperimentManifest) else re.ExperimentManifest.from_mapping(manifest)
            if (m.control_policy, m.treatment_policy) != (control, treatment):
                raise re.ExperimentError("manifest arms mismatch")
            # Missing tasks in the manifest count against coverage even if neither arm ran.
            coverage = len(paired_tasks) / len(m.expected_task_ids)
            eligibility["paired_coverage"] = coverage >= config.min_paired_coverage
            wrapped = list(experiment_events)
            re.build_joint_report(m, [re.ReceiptRecord(r, frozenset(asdict(r))) for r in receipts], wrapped)
            context_runs = {e.run_id for e in wrapped}
            eligibility["manifest_valid"] = bool(paired) and paired_ids <= context_runs
            eligibility["evidence_class"] = m.declared_evidence_class in {"runtime-A/B", "task-economic"} and m.assignment_method in {"paired-fixed", "counterbalanced", "randomized"}
            eligibility["held_out_tasks"] = bool(held_out_task_set_ref) and held_out_task_set_ref == m.task_set_ref
        except (re.ExperimentError, te.ReceiptError, TypeError, ValueError) as exc:
            reason = str(exc)
    performance = all(checks.values())
    eligible = all(eligibility.values())
    return {"scope": "candidate-gate-only-no-auto-enable", "checks": checks,
            "eligibility_checks": eligibility, "eligibility_error": reason,
            "performance_candidate": performance, "evidence_eligible": eligible,
            "candidate_for_promotion": performance and eligible,
            "shadow_candidate_only": performance and not eligible,
            "target": target, "allow_estimated": allow_estimated,
            "paired_task_ids": pair["paired_task_ids"], "paired_coverage": coverage,
            "paired_aggregates": te._json_safe(groups),
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
