# Context Economics 0.6.x — current evidence boundary

This document is the current post-merge evidence boundary for the Context Economics 0.6.x line. It separates **accepted engineering capability** from **empirical claims that have not yet been established**.

The 0.6.1 documentation/productization patch does not change this evidence level.

## Accepted engineering identity

- Repository: `xngg1021/context-economics`
- 0.6.0 feature head: `ca3153982a6d0a80e055ee8ad149edf0b55bab40`
- Feature tree: `539d135173e47396698bae692559aee057ef8f90`
- 0.6.0 merge: `2aef1e7043273637adff1453d22dafc83d5e0e94`
- Merge parents: `79447daafd365edb228c4864fc630f6265dc6287`, `ca3153982a6d0a80e055ee8ad149edf0b55bab40`
- Final exact-head Code/Security review: completed clean on `ca3153982a`
- Review findings: eight P1 findings were forward-fixed; zero unresolved review threads remained at merge
- Final PR validation: `34142353602`, Python 3.11 / 3.13 success
- Post-merge main validation: `34142898117`, Python 3.11 / 3.13 success

Detailed review chronology belongs in [`CHANGELOG.md`](CHANGELOG.md), [`PROVENANCE.md`](PROVENANCE.md), and PR #6 rather than the homepage.

## Strongest evidence actually reached

The strongest public evidence currently reached by Context Economics is:

```text
simulation
+ deterministic local runtime transport contract E2E
+ exact-source component trace-replay
```

The repository has **not** yet reached credential-backed runtime-A/B or task-economic evidence for a production context policy.

## Completed bounded engineering

The 0.6.0 engineering milestone includes:

- strict request/tool/context/compression/outcome runtime telemetry;
- redacting collection and canonical normalization;
- L5 task-economics receipts and L6 context-access projections;
- paired-fixed and counterbalanced AB/BA experiment orchestration;
- deterministic bootstrap and explicit acceptance gates;
- train/holdout-separated shadow-controller calibration infrastructure;
- native fixture-tested OpenAI Chat Completions and Anthropic Messages executors;
- frozen smoke / pilot / train / holdout campaign preparation;
- exact dated model preflight;
- task, policy, scorer, pricing, source-commit, and source-tree binding;
- trusted isolated credentialed bootstrap that validates source and campaign identity before provider-key delivery;
- immutable partial/aborted-campaign records with validated telemetry only;
- offline external-reference attestation verification with no shipped trust root;
- deterministic content-retention/reacquisition fixtures;
- selected exact-source Hermes compressor component replay;
- immutable official pricing snapshots and refresh checks.

No item in this list implies that a real provider campaign has already been executed.

## Real-runtime evidence status

| Field | Current result |
| --- | --- |
| Authorized provider credential present in the accepted public run | No |
| Actual authenticated completion requests | `0` |
| Actual provider Models API requests | `0` |
| Actual paired real tasks | `0` |
| Real smoke / pilot / holdout campaign | Not executed |
| Real success rate / task score | Unavailable |
| Request-level observed monetary bill | Not established |
| Input / output / cached / cache-write tokens from a real accepted run | Unavailable |
| Real p50 / p95 / p99 wall latency | Unavailable |
| Non-streaming TTFT | Remains `null` unless actually observable |
| Real reacquisition / retry / failure / context metrics | Unavailable |
| Real L6 calibration | Not run |
| Real cache × compression factorial | Not run |
| Second-provider empirical generalization | Not run |
| Coding-agent / multi-harness empirical campaign | Not run |

Zero requests do **not** imply a measured 0% failure rate or a zero provider bill.

## Billing boundary

The repository can estimate provider cost from an immutable pricing snapshot. Such values remain explicitly labeled `estimated`.

The reviewed OpenAI and Anthropic aggregate cost-reporting schemas did not establish an exact individual request-ID-to-money linkage suitable for request-level observed billing in the accepted campaign path. Therefore:

- no bucket total is allocated back to individual requests as if it were observed;
- `task-economic` evidence always rejects estimated billing, including when runtime-A/B tooling permits estimates for a weaker evidence class;
- a future observed-billing adapter must provide reviewed, exact provenance for the request-to-money linkage.

## Deterministic content fixtures

The accepted fixture suite contains 12 content types:

```text
path
identifier
number
date
negation
constraint
intent
tool_protocol
structured_id
retrievable_output
reasoning_state
social_intent
```

Each type has two deterministic tasks, one with the critical fact early and one late.

| Policy | Deterministic success |
| --- | ---: |
| Full history | 100% |
| Tail-8 | 50% |
| Tail-4 | 50% |
| Bounded tail + exact lookup/reacquisition | 100% |

These results establish only the structural effect of deterministic history bounding and exact reacquisition in public fixtures. They are **not** LLM retention probabilities, provider-runtime accuracy, or task-economic superiority.

Records:

- [`evidence/closeout-20260907/retention-outcomes.json`](evidence/closeout-20260907/retention-outcomes.json)
- [`evidence/closeout-20260907/reacquisition-outcomes.json`](evidence/closeout-20260907/reacquisition-outcomes.json)
- [`evidence/closeout-20260907/hermes-components.json`](evidence/closeout-20260907/hermes-components.json)

## Hermes boundary

Historical exact-source component replay remains pinned to Hermes commit:

`f17f18cd11e0dc203e683ab2b77b6a5aafe5afa7`

with source SHA-256:

`454bf3779ca3ad8c5b07f7a093eeb5f13f77ddec4a64ffc18b2168989813bec0`

The accepted replay covers selected budget properties and helper behavior including head protection, supplied-summary assembly, summary-template structure, and compaction-state reset helpers.

It does **not** certify:

- full `compress()` execution;
- actual LLM summary generation;
- summary-model provider bill;
- complete memory/profile injection;
- host prompt reconstruction;
- full tool-schema placement;
- host session-boundary behavior;
- provider transport behavior.

No substitute summarizer or proxy token ratio is relabeled as a real Hermes compression result.

## Attestation boundary

`attestation_verifier.py` implements an offline verification interface for externally authenticated references and artifact digests. The shipped trust-root set is deliberately empty.

Therefore internal artifact consistency alone does not create independent trust, and caller declarations cannot make evidence eligible.

## Promotion state

```text
performance_candidate: not established from real provider data
evidence_structurally_eligible: not established for a real campaign
evidence_eligible: false
candidate_for_promotion: false
production_mutation: false
```

The L6 controller remains shadow/advisory only.

## Remaining empirical gates

The next evidence upgrades require real data, not more relabeling of fixtures:

1. authorized provider credential and reviewed smoke execution;
2. pilot campaign followed by a frozen 24+ paired holdout campaign;
3. real task outcomes, usage, cache observations, latency, retries, reacquisition, and failures;
4. exact request-level observed monetary evidence if task-economic eligibility is sought;
5. independent trust root / attestation path for authenticated evidence eligibility;
6. real train data for L6 calibration and a disjoint holdout evaluation;
7. observable cache semantics for a real cache × compression factorial;
8. fuller pinned Hermes compressor/host replay if Hermes-specific compression claims are pursued;
9. second-provider and multi-harness campaigns only after the first real provider campaign is established.

A successful experiment may produce a reviewed recommendation. It does not automatically authorize a production configuration change.
