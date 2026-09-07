# -*- coding: utf-8 -*-
"""Version-pinned runtime experiment contract for Context Economics.

This module joins L5 run receipts with L6 context-access telemetry. It validates
structural comparability and pairing, but it does not prove that a declared run
was real, randomized, causal, or provider-billed. Those remain provenance and
experimental-design obligations outside the parser.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from datetime import datetime
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Mapping, Sequence

import adaptive_control as ac
import task_economics as te


EVIDENCE_CLASSES = {"synthetic-contract", "trace-replay", "runtime-A/B"}
ASSIGNMENT_METHODS = {"paired-fixed", "counterbalanced", "randomized", "observational"}
REQUIRED_RECEIPT_FIELDS = {
    "run_id",
    "task_id",
    "policy_id",
    "success",
    "provider",
    "model",
    "model_revision",
    "harness_revision",
    "started_at",
    "ended_at",
    "task_score",
    "input_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "output_tokens",
    "provider_bill_usd",
    "tool_cost_usd",
    "reacquisition_cost_usd",
    "retry_cost_usd",
    "latency_cost_usd",
    "failure_cost_usd",
    "tool_calls",
    "retrieval_calls",
    "reacquisition_calls",
    "retry_count",
    "compression_calls",
    "ttft_ms",
    "wall_time_ms",
    "failure_class",
}


class ExperimentError(ValueError):
    """Experiment contract or alignment error."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExperimentError(f"{name} must be a non-empty string")
    return value


def _git_sha(value: object, name: str) -> str:
    text = _text(value, name)
    if re.fullmatch(r"[0-9a-f]{40}", text) is None:
        raise ExperimentError(f"{name} must be an exact 40-character lowercase Git SHA")
    return text


def _timestamp(value: object, name: str) -> datetime:
    text = _text(value, name)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ExperimentError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExperimentError(f"{name} must include an explicit timezone offset")
    return parsed


def _string_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ExperimentError(f"{name} must be a non-empty list of strings")
    out = tuple(_text(item, f"{name}[]") for item in value)
    if len(set(out)) != len(out):
        raise ExperimentError(f"{name} must not contain duplicates")
    return out


@dataclass(frozen=True)
class ExperimentManifest:
    experiment_id: str
    declared_evidence_class: str
    assignment_method: str
    control_policy: str
    treatment_policy: str
    provider: str
    model: str
    model_revision: str
    harness_revision: str
    repository_commit: str
    runtime_environment_ref: str
    task_set_ref: str
    pricing_snapshot_ref: str
    policy_bundle_ref: str
    expected_task_ids: tuple[str, ...]

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "ExperimentManifest":
        if not isinstance(row, Mapping):
            raise ExperimentError("manifest must be an object")
        allowed = {f.name for f in fields(cls)}
        unknown = sorted(set(row) - allowed)
        missing = sorted(allowed - set(row))
        if unknown:
            raise ExperimentError("unknown manifest fields: " + ", ".join(unknown))
        if missing:
            raise ExperimentError("missing manifest fields: " + ", ".join(missing))

        evidence = _text(row["declared_evidence_class"], "declared_evidence_class")
        if evidence not in EVIDENCE_CLASSES:
            raise ExperimentError(f"unsupported declared_evidence_class: {evidence}")
        assignment = _text(row["assignment_method"], "assignment_method")
        if assignment not in ASSIGNMENT_METHODS:
            raise ExperimentError(f"unsupported assignment_method: {assignment}")

        control = _text(row["control_policy"], "control_policy")
        treatment = _text(row["treatment_policy"], "treatment_policy")
        if control == treatment:
            raise ExperimentError("control_policy and treatment_policy must differ")

        return cls(
            experiment_id=_text(row["experiment_id"], "experiment_id"),
            declared_evidence_class=evidence,
            assignment_method=assignment,
            control_policy=control,
            treatment_policy=treatment,
            provider=_text(row["provider"], "provider"),
            model=_text(row["model"], "model"),
            model_revision=_text(row["model_revision"], "model_revision"),
            harness_revision=_text(row["harness_revision"], "harness_revision"),
            repository_commit=_git_sha(row["repository_commit"], "repository_commit"),
            runtime_environment_ref=_text(row["runtime_environment_ref"], "runtime_environment_ref"),
            task_set_ref=_text(row["task_set_ref"], "task_set_ref"),
            pricing_snapshot_ref=_text(row["pricing_snapshot_ref"], "pricing_snapshot_ref"),
            policy_bundle_ref=_text(row["policy_bundle_ref"], "policy_bundle_ref"),
            expected_task_ids=_string_list(row["expected_task_ids"], "expected_task_ids"),
        )


@dataclass(frozen=True)
class ReceiptRecord:
    receipt: te.RunReceipt
    explicit_fields: frozenset[str]


@dataclass(frozen=True)
class ExperimentContextEvent:
    run_id: str
    policy_id: str
    event: ac.ContextAccessEvent

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "ExperimentContextEvent":
        if not isinstance(row, Mapping):
            raise ExperimentError("experiment context event must be an object")
        base_fields = {f.name for f in fields(ac.ContextAccessEvent)}
        allowed = base_fields | {"run_id", "policy_id"}
        unknown = sorted(set(row) - allowed)
        if unknown:
            raise ExperimentError("unknown experiment event fields: " + ", ".join(unknown))
        if "run_id" not in row or "policy_id" not in row:
            raise ExperimentError("experiment event requires run_id and policy_id")
        base = {key: value for key, value in row.items() if key in base_fields}
        try:
            event = ac.ContextAccessEvent.from_mapping(base)
        except ac.ControlError as exc:
            raise ExperimentError(str(exc)) from exc
        return cls(
            run_id=_text(row["run_id"], "event.run_id"),
            policy_id=_text(row["policy_id"], "event.policy_id"),
            event=event,
        )


def _load_wrapper(path: str | Path, key: str) -> list[Mapping[str, object]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ExperimentError(f"{key} file must be a wrapper object")
    allowed = {"schema_version", "note", key}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ExperimentError(f"unknown {key} wrapper fields: " + ", ".join(unknown))
    if payload.get("schema_version") != 1:
        raise ExperimentError(f"{key} wrapper requires schema_version=1")
    rows = payload.get(key)
    if not isinstance(rows, list):
        raise ExperimentError(f"{key} must be a list")
    if not all(isinstance(row, Mapping) for row in rows):
        raise ExperimentError(f"every {key} row must be an object")
    return rows


def load_manifest(path: str | Path) -> ExperimentManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ExperimentError("manifest file must be an object")
    allowed = {"schema_version", "note", "manifest"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ExperimentError("unknown manifest wrapper fields: " + ", ".join(unknown))
    if payload.get("schema_version") != 1:
        raise ExperimentError("manifest wrapper requires schema_version=1")
    manifest = payload.get("manifest")
    if not isinstance(manifest, Mapping):
        raise ExperimentError("manifest wrapper requires manifest object")
    return ExperimentManifest.from_mapping(manifest)


def load_receipt_records(path: str | Path) -> list[ReceiptRecord]:
    rows = _load_wrapper(path, "runs")
    out: list[ReceiptRecord] = []
    seen: set[str] = set()
    for raw in rows:
        missing = sorted(REQUIRED_RECEIPT_FIELDS - set(raw))
        if missing:
            raise ExperimentError(
                "runtime experiment receipt is missing explicit fields: " + ", ".join(missing)
            )
        try:
            receipt = te.RunReceipt.from_mapping(raw)
        except te.ReceiptError as exc:
            raise ExperimentError(str(exc)) from exc
        if receipt.run_id in seen:
            raise ExperimentError(f"duplicate run_id: {receipt.run_id}")
        seen.add(receipt.run_id)
        out.append(ReceiptRecord(receipt, frozenset(raw)))
    if not out:
        raise ExperimentError("runtime experiment requires at least one receipt")
    return out


def load_experiment_events(path: str | Path) -> list[ExperimentContextEvent]:
    rows = _load_wrapper(path, "events")
    out: list[ExperimentContextEvent] = []
    event_ids: set[str] = set()
    for raw in rows:
        event = ExperimentContextEvent.from_mapping(raw)
        if event.event.event_id in event_ids:
            raise ExperimentError(f"duplicate event_id: {event.event.event_id}")
        event_ids.add(event.event.event_id)
        out.append(event)
    if not out:
        raise ExperimentError("runtime experiment requires context events")
    return out


def _validate_receipt_pin(manifest: ExperimentManifest, receipt: te.RunReceipt) -> None:
    expected = {
        "provider": manifest.provider,
        "model": manifest.model,
        "model_revision": manifest.model_revision,
        "harness_revision": manifest.harness_revision,
    }
    for name, wanted in expected.items():
        actual = getattr(receipt, name)
        if actual != wanted:
            raise ExperimentError(
                f"run {receipt.run_id}: {name} mismatch: {actual!r} != {wanted!r}"
            )

    started = _timestamp(receipt.started_at, f"run {receipt.run_id}.started_at")
    ended = _timestamp(receipt.ended_at, f"run {receipt.run_id}.ended_at")
    if ended < started:
        raise ExperimentError(f"run {receipt.run_id}: ended_at precedes started_at")


def build_joint_report(
    manifest: ExperimentManifest,
    receipt_records: Sequence[ReceiptRecord],
    experiment_events: Sequence[ExperimentContextEvent],
    *,
    require_complete: bool = False,
) -> dict:
    receipts = [record.receipt for record in receipt_records]
    policies = {manifest.control_policy, manifest.treatment_policy}
    expected_tasks = set(manifest.expected_task_ids)

    by_run: dict[str, te.RunReceipt] = {}
    by_task_arm: dict[str, dict[str, list[te.RunReceipt]]] = {
        task_id: {manifest.control_policy: [], manifest.treatment_policy: []}
        for task_id in manifest.expected_task_ids
    }
    for receipt in receipts:
        if receipt.run_id in by_run:
            raise ExperimentError(f"duplicate run_id: {receipt.run_id}")
        by_run[receipt.run_id] = receipt
        _validate_receipt_pin(manifest, receipt)
        if receipt.policy_id not in policies:
            raise ExperimentError(
                f"run {receipt.run_id}: policy {receipt.policy_id!r} is outside experiment arms"
            )
        if receipt.task_id not in expected_tasks:
            raise ExperimentError(
                f"run {receipt.run_id}: unexpected task_id {receipt.task_id!r}"
            )
        by_task_arm[receipt.task_id][receipt.policy_id].append(receipt)

    missing_arms: list[dict] = []
    duplicate_arms: list[dict] = []
    for task_id in manifest.expected_task_ids:
        for policy_id in (manifest.control_policy, manifest.treatment_policy):
            count = len(by_task_arm[task_id][policy_id])
            if count == 0:
                missing_arms.append({"task_id": task_id, "policy_id": policy_id})
            elif count > 1:
                duplicate_arms.append(
                    {"task_id": task_id, "policy_id": policy_id, "count": count}
                )

    events_by_run: dict[str, list[ac.ContextAccessEvent]] = {run_id: [] for run_id in by_run}
    policy_events: dict[str, list[ac.ContextAccessEvent]] = {
        manifest.control_policy: [],
        manifest.treatment_policy: [],
    }
    for wrapped in experiment_events:
        receipt = by_run.get(wrapped.run_id)
        if receipt is None:
            raise ExperimentError(
                f"event {wrapped.event.event_id}: unknown run_id {wrapped.run_id!r}"
            )
        if wrapped.policy_id != receipt.policy_id:
            raise ExperimentError(
                f"event {wrapped.event.event_id}: policy mismatch with run {wrapped.run_id}"
            )
        if wrapped.event.task_id != receipt.task_id:
            raise ExperimentError(
                f"event {wrapped.event.event_id}: task mismatch with run {wrapped.run_id}"
            )
        events_by_run[wrapped.run_id].append(wrapped.event)
        policy_events[wrapped.policy_id].append(wrapped.event)

    runs_without_context_events = sorted(
        run_id for run_id, rows in events_by_run.items() if not rows
    )
    complete = not missing_arms and not duplicate_arms and not runs_without_context_events
    if require_complete and not complete:
        raise ExperimentError(
            "experiment is structurally incomplete: missing/duplicate arms or runs without context events"
        )

    paired = te.paired_task_report(
        receipts, manifest.control_policy, manifest.treatment_policy
    )
    by_policy_task = te.aggregate_by_policy(receipts)
    by_policy_context = {
        policy_id: ac.aggregate_access(policy_events[policy_id])
        for policy_id in (manifest.control_policy, manifest.treatment_policy)
    }

    runtime_design_structurally_ready = (
        complete
        and manifest.declared_evidence_class == "runtime-A/B"
        and manifest.assignment_method in {"paired-fixed", "counterbalanced", "randomized"}
    )

    return {
        "scope": "version-pinned-l5-l6-join-not-causal-proof",
        "experiment_id": manifest.experiment_id,
        "declared_evidence_class": manifest.declared_evidence_class,
        "assignment_method": manifest.assignment_method,
        "pins": {
            "provider": manifest.provider,
            "model": manifest.model,
            "model_revision": manifest.model_revision,
            "harness_revision": manifest.harness_revision,
            "repository_commit": manifest.repository_commit,
            "runtime_environment_ref": manifest.runtime_environment_ref,
            "task_set_ref": manifest.task_set_ref,
            "pricing_snapshot_ref": manifest.pricing_snapshot_ref,
            "policy_bundle_ref": manifest.policy_bundle_ref,
        },
        "expected_tasks": len(manifest.expected_task_ids),
        "receipts": len(receipts),
        "context_events": len(experiment_events),
        "structurally_complete": complete,
        "runtime_design_structurally_ready": runtime_design_structurally_ready,
        "causal_claim": "not inferred by this validator",
        "missing_arms": missing_arms,
        "duplicate_arms": duplicate_arms,
        "runs_without_context_events": runs_without_context_events,
        "by_policy_task_economics": by_policy_task,
        "by_policy_context_telemetry": by_policy_context,
        "paired_task_report": paired,
    }


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
        description="Validate and join a version-pinned Context Economics runtime experiment."
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--receipts", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="fail unless every expected task has exactly one run per arm and every run has context events",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_joint_report(
            load_manifest(args.manifest),
            load_receipt_records(args.receipts),
            load_experiment_events(args.events),
            require_complete=args.require_complete,
        )
        print(json.dumps(_json_safe(report), ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ExperimentError, json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "ERROR", "error": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
