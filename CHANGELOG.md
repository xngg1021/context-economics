# Changelog

## Unreleased — L6 Adaptive Context Control

### L5 accounting hardening

- receipt ingestion now rejects ambiguous booleans, unknown fields, duplicate run IDs, non-finite/negative accounting fields, impossible cached-token counts and reacquisition counts above retrieval counts;
- policy aggregation now reports token/cache totals, task scores, latency percentiles and failure classes;
- paired treatment/control output now exposes pairing coverage plus missing/duplicate-arm exclusions.

### L6 control plane

- adds `adaptive_control.py` with generic `context_hit / soft_miss / hard_miss / stale_hit` telemetry;
- adds evidence-gated admission/residency with explicit counterfactual-value handling and bounded exact 0/1 packing;
- adds locator-token economics, co-demand speculative prefetch with anti-self-training, bounded vector context-budget feedback, context mutation amplification and immutable shared-base economics;
- adds synthetic L6 fixtures, contract tests and CI smoke coverage;
- preserves the hard boundary between Context Economics `L0-L6` Layers and THM `T0-T3` memory Tiers; no production policy mutation is enabled.

## Unreleased — 2026-09-07 hardening

Base: `main@53d1e9c84025a76a0e6169ca49afdcf68926fc4a`

### Correctness

- separated Hermes `target_ratio` tail-budget semantics from modeled summary size;
- removed the false implication that a finite grid endpoint is a global compression optimum;
- added nonlinear long-context pricing support;
- renamed modeled trace-replay quality outputs to explicit `proxy_*` metrics;
- removed private hard-coded database paths from public replay;
- corrected L4: ordinary mid-session Hermes memory writes do not change the frozen current-session system prompt;
- downgraded `prompt_cache_key` from a cache-hit guarantee to a provider routing/caching hint.

### Research

- added L5 Task Economics & Observability;
- added 2026 evidence on billed cost, reacquisition, runtime reliability, temporal-information loss, and resource-level KV reuse;
- added machine-readable pricing snapshot and provenance rules.

### Reproducibility

- added synthetic trace and run-receipt fixtures;
- added standard-library unit/documentation tests;
- added Python 3.11/3.13 GitHub Actions validation;
- added task-level receipt aggregation and paired treatment-control deltas.

No private `state.db`, raw memory file, API credential, or private conversation content is included.
