# Changelog

All notable Context Economics repository milestones are recorded here by version. The homepage describes the current system only; detailed implementation chronology, review findings, forward fixes, and evidence-boundary changes belong in this file and the linked provenance documents.

## 0.6.1 — 2026-09-08 — README productization and localization

Documentation-only patch on top of the accepted 0.6.0 engineering milestone.

### Changed

- Replaced the debug/history-heavy root README with a current-facing product/research homepage.
- Added complete maintained homepages for English, Simplified Chinese, Traditional Chinese, Japanese, Korean, German, French, and Spanish.
- Added a common language switcher to every homepage.
- Moved historical implementation chronology out of the homepage and into versioned release notes.
- Added `VERSION` and `VERSIONING.md` with an explicit pre-1.0 milestone policy.
- Kept the current evidence boundary unchanged: no real provider A/B, observed request-level bill, real L6 calibration, or production promotion is created by this documentation patch.

## 0.6.0 — 2026-09-08 — Secure real-runtime campaign engineering

Accepted engineering anchor: merge `2aef1e7043273637adff1453d22dafc83d5e0e94` (PR #6), tree `539d135173e47396698bae692559aee057ef8f90`.

### Added

- Native fixture-tested OpenAI Chat Completions and Anthropic Messages provider executors.
- Frozen smoke / pilot / train / holdout campaign preparation with counterbalanced AB/BA support.
- Exact model preflight, task/policy/scorer/pricing/source identity binding, and immutable aborted-campaign artifacts.
- Trusted isolated credentialed bootstrap that validates exact reviewed source and campaign identity before provider credential delivery.
- Offline external-reference attestation verifier with no preconfigured self-trust root.
- Deterministic 12-type content-retention/reacquisition tasks and evidence artifacts.
- Expanded exact-source Hermes component replay for selected compressor helpers.
- Official pricing snapshot refresh/check path.

### Security / correctness closeout

Eight P1 findings discovered during code/security review were forward-fixed, covering:

- provider credential inheritance into Git subprocesses;
- Git repository-location override spoofing;
- rehashed workload expansion beyond the reviewed paid-task bound;
- local module/bytecode execution before source verification;
- rehashed model/pricing/campaign substitution;
- current-directory/PATH Git executable hijacking;
- noncanonical/private partial payload retention;
- Git replacement-ref source substitution.

Final exact-head review completed clean on feature head `ca3153982a6d0a80e055ee8ad149edf0b55bab40`; all review threads were resolved. Final PR CI `34142353602` and post-merge main CI `34142898117` passed Python 3.11 and 3.13.

### Evidence boundary

- Actual credential-backed completion requests: **0** in the public evidence set.
- Actual real task pairs: **0**.
- Request-level observed monetary bill: **not established**.
- L6 real calibration: **not run**.
- Real cache × compression factorial: **not run**.
- Full Hermes `compress()` / host prompt replay: **incomplete**.
- `evidence_eligible=false`; `candidate_for_promotion=false`; production mutation disabled.

See [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) and [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md).

## 0.5.0 — 2026-09-07 — Runtime correctness recovery and full experiment runner

Accepted anchor: merge `79447daafd365edb228c4864fc630f6265dc6287` (PR #5), tree `a3eba4099fb8abd24c686ceb16b2ae34fae7aa66`.

### Added / hardened

- Correct non-overlapping cost ledger semantics: provider/tool/external/latency/failure remain additive while reacquisition/retry are overlapping attribution subsets.
- Recursive metadata/privacy validation and retrieval/timestamp invariants.
- Standard text chat-completions compatibility with explicit estimated billing and unknown non-streaming TTFT.
- Exact paired cohort gates and separation of performance candidate from evidence eligibility.
- Validated train/holdout calibration and metric-specific direction semantics.
- Full paired-fixed / counterbalanced AB/BA experiment runner with atomic publication of the contract artifact set.
- Seeded invariant/adversarial regression coverage.

### Review closeout

PR #4’s six original correctness findings plus seven successor findings were forward-fixed. Final Code Review completed clean on `b2fce60fc107f656026ddc3f89b4254eb5e04292`. Post-merge validate run `34109557962` succeeded on Python 3.11 and 3.13.

### Evidence boundary

Public evidence remained simulation / deterministic local runtime transport contract E2E. No credential-backed runtime A/B, observed provider bill, task-economic promotion, or production controller improvement was claimed.

## 0.4.0 — 2026-09-07 — Runtime telemetry, paired analysis, and adaptive calibration

Accepted anchor: merge `1c9afadac48f32bfbd34df5c148d17702d60aaf6` (PR #4).

### Added

- Strict versioned request/tool/context/compression/outcome telemetry schema and redacting collector.
- L5/L6 runtime normalization and provider-agnostic HTTP adapter contract E2E.
- Counterbalanced AB/BA scheduling, paired descriptive statistics, deterministic bootstrap intervals, and candidate gates.
- Offline L6 parameter sweep with disjoint train/holdout behavior.

### Evidence boundary

The runtime pipeline was engineering-complete for local deterministic HTTP contract testing only. No real provider runtime, observed provider bill, or task-economic result was established.

## 0.3.0 — 2026-09-07 — Version-pinned runtime experiment contract

Accepted anchor: merge `1979c22840559162897ed7d1e48ea5bd2a9153a1` (PR #3).

### Added

- `runtime_experiment.py` for exact L5 receipt + L6 telemetry joins by run/task/policy identity.
- Manifest pins for provider, model/revision, harness revision, repository SHA, runtime environment, task set, pricing snapshot, and policy bundle.
- Fail-closed completeness checks for missing/duplicate arms and orphan/cross-arm context events.
- Explicit timezone-aware timing/token/cache/cost/failure receipt fields.
- Producer-declared evidence class retained strictly as metadata rather than causal proof.

### Evidence boundary

Synthetic contract fixtures only; no real provider runtime-A/B claim.

## 0.2.0 — 2026-09-07 — L6 Adaptive Context Control

Accepted anchor: merge `029b375a21ad81f8d062cf33e37348a82f34b4eb` (PR #2).

### Added

- `context_hit / soft_miss / hard_miss / stale_hit / planned_retrieval / prefetch` telemetry.
- Explicit avoidability and miss-cost accounting.
- Evidence-gated admission/residency and counterfactual-value protection.
- Bounded exact 0/1 packing.
- Locator-token economics.
- Anti-self-training co-demand speculative prefetch metrics.
- Bounded vector budget feedback across history/retrieval/memory/tools/repo-map/prefetch/compression retention.
- Context mutation amplification and immutable shared-base/private-delta economics.

### Boundary

L0–L6 Context Economics Layers remained explicitly independent from THM T0–T3 memory Tiers. All control output remained shadow/advisory.

## 0.1.0 — 2026-09-07 — L5 Task Economics and evidence hardening

Accepted anchor: merge `1f7a71b6ab930183c5f05c40065149d3839a6e23` (PR #1).

### Correctness

- Separated Hermes `target_ratio` tail-budget semantics from modeled summary size.
- Removed the false implication that a finite-grid endpoint is a global compression optimum.
- Added nonlinear long-context pricing support.
- Renamed modeled replay quality outputs to explicit `proxy_*` metrics.
- Removed private hard-coded database paths from public replay.
- Corrected L4 frozen-memory behavior: ordinary mid-session Hermes memory writes do not change the current frozen system prompt.
- Downgraded `prompt_cache_key` from a cache-hit guarantee to a routing/caching hint.

### Added

- L5 Task Economics & Observability.
- Machine-readable pricing snapshot and provenance/evidence classes.
- Synthetic trace/run-receipt fixtures and portable CI.
- Task-level receipt aggregation, paired policy deltas, and `cost_per_success`.

## Pre-version research snapshot — 2026-08-19

The original L0–L3 research materials on pricing, serving/KV, compression, and harness behavior predate the formal repository version line. They are preserved as dated research snapshots rather than retroactively renamed as a software release.
