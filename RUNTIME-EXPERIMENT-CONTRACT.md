# Version-Pinned Runtime Experiment Contract

The upstream raw-to-normalized contract is executable in `context_runtime.py`;
paired analysis and promotion-candidate gates are in `experiment_analysis.py`.
The local HTTP E2E uses an estimated fixture bill and therefore does not upgrade
this repository to real provider runtime evidence.

> Added: 2026-09-07. Executable contract: `runtime_experiment.py`.
> Current public fixtures are **synthetic contract fixtures**. This file does not claim that a real provider/harness A/B has already been executed.

## 1. Purpose

L5 records task economics and L6 records context-access/control telemetry. A real policy comparison is only interpretable if both streams refer to the same run, task, arm and runtime identity. This contract makes that join explicit.

The validator consumes three files:

```text
manifest
  -> experiment identity + provider/model/harness/repository/task/policy pins

run receipts
  -> L5 success, billed tokens/cost, tool/retrieval/reacquisition/retry/latency

context events
  -> L6 hit/miss/stale/planned-retrieval/prefetch telemetry linked to run_id
```

## 2. Version pins

Every manifest must explicitly pin:

```text
provider
model
model_revision
harness_revision
repository_commit
runtime_environment_ref
task_set_ref
pricing_snapshot_ref
policy_bundle_ref
control_policy
treatment_policy
expected_task_ids
```

`repository_commit` must be an exact lowercase 40-character Git SHA. Other references are opaque versioned identifiers because different runtimes may use image digests, fixture IDs, release IDs or content-addressed manifests rather than Git.

Each receipt must repeat provider/model/model_revision/harness_revision. A mismatch fails instead of being averaged into the experiment. `started_at` and `ended_at` must be timezone-aware ISO-8601 timestamps and `ended_at >= started_at`.

## 3. Runtime receipts are stricter than generic L5 fixtures

For this contract, fields that generic `RunReceipt` can default are required to be explicit. The runtime receipt must include:

```text
run/task/policy/success/task_score
provider/model/model_revision/harness_revision
started_at/ended_at
input/cached-input/cache-write/output tokens
provider bill
tool/reacquisition/retry/latency/failure cost components
tool/retrieval/reacquisition/retry/compression counts
TTFT/wall time
failure_class
```

Zero is allowed when it is an observed or deliberately assigned zero. Missing is not silently converted to zero by the runtime-experiment loader.

## 4. L6 telemetry must be run-linked

Every context event adds:

```text
run_id
policy_id
```

to the normal L6 event contract. The validator checks that:

- `run_id` exists in the receipt set;
- event `policy_id` equals the receipt arm;
- event `task_id` equals the receipt task;
- event IDs remain globally unique.

An orphan or cross-arm event fails.

## 5. Structural completeness

For every `expected_task_id`, the contract expects exactly one control and one treatment run. It separately reports:

```text
missing_arms
duplicate_arms
runs_without_context_events
paired_coverage
```

`--require-complete` turns any of these structural gaps into a hard failure.

## 6. Evidence-class boundary

The manifest contains `declared_evidence_class`:

```text
synthetic-contract
trace-replay
runtime-A/B
```

This value is a **declaration by the experiment producer**. The parser cannot prove that a provider was contacted, that billing came from a provider invoice, that assignment was randomized, or that task scoring is trustworthy.

Likewise:

```text
runtime_design_structurally_ready = true
```

means only that the manifest declares `runtime-A/B`, the pairing is structurally complete, and the assignment method is one of `paired-fixed / counterbalanced / randomized`. It is not a causal certificate. Every report therefore includes:

```text
causal_claim = "not inferred by this validator"
```

## 7. Joint report

A successful join returns both evidence streams without collapsing them into one synthetic score:

```text
by_policy_task_economics
by_policy_context_telemetry
paired_task_report
```

This preserves the distinction between "the agent missed context" and "the task failed/cost more". Causal interpretation remains an experimental-design step.

If a policy has zero successes, L5 correctly represents `cost_per_success` as infinity internally. The runtime-contract CLI serializes non-finite derived values as JSON `null` rather than emitting non-standard `Infinity` or crashing.

## 8. Public synthetic reproduction

```bash
python runtime_experiment.py \
  --manifest fixtures/runtime_experiment_manifest.json \
  --receipts fixtures/runtime_ab_receipts.json \
  --events fixtures/runtime_context_events.json \
  --require-complete
```

The three public files are labeled synthetic and exist only to test the contract. Their numeric deltas are not product/runtime benchmark results.

## 9. Promotion rule

A future result may be described as a real `runtime-A/B` only when the run producer supplies real version-pinned runtime records and provenance. A stronger `task-economic` claim additionally requires interpretable real task outcomes plus billed cost and interaction/retry/latency accounting.

Passing this parser is necessary data hygiene for that experiment; it is not sufficient evidence that the treatment is better.

## Executable experiment runner

`python experiment_runner.py --local-demo --output-root artifacts` executes both
arms for each task, alternating AB/BA over actual loopback HTTP. `--assignment
paired-fixed` runs AB throughout. The injectable RuntimeExecutor owns provider
integration; the runner receives only canonical redacted events and does not
manage credentials. Both arms must match scheduled identities and manifest pins.
Local executors cannot declare runtime-A/B or task-economic evidence.

A completed directory contains manifest.json, schedule.json, raw-telemetry.json,
normalized.json, l5-receipts.json, l6-events.json, joint-report.json,
paired-statistics.json, acceptance.json and provenance.json. Schedule retains
task order, arm order and run/task/policy IDs. Existing directories are refused.
Private artifacts are ignored by git; the local CLI emits only synthetic data.
The joint report requires complete L5/L6 evidence for every run before writing.
Provenance includes all manifest pins, scorer/billing sources, assignment and
bootstrap seed. Wall timings are measured and vary across executions; replaying
the same recorded receipts yields identical statistics and acceptance. The two
local arms are intentionally identical, proving orchestration rather than gains.


Review hardening: artifact files are first written to a private same-parent
staging directory and then published by atomic directory rename. Ordinary write
failures clean staging and permit retry; hard process termination may leave an
unpublished staging directory but no final output or stale lock. This is atomic
visibility, not a promise of power-loss durability/fsync. Completed output
is nonempty and is never replaced by concurrent publishers.

Executor evidence_origin is an informational declaration only. Structural
eligibility does not authenticate provider, scorer or billing evidence. Formal
promotion is disabled until an independent trusted attestation verifier exists.
