# -*- coding: utf-8 -*-
"""L6 Adaptive Context Control.

A deterministic, standard-library reference implementation for Context Economics.
It models context access/miss economics, admission/residency, speculative prefetch,
bounded budget feedback, locator-token ROI, mutation amplification, and immutable
shared-base economics.

This module is advisory. It never mutates a harness, provider, memory system, or
THM tier assignment. Callers must supply task/runtime observations and explicit
cost units; the implementation does not infer causal use from retrieval/prefetch.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, fields
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping, Sequence


ACCESS_KINDS = {
    "context_hit",
    "soft_miss",
    "hard_miss",
    "stale_hit",
    "planned_retrieval",
    "prefetch",
}
DEMAND_KINDS = {"context_hit", "soft_miss", "hard_miss", "stale_hit"}
MISS_KINDS = {"soft_miss", "hard_miss"}
ASSET_TYPES = {
    "history",
    "retrieval",
    "memory",
    "tools",
    "repo_map",
    "locator",
    "evidence",
    "document",
    "other",
}

MAX_EXACT_BUDGET_UNITS = 100_000
MAX_EXACT_CANDIDATES = 1_024
MAX_EXACT_WORK = 5_000_000


class ControlError(ValueError):
    """Structured control-plane validation error."""


def _text(value: object, name: str, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ControlError(f"{name} must be a non-empty string")
    return value


def _boolean(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise ControlError(f"{name} must be boolean")
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
        raise ControlError(f"{name} must be numeric")
    out = float(value)
    if not math.isfinite(out):
        raise ControlError(f"{name} must be finite")
    if minimum is not None and out < minimum:
        raise ControlError(f"{name} must be >= {minimum}")
    if maximum is not None and out > maximum:
        raise ControlError(f"{name} must be <= {maximum}")
    return out


def _integer(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ControlError(f"{name} must be an integer")
    if value < minimum:
        raise ControlError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True)
class ContextAccessEvent:
    event_id: str
    task_id: str
    kind: str
    asset_id: str
    avoidable: bool = False
    extra_cost_units: float = 0.0
    extra_tokens: float = 0.0
    extra_tool_calls: int = 0
    extra_latency_ms: float = 0.0
    provider_cost_usd: float = 0.0
    used: bool | None = None
    avoided_miss: bool | None = None
    avoided_cost_units: float = 0.0
    prefetched_units: int = 0
    confidence: float | None = None

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "ContextAccessEvent":
        if not isinstance(row, Mapping):
            raise ControlError("context event must be an object")
        allowed = {f.name for f in fields(cls)}
        unknown = sorted(set(row) - allowed)
        if unknown:
            raise ControlError("unknown context event fields: " + ", ".join(unknown))

        event_id = _text(row.get("event_id"), "event_id")
        task_id = _text(row.get("task_id"), "task_id")
        kind = _text(row.get("kind"), "kind")
        asset_id = _text(row.get("asset_id"), "asset_id")
        assert isinstance(event_id, str) and isinstance(task_id, str)
        assert isinstance(kind, str) and isinstance(asset_id, str)

        if kind not in ACCESS_KINDS:
            raise ControlError(f"unsupported context event kind: {kind}")

        avoidable = _boolean(row.get("avoidable", False), "avoidable")
        if avoidable and kind not in MISS_KINDS:
            raise ControlError("avoidable=true is valid only for soft_miss/hard_miss")

        used_raw = row.get("used")
        used = None if used_raw is None else _boolean(used_raw, "used")
        avoided_raw = row.get("avoided_miss")
        avoided_miss = (
            None if avoided_raw is None else _boolean(avoided_raw, "avoided_miss")
        )
        confidence_raw = row.get("confidence")
        confidence = (
            None
            if confidence_raw is None
            else _number(confidence_raw, "confidence", maximum=1.0)
        )

        prefetched_units = _integer(
            row.get("prefetched_units", 0), "prefetched_units"
        )
        avoided_cost_units = _number(
            row.get("avoided_cost_units", 0.0) or 0.0,
            "avoided_cost_units",
        )

        if kind == "prefetch":
            if used is None:
                raise ControlError("prefetch event requires explicit used=true/false")
        else:
            if used is not None or avoided_miss is not None or confidence is not None:
                raise ControlError(
                    "used/avoided_miss/confidence are prefetch-only fields"
                )
            if prefetched_units or avoided_cost_units:
                raise ControlError(
                    "prefetched_units/avoided_cost_units are prefetch-only fields"
                )

        return cls(
            event_id=event_id,
            task_id=task_id,
            kind=kind,
            asset_id=asset_id,
            avoidable=avoidable,
            extra_cost_units=_number(
                row.get("extra_cost_units", 0.0) or 0.0, "extra_cost_units"
            ),
            extra_tokens=_number(
                row.get("extra_tokens", 0.0) or 0.0, "extra_tokens"
            ),
            extra_tool_calls=_integer(
                row.get("extra_tool_calls", 0) or 0, "extra_tool_calls"
            ),
            extra_latency_ms=_number(
                row.get("extra_latency_ms", 0.0) or 0.0, "extra_latency_ms"
            ),
            provider_cost_usd=_number(
                row.get("provider_cost_usd", 0.0) or 0.0, "provider_cost_usd"
            ),
            used=used,
            avoided_miss=avoided_miss,
            avoided_cost_units=avoided_cost_units,
            prefetched_units=prefetched_units,
            confidence=confidence,
        )


def load_events(path: str | Path) -> list[ContextAccessEvent]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        if set(payload) - {"schema_version", "note", "events"}:
            unknown = sorted(set(payload) - {"schema_version", "note", "events"})
            raise ControlError("unknown event wrapper fields: " + ", ".join(unknown))
        if payload.get("schema_version") != 1:
            raise ControlError("event wrapper requires schema_version=1")
        rows = payload.get("events")
    else:
        rows = payload
    if not isinstance(rows, list):
        raise ControlError("events must be a list")

    events: list[ContextAccessEvent] = []
    seen: set[str] = set()
    for raw in rows:
        event = ContextAccessEvent.from_mapping(raw)
        if event.event_id in seen:
            raise ControlError(f"duplicate event_id: {event.event_id}")
        seen.add(event.event_id)
        events.append(event)
    return events


def aggregate_access(events: Iterable[ContextAccessEvent]) -> dict:
    rows = list(events)
    task_ids = {row.task_id for row in rows}
    demand_rows = [row for row in rows if row.kind in DEMAND_KINDS]
    demand_tasks = {row.task_id for row in demand_rows}
    miss_rows = [row for row in rows if row.kind in MISS_KINDS]
    avoidable_rows = [row for row in miss_rows if row.avoidable]
    stale_rows = [row for row in rows if row.kind == "stale_hit"]
    planned_rows = [row for row in rows if row.kind == "planned_retrieval"]
    prefetch_rows = [row for row in rows if row.kind == "prefetch"]

    by_asset: dict[str, dict] = {}
    for row in demand_rows:
        stats = by_asset.setdefault(
            row.asset_id,
            {
                "demand_task_ids": set(),
                "context_hits": 0,
                "soft_misses": 0,
                "hard_misses": 0,
                "stale_hits": 0,
                "avoidable_misses": 0,
                "avoidable_penalty_units": 0.0,
                "stale_penalty_units": 0.0,
                "miss_extra_tokens": 0.0,
                "miss_extra_tool_calls": 0,
                "miss_extra_latency_ms": 0.0,
                "miss_provider_cost_usd": 0.0,
            },
        )
        stats["demand_task_ids"].add(row.task_id)
        if row.kind == "context_hit":
            stats["context_hits"] += 1
        elif row.kind == "soft_miss":
            stats["soft_misses"] += 1
        elif row.kind == "hard_miss":
            stats["hard_misses"] += 1
        elif row.kind == "stale_hit":
            stats["stale_hits"] += 1
            stats["stale_penalty_units"] += row.extra_cost_units
        if row.kind in MISS_KINDS:
            stats["miss_extra_tokens"] += row.extra_tokens
            stats["miss_extra_tool_calls"] += row.extra_tool_calls
            stats["miss_extra_latency_ms"] += row.extra_latency_ms
            stats["miss_provider_cost_usd"] += row.provider_cost_usd
            if row.avoidable:
                stats["avoidable_misses"] += 1
                stats["avoidable_penalty_units"] += row.extra_cost_units

    clean_assets: dict[str, dict] = {}
    demand_task_count = len(demand_tasks)
    for asset_id, stats in sorted(by_asset.items()):
        demand_ids = stats.pop("demand_task_ids")
        misses = stats["soft_misses"] + stats["hard_misses"]
        clean_assets[asset_id] = {
            **stats,
            "demand_tasks": len(demand_ids),
            "need_task_rate": (
                len(demand_ids) / demand_task_count if demand_task_count else None
            ),
            "misses": misses,
            "avoidable_penalty_per_demand_task": (
                stats["avoidable_penalty_units"] / demand_task_count
                if demand_task_count
                else None
            ),
            "stale_penalty_per_demand_task": (
                stats["stale_penalty_units"] / demand_task_count
                if demand_task_count
                else None
            ),
        }

    used_prefetches = sum(1 for row in prefetch_rows if row.used)
    avoided_prefetches = sum(1 for row in prefetch_rows if row.avoided_miss is True)
    total_prefetched = sum(row.prefetched_units for row in prefetch_rows)
    unused_prefetched = sum(
        row.prefetched_units for row in prefetch_rows if row.used is False
    )
    prefetch_cost = sum(row.extra_cost_units for row in prefetch_rows)
    avoided_cost = sum(row.avoided_cost_units for row in prefetch_rows)

    demand_event_count = len(demand_rows)
    miss_task_ids = {row.task_id for row in miss_rows}
    return {
        "scope": "explicit-context-access-telemetry-not-causal-proof",
        "tasks": len(task_ids),
        "demand_tasks": demand_task_count,
        "demand_events": demand_event_count,
        "context_hits": sum(row.kind == "context_hit" for row in demand_rows),
        "soft_misses": sum(row.kind == "soft_miss" for row in demand_rows),
        "hard_misses": sum(row.kind == "hard_miss" for row in demand_rows),
        "stale_hits": len(stale_rows),
        "planned_retrievals": len(planned_rows),
        "raw_misses": len(miss_rows),
        "avoidable_misses": len(avoidable_rows),
        "miss_event_rate": (
            len(miss_rows) / demand_event_count if demand_event_count else None
        ),
        "miss_task_rate": (
            len(miss_task_ids) / demand_task_count if demand_task_count else None
        ),
        "avoidable_miss_event_rate": (
            len(avoidable_rows) / demand_event_count if demand_event_count else None
        ),
        "stale_hit_event_rate": (
            len(stale_rows) / demand_event_count if demand_event_count else None
        ),
        "miss_extra_tokens": sum(row.extra_tokens for row in miss_rows),
        "miss_extra_tool_calls": sum(row.extra_tool_calls for row in miss_rows),
        "miss_extra_latency_ms": sum(row.extra_latency_ms for row in miss_rows),
        "miss_provider_cost_usd": sum(row.provider_cost_usd for row in miss_rows),
        "avoidable_penalty_units": sum(row.extra_cost_units for row in avoidable_rows),
        "prefetches": len(prefetch_rows),
        "prefetch_accuracy": (
            used_prefetches / len(prefetch_rows) if prefetch_rows else None
        ),
        "prefetch_observed_avoided_misses": avoided_prefetches,
        "prefetch_units": total_prefetched,
        "unused_prefetched_units": unused_prefetched,
        "prefetch_pollution_rate": (
            unused_prefetched / total_prefetched if total_prefetched else None
        ),
        "prefetch_cost_units": prefetch_cost,
        "prefetch_avoided_cost_units": avoided_cost,
        "prefetch_net_value_units": avoided_cost - prefetch_cost,
        "by_asset": clean_assets,
    }


@dataclass(frozen=True)
class ContextAsset:
    asset_id: str
    asset_type: str
    resident_units: int
    carry_cost_units_per_task: float
    currently_resident: bool = False
    protected: bool = False
    interference_cost_units_per_task: float = 0.0
    counterfactual_miss_cost_units: float | None = None
    locator: str | None = None
    locator_units: int = 0
    locator_carry_cost_units_per_task: float = 0.0
    search_avoided_units: float = 0.0
    prefetch_units: int = 0
    prefetch_cost_units: float = 0.0
    prefetch_value_units: float | None = None
    shareable_immutable: bool = False

    @classmethod
    def from_mapping(cls, asset_id: str, row: Mapping[str, object]) -> "ContextAsset":
        if not isinstance(row, Mapping):
            raise ControlError(f"asset {asset_id!r} must be an object")
        allowed = {f.name for f in fields(cls)} - {"asset_id"}
        unknown = sorted(set(row) - allowed)
        if unknown:
            raise ControlError(
                f"asset {asset_id}: unknown fields: " + ", ".join(unknown)
            )
        asset_type = _text(row.get("asset_type"), f"{asset_id}.asset_type")
        assert isinstance(asset_type, str)
        if asset_type not in ASSET_TYPES:
            raise ControlError(f"asset {asset_id}: unsupported asset_type {asset_type}")

        locator_raw = row.get("locator")
        locator = _text(locator_raw, f"{asset_id}.locator", allow_none=True)
        miss_cost_raw = row.get("counterfactual_miss_cost_units")
        miss_cost = (
            None
            if miss_cost_raw is None
            else _number(
                miss_cost_raw, f"{asset_id}.counterfactual_miss_cost_units"
            )
        )
        prefetch_value_raw = row.get("prefetch_value_units")
        prefetch_value = (
            None
            if prefetch_value_raw is None
            else _number(prefetch_value_raw, f"{asset_id}.prefetch_value_units")
        )

        return cls(
            asset_id=asset_id,
            asset_type=asset_type,
            resident_units=_integer(
                row.get("resident_units"), f"{asset_id}.resident_units", minimum=1
            ),
            carry_cost_units_per_task=_number(
                row.get("carry_cost_units_per_task"),
                f"{asset_id}.carry_cost_units_per_task",
            ),
            currently_resident=_boolean(
                row.get("currently_resident", False),
                f"{asset_id}.currently_resident",
            ),
            protected=_boolean(row.get("protected", False), f"{asset_id}.protected"),
            interference_cost_units_per_task=_number(
                row.get("interference_cost_units_per_task", 0.0) or 0.0,
                f"{asset_id}.interference_cost_units_per_task",
            ),
            counterfactual_miss_cost_units=miss_cost,
            locator=locator,
            locator_units=_integer(
                row.get("locator_units", 0) or 0, f"{asset_id}.locator_units"
            ),
            locator_carry_cost_units_per_task=_number(
                row.get("locator_carry_cost_units_per_task", 0.0) or 0.0,
                f"{asset_id}.locator_carry_cost_units_per_task",
            ),
            search_avoided_units=_number(
                row.get("search_avoided_units", 0.0) or 0.0,
                f"{asset_id}.search_avoided_units",
            ),
            prefetch_units=_integer(
                row.get("prefetch_units", 0) or 0, f"{asset_id}.prefetch_units"
            ),
            prefetch_cost_units=_number(
                row.get("prefetch_cost_units", 0.0) or 0.0,
                f"{asset_id}.prefetch_cost_units",
            ),
            prefetch_value_units=prefetch_value,
            shareable_immutable=_boolean(
                row.get("shareable_immutable", False),
                f"{asset_id}.shareable_immutable",
            ),
        )


def load_catalog(path: str | Path) -> dict[str, ContextAsset]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ControlError("asset catalog must be an object")
    unknown = sorted(set(payload) - {"schema_version", "note", "assets"})
    if unknown:
        raise ControlError("unknown catalog wrapper fields: " + ", ".join(unknown))
    if payload.get("schema_version") != 1:
        raise ControlError("asset catalog requires schema_version=1")
    raw_assets = payload.get("assets")
    if not isinstance(raw_assets, dict):
        raise ControlError("asset catalog assets must be an object")
    out: dict[str, ContextAsset] = {}
    for asset_id, row in raw_assets.items():
        clean_id = _text(asset_id, "asset_id")
        assert isinstance(clean_id, str)
        if clean_id in out:
            raise ControlError(f"duplicate asset_id: {clean_id}")
        out[clean_id] = ContextAsset.from_mapping(clean_id, row)
    return out


def _asset_evidence(
    asset: ContextAsset,
    stats: Mapping[str, object] | None,
    demand_tasks: int,
    *,
    min_asset_demands: int,
) -> dict:
    if stats is None:
        observed_demands = 0
        avoidable_misses = 0
        avoidable_penalty = 0.0
        stale_penalty = 0.0
        need_task_rate = 0.0
    else:
        observed_demands = int(stats.get("demand_tasks", 0) or 0)
        avoidable_misses = int(stats.get("avoidable_misses", 0) or 0)
        avoidable_penalty = float(stats.get("avoidable_penalty_units", 0.0) or 0.0)
        stale_penalty = float(stats.get("stale_penalty_units", 0.0) or 0.0)
        need_task_rate = float(stats.get("need_task_rate", 0.0) or 0.0)

    demand_support = bool(demand_tasks) and observed_demands >= min_asset_demands
    explicit_counterfactual = asset.counterfactual_miss_cost_units is not None

    # A resident asset can generate many hits and zero observed misses precisely because it
    # stayed resident. Treating those zero misses as zero counterfactual value would create
    # a destructive feedback loop. An actionable value estimate therefore needs either an
    # explicit caller-supplied counterfactual miss cost or at least one observed avoidable
    # miss while the asset was not resident.
    value_basis = explicit_counterfactual or avoidable_misses > 0
    evidence_sufficient = demand_support and value_basis

    if explicit_counterfactual:
        benefit_per_task = (
            need_task_rate * float(asset.counterfactual_miss_cost_units)
        )
        benefit_source = "explicit-counterfactual-miss-cost"
    else:
        benefit_per_task = (
            avoidable_penalty / demand_tasks if demand_tasks else 0.0
        )
        benefit_source = (
            "observed-avoidable-miss-penalty"
            if avoidable_misses > 0
            else "missing-counterfactual-value"
        )

    stale_per_task = stale_penalty / demand_tasks if demand_tasks else 0.0
    carry_per_task = (
        asset.carry_cost_units_per_task
        + asset.interference_cost_units_per_task
    )
    net_per_task = benefit_per_task - stale_per_task - carry_per_task

    return {
        "asset_id": asset.asset_id,
        "asset_type": asset.asset_type,
        "currently_resident": asset.currently_resident,
        "protected": asset.protected,
        "resident_units": asset.resident_units,
        "observed_demand_tasks": observed_demands,
        "observed_avoidable_misses": avoidable_misses,
        "need_task_rate": need_task_rate,
        "demand_support_sufficient": demand_support,
        "counterfactual_value_available": value_basis,
        "counterfactual_miss_cost_units": asset.counterfactual_miss_cost_units,
        "benefit_source": benefit_source,
        "evidence_sufficient": evidence_sufficient,
        "avoidable_miss_benefit_units_per_task": benefit_per_task,
        "stale_penalty_units_per_task": stale_per_task,
        "carry_plus_interference_units_per_task": carry_per_task,
        "net_residency_value_units_per_task": net_per_task,
    }


def _exact_pack(
    candidates: Sequence[tuple[str, int, float]],
    budget_units: int,
) -> set[str]:
    budget_units = _integer(budget_units, "budget_units")
    if budget_units > MAX_EXACT_BUDGET_UNITS:
        raise ControlError(
            f"exact packing budget exceeds public limit {MAX_EXACT_BUDGET_UNITS}; "
            "coarsen capacity units explicitly"
        )
    if len(candidates) > MAX_EXACT_CANDIDATES:
        raise ControlError(
            f"exact packing candidate count exceeds public limit {MAX_EXACT_CANDIDATES}"
        )
    if len(candidates) * max(budget_units, 1) > MAX_EXACT_WORK:
        raise ControlError(
            f"exact packing work exceeds public limit {MAX_EXACT_WORK}; "
            "coarsen units or pre-filter candidates explicitly"
        )

    # capacity -> (value, sorted ids). Sparse DP keeps deterministic ties without
    # allocating a dense matrix. Value is arbitrary explicit cost units, not dollars.
    states: dict[int, tuple[float, tuple[str, ...]]] = {0: (0.0, ())}
    for asset_id, units, value in sorted(candidates):
        units = _integer(units, f"{asset_id}.units", minimum=1)
        value = _number(value, f"{asset_id}.value", minimum=None)
        assert isinstance(value, float)
        previous = list(states.items())
        for used, (score, ids) in previous:
            new_used = used + units
            if new_used > budget_units:
                continue
            new_score = score + value
            new_ids = tuple(sorted((*ids, asset_id)))
            old = states.get(new_used)
            if old is None or new_score > old[0] + 1e-12 or (
                abs(new_score - old[0]) <= 1e-12 and new_ids < old[1]
            ):
                states[new_used] = (new_score, new_ids)

        # Remove dominated states: if a lower/equal capacity has >= value, the larger
        # state can never improve a future solution. This bounds common workloads.
        best_value = -math.inf
        compact: dict[int, tuple[float, tuple[str, ...]]] = {}
        for used in sorted(states):
            score, ids = states[used]
            if score > best_value + 1e-12:
                compact[used] = (score, ids)
                best_value = score
            elif abs(score - best_value) <= 1e-12:
                # Equal value at more capacity is dominated.
                continue
        states = compact

    best = max(
        states.items(),
        key=lambda item: (item[1][0], -item[0], tuple(reversed(item[1][1]))),
    )
    return set(best[1][1])


def recommend_residency(
    events: Iterable[ContextAccessEvent],
    assets: Mapping[str, ContextAsset],
    budget_units: int,
    *,
    min_demand_tasks: int = 3,
    min_asset_demands: int = 2,
) -> dict:
    budget_units = _integer(budget_units, "budget_units")
    min_demand_tasks = _integer(
        min_demand_tasks, "min_demand_tasks", minimum=1
    )
    min_asset_demands = _integer(
        min_asset_demands, "min_asset_demands", minimum=1
    )

    aggregate_report = aggregate_access(events)
    demand_tasks = int(aggregate_report["demand_tasks"])
    by_asset = aggregate_report["by_asset"]

    unknown_event_assets = sorted(set(by_asset) - set(assets))
    if unknown_event_assets:
        raise ControlError(
            "telemetry references assets absent from catalog: "
            + ", ".join(unknown_event_assets)
        )

    evidence = {
        asset_id: _asset_evidence(
            asset,
            by_asset.get(asset_id),
            demand_tasks,
            min_asset_demands=min_asset_demands,
        )
        for asset_id, asset in sorted(assets.items())
    }

    global_sufficient = demand_tasks >= min_demand_tasks
    protected_current = {
        asset_id
        for asset_id, asset in assets.items()
        if asset.currently_resident
        and (
            asset.protected
            or not global_sufficient
            or not evidence[asset_id]["evidence_sufficient"]
        )
    }
    protected_units = sum(assets[asset_id].resident_units for asset_id in protected_current)
    if protected_units > budget_units:
        return {
            "scope": "shadow-admission-residency-not-runtime-mutation",
            "status": "protected-over-budget",
            "budget_units": budget_units,
            "protected_units": protected_units,
            "selected": sorted(protected_current),
            "decisions": [
                {
                    **evidence[asset_id],
                    "action": "keep-protected"
                    if assets[asset_id].currently_resident
                    else "review",
                }
                for asset_id in sorted(assets)
            ],
        }

    candidate_rows: list[tuple[str, int, float]] = []
    for asset_id, asset in sorted(assets.items()):
        ev = evidence[asset_id]
        if asset_id in protected_current:
            continue
        if asset.protected and not asset.currently_resident:
            continue
        if not global_sufficient or not ev["evidence_sufficient"]:
            continue
        value = float(ev["net_residency_value_units_per_task"])
        if value > 0:
            candidate_rows.append((asset_id, asset.resident_units, value))

    selected = set(protected_current)
    remaining = budget_units - protected_units
    selected |= _exact_pack(candidate_rows, remaining)

    decisions: list[dict] = []
    for asset_id, asset in sorted(assets.items()):
        ev = evidence[asset_id]
        if asset_id in protected_current:
            action = "keep-protected"
        elif asset.protected and not asset.currently_resident:
            action = "review-protected-nonresident"
        elif not global_sufficient or not ev["evidence_sufficient"]:
            action = "review-insufficient-evidence"
        elif asset_id in selected and asset.currently_resident:
            action = "keep"
        elif asset_id in selected and not asset.currently_resident:
            action = "admit"
        elif asset.currently_resident:
            action = "evict"
        else:
            action = "defer"
        decisions.append({**ev, "action": action})

    return {
        "scope": "shadow-admission-residency-not-runtime-mutation",
        "status": "ok" if global_sufficient else "insufficient-global-evidence",
        "budget_units": budget_units,
        "selected_units": sum(assets[i].resident_units for i in selected),
        "selected": sorted(selected),
        "demand_tasks": demand_tasks,
        "min_demand_tasks": min_demand_tasks,
        "min_asset_demands": min_asset_demands,
        "decisions": decisions,
    }


def locator_economics(
    *,
    locator_units: int,
    locator_carry_cost_units_per_task: float,
    fetch_probability: float,
    search_avoided_units: float,
    fetch_cost_units: float = 0.0,
) -> dict:
    locator_units = _integer(locator_units, "locator_units", minimum=1)
    carry = _number(
        locator_carry_cost_units_per_task, "locator_carry_cost_units_per_task"
    )
    probability = _number(fetch_probability, "fetch_probability", maximum=1.0)
    avoided = _number(search_avoided_units, "search_avoided_units")
    fetch_cost = _number(fetch_cost_units, "fetch_cost_units")

    expected_avoided = probability * avoided
    expected_fetch_cost = probability * fetch_cost
    net = expected_avoided - expected_fetch_cost - carry
    denominator = carry + expected_fetch_cost
    return {
        "locator_units": locator_units,
        "expected_search_avoided_units_per_task": expected_avoided,
        "expected_fetch_cost_units_per_task": expected_fetch_cost,
        "locator_carry_cost_units_per_task": carry,
        "net_locator_value_units_per_task": net,
        "benefit_cost_ratio": (
            expected_avoided / denominator if denominator > 0 else math.inf
        ),
    }


def recommend_prefetch(
    events: Iterable[ContextAccessEvent],
    assets: Mapping[str, ContextAsset],
    seed_asset_ids: Sequence[str],
    budget_units: int,
    *,
    min_seed_demands: int = 2,
    min_joint_tasks: int = 2,
) -> dict:
    budget_units = _integer(budget_units, "budget_units")
    min_seed_demands = _integer(
        min_seed_demands, "min_seed_demands", minimum=1
    )
    min_joint_tasks = _integer(min_joint_tasks, "min_joint_tasks", minimum=1)

    seeds = sorted(set(seed_asset_ids))
    if not seeds:
        raise ControlError("at least one seed asset is required")
    unknown = sorted(set(seeds) - set(assets))
    if unknown:
        raise ControlError("unknown prefetch seed assets: " + ", ".join(unknown))

    demand_task_ids: dict[str, set[str]] = {}
    for row in events:
        # Deliberate anti-feedback boundary: prefetch and planned retrieval do not train demand.
        if row.kind not in DEMAND_KINDS:
            continue
        demand_task_ids.setdefault(row.asset_id, set()).add(row.task_id)

    seed_tasks: set[str] = set()
    for seed in seeds:
        seed_tasks |= demand_task_ids.get(seed, set())
    if len(seed_tasks) < min_seed_demands:
        return {
            "scope": "shadow-prefetch-not-runtime-fetch",
            "status": "insufficient-seed-demand",
            "seed_assets": seeds,
            "seed_demand_tasks": len(seed_tasks),
            "selected": [],
            "candidates": [],
        }

    candidates: list[dict] = []
    pack_rows: list[tuple[str, int, float]] = []
    for asset_id, asset in sorted(assets.items()):
        if asset_id in seeds or asset.currently_resident:
            continue
        joint = seed_tasks & demand_task_ids.get(asset_id, set())
        if len(joint) < min_joint_tasks:
            continue
        confidence = len(joint) / len(seed_tasks)
        complete = (
            asset.locator is not None
            and asset.prefetch_units > 0
            and asset.prefetch_value_units is not None
        )
        net = None
        if complete:
            net = (
                confidence * float(asset.prefetch_value_units)
                - asset.prefetch_cost_units
            )
            if net > 0:
                pack_rows.append((asset_id, asset.prefetch_units, net))
        candidates.append(
            {
                "asset_id": asset_id,
                "asset_type": asset.asset_type,
                "locator": asset.locator,
                "joint_demand_tasks": len(joint),
                "seed_demand_tasks": len(seed_tasks),
                "confidence": confidence,
                "prefetch_units": asset.prefetch_units,
                "prefetch_cost_units": asset.prefetch_cost_units,
                "prefetch_value_units": asset.prefetch_value_units,
                "net_prefetch_value_units": net,
                "evidence_complete": complete,
            }
        )

    selected = _exact_pack(pack_rows, budget_units)
    selected_units = sum(assets[i].prefetch_units for i in selected)
    return {
        "scope": "shadow-prefetch-not-runtime-fetch",
        "status": "ok",
        "seed_assets": seeds,
        "seed_demand_tasks": len(seed_tasks),
        "budget_units": budget_units,
        "selected_units": selected_units,
        "selected": sorted(selected),
        "candidates": candidates,
    }


@dataclass(frozen=True)
class ContextBudget:
    history_units: int
    retrieval_units: int
    memory_units: int
    tools_units: int
    repo_map_units: int
    prefetch_units: int
    compression_retained_ratio: float

    @classmethod
    def from_mapping(cls, row: Mapping[str, object], prefix: str = "budget") -> "ContextBudget":
        if not isinstance(row, Mapping):
            raise ControlError(f"{prefix} must be an object")
        allowed = {f.name for f in fields(cls)}
        unknown = sorted(set(row) - allowed)
        if unknown:
            raise ControlError(f"{prefix}: unknown fields: " + ", ".join(unknown))
        return cls(
            history_units=_integer(row.get("history_units"), f"{prefix}.history_units"),
            retrieval_units=_integer(row.get("retrieval_units"), f"{prefix}.retrieval_units"),
            memory_units=_integer(row.get("memory_units"), f"{prefix}.memory_units"),
            tools_units=_integer(row.get("tools_units"), f"{prefix}.tools_units"),
            repo_map_units=_integer(row.get("repo_map_units"), f"{prefix}.repo_map_units"),
            prefetch_units=_integer(row.get("prefetch_units"), f"{prefix}.prefetch_units"),
            compression_retained_ratio=_number(
                row.get("compression_retained_ratio"),
                f"{prefix}.compression_retained_ratio",
                minimum=0.01,
                maximum=1.0,
            ),
        )

    def as_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True)
class BudgetBounds:
    minimum: ContextBudget
    maximum: ContextBudget

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "BudgetBounds":
        if not isinstance(row, Mapping):
            raise ControlError("bounds must be an object")
        if set(row) != {"minimum", "maximum"}:
            raise ControlError("bounds requires exactly minimum and maximum")
        minimum = ContextBudget.from_mapping(row["minimum"], "bounds.minimum")
        maximum = ContextBudget.from_mapping(row["maximum"], "bounds.maximum")
        for name in (
            "history_units", "retrieval_units", "memory_units",
            "tools_units", "repo_map_units", "prefetch_units",
            "compression_retained_ratio",
        ):
            if getattr(minimum, name) > getattr(maximum, name):
                raise ControlError(f"bounds minimum exceeds maximum for {name}")
        return cls(minimum=minimum, maximum=maximum)


@dataclass(frozen=True)
class ControllerObservation:
    miss_rate: float
    hard_miss_rate: float
    reacquisition_cost_units_per_task: float
    dependency_depth: float
    cache_hit_share: float
    context_pressure: float
    ttft_ms: float
    prefetch_pollution_rate: float
    interference_rate: float

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "ControllerObservation":
        if not isinstance(row, Mapping):
            raise ControlError("observation must be an object")
        allowed = {f.name for f in fields(cls)}
        unknown = sorted(set(row) - allowed)
        if unknown:
            raise ControlError("observation: unknown fields: " + ", ".join(unknown))
        return cls(
            miss_rate=_number(row.get("miss_rate"), "observation.miss_rate", maximum=1.0),
            hard_miss_rate=_number(
                row.get("hard_miss_rate"), "observation.hard_miss_rate", maximum=1.0
            ),
            reacquisition_cost_units_per_task=_number(
                row.get("reacquisition_cost_units_per_task"),
                "observation.reacquisition_cost_units_per_task",
            ),
            dependency_depth=_number(
                row.get("dependency_depth"), "observation.dependency_depth"
            ),
            cache_hit_share=_number(
                row.get("cache_hit_share"), "observation.cache_hit_share", maximum=1.0
            ),
            context_pressure=_number(
                row.get("context_pressure"), "observation.context_pressure", maximum=1.0
            ),
            ttft_ms=_number(row.get("ttft_ms"), "observation.ttft_ms"),
            prefetch_pollution_rate=_number(
                row.get("prefetch_pollution_rate"),
                "observation.prefetch_pollution_rate",
                maximum=1.0,
            ),
            interference_rate=_number(
                row.get("interference_rate"),
                "observation.interference_rate",
                maximum=1.0,
            ),
        )


@dataclass(frozen=True)
class ControllerPolicy:
    target_miss_rate: float = 0.10
    target_hard_miss_rate: float = 0.03
    target_reacquisition_cost_units_per_task: float = 1.0
    target_dependency_depth: float = 3.0
    target_cache_hit_share: float = 0.70
    target_context_pressure: float = 0.80
    target_ttft_ms: float = 1500.0
    target_prefetch_pollution_rate: float = 0.30
    target_interference_rate: float = 0.05
    base_step_fraction: float = 0.05
    max_step_fraction: float = 0.20
    deadband: float = 0.10

    @classmethod
    def from_mapping(cls, row: Mapping[str, object] | None) -> "ControllerPolicy":
        if row is None:
            return cls()
        if not isinstance(row, Mapping):
            raise ControlError("policy must be an object")
        allowed = {f.name for f in fields(cls)}
        unknown = sorted(set(row) - allowed)
        if unknown:
            raise ControlError("policy: unknown fields: " + ", ".join(unknown))
        values = {}
        defaults = cls()
        for name in allowed:
            default = getattr(defaults, name)
            raw = row.get(name, default)
            maximum = 1.0 if any(token in name for token in ("rate", "share", "fraction")) else None
            values[name] = _number(raw, f"policy.{name}", maximum=maximum)
        if values["base_step_fraction"] > values["max_step_fraction"]:
            raise ControlError("base_step_fraction cannot exceed max_step_fraction")
        return cls(**values)


def _normalized_high(value: float, target: float) -> float:
    if target <= 0:
        return min(3.0, value)
    return min(3.0, max(0.0, (value - target) / target))


def _normalized_low(value: float, target: float) -> float:
    if target <= 0:
        return 0.0
    return min(3.0, max(0.0, (target - value) / target))


def _step_fraction(score: float, policy: ControllerPolicy) -> float:
    if abs(score) <= policy.deadband:
        return 0.0
    magnitude = min(
        policy.max_step_fraction,
        policy.base_step_fraction * max(1.0, abs(score)),
    )
    return math.copysign(magnitude, score)


def _adjust_int(
    current: int,
    minimum: int,
    maximum: int,
    score: float,
    policy: ControllerPolicy,
) -> int:
    fraction = _step_fraction(score, policy)
    if fraction == 0:
        return current
    delta = max(1, round(current * abs(fraction)))
    proposed = current + delta if fraction > 0 else current - delta
    return min(maximum, max(minimum, proposed))


def _adjust_ratio(
    current: float,
    minimum: float,
    maximum: float,
    score: float,
    policy: ControllerPolicy,
) -> float:
    fraction = _step_fraction(score, policy)
    if fraction == 0:
        return current
    proposed = current + fraction
    return min(maximum, max(minimum, proposed))


def suggest_budget(
    current: ContextBudget,
    bounds: BudgetBounds,
    observation: ControllerObservation,
    policy: ControllerPolicy | None = None,
) -> dict:
    policy = policy or ControllerPolicy()

    for name in (
        "history_units", "retrieval_units", "memory_units",
        "tools_units", "repo_map_units", "prefetch_units",
        "compression_retained_ratio",
    ):
        value = getattr(current, name)
        if not (getattr(bounds.minimum, name) <= value <= getattr(bounds.maximum, name)):
            raise ControlError(f"current budget outside bounds for {name}")

    miss = _normalized_high(observation.miss_rate, policy.target_miss_rate)
    hard = _normalized_high(
        observation.hard_miss_rate, policy.target_hard_miss_rate
    )
    reacq = _normalized_high(
        observation.reacquisition_cost_units_per_task,
        policy.target_reacquisition_cost_units_per_task,
    )
    depth = _normalized_high(
        observation.dependency_depth, policy.target_dependency_depth
    )
    cache = _normalized_low(
        observation.cache_hit_share, policy.target_cache_hit_share
    )
    pressure = _normalized_high(
        observation.context_pressure, policy.target_context_pressure
    )
    ttft = _normalized_high(observation.ttft_ms, policy.target_ttft_ms)
    pollution = _normalized_high(
        observation.prefetch_pollution_rate,
        policy.target_prefetch_pollution_rate,
    )
    interference = _normalized_high(
        observation.interference_rate, policy.target_interference_rate
    )

    scores = {
        # Positive score means retain/provision more of the dimension.
        "history_units": miss + 0.5 * reacq + 0.5 * depth - cache - pressure - 0.5 * ttft - interference,
        "retrieval_units": miss + hard + reacq + 0.5 * depth - 0.5 * pressure - 0.25 * ttft,
        "memory_units": miss + reacq - pressure - interference - 0.5 * cache,
        "tools_units": hard + 0.75 * depth - pressure - interference,
        "repo_map_units": hard + depth - 0.75 * pressure - 0.5 * ttft,
        "prefetch_units": miss + hard + 0.5 * depth - 1.5 * pollution - pressure,
        # Higher retained ratio == less aggressive compression.
        "compression_retained_ratio": miss + reacq + 0.5 * depth - cache - pressure - ttft - interference,
    }

    proposal = ContextBudget(
        history_units=_adjust_int(
            current.history_units,
            bounds.minimum.history_units,
            bounds.maximum.history_units,
            scores["history_units"],
            policy,
        ),
        retrieval_units=_adjust_int(
            current.retrieval_units,
            bounds.minimum.retrieval_units,
            bounds.maximum.retrieval_units,
            scores["retrieval_units"],
            policy,
        ),
        memory_units=_adjust_int(
            current.memory_units,
            bounds.minimum.memory_units,
            bounds.maximum.memory_units,
            scores["memory_units"],
            policy,
        ),
        tools_units=_adjust_int(
            current.tools_units,
            bounds.minimum.tools_units,
            bounds.maximum.tools_units,
            scores["tools_units"],
            policy,
        ),
        repo_map_units=_adjust_int(
            current.repo_map_units,
            bounds.minimum.repo_map_units,
            bounds.maximum.repo_map_units,
            scores["repo_map_units"],
            policy,
        ),
        prefetch_units=_adjust_int(
            current.prefetch_units,
            bounds.minimum.prefetch_units,
            bounds.maximum.prefetch_units,
            scores["prefetch_units"],
            policy,
        ),
        compression_retained_ratio=_adjust_ratio(
            current.compression_retained_ratio,
            bounds.minimum.compression_retained_ratio,
            bounds.maximum.compression_retained_ratio,
            scores["compression_retained_ratio"],
            policy,
        ),
    )

    return {
        "scope": "shadow-budget-feedback-not-runtime-mutation",
        "current": current.as_dict(),
        "proposed": proposal.as_dict(),
        "dimension_scores": scores,
        "signal_components": {
            "miss_pressure": miss,
            "hard_miss_pressure": hard,
            "reacquisition_pressure": reacq,
            "dependency_depth_pressure": depth,
            "cache_efficiency_pressure": cache,
            "context_pressure": pressure,
            "ttft_pressure": ttft,
            "prefetch_pollution_pressure": pollution,
            "interference_pressure": interference,
        },
        "policy": {
            f.name: getattr(policy, f.name) for f in fields(policy)
        },
    }


def load_budget_state(path: str | Path) -> tuple[
    ContextBudget, BudgetBounds, ControllerObservation, ControllerPolicy
]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ControlError("budget state must be an object")
    allowed = {"schema_version", "note", "current", "bounds", "observation", "policy"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ControlError("unknown budget-state fields: " + ", ".join(unknown))
    if payload.get("schema_version") != 1:
        raise ControlError("budget state requires schema_version=1")
    return (
        ContextBudget.from_mapping(payload.get("current"), "current"),
        BudgetBounds.from_mapping(payload.get("bounds")),
        ControllerObservation.from_mapping(payload.get("observation")),
        ControllerPolicy.from_mapping(payload.get("policy")),
    )


@dataclass(frozen=True)
class MutationReceipt:
    mutation_id: str
    semantic_source_units: float
    storage_bytes_changed: float = 0.0
    recomputed_tokens: float = 0.0
    compute_ms: float = 0.0
    invalidated_cache_tokens: float = 0.0
    derived_writes: int = 0


def mutation_amplification(receipt: MutationReceipt) -> dict:
    source = _number(
        receipt.semantic_source_units, "semantic_source_units", minimum=1e-12
    )
    storage = _number(receipt.storage_bytes_changed, "storage_bytes_changed")
    tokens = _number(receipt.recomputed_tokens, "recomputed_tokens")
    compute = _number(receipt.compute_ms, "compute_ms")
    invalidated = _number(
        receipt.invalidated_cache_tokens, "invalidated_cache_tokens"
    )
    writes = _integer(receipt.derived_writes, "derived_writes")
    return {
        "mutation_id": _text(receipt.mutation_id, "mutation_id"),
        "storage_amplification": storage / source,
        "token_recompute_amplification": tokens / source,
        "compute_ms_per_semantic_unit": compute / source,
        "cache_invalidation_amplification": invalidated / source,
        "derived_write_fanout": writes,
    }


def shared_immutable_context_economics(
    *, base_units: int, consumers: int, private_delta_units_per_consumer: int
) -> dict:
    base = _integer(base_units, "base_units")
    n = _integer(consumers, "consumers", minimum=1)
    delta = _integer(
        private_delta_units_per_consumer, "private_delta_units_per_consumer"
    )
    duplicated = n * (base + delta)
    shared = base + n * delta
    savings = duplicated - shared
    return {
        "duplicated_units": duplicated,
        "shared_base_plus_private_delta_units": shared,
        "saved_units": savings,
        "saving_fraction": savings / duplicated if duplicated else 0.0,
        "boundary": "share immutable/content-addressed base only; private deltas remain isolated",
    }


def _json_safe(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _print_json(value: object) -> None:
    print(json.dumps(_json_safe(value), ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="L6 Adaptive Context Control shadow reference implementation."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    telemetry = sub.add_parser("telemetry", help="aggregate context access/miss telemetry")
    telemetry.add_argument("--events", required=True)

    residency = sub.add_parser("residency", help="shadow admission/residency recommendation")
    residency.add_argument("--events", required=True)
    residency.add_argument("--catalog", required=True)
    residency.add_argument("--budget", type=int, required=True)
    residency.add_argument("--min-demand-tasks", type=int, default=3)
    residency.add_argument("--min-asset-demands", type=int, default=2)

    prefetch = sub.add_parser("prefetch", help="shadow co-demand prefetch recommendation")
    prefetch.add_argument("--events", required=True)
    prefetch.add_argument("--catalog", required=True)
    prefetch.add_argument("--seed", action="append", required=True)
    prefetch.add_argument("--budget", type=int, required=True)
    prefetch.add_argument("--min-seed-demands", type=int, default=2)
    prefetch.add_argument("--min-joint-tasks", type=int, default=2)

    budget = sub.add_parser("budget", help="shadow vector-budget feedback")
    budget.add_argument("--state", required=True)

    locator = sub.add_parser("locator", help="evaluate locator-token economics")
    locator.add_argument("--locator-units", type=int, required=True)
    locator.add_argument("--carry-cost", type=float, required=True)
    locator.add_argument("--fetch-probability", type=float, required=True)
    locator.add_argument("--search-avoided", type=float, required=True)
    locator.add_argument("--fetch-cost", type=float, default=0.0)

    amplification = sub.add_parser(
        "amplification", help="measure context mutation/write amplification"
    )
    amplification.add_argument("--mutation-id", required=True)
    amplification.add_argument("--semantic-source-units", type=float, required=True)
    amplification.add_argument("--storage-bytes-changed", type=float, default=0.0)
    amplification.add_argument("--recomputed-tokens", type=float, default=0.0)
    amplification.add_argument("--compute-ms", type=float, default=0.0)
    amplification.add_argument("--invalidated-cache-tokens", type=float, default=0.0)
    amplification.add_argument("--derived-writes", type=int, default=0)

    share = sub.add_parser(
        "share", help="compare duplicated context with immutable shared-base plus private delta"
    )
    share.add_argument("--base-units", type=int, required=True)
    share.add_argument("--consumers", type=int, required=True)
    share.add_argument("--private-delta-units", type=int, required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "telemetry":
            _print_json(aggregate_access(load_events(args.events)))
        elif args.command == "residency":
            _print_json(
                recommend_residency(
                    load_events(args.events),
                    load_catalog(args.catalog),
                    args.budget,
                    min_demand_tasks=args.min_demand_tasks,
                    min_asset_demands=args.min_asset_demands,
                )
            )
        elif args.command == "prefetch":
            _print_json(
                recommend_prefetch(
                    load_events(args.events),
                    load_catalog(args.catalog),
                    args.seed,
                    args.budget,
                    min_seed_demands=args.min_seed_demands,
                    min_joint_tasks=args.min_joint_tasks,
                )
            )
        elif args.command == "budget":
            current, bounds, observation, policy = load_budget_state(args.state)
            _print_json(suggest_budget(current, bounds, observation, policy))
        elif args.command == "locator":
            _print_json(
                locator_economics(
                    locator_units=args.locator_units,
                    locator_carry_cost_units_per_task=args.carry_cost,
                    fetch_probability=args.fetch_probability,
                    search_avoided_units=args.search_avoided,
                    fetch_cost_units=args.fetch_cost,
                )
            )
        elif args.command == "amplification":
            _print_json(
                mutation_amplification(
                    MutationReceipt(
                        mutation_id=args.mutation_id,
                        semantic_source_units=args.semantic_source_units,
                        storage_bytes_changed=args.storage_bytes_changed,
                        recomputed_tokens=args.recomputed_tokens,
                        compute_ms=args.compute_ms,
                        invalidated_cache_tokens=args.invalidated_cache_tokens,
                        derived_writes=args.derived_writes,
                    )
                )
            )
        elif args.command == "share":
            _print_json(
                shared_immutable_context_economics(
                    base_units=args.base_units,
                    consumers=args.consumers,
                    private_delta_units_per_consumer=args.private_delta_units,
                )
            )
        else:  # pragma: no cover
            raise ControlError(f"unknown command: {args.command}")
    except (ControlError, json.JSONDecodeError, OSError, KeyError, TypeError) as exc:
        print(
            json.dumps(
                {"status": "ERROR", "error": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
            )
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
