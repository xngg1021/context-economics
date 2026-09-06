# Changelog

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
