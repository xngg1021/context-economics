# -*- coding: utf-8 -*-
"""
Context Economics — trace replay with explicitly proxy quality metrics.

What is empirical:
- message order and character sizes from a supplied trace,
- provider/model labels,
- aggregate input/cache-read accounting when present.

What is modeled:
- character/token conversion when exact per-message tokenization is unavailable,
- compression summary retention,
- long-context degradation,
- reference probability and failure threshold.

Therefore this script MUST NOT be described as measuring real recall or real UX
failure. It estimates proxy metrics under named assumptions.

The script can read:
1) a portable JSON fixture (`--fixture`), or
2) Hermes SQLite databases (`--db name=path ...`) without modifying them.

No private paths are required for reproducibility.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Iterable, Sequence


# Historical/local price snapshots ($ / 1M tokens). See pricing-snapshot.json.
PRICES = {
    "kimi": (3.00, 0.30, 15.00),
    "deepseek": (0.28, 0.006, 0.42),
    "gemini": (0.30, 0.075, 2.50),
}


def price_of(model: str) -> tuple[float, float, float]:
    m = (model or "").lower()
    if "deepseek" in m:
        return PRICES["deepseek"]
    if "gemini" in m:
        return PRICES["gemini"]
    return PRICES["kimi"]


WINDOW = 1_000_000
STABLE_PREFIX = 15_000

# Keep Hermes-style tail-budget semantics separate from the modeled summary size.
TAIL_RATIO_OF_THRESHOLD = 0.20
SUMMARY_RATIO_OF_MIDDLE = 0.20

# Proxy-quality assumptions. These are NOT measured provider/model recall rates.
LENGTH_DEGRADATION_START = 115_000
LENGTH_DEGRADATION_DROP = 0.30
LENGTH_DEGRADATION_END = 1_500_000
LENGTH_SLOPE = LENGTH_DEGRADATION_DROP / (
    LENGTH_DEGRADATION_END - LENGTH_DEGRADATION_START
)
ROLE_RETENTION = {"user": 0.95, "assistant": 0.85, "tool": 0.70}
ROLE_IMPORTANCE = {"user": 3.0, "assistant": 2.0, "tool": 1.0}
REFERENCE_PROBABILITY = 0.25
REFERENCE_AGE_TURNS = 12
PROXY_FAILURE_LINE = 0.60


@dataclass
class Msg:
    role: str
    tok: float
    retention: float = 1.0
    born_turn: int = 0


def _cache_share(input_tokens: float, cache_read_tokens: float) -> float:
    total = max(1.0, float(input_tokens or 0) + float(cache_read_tokens or 0))
    return min(max(float(cache_read_tokens or 0) / total, 0.0), 0.99)


def load_sessions_from_fixture(path: str | os.PathLike[str]) -> list[dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_sessions = payload["sessions"] if isinstance(payload, dict) else payload
    sessions: list[dict] = []
    for item in raw_sessions:
        messages = []
        for msg in item.get("messages", []):
            if isinstance(msg, dict):
                messages.append((str(msg["role"]), int(msg["chars"])))
            else:
                role, chars = msg
                messages.append((str(role), int(chars)))
        sessions.append(
            {
                "profile": str(item.get("profile", "fixture")),
                "sid": str(item.get("sid", f"fixture-{len(sessions)+1}")),
                "model": str(item.get("model", "kimi")),
                "messages": messages,
                "calls": int(item.get("api_call_count", 0))
                or sum(1 for role, _ in messages if role == "assistant"),
                "input_tokens": float(item.get("input_tokens", 0)),
                "cache_read_tokens": float(item.get("cache_read_tokens", 0)),
                "compacted": int(item.get("compacted", 0)),
                "chars": sum(chars for _, chars in messages),
            }
        )
    for s in sessions:
        s["rho"] = _cache_share(s["input_tokens"], s["cache_read_tokens"])
        s["total_input_tokens"] = s["input_tokens"] + s["cache_read_tokens"]
    return sessions


def _parse_db_spec(spec: str) -> tuple[str, str]:
    if "=" not in spec:
        raise ValueError("--db must use profile=/path/to/state.db")
    profile, path = spec.split("=", 1)
    if not profile or not path:
        raise ValueError("--db must use non-empty profile and path")
    return profile, os.path.expandvars(os.path.expanduser(path))


def load_sessions_from_sqlite(db_specs: Sequence[str]) -> list[dict]:
    sessions: list[dict] = []
    for spec in db_specs:
        profile, path = _parse_db_spec(spec)
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            ids = [
                row[0]
                for row in con.execute(
                    "SELECT id FROM sessions WHERE message_count >= 8"
                )
            ]
            for sid in ids:
                messages = con.execute(
                    """
                    SELECT role,
                           LENGTH(COALESCE(content,'')) +
                           LENGTH(COALESCE(tool_calls,'')) +
                           LENGTH(COALESCE(reasoning_content,''))
                    FROM messages
                    WHERE session_id=?
                    ORDER BY timestamp, id
                    """,
                    (sid,),
                ).fetchall()
                row = con.execute(
                    """
                    SELECT model, api_call_count, input_tokens, cache_read_tokens
                    FROM sessions WHERE id=?
                    """,
                    (sid,),
                ).fetchone()
                compacted = con.execute(
                    "SELECT COALESCE(SUM(compacted),0) FROM messages WHERE session_id=?",
                    (sid,),
                ).fetchone()[0]
                if not messages or not row:
                    continue
                model, calls, input_tokens, cache_read_tokens = row
                record = {
                    "profile": profile,
                    "sid": str(sid),
                    "model": model or "",
                    "messages": [(str(role), int(chars or 0)) for role, chars in messages],
                    "calls": int(calls or 0)
                    or sum(1 for role, _ in messages if role == "assistant"),
                    "input_tokens": float(input_tokens or 0),
                    "cache_read_tokens": float(cache_read_tokens or 0),
                    "compacted": int(compacted or 0),
                    "chars": sum(int(chars or 0) for _, chars in messages),
                }
                record["rho"] = _cache_share(
                    record["input_tokens"], record["cache_read_tokens"]
                )
                record["total_input_tokens"] = (
                    record["input_tokens"] + record["cache_read_tokens"]
                )
                sessions.append(record)
        finally:
            con.close()
    return sessions


def calibrate_char_per_token(sessions: Iterable[dict], fallback: float = 2.30) -> float:
    """Estimate chars/token from sessions that report no prior compaction.

    This is a coarse calibration from aggregate accounting. It is not tokenizer
    ground truth and should be replaced by exact tokenization when available.
    """
    ratios: list[float] = []
    for s in sessions:
        calls = int(s.get("calls", 0))
        chars = float(s.get("chars", 0))
        total_input = float(s.get("total_input_tokens", 0))
        if (
            int(s.get("compacted", 0)) == 0
            and calls >= 8
            and chars > 80_000
            and total_input > 0
        ):
            peak_est = 2.0 * total_input / calls - STABLE_PREFIX
            if peak_est > STABLE_PREFIX * 2:
                ratios.append(chars / peak_est)
    return float(median(ratios)) if ratios else fallback


def length_factor(context_tokens: float) -> float:
    """Proxy long-context degradation curve used only for sensitivity analysis."""
    return max(
        0.50,
        1.0
        - LENGTH_SLOPE
        * max(0.0, context_tokens - LENGTH_DEGRADATION_START),
    )


def replay(
    session: dict,
    char_per_token: float,
    threshold: float | None,
    *,
    reference_probability: float = REFERENCE_PROBABILITY,
    tail_ratio_of_threshold: float = TAIL_RATIO_OF_THRESHOLD,
    summary_ratio_of_middle: float = SUMMARY_RATIO_OF_MIDDLE,
) -> dict:
    if char_per_token <= 0:
        raise ValueError("char_per_token must be > 0")
    if threshold is not None and threshold <= 0:
        raise ValueError("threshold must be > 0 or None")

    p_in, p_cache, p_out = price_of(session["model"])
    rho = float(session["rho"])
    p_eff = (1 - rho) * p_in + rho * p_cache

    live = [Msg("sys", STABLE_PREFIX)]
    ctx = float(STABLE_PREFIX)
    turn = 0
    cost = 0.0
    n_cmp = 0
    proxy_fail = 0.0
    integrity_integral = 0.0
    persist_samples: list[int] = []

    trigger = float("inf") if threshold is None else threshold * WINDOW
    tail_budget = (
        float("inf")
        if threshold is None
        else tail_ratio_of_threshold * threshold * WINDOW
    )

    for role, chars in session["messages"]:
        tok = max(1.0, float(chars) / char_per_token)
        normalized_role = "tool" if role == "tool" else role

        if role == "user":
            turn += 1
            old = [
                msg
                for msg in live[1:]
                if turn - msg.born_turn >= REFERENCE_AGE_TURNS
            ]
            if old:
                weight = sum(ROLE_IMPORTANCE.get(msg.role, 1.0) for msg in old)
                proxy_old = (
                    length_factor(ctx)
                    * sum(
                        msg.retention * ROLE_IMPORTANCE.get(msg.role, 1.0)
                        for msg in old
                    )
                    / weight
                )
                if proxy_old < PROXY_FAILURE_LINE:
                    proxy_fail += reference_probability

        if role == "assistant":
            cost += ctx * p_eff / 1e6
            cost += tok * p_out / 1e6
            if len(live) > 1:
                weight = sum(
                    ROLE_IMPORTANCE.get(msg.role, 1.0) for msg in live[1:]
                )
                integrity_integral += (
                    length_factor(ctx)
                    * sum(
                        msg.retention * ROLE_IMPORTANCE.get(msg.role, 1.0)
                        for msg in live[1:]
                    )
                    / weight
                )

        live.append(Msg(normalized_role, tok, 1.0, turn))
        ctx += tok

        if ctx >= trigger:
            tail_target = min(
                max(0.0, ctx - STABLE_PREFIX),
                tail_budget,
            )
            accumulated = 0.0
            cut = len(live)
            for i in range(len(live) - 1, 0, -1):
                accumulated += live[i].tok
                if accumulated >= tail_target:
                    cut = i
                    break

            middle = live[1:cut]
            middle_tokens = sum(msg.tok for msg in middle)
            if middle_tokens <= 0:
                continue

            n_cmp += 1
            summary_tokens = summary_ratio_of_middle * middle_tokens
            cost += (
                middle_tokens * p_in + summary_tokens * p_out
            ) / 1e6

            for msg in middle:
                if msg.role == "user":
                    persist_samples.append(turn - msg.born_turn)

            weight = sum(ROLE_IMPORTANCE.get(msg.role, 1.0) for msg in middle)
            if weight:
                summary_retention = sum(
                    msg.retention
                    * ROLE_RETENTION.get(msg.role, 0.70)
                    * ROLE_IMPORTANCE.get(msg.role, 1.0)
                    for msg in middle
                ) / weight
            else:
                summary_retention = min(ROLE_RETENTION.values())

            summary = Msg("tool", summary_tokens, summary_retention, turn)
            live = [live[0], summary] + live[cut:]
            ctx = STABLE_PREFIX + summary_tokens + sum(msg.tok for msg in live[2:])

            # Scenario approximation: after a compaction-triggered prompt rebuild,
            # previously cached dynamic bytes may require one uncached prefill.
            # This is intentionally attached to compaction, NOT ordinary mid-session
            # MEMORY.md/USER.md writes (Hermes memory is a frozen session snapshot).
            dynamic = max(0.0, ctx - STABLE_PREFIX)
            cost += dynamic * rho * max(0.0, p_in - p_cache) / 1e6

    if len(live) > 1:
        weight = sum(ROLE_IMPORTANCE.get(msg.role, 1.0) for msg in live[1:])
        proxy_final = (
            length_factor(ctx)
            * sum(
                msg.retention * ROLE_IMPORTANCE.get(msg.role, 1.0)
                for msg in live[1:]
            )
            / weight
        )
    else:
        proxy_final = 1.0

    alive_user_ages = [
        turn - msg.born_turn for msg in live[1:] if msg.role == "user"
    ]
    proxy_persistence = (
        sum(alive_user_ages) + sum(persist_samples)
    ) / max(1, len(alive_user_ages) + len(persist_samples))

    n_assistant = max(
        1, sum(1 for role, _ in session["messages"] if role == "assistant")
    )
    return {
        "cost": cost,
        "n_cmp": n_cmp,
        "proxy_final_recall": proxy_final,
        "proxy_integrity": integrity_integral / n_assistant,
        "proxy_persistence_turns": proxy_persistence,
        "proxy_ux_failures": proxy_fail,
        "turns": max(1, turn),
        "final_context_tokens": ctx,
    }


def aggregate_replay(
    sessions: Sequence[dict],
    char_per_token: float,
    thresholds: Sequence[float | None],
) -> list[dict]:
    rows: list[dict] = []
    base_cost: float | None = None
    for threshold in thresholds:
        aggregate = {
            "cost": 0.0,
            "n_cmp": 0,
            "recall": [],
            "integrity": [],
            "persistence": [],
            "ux": [],
            "quality_turns": 0.0,
        }
        for session in sessions:
            result = replay(session, char_per_token, threshold)
            aggregate["cost"] += result["cost"]
            aggregate["n_cmp"] += result["n_cmp"]
            aggregate["recall"].append(result["proxy_final_recall"])
            aggregate["integrity"].append(result["proxy_integrity"])
            aggregate["persistence"].append(result["proxy_persistence_turns"])
            aggregate["ux"].append(result["proxy_ux_failures"])
            aggregate["quality_turns"] += (
                result["turns"] * result["proxy_integrity"]
            )
        if base_cost is None:
            base_cost = aggregate["cost"]
        n = max(1, len(sessions))
        rows.append(
            {
                "threshold": threshold,
                "cost": aggregate["cost"],
                "saving_vs_no_compression": (
                    0.0
                    if not base_cost
                    else (1.0 - aggregate["cost"] / base_cost) * 100.0
                ),
                "compression_calls": aggregate["n_cmp"],
                "proxy_final_recall": sum(aggregate["recall"]) / n,
                "proxy_integrity": sum(aggregate["integrity"]) / n,
                "proxy_persistence_turns": sum(aggregate["persistence"]) / n,
                "proxy_ux_failures": sum(aggregate["ux"]) / n,
                "cost_per_proxy_quality_turn": aggregate["cost"]
                / max(1e-9, aggregate["quality_turns"]),
            }
        )
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay context-compression policies on portable or local traces."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--fixture", help="portable JSON fixture")
    source.add_argument(
        "--db",
        action="append",
        help="Hermes database as profile=/path/to/state.db; repeat for profiles",
    )
    parser.add_argument(
        "--char-per-token",
        type=float,
        default=None,
        help="override aggregate char/token calibration",
    )
    parser.add_argument(
        "--thresholds",
        default="none,0.08,0.12,0.15,0.20,0.30,0.50",
        help="comma-separated thresholds; include 'none' for no compression",
    )
    return parser


def parse_thresholds(raw: str) -> list[float | None]:
    out: list[float | None] = []
    for item in raw.split(","):
        token = item.strip().lower()
        if not token:
            continue
        out.append(None if token in {"none", "off", "inf"} else float(token))
    if not out:
        raise ValueError("no thresholds supplied")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sessions = (
        load_sessions_from_fixture(args.fixture)
        if args.fixture
        else load_sessions_from_sqlite(args.db)
    )
    if not sessions:
        raise SystemExit("no eligible sessions found")

    ratio = (
        float(args.char_per_token)
        if args.char_per_token is not None
        else calibrate_char_per_token(sessions)
    )
    thresholds = parse_thresholds(args.thresholds)
    rows = aggregate_replay(sessions, ratio, thresholds)

    print(
        f"trace sessions={len(sessions)}; chars/token={ratio:.3f}; "
        "quality columns below are MODEL PROXIES, not measured recall."
    )
    print(
        f"{'theta':>7}{'cost$':>10}{'save':>9}{'cmp':>6}"
        f"{'proxy-rec':>11}{'proxy-int':>11}{'proxy-ux':>10}"
    )
    for row in rows:
        label = "none" if row["threshold"] is None else f"{row['threshold']:.2f}"
        print(
            f"{label:>7}{row['cost']:>10.3f}"
            f"{row['saving_vs_no_compression']:>8.1f}%"
            f"{row['compression_calls']:>6}"
            f"{row['proxy_final_recall']:>11.3f}"
            f"{row['proxy_integrity']:>11.3f}"
            f"{row['proxy_ux_failures']:>10.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
