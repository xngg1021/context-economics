# Experiment analysis and acceptance

`experiment_analysis.py` creates deterministic AB/BA schedules, reports paired
mean, median, p50, p95, range and win/loss/tie counts, and supplies a fixed-seed
paired bootstrap mean interval. Fewer than 20 pairs is labeled
`descriptive-only`; an interval is not production proof.

Hard gates are configurable for paired coverage, success-quality floor,
cost-per-success improvement, reacquisition, p95 wall time, prefetch pollution,
and stale-hit rate. Passing emits only `candidate_for_promotion=true`; there is
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

