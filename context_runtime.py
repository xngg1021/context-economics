# -*- coding: utf-8 -*-
"""Strict runtime telemetry capture and normalization.

The wire format is intentionally provider agnostic.  Adapters emit public,
redacted events; this module validates them and produces the existing L5 run
receipt plus L6 context events.  Raw prompts, completions and credentials are
never accepted by the public schema.
"""
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

import adaptive_control as ac
import task_economics as te


SCHEMA_VERSION = 1
EVENT_KINDS = {"request", "tool", "context", "compression", "outcome"}
CONTEXT_KINDS = {
    "context_hit", "soft_miss", "hard_miss", "stale_hit",
    "planned_retrieval", "prefetch",
}
SECRET_KEYS = {
    "apikey", "xapikey", "authorization", "authorizationheader", "cookie",
    "setcookie", "accesstoken", "refreshtoken", "accountid", "rawprompt",
    "rawcompletion", "prompt", "completion",
    "proxyauthorization", "password", "passwd", "pwd", "clientsecret",
    "sessiontoken", "sessionid", "idtoken", "token", "secret", "credential",
    "authtoken", "apitoken", "bearertoken", "oauthtoken",
    "credentials", "privatekey", "secretkey", "accesskey", "accesskeyid",
    "secretaccesskey", "awsaccesskeyid", "awssecretaccesskey", "awssecuritytoken",
}
SAFE_PROVIDER_METADATA_KEYS = {
    "route", "region", "responseid", "servicetier", "cachehint", "type",
    "cachewriteusageavailable",
}
MAX_METADATA_DEPTH = 16
MAX_METADATA_BYTES = 65536
MAX_METADATA_NODES = 4096
TOOL_CATEGORIES = {"retrieval", "filesystem", "search", "database", "web", "compute", "action", "other"}



class TelemetryError(ValueError):
    """Invalid or unsafe runtime telemetry."""


def _text(value: object, name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TelemetryError(f"{name} must be a non-empty string")
    return value


def _bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise TelemetryError(f"{name} must be boolean")
    return value


def _int(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise TelemetryError(f"{name} must be an integer >= {minimum}")
    return value


def _num(value: object, name: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TelemetryError(f"{name} must be numeric")
    out = float(value)
    if not math.isfinite(out) or out < minimum:
        raise TelemetryError(f"{name} must be finite and >= {minimum}")
    return out


def _time(value: object, name: str) -> str:
    raw = _text(value, name)
    assert isinstance(raw, str)
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise TelemetryError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TelemetryError(f"{name} must include a timezone")
    return raw


def _mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TelemetryError(f"{name} must be an object")
    nodes = 0
    def visit(item, depth=0, provider_metadata=False):
        nonlocal nodes
        nodes += 1
        if depth > MAX_METADATA_DEPTH or nodes > MAX_METADATA_NODES:
            raise TelemetryError("metadata exceeds depth/node limit")
        if isinstance(item, Mapping):
            out = {}
            for key, child in item.items():
                if not isinstance(key, str):
                    raise TelemetryError("metadata keys must be strings")
                normalized_key = key.lower().replace("-", "").replace("_", "")
                if normalized_key in SECRET_KEYS:
                    raise TelemetryError("metadata contains forbidden private field")
                if provider_metadata and normalized_key not in SAFE_PROVIDER_METADATA_KEYS:
                    raise TelemetryError("provider metadata key is not allowlisted")
                out[key] = visit(child, depth+1, provider_metadata or normalized_key == "providermetadata")
            return out
        if isinstance(item, (list, tuple)):
            return [visit(child, depth+1, provider_metadata) for child in item]
        if isinstance(item, str) and len(item) > MAX_METADATA_BYTES:
            raise TelemetryError("metadata exceeds size limit")
        if item is None or type(item) in (str, bool, int):
            return item
        if type(item) is float and math.isfinite(item):
            return item
        raise TelemetryError("metadata must contain finite JSON-safe values")
    out = visit(value, provider_metadata=name == "provider_metadata")
    try:
        size = len(json.dumps(out, allow_nan=False).encode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise TelemetryError("metadata is not JSON-safe") from exc
    if size > MAX_METADATA_BYTES:
        raise TelemetryError("metadata exceeds size limit")
    return out


@dataclass(frozen=True)
class Envelope:
    event_id: str
    event_kind: str
    run_id: str
    task_id: str
    policy_id: str
    occurred_at: str
    payload: dict[str, object]

    @classmethod
    def parse(cls, row: Mapping[str, object]) -> "Envelope":
        if not isinstance(row, Mapping):
            raise TelemetryError("event must be an object")
        allowed = {f.name for f in fields(cls)}
        unknown = sorted(set(row) - allowed)
        missing = sorted(allowed - set(row))
        if unknown or missing:
            raise TelemetryError(
                "event fields invalid; unknown=" + repr(unknown) + ", missing=" + repr(missing)
            )
        kind = _text(row["event_kind"], "event_kind")
        assert isinstance(kind, str)
        if kind not in EVENT_KINDS:
            raise TelemetryError(f"unsupported event_kind: {kind}")
        return cls(
            event_id=str(_text(row["event_id"], "event_id")),
            event_kind=kind,
            run_id=str(_text(row["run_id"], "run_id")),
            task_id=str(_text(row["task_id"], "task_id")),
            policy_id=str(_text(row["policy_id"], "policy_id")),
            occurred_at=_time(row["occurred_at"], "occurred_at"),
            payload=_mapping(row["payload"], "payload"),
        )


class RuntimeAdapter(Protocol):
    """Minimal adapter: provider-native data in, canonical envelopes out."""

    adapter_id: str

    def adapt(self, native_event: Mapping[str, object]) -> Iterable[Mapping[str, object]]:
        ...


class CanonicalAdapter:
    """Adapter for runtimes that already emit the canonical event envelope."""

    adapter_id = "canonical-v1"

    def adapt(self, native_event: Mapping[str, object]) -> Iterable[Mapping[str, object]]:
        yield dict(native_event)


class Collector:
    """In-memory strict collector suitable for harness integrations and tests."""

    def __init__(self, adapter: RuntimeAdapter) -> None:
        self.adapter = adapter
        self._events: list[Envelope] = []
        self._ids: set[str] = set()

    def capture(self, native_event: Mapping[str, object]) -> None:
        for raw in self.adapter.adapt(native_event):
            event = Envelope.parse(raw)
            if event.event_id in self._ids:
                raise TelemetryError(f"duplicate event_id: {event.event_id}")
            self._ids.add(event.event_id)
            self._events.append(event)

    def bundle(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "adapter_id": self.adapter.adapter_id,
            "events": [
                {
                    "event_id": e.event_id, "event_kind": e.event_kind,
                    "run_id": e.run_id, "task_id": e.task_id,
                    "policy_id": e.policy_id, "occurred_at": e.occurred_at,
                    "payload": _mapping(e.payload, "payload"),
                }
                for e in self._events
            ],
        }


def load_raw(path: str | Path) -> list[Envelope]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise TelemetryError("raw telemetry must be a wrapper object")
    unknown = sorted(set(value) - {"schema_version", "adapter_id", "events", "note"})
    if unknown or value.get("schema_version") != SCHEMA_VERSION:
        raise TelemetryError("invalid telemetry wrapper")
    _text(value.get("adapter_id"), "adapter_id")
    rows = value.get("events")
    if not isinstance(rows, list):
        raise TelemetryError("events must be a list")
    events = [Envelope.parse(row) for row in rows]
    ids = [event.event_id for event in events]
    if len(ids) != len(set(ids)):
        raise TelemetryError("event_id values must be globally unique")
    return events


def _exact(payload: Mapping[str, object], allowed: set[str], required: set[str], name: str) -> None:
    unknown = sorted(set(payload) - allowed)
    missing = sorted(required - set(payload))
    if unknown or missing:
        raise TelemetryError(
            f"{name} fields invalid; unknown={unknown!r}, missing={missing!r}"
        )


def normalize(events: Sequence[Envelope]) -> dict[str, object]:
    """Normalize a multi-run event stream into L5 receipts and L6 events."""
    if not events:
        raise TelemetryError("at least one event is required")
    events = [Envelope.parse({f.name: getattr(e, f.name) for f in fields(Envelope)}) for e in events]
    if len({e.event_id for e in events}) != len(events):
        raise TelemetryError("event IDs must be globally unique")
    groups: dict[str, list[Envelope]] = {}
    identity: dict[str, tuple[str, str]] = {}
    for event in events:
        pair = (event.task_id, event.policy_id)
        if event.run_id in identity and identity[event.run_id] != pair:
            raise TelemetryError(f"run {event.run_id} crosses task or policy")
        identity[event.run_id] = pair
        groups.setdefault(event.run_id, []).append(event)

    receipts: list[dict[str, object]] = []
    context_events: list[dict[str, object]] = []
    normalized_runs: list[dict[str, object]] = []
    for run_id, rows in sorted(groups.items()):
        requests: list[dict[str, object]] = []
        tools: list[dict[str, object]] = []
        compressions: list[dict[str, object]] = []
        outcomes: list[dict[str, object]] = []
        task_id, policy_id = identity[run_id]
        occurred = [_time_dt(e.occurred_at) for e in rows]
        if occurred != sorted(occurred):
            raise TelemetryError("run event timestamps must be ordered")
        if rows[-1].event_kind != "outcome":
            raise TelemetryError("outcome must be the last event in a run")
        for event in rows:
            p = event.payload
            if event.event_kind == "request":
                allowed = {
                    "request_id", "sequence_index", "provider", "model", "model_revision",
                    "endpoint_tier", "request_start", "request_end", "input_tokens",
                    "cached_input_tokens", "uncached_input_tokens", "cache_write_tokens",
                    "output_tokens", "provider_bill_usd", "provider_bill_source",
                    "billing_status", "ttft_ms", "request_wall_time_ms",
                    "context_length_before", "context_length_after", "compression_triggered",
                    "compression_id", "cache_routing_hint", "cache_break_observed",
                    "provider_metadata", "usage_observations",
                }
                required = {
                    "request_id", "sequence_index", "provider", "model", "model_revision",
                    "request_start", "request_end", "input_tokens", "cached_input_tokens",
                    "uncached_input_tokens", "cache_write_tokens", "output_tokens",
                    "provider_bill_usd", "provider_bill_source", "billing_status",
                    "ttft_ms", "request_wall_time_ms", "context_length_before",
                    "context_length_after", "compression_triggered",
                }
                _exact(p, allowed, required, "request")
                q = dict(p)
                for key in ("request_id", "provider", "model", "model_revision", "provider_bill_source", "billing_status"):
                    q[key] = _text(q[key], key)
                q["sequence_index"] = _int(q["sequence_index"], "sequence_index")
                for key in ("input_tokens", "cached_input_tokens", "uncached_input_tokens", "cache_write_tokens", "output_tokens", "context_length_before", "context_length_after"):
                    q[key] = _int(q[key], key)
                if q["cached_input_tokens"] + q["uncached_input_tokens"] != q["input_tokens"]:
                    raise TelemetryError("cached + uncached input tokens must equal input_tokens")
                for key in ("provider_bill_usd", "ttft_ms", "request_wall_time_ms"):
                    q[key] = None if key == "ttft_ms" and q[key] is None else _num(q[key], key)
                q["compression_triggered"] = _bool(q["compression_triggered"], "compression_triggered")
                q["request_start"] = _time(q["request_start"], "request_start")
                q["request_end"] = _time(q["request_end"], "request_end")
                if _time_dt(event.occurred_at) < _time_dt(q["request_end"]):
                    raise TelemetryError("request event precedes request completion")
                if _time_dt(q["request_end"]) < _time_dt(q["request_start"]):
                    raise TelemetryError("request_end precedes request_start")
                status = _text(q["billing_status"], "billing_status")
                if status not in {"observed", "estimated"}:
                    raise TelemetryError("billing_status must be observed or estimated")
                if "provider_metadata" in q:
                    q["provider_metadata"] = _mapping(q["provider_metadata"], "provider_metadata")
                if "usage_observations" in q:
                    observations = _mapping(q["usage_observations"], "usage_observations")
                    observation_fields = {"input_tokens", "output_tokens", "cached_input_tokens", "cache_write_tokens", "service_tier", "response_id"}
                    _exact(observations, observation_fields, observation_fields, "usage_observations")
                    for field in observation_fields - {"service_tier", "response_id"}:
                        value = observations[field]
                        if value is not None:
                            _int(value, field)
                            if value != q[field]:
                                raise TelemetryError("usage observation conflicts with ledger")
                        elif field in {"input_tokens", "output_tokens"}:
                            raise TelemetryError("input/output usage required")
                    for field in ("service_tier", "response_id"):
                        if observations[field] is not None:
                            _text(observations[field], field)
                    q["usage_observations"] = observations
                requests.append(q)
            elif event.event_kind == "tool":
                allowed = {"tool_call_id", "tool_name", "category", "start", "end", "cost_usd", "result_size_bytes", "result_token_estimate", "retry", "error", "whether_reacquisition", "reacquisition_reason", "is_retrieval"}
                required = allowed - {"reacquisition_reason", "is_retrieval"}
                _exact(p, allowed, required, "tool")
                q = dict(p)
                for key in ("tool_call_id", "tool_name", "category"):
                    q[key] = _text(q[key], key)
                for key in ("cost_usd",): q[key] = _num(q[key], key)
                for key in ("result_size_bytes", "result_token_estimate"): q[key] = _int(q[key], key)
                for key in ("retry", "error", "whether_reacquisition"): q[key] = _bool(q[key], key)
                if q["category"] not in TOOL_CATEGORIES:
                    raise TelemetryError("unsupported tool category")
                q["is_retrieval"] = _bool(q.get("is_retrieval", q["category"] == "retrieval" or q["whether_reacquisition"]), "is_retrieval")
                if q["whether_reacquisition"] and not q["is_retrieval"]:
                    raise TelemetryError("reacquisition requires is_retrieval=true")
                q["start"] = _time(q["start"], "tool.start")
                q["end"] = _time(q["end"], "tool.end")
                if _time_dt(event.occurred_at) < _time_dt(q["end"]):
                    raise TelemetryError("tool event precedes tool completion")
                if _time_dt(q["end"]) < _time_dt(q["start"]):
                    raise TelemetryError("tool end precedes start")
                reason = q.get("reacquisition_reason")
                if q["whether_reacquisition"] and not _text(reason, "reacquisition_reason", optional=True):
                    raise TelemetryError("reacquisition requires a reason")
                tools.append(q)
            elif event.event_kind == "context":
                allowed = {"kind", "asset_id", "avoidable", "extra_cost_units", "extra_tokens", "extra_tool_calls", "extra_latency_ms", "provider_cost_usd", "used", "avoided_miss", "avoided_cost_units", "prefetched_units", "confidence"}
                _exact(p, allowed, {"kind", "asset_id"}, "context")
                if p["kind"] not in CONTEXT_KINDS:
                    raise TelemetryError(f"unsupported context kind: {p['kind']}")
                candidate = {"event_id": event.event_id, "task_id": task_id, **p}
                try:
                    canonical = ac.ContextAccessEvent.from_mapping(candidate)
                except ac.ControlError as exc:
                    raise TelemetryError(str(exc)) from exc
                context_events.append({
                    "run_id": run_id, "policy_id": policy_id,
                    **{f.name: getattr(canonical, f.name) for f in fields(ac.ContextAccessEvent)},
                })
            elif event.event_kind == "compression":
                allowed = {"compression_id", "trigger_reason", "pre_context_length", "post_context_length", "retained_recent_tail", "summary_budget", "protected_messages", "provider_visible_prompt_mutation", "cache_break_observed"}
                _exact(p, allowed, allowed, "compression")
                q = dict(p)
                for key in ("compression_id", "trigger_reason"):
                    q[key] = _text(q[key], key)
                for key in ("pre_context_length", "post_context_length", "retained_recent_tail", "summary_budget", "protected_messages"): q[key] = _int(q[key], key)
                q["provider_visible_prompt_mutation"] = _bool(q["provider_visible_prompt_mutation"], "provider_visible_prompt_mutation")
                if q["cache_break_observed"] not in {True, False, "unknown"}:
                    raise TelemetryError("cache_break_observed must be true, false, or unknown")
                compressions.append(q)
            else:
                allowed = {"success", "task_score", "scorer_id", "scorer_version", "failure_class", "scoring_provenance", "harness_revision"}
                required = allowed - {"failure_class"}
                _exact(p, allowed, required, "outcome")
                q = dict(p)
                for key in ("scorer_id", "scorer_version", "scoring_provenance", "harness_revision"):
                    q[key] = _text(q[key], key)
                q["success"] = _bool(q["success"], "success")
                q["task_score"] = _num(q["task_score"], "task_score", minimum=-math.inf)
                if q["scoring_provenance"] not in {"human", "automatic", "benchmark"}:
                    raise TelemetryError("invalid scoring_provenance")
                outcomes.append(q)

        if not requests or len(outcomes) != 1:
            raise TelemetryError(f"run {run_id} requires requests and exactly one outcome")
        sequence = [q["sequence_index"] for q in requests]
        if sequence != sorted(sequence) or len(sequence) != len(set(sequence)):
            raise TelemetryError(f"run {run_id} request sequence must be strictly increasing")
        request_ids = [q["request_id"] for q in requests]
        tool_ids = [q["tool_call_id"] for q in tools]
        if len(request_ids) != len(set(request_ids)) or len(tool_ids) != len(set(tool_ids)):
            raise TelemetryError(f"run {run_id} request/tool ids must be unique")
        provider_pins = {(q["provider"], q["model"], q["model_revision"]) for q in requests}
        if len(provider_pins) != 1:
            raise TelemetryError(f"run {run_id} changes provider/model pin")
        provider, model, revision = next(iter(provider_pins))
        outcome = outcomes[0]
        starts = [_time_dt(q["request_start"]) for q in requests]
        ends = [_time_dt(q["request_end"]) for q in requests]
        if starts != sorted(starts):
            raise TelemetryError("request starts must follow sequence order")
        starts.extend(_time_dt(q["start"]) for q in tools)
        ends.extend(_time_dt(q["end"]) for q in tools)
        ends.append(_time_dt(rows[-1].occurred_at))
        billing_statuses = {q["billing_status"] for q in requests}
        receipt = {
            "run_id": run_id, "task_id": task_id, "policy_id": policy_id,
            "success": outcome["success"], "provider": provider, "model": model,
            "model_revision": revision, "harness_revision": outcome["harness_revision"],
            "started_at": min(starts).isoformat(), "ended_at": max(ends).isoformat(),
            "task_score": outcome["task_score"],
            "input_tokens": sum(q["input_tokens"] for q in requests),
            "cached_input_tokens": sum(q["cached_input_tokens"] for q in requests),
            "cache_write_tokens": sum(q["cache_write_tokens"] for q in requests),
            "output_tokens": sum(q["output_tokens"] for q in requests),
            "provider_bill_usd": sum(q["provider_bill_usd"] for q in requests),
            "provider_bill_source": ";".join(sorted({str(q["provider_bill_source"]) for q in requests})),
            "billing_status": next(iter(billing_statuses)) if len(billing_statuses) == 1 else "estimated",
            "cost_ledger_version": 2, "external_cost_usd": 0.0,
            "tool_cost_usd": sum(q["cost_usd"] for q in tools),
            "reacquisition_cost_usd": sum(q["cost_usd"] for q in tools if q["whether_reacquisition"]),
            "retry_cost_usd": sum(q["cost_usd"] for q in tools if q["retry"]),
            "latency_cost_usd": 0.0, "failure_cost_usd": 0.0,
            "tool_calls": len(tools), "retrieval_calls": sum(q["is_retrieval"] for q in tools),
            "reacquisition_calls": sum(bool(q["whether_reacquisition"]) for q in tools),
            "retry_count": sum(bool(q["retry"]) for q in tools),
            "compression_calls": len(compressions),
            "ttft_ms": requests[0]["ttft_ms"],
            "wall_time_ms": (max(ends) - min(starts)).total_seconds() * 1000,
            "failure_class": outcome.get("failure_class"),
            "scorer_id": outcome["scorer_id"], "scorer_version": outcome["scorer_version"],
            "scoring_provenance": outcome["scoring_provenance"], "notes": [],
        }
        te.RunReceipt.from_mapping(receipt)
        receipts.append(receipt)
        normalized_runs.append({"run_id": run_id, "requests": requests, "tools": tools, "compressions": compressions, "outcome": outcome})
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_class": "runtime-ready-normalized-receipt",
        "runs": normalized_runs,
        "l5_receipts": {"schema_version": 1, "runs": receipts},
        "l6_context_events": {"schema_version": 1, "events": context_events},
    }


def _time_dt(value: object) -> datetime:
    raw = str(value)
    return datetime.fromisoformat(raw[:-1] + "+00:00" if raw.endswith("Z") else raw)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalize strict runtime telemetry")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        result = normalize(load_raw(args.input))
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output:
            Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
        return 0
    except (TelemetryError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "error": type(exc).__name__, "message": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
