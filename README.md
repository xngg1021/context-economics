# Context Economics

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md)

**Context Economics is a reproducible measurement, experiment, and bounded-control framework for the economics of LLM/agent context.**

> Token reduction is not cost reduction. The unit that matters is the successful task.

Current repository version: **0.6.1**. Version history lives in [`CHANGELOG.md`](CHANGELOG.md); versioning policy lives in [`VERSIONING.md`](VERSIONING.md). The homepage describes the current product/research surface only.

## What problem does this repository solve?

Long-running agents repeatedly carry, cache, compress, retrieve, rebuild, and sometimes lose context. A policy that saves input tokens can still be worse overall if it increases retries, retrieval, latency, failures, cache writes, or task errors.

Context Economics therefore treats context as an operating asset rather than a raw token count. The core decision is to compare three classes of cost:

```text
Carry Cost
  input bill / cache read-write-storage / prefill / latency / mutation amplification

Transformation Cost
  compression / summarization / indexing / serialization / quality loss introduced by transformation

Absence Cost
  reacquisition / retry / tool calls / latency / failure / wrong answer / violated constraints
```

A context action is economically justified only when its total expected task cost is lower than the alternatives while preserving an explicit quality floor.

## Research and engineering model

The repository is organized as seven independent analysis/control layers:

| Layer | Scope |
| --- | --- |
| **L0 Pricing** | Provider input/output pricing, cached reads, cache writes/storage, long-context tiers, service classes |
| **L1 Serving & KV** | Prefill, KV/prefix reuse, cache stability, serving-side reuse and resource economics |
| **L2 Compression** | Truncation, summarization, externalization, RAG, content-type retention and transformation loss |
| **L3 Harness** | Prompt assembly, tool schemas, compaction, subagents, repo maps, scheduling and reacquisition |
| **L4 Memory & Profile** | Persistent context, frozen session snapshots, profile scope, residency cost, source/version semantics |
| **L5 Task Economics & Observability** | Provider bill, tools, external cost, latency, failure, task success, `cost_per_success` |
| **L6 Adaptive Context Control** | Admission, residency, locators, prefetch, bounded vector budgets, mutation amplification, shared immutable base |

Context Economics `L0–L6` are **Layers**. They are not THM `T0–T3` memory **Tiers**. The two repositories are independent and exchange only measurements/contracts where their research questions overlap.

## What is implemented today?

### Deterministic models and task economics

- `model.py` provides reproducible cost and sensitivity models, including nonlinear pricing support.
- `real_model.py` replays public fixtures or user-supplied traces while labeling modeled outputs as proxies rather than measured quality.
- `task_economics.py` aggregates run receipts into success, provider bill, additive cost, latency, retries, retrieval/reacquisition, and `cost_per_success`.
- Finite optimization grids are reported only as the **`lowest-cost point in THIS GRID`**, never as a global optimum.

### Runtime instrumentation and experiment contracts

- `context_runtime.py` defines strict request/tool/context/compression/outcome event schemas, collection, validation, redaction, and normalization.
- `runtime_experiment.py` joins L5 receipts and L6 context telemetry under exact run/task/policy identity and version pins.
- `experiment_runner.py` executes paired-fixed or counterbalanced AB/BA experiments and publishes an atomic artifact set.
- `experiment_analysis.py` provides paired descriptive statistics, deterministic bootstrap intervals, coverage checks, and candidate gates.
- `controller_calibration.py` keeps calibration and holdout evaluation separated.

### Shadow adaptive control

`adaptive_control.py` implements deterministic, advisory-only surfaces for:

- `context_hit / soft_miss / hard_miss / stale_hit / planned_retrieval / prefetch` telemetry;
- miss-cost and counterfactual-value accounting;
- bounded exact 0/1 admission/residency packing;
- locator-token economics;
- anti-self-training speculative prefetch metrics;
- bounded vector budget feedback;
- context mutation amplification;
- immutable shared-base + scoped-delta economics.

No production setting is automatically mutated.

### Real-provider campaign engineering

Version 0.6.x adds a secured execution path for real provider experiments:

- native OpenAI Chat Completions and Anthropic Messages parsers/executors;
- frozen public-task smoke / pilot / train / holdout campaign bundles;
- exact dated model preflight;
- pricing, task, policy, scorer, source-commit, and source-tree binding;
- a trusted isolated credentialed bootstrap that validates source and campaign identity before delivering a provider key;
- immutable aborted-campaign records and validated partial telemetry;
- an offline external-reference attestation verifier.

The trusted credentialed bootstrap currently supports the reviewed POSIX deployment path and fails closed on unsupported platforms rather than weakening source-integrity checks.

### Hermes component replay and retention fixtures

The repository includes exact-source, hash-pinned replay of selected Hermes compressor components and deterministic content-retention/reacquisition fixtures. These are useful for structural analysis, but they are **not** a certified full Hermes `compress()` run and are not evidence of real model quality.

## Current evidence status

The distinction between engineering capability and empirical evidence is deliberate.

| Question | Current status |
| --- | --- |
| Deterministic cost / accounting / contract tests | **Implemented and CI-validated** |
| Local HTTP contract E2E | **Implemented** |
| OpenAI / Anthropic native adapters | **Fixture-tested** |
| Credential-backed provider smoke / pilot / holdout | **Not yet executed in the public evidence set** |
| Request-level observed monetary bill | **Not established**; estimator output remains labeled estimated |
| Real L6 train/holdout calibration | **Not established** |
| Real cache × compression factorial | **Not established** |
| Full Hermes compressor + host prompt replay | **Incomplete** |
| Independent external trust root | **Not provisioned** |
| `evidence_eligible` / promotion | **False** |
| Automatic production controller mutation | **Disabled** |

The current public evidence ceiling is simulation / deterministic contract E2E plus exact-source component trace-replay. For the full boundary, see [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) and [`PROVENANCE.md`](PROVENANCE.md).

## Quick start

The core remains standard-library oriented.

```bash
python model.py
python real_model.py --fixture fixtures/sample_sessions.json

python task_economics.py \
  --receipts fixtures/run_receipts.json \
  --control no-compression \
  --treatment aggressive-compression

python experiment_runner.py --local-demo --output-root artifacts
```

Inspect the version-pinned joint contract:

```bash
python runtime_experiment.py \
  --manifest artifacts/local-e2e/manifest.json \
  --receipts artifacts/local-e2e/l5-receipts.json \
  --events artifacts/local-e2e/l6-events.json \
  --require-complete
```

Prepare a real-provider smoke campaign without putting credentials in the command line or repository:

```bash
python runtime_campaign.py prepare \
  --provider openai \
  --revision gpt-4.1-mini-2025-04-14 \
  --pricing pricing/official-20260907-runtime-stage.json \
  --output artifacts/staged-smoke \
  --experiment-id runtime-smoke-UNIQUE \
  --split smoke \
  --count 2
```

Credentialed execution must follow the reviewed trusted-bootstrap procedure in [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md). Do not paste API keys into issues, commands, committed files, or experiment artifacts.

## Experiment discipline

A useful comparison keeps the task, model, revision, harness, scorer, and task set fixed while changing one context policy at a time.

For a formal campaign the repository expects, where applicable:

- exact control/treatment pairing;
- counterbalanced AB/BA ordering;
- a frozen policy and task set;
- calibration data separated from held-out acceptance data;
- explicit `observed` versus `estimated` billing status;
- task success/score reported alongside cost;
- retries, reacquisition, latency, and failures retained rather than silently dropped;
- no promotion from caller-declared evidence alone.

`performance_candidate`, structural evidence readiness, independently authenticated evidence, and production promotion are separate states.

## Core objective

The general objective is not “minimize tokens” but maximize task value net of operating cost:

```text
J(policy) =
    E[task_value]
  - E[provider/cache bill
      + tool cost
      + external cost
      + latency cost
      + failure cost]
```

Reacquisition and retry costs may be tracked as overlapping attribution subsets; they are not silently double-counted as new additive ledger items.

If task value cannot be monetized, report at least:

```text
success_rate
 task_score
 provider_bill
 total_cost
 cost_per_success
 p50/p95/p99 wall latency
 input/output/cached tokens
 tool/retrieval/reacquisition/retry counts
 compression count
 context miss/stale metrics
 prefetch coverage/pollution
```

## Repository guide

| Document / module | Purpose |
| --- | --- |
| [`CHANGELOG.md`](CHANGELOG.md) | Version-by-version history; implementation chronology lives here, not on the homepage |
| [`VERSIONING.md`](VERSIONING.md) | Version policy and milestone mapping |
| [`PROVENANCE.md`](PROVENANCE.md) | Evidence classes, source identity, and research provenance |
| [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) | Exact 0.6.x closeout boundary and remaining empirical gaps |
| [`RUNTIME-INSTRUMENTATION.md`](RUNTIME-INSTRUMENTATION.md) | Canonical runtime telemetry schema and collection semantics |
| [`RUNTIME-EXPERIMENT-CONTRACT.md`](RUNTIME-EXPERIMENT-CONTRACT.md) | Version-pinned experiment join and completeness contract |
| [`EXPERIMENT-ACCEPTANCE.md`](EXPERIMENT-ACCEPTANCE.md) | Statistical/evidence acceptance boundaries |
| [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md) | Staged provider execution procedure and security boundaries |
| [`RESEARCH-ADDENDUM-2026-09-07.md`](RESEARCH-ADDENDUM-2026-09-07.md) | Dated research/source updates without rewriting historical snapshots |
| `L0-pricing.md` … `L6-adaptive-context-control.md` | Layer-specific research and design |
| `context_runtime.py` | Runtime event collection/normalization |
| `task_economics.py` | Task-level cost ledger and aggregation |
| `adaptive_control.py` | Deterministic shadow control surfaces |
| `experiment_runner.py` | Paired experiment orchestration |
| `runtime_campaign.py` | Frozen real-provider campaign preparation/execution |
| `trusted_runtime_bootstrap.py` | Reviewed isolated credential boundary |

## Project boundaries

Context Economics is not a memory database, a compressor implementation, or an agent harness. It measures and evaluates context policies across those systems.

The repository may study Hermes, Claude Code, Codex, Gemini CLI, OpenAI Agents, LangGraph, THM, or other systems as external runtimes or policies. Research coverage does not mean a live adapter exists unless the corresponding code and validation explicitly say so.

Ordinary mid-session Hermes memory writes persist to disk but do not rewrite the current **frozen** session system-prompt snapshot; cache effects must be observed from actual serialized runtime behavior rather than inferred from the file write alone.

## Validation

The accepted 0.6.0 engineering milestone passed the full Python 3.11 / 3.13 validation matrix after merge. Current docs/productization changes remain subject to the same repository CI before acceptance.

## Version history

Only the current release line belongs on this homepage. Detailed chronology, PR mapping, review findings, fixes, and evidence-boundary changes are maintained in [`CHANGELOG.md`](CHANGELOG.md).

Current version: **0.6.1**.

---

Context Economics is research software. Before 1.0, public contracts and evidence interfaces may still evolve; version numbers never substitute for evidence class.
