# -*- coding: utf-8 -*-
"""Offline-only calibration for the L6 shadow vector controller."""
from __future__ import annotations

import argparse
import itertools
import json
import math
from dataclasses import fields
from pathlib import Path
from statistics import mean
from typing import Mapping, Sequence

import adaptive_control as ac


class CalibrationError(ValueError): pass


def _rows(payload: object) -> list[Mapping[str, object]]:
    if not isinstance(payload, Mapping) or set(payload) - {"schema_version", "rows", "note"}:
        raise CalibrationError("calibration input must be a strict wrapper")
    if payload.get("schema_version") != 1 or not isinstance(payload.get("rows"), list):
        raise CalibrationError("calibration requires schema_version=1 and rows")
    return payload["rows"]


def _loss(row: Mapping[str, object], policy: ac.ControllerPolicy) -> float:
    allowed = {"task_id", "split", "current", "bounds", "observation", "target"}
    if set(row) != allowed: raise CalibrationError("calibration row fields mismatch")
    if row["split"] not in {"train", "holdout"}: raise CalibrationError("split must be train or holdout")
    current = ac.ContextBudget.from_mapping(row["current"], "current")
    bounds = ac.BudgetBounds.from_mapping(row["bounds"])
    obs = ac.ControllerObservation.from_mapping(row["observation"])
    target = ac.ContextBudget.from_mapping(row["target"], "target")
    proposed = ac.suggest_budget(current, bounds, obs, policy)["proposed"]
    losses = []
    for f in fields(ac.ContextBudget):
        span = getattr(bounds.maximum, f.name) - getattr(bounds.minimum, f.name)
        scale = float(span) if span else 1.0
        losses.append(((float(proposed[f.name])-float(getattr(target, f.name)))/scale)**2)
    return mean(losses)


def calibrate(rows: Sequence[Mapping[str, object]], grid: Mapping[str, Sequence[float]], *, min_train=3, min_holdout=2) -> dict:
    if set(grid) != {"base_step_fraction", "max_step_fraction", "deadband"}:
        raise CalibrationError("grid must contain base_step_fraction, max_step_fraction, deadband")
    policies = []
    for name, values in grid.items():
        if not isinstance(values, (list, tuple)) or not values:
            raise CalibrationError("grid axes must be non-empty lists/tuples")
    for base, maximum, deadband in itertools.product(grid["base_step_fraction"], grid["max_step_fraction"], grid["deadband"]):
        try:
            policy = ac.ControllerPolicy.from_mapping({"base_step_fraction":base, "max_step_fraction":maximum, "deadband":deadband})
        except ac.ControlError as exc:
            raise CalibrationError(str(exc)) from exc
        policies.append((base, maximum, deadband, policy))
    ids = {"train": set(), "holdout": set()}
    for row in rows:
        task = row.get("task_id"); split = row.get("split")
        if not isinstance(task, str) or not task or split not in ids: raise CalibrationError("invalid task_id/split")
        ids[split].add(task)
    if ids["train"] & ids["holdout"]:
        raise CalibrationError("train and holdout task IDs must be disjoint")
    if len(ids["train"]) < min_train or len(ids["holdout"]) < min_holdout:
        return {"status": "insufficient evidence", "train_tasks": len(ids["train"]), "holdout_tasks": len(ids["holdout"])}
    candidates = []
    for base, maximum, deadband, policy in policies:
        train_loss = mean(_loss(row, policy) for row in rows if row["split"] == "train")
        candidates.append((train_loss, base, maximum, deadband, policy))
    if not candidates: raise CalibrationError("grid contains no valid candidates")
    train_loss, base, maximum, deadband, winner = min(candidates, key=lambda x: x[:4])
    holdout_loss = mean(_loss(row, winner) for row in rows if row["split"] == "holdout")
    return {"status": "shadow-candidate", "scope": "offline-replay-not-production-control",
            "selected": {"base_step_fraction": base, "max_step_fraction": maximum, "deadband": deadband},
            "train_loss": train_loss, "holdout_loss": holdout_loss,
            "train_tasks": len(ids["train"]), "holdout_tasks": len(ids["holdout"]),
            "candidate_count": len(candidates), "auto_enable": False}


def main(argv=None) -> int:
    p=argparse.ArgumentParser(); p.add_argument("--input",required=True); p.add_argument("--grid",required=True); args=p.parse_args(argv)
    try:
        payload=json.loads(Path(args.input).read_text()); grid=json.loads(Path(args.grid).read_text())
        print(json.dumps(calibrate(_rows(payload), grid), indent=2, allow_nan=False)); return 0
    except (CalibrationError, ac.ControlError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status":"ERROR","error":type(exc).__name__,"message":str(exc)})); return 2


if __name__ == "__main__": raise SystemExit(main())
