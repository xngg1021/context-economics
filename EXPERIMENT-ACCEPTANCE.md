# Experiment analysis and acceptance

> Runtime successor status (2026-09-07): provider adapters are fixture-tested; credential-backed evidence is BLOCKED by runtime authorization. Partial Hermes trace-replay and synthetic retention do not establish runtime-A/B or task-economic results. Production mutation remains disabled. See [REAL-RUNTIME-CAMPAIGN.md](REAL-RUNTIME-CAMPAIGN.md).

`experiment_analysis.py` creates deterministic AB/BA schedules, reports paired
mean, median, p50, p95, range and win/loss/tie counts, and supplies a fixed-seed
paired bootstrap mean interval. Fewer than 20 pairs is labeled
`descriptive-only`; an interval is not production proof.

Hard gates are configurable for paired coverage, success-quality floor,
cost-per-success improvement, reacquisition, p95 wall time, prefetch pollution,
and stale-hit rate. Numerical passing emits `performance_candidate=true`;
formal candidacy additionally requires evidence eligibility (below). There is
no production-controller mutation path.

`controller_calibration.py` performs an offline grid sweep over the L6 shadow
controller's step fractions and deadband. It selects on train tasks and evaluates
once on disjoint holdout task IDs. Overlap fails. Too few tasks yields
`insufficient evidence`. The loss is a normalized budget-vector replay loss, so
it calibrates reproduction of supplied target vectors; it does not establish
that those targets improve task economics.

Evidence progression remains explicit:

| Class | What is established |
|---|---|
| analytic | Formula/schema properties |
| simulation | Synthetic generated behavior |
| trace-replay | Offline recorded telemetry |
| runtime-A/B | Pinned arms executed in a runtime |
| task-economic | Outcome, observed bill and trajectory jointly support the decision |


## Correctness recovery contract

All performance aggregates use the single exact unique paired cohort, including
context metrics filtered to paired runs when wrapped events are available.
Missing and duplicate arms never improve performance gates. Coverage is an
eligibility check, not a performance metric; manifest tasks missing both arms
still count in its denominator. Zero pairs cannot pass.

`performance_candidate` reports numerical checks. `evidence_structurally_eligible` separately
requires a valid pinned manifest/join, sufficient paired coverage, scorer
identity/version/provenance, v2 billing provenance, declared runtime-A/B or
task-economic evidence, explicit real-provider origin and held-out task-set ref.
`evidence_eligible` additionally requires independently verified attestation. This
package has no such verifier, so evidence_eligible and candidate_for_promotion
remain false even when every caller declaration looks valid. A future trusted
control plane must authenticate evidence outside the executor/caller boundary;
there is no caller boolean that enables formal promotion. Default billing must be observed;
only explicit `allow_estimated=True` admits estimates (reported in output).
Synthetic/loopback evidence remains shadow-only. Eligibility is structural
validation of supplied provenance, not authentication of the caller's claims or
proof of statistical superiority. No production mutation is performed.

Metric direction is explicit: success/score higher is better; cost, retry,
reacquisition and latency lower is better. Token/cache/compression/tool counts
are descriptive only and have no win/loss labels. Calibration validates every
Cartesian grid candidate through ControllerPolicy.from_mapping before checking
sample sufficiency. Fractions and deadband are in [0,1], base <= maximum;
invalid values or combinations fail the entire grid instead of being skipped.
