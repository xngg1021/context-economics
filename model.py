# -*- coding: utf-8 -*-
"""
Context Economics — deterministic cost model.

This module intentionally separates:
1) pricing mechanics,
2) a generic compression policy,
3) Hermes-compatible tail-budget semantics.

It is a cost model, not a task-quality model. Any quality/reliability term belongs
in a higher-level task-economics evaluation (see L5-task-economics.md).

All prices are USD per 1M tokens unless stated otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Iterable, Optional


@dataclass(frozen=True)
class Pricing:
    name: str
    p_in: float
    p_cache: float
    p_out: float
    cache_write_multiplier: float = 1.0
    cache_storage_per_mtok_hour: float = 0.0
    long_context_threshold: Optional[int] = None
    long_input_multiplier: float = 1.0
    long_output_multiplier: float = 1.0

    def request_rates(self, prompt_tokens: float) -> tuple[float, float, float]:
        """Return uncached-input, cached-input, output rates for this request.

        Some providers apply nonlinear long-context pricing to the whole request.
        When no tier is configured, the base rates are returned.
        """
        if (
            self.long_context_threshold is not None
            and prompt_tokens > self.long_context_threshold
        ):
            return (
                self.p_in * self.long_input_multiplier,
                self.p_cache * self.long_input_multiplier,
                self.p_out * self.long_output_multiplier,
            )
        return self.p_in, self.p_cache, self.p_out

    def effective_input_rate(self, rho: float, prompt_tokens: float = 0.0) -> float:
        """Effective input rate for cache-hit share rho."""
        if not 0.0 <= rho <= 1.0:
            raise ValueError("rho must be in [0, 1]")
        p_in, p_cache, _ = self.request_rates(prompt_tokens)
        return (1.0 - rho) * p_in + rho * p_cache


# Historical/local study configuration retained for reproducibility.
KIMI_K3 = Pricing("kimi-k3-study-snapshot", 3.00, 0.30, 15.00)
DEEPSEEK = Pricing("deepseek-study-snapshot", 0.28, 0.006, 0.42)
GEMINI_FL = Pricing("gemini-flash-study-snapshot", 0.30, 0.075, 2.50)

# Example of a nonlinear pricing schedule. Snapshot is documented in
# pricing-snapshot.json; do not treat this constant as a live quote.
OPENAI_GPT56_SOL = Pricing(
    "gpt-5.6-sol-2026-09-07",
    4.00,
    0.40,
    20.00,
    cache_write_multiplier=1.25,
    long_context_threshold=272_000,
    long_input_multiplier=2.0,
    long_output_multiplier=1.5,
)


@dataclass(frozen=True)
class SessionShape:
    window: int = 1_000_000
    stable_prefix: int = 14_000
    user_tokens: int = 300
    assistant_tokens: int = 800
    tool_tokens: int = 4_000
    turns: int = 120

    @property
    def growth_per_turn(self) -> int:
        return self.user_tokens + self.assistant_tokens + self.tool_tokens


@dataclass(frozen=True)
class CompressionPolicy:
    threshold: float
    tail_ratio_of_threshold: float = 0.20
    summary_ratio_of_middle: float = 0.20

    def __post_init__(self) -> None:
        if self.threshold <= 0:
            raise ValueError("threshold must be > 0")
        if not 0 <= self.tail_ratio_of_threshold <= 1:
            raise ValueError("tail_ratio_of_threshold must be in [0, 1]")
        if not 0 <= self.summary_ratio_of_middle <= 1:
            raise ValueError("summary_ratio_of_middle must be in [0, 1]")

    def trigger_tokens(self, window: int) -> float:
        return self.threshold * window

    def tail_budget_tokens(self, window: int) -> float:
        """Hermes-style legacy tail semantics: target_ratio × threshold × window."""
        return self.tail_ratio_of_threshold * self.threshold * window


@dataclass(frozen=True)
class SimResult:
    threshold: float
    total_cost: float
    input_cost: float
    output_cost: float
    compression_cost: float
    cache_break_cost: float
    compression_calls: int
    final_context_tokens: float
    cost_per_turn: float


def _request_cost(
    price: Pricing,
    prompt_tokens: float,
    rho: float,
    output_tokens: float,
) -> tuple[float, float]:
    p_in, p_cache, p_out = price.request_rates(prompt_tokens)
    input_rate = (1.0 - rho) * p_in + rho * p_cache
    return prompt_tokens * input_rate / 1e6, output_tokens * p_out / 1e6


def simulate(
    price: Pricing,
    shape: SessionShape,
    policy: Optional[CompressionPolicy],
    rho: float,
    *,
    cache_break_on_compression: bool = True,
) -> SimResult:
    """Simulate repeated-context billing under an abstract compressor.

    The compression trigger and recent-tail budget use Hermes' ratio semantics:
      trigger = threshold × context_window
      recent_tail_budget = target_ratio × threshold × context_window

    The summary-size ratio is deliberately separate. Hermes' real summary budget
    is implementation/version dependent; callers must not reuse target_ratio as
    a synonym for summary size.

    cache_break_on_compression models one conservative re-prefill opportunity
    cost after a prompt rebuild. It is a scenario switch, not a universal law.
    """
    if not 0 <= rho <= 1:
        raise ValueError("rho must be in [0, 1]")

    ctx = float(shape.stable_prefix)
    cost_in = cost_out = cost_cmp = cost_break = 0.0
    n_cmp = 0

    for _ in range(shape.turns):
        ctx += shape.user_tokens
        c_in, c_out = _request_cost(
            price, ctx, rho=rho, output_tokens=shape.assistant_tokens
        )
        cost_in += c_in
        cost_out += c_out
        ctx += shape.assistant_tokens + shape.tool_tokens

        if policy is not None and ctx >= policy.trigger_tokens(shape.window):
            tail = min(
                max(0.0, ctx - shape.stable_prefix),
                policy.tail_budget_tokens(shape.window),
            )
            middle = max(0.0, ctx - shape.stable_prefix - tail)

            if middle <= 0:
                continue

            p_in, _, p_out = price.request_rates(middle)
            summary_tokens = policy.summary_ratio_of_middle * middle
            cost_cmp += (middle * p_in + summary_tokens * p_out) / 1e6

            new_ctx = shape.stable_prefix + summary_tokens + tail

            if cache_break_on_compression and rho > 0:
                # Scenario approximation: if a prompt rebuild invalidates the
                # previously cached dynamic portion, charge the delta between
                # uncached and cached input rates once on that portion.
                p_in2, p_cache2, _ = price.request_rates(new_ctx)
                dynamic = max(0.0, new_ctx - shape.stable_prefix)
                cost_break += dynamic * rho * max(0.0, p_in2 - p_cache2) / 1e6

            ctx = new_ctx
            n_cmp += 1

    total = cost_in + cost_out + cost_cmp + cost_break
    return SimResult(
        threshold=inf if policy is None else policy.threshold,
        total_cost=total,
        input_cost=cost_in,
        output_cost=cost_out,
        compression_cost=cost_cmp,
        cache_break_cost=cost_break,
        compression_calls=n_cmp,
        final_context_tokens=ctx,
        cost_per_turn=total / shape.turns,
    )


def breakeven_turns(
    price: Pricing,
    rho: float,
    summary_ratio: float,
    *,
    prompt_tokens: float = 0.0,
    one_time_extra_cost_per_middle_token: float = 0.0,
) -> float:
    """Break-even turns for compressing middle region M by summary_ratio.

    M cancels only under the constant-rate, fixed-rho assumptions represented by
    this function. For nonlinear pricing tiers or changing cache hit rates, use
    a full simulation instead of interpreting this as a global "law".
    """
    if not 0 <= summary_ratio < 1:
        raise ValueError("summary_ratio must be in [0, 1)")
    p_eff = price.effective_input_rate(rho, prompt_tokens)
    _, _, p_out = price.request_rates(prompt_tokens)
    p_in, _, _ = price.request_rates(prompt_tokens)
    once = p_in + summary_ratio * p_out + one_time_extra_cost_per_middle_token
    per_turn_save = (1.0 - summary_ratio) * p_eff
    if per_turn_save <= 0:
        return inf
    return once / per_turn_save


def grid_search(
    price: Pricing,
    shape: SessionShape,
    thresholds: Iterable[float],
    rho: float,
    *,
    tail_ratio_of_threshold: float = 0.20,
    summary_ratio_of_middle: float = 0.20,
    cache_break_on_compression: bool = True,
) -> list[SimResult]:
    """Evaluate a caller-specified grid.

    This intentionally does not label the smallest tested point as a global
    optimum. A cost-only model often prefers increasingly aggressive
    compression; a meaningful optimum requires quality/reliability costs.
    """
    out: list[SimResult] = []
    for theta in thresholds:
        policy = CompressionPolicy(
            threshold=theta,
            tail_ratio_of_threshold=tail_ratio_of_threshold,
            summary_ratio_of_middle=summary_ratio_of_middle,
        )
        out.append(
            simulate(
                price,
                shape,
                policy,
                rho,
                cache_break_on_compression=cache_break_on_compression,
            )
        )
    return out


def main() -> None:
    shape = SessionShape()
    print("=" * 88)
    print("Context Economics deterministic cost model")
    print("=" * 88)
    print(
        "Important: this output optimizes billed-token mechanics only. "
        "It does not estimate task quality."
    )

    for rho in (0.0, 0.85):
        base = simulate(KIMI_K3, shape, None, rho)
        grid = grid_search(
            KIMI_K3,
            shape,
            thresholds=(0.05, 0.08, 0.12, 0.15, 0.20, 0.30, 0.50),
            rho=rho,
        )
        print(f"\n--- kimi study snapshot, cache-hit share rho={rho:.2f} ---")
        print(
            f"{'theta':>7}{'cost$':>11}{'saving':>10}{'compress':>10}"
            f"{'break$':>10}{'final ctx':>12}"
        )
        print(
            f"{'none':>7}{base.total_cost:>11.3f}{0:>9.1f}%"
            f"{base.compression_calls:>10}{base.cache_break_cost:>10.3f}"
            f"{base.final_context_tokens:>12.0f}"
        )
        for res in grid:
            saving = (1 - res.total_cost / base.total_cost) * 100
            print(
                f"{res.threshold:>7.2f}{res.total_cost:>11.3f}{saving:>9.1f}%"
                f"{res.compression_calls:>10}{res.cache_break_cost:>10.3f}"
                f"{res.final_context_tokens:>12.0f}"
            )
        lowest = min(grid, key=lambda r: r.total_cost)
        print(
            f"lowest-cost point in THIS GRID: theta={lowest.threshold:.2f}; "
            "do not interpret as a global optimum without a quality cost."
        )

    print("\nBreak-even examples (constant-rate local approximation, r=0.2):")
    for rho in (0.0, 0.85, 0.95):
        print(f"  rho={rho:.2f}: {breakeven_turns(KIMI_K3, rho, 0.2):.2f} turns")


if __name__ == "__main__":
    main()
