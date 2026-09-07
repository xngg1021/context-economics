# Provenance and reproducibility

Last hardening review: **2026-09-07**

## Repository identity

Hardening base:

- repository: `xngg1021/context-economics`
- base branch: `main`
- base commit: `53d1e9c84025a76a0e6169ca49afdcf68926fc4a`
- hardening branch: `chat/context-economics-hardening-20260907`
- merged hardening commit: `1f7a71b6ab930183c5f05c40065149d3839a6e23`
- L6 successor branch: `chat/context-l6-adaptive-control-20260907`

The hardening is forward-only: no rebase, reset or force-push is required.

## Evidence classes

| Class | Meaning |
|---|---|
| `runtime-measured` | directly observed in a real runtime/bill/trace |
| `source-code` | confirmed from a named source-code revision |
| `provider-doc` | official provider documentation, pricing or API contract |
| `paper-result` | result reported by a publication under its experiment |
| `model-proxy` | derived from this repository's assumptions/simulation |

A claim may use multiple classes. `model-proxy` must never be renamed to `runtime-measured`.

## Hermes source boundary

The 2026-09-07 hardening used current upstream Hermes documentation/code surfaced at code-search revision:

`2d7799275046ef5cd48f4a11dbff9c49cddee9ee`

Relevant observed upstream paths included:

- `website/docs/user-guide/which-file-does-what.md`
- `website/docs/user-guide/features/memory.md`
- `website/docs/developer-guide/context-compression-and-caching.md`
- `website/docs/developer-guide/prompt-assembly.md`
- `agent/system_prompt.py`
- `agent/context_compressor.py`
- `agent/conversation_compression.py`
- `tools/memory_tool.py`

Important: this records the source snapshot used for this review. It does **not** claim every historical local Hermes run used that same revision.

## Historical local measurements

The original 2026-08-19 study used private local Hermes profile/session data.

Public repository contents intentionally exclude:

- private `state.db` files;
- raw conversation messages;
- private `MEMORY.md` / `USER.md`;
- API keys;
- account identifiers.

Published historical measurements (for example profile memory character counts and aggregate session counts) are retained as anonymized derived observations.

`fixtures/sample_sessions.json` is synthetic and is the only fixture used by public CI.

## Price data

Provider pricing and cache semantics are fast-decaying external data.

Rules:

1. every machine-readable snapshot must include `observed_at`;
2. live product decisions must re-check provider official docs;
3. historical simulations may pin an old snapshot for reproducibility;
4. pricing changes do not retroactively rewrite old experiment results;
5. statements such as "all models use 0.1x cache read" are forbidden when provider-specific exceptions exist.

See `pricing-snapshot.json`.

## Papers added in 2026-09-07 hardening

- arXiv:2607.12161 — Token Reduction Is Not Cost Reduction
- arXiv:2608.16370 — What Does Context Compression Cost an Agent?
- arXiv:2608.01056 — Control Under Compression
- arXiv:2608.11775 — The Sleeping Agent
- arXiv:2608.19662 — ReCache
- arXiv:2608.00902 — Practical Online KV Cache Compaction for LLM Agents
- Megiddo and Modha, FAST 2003 — ARC: A Self-Tuning, Low Overhead Replacement Cache
- Einziger, Friedman and Manes, arXiv:1512.00727 / ACM TOCS — TinyLFU and W-TinyLFU

These are used for the claims explicitly described in `README.md` and `L5-task-economics.md`; their reported numbers remain scoped to their own experimental settings.

Provider cache semantics were rechecked on 2026-09-07 against the official
OpenAI prompt-caching guide, Anthropic prompt-caching documentation, and Gemini
context-caching/pricing documentation. The unified runtime schema consequently
preserves provider-native metadata and does not normalize a routing hint into a
cache hit, a cache write into invalidation, or a provider-specific storage fee
into a universal field.

## Runtime evidence completion boundary

The deterministic loopback HTTP fixture executes socket I/O and validates the
full adapter -> collector -> normalizer path. Its billing source is a fixture and
its status is `estimated`. Current public evidence is therefore analytic,
simulation, and contract E2E. Credential-backed provider traces, observed bills,
pinned runtime A/B, and task-economic promotion remain unverified.

## L6 implementation evidence boundary

`adaptive_control.py` is a deterministic standard-library **reference/control implementation**. Its public fixtures are synthetic. Current claims are limited to analytic, simulation and contract behavior:

- event/schema validation;
- miss taxonomy and explicit avoidability;
- evidence-gated admission/residency;
- locator/prefetch/budget arithmetic;
- bounded exact packing;
- anti-self-training prefetch semantics;
- mutation/share accounting.

It has not yet been promoted to `runtime-A/B` or `task-economic` evidence. In particular, the repository does not claim that any proposed context budget, prefetch or admission policy improves a real provider/harness workload until version-pinned held-out tasks produce the corresponding L5 receipts.

Context Economics `L0-L6` and THM `T0-T3` are independent taxonomies. Cross-repository measurements may be exchanged, but neither hierarchy is rewritten as the other.

## Runtime experiment contract boundary

`runtime_experiment.py` joins L5 receipts and L6 events under exact experiment pins. The public `runtime_*` fixtures are synthetic and validate only schema/alignment behavior.

`declared_evidence_class` is producer-supplied metadata, not independently verified evidence. `runtime_design_structurally_ready=true` means the declared runtime design has complete arms/run-linked telemetry and an eligible assignment method; it does not prove provider contact, provider billing, randomization, scoring validity or causality. The validator therefore never emits a causal-success claim.

Real runtime promotion still requires external provenance for the version-pinned provider/model/harness/runtime/task execution. See `RUNTIME-EXPERIMENT-CONTRACT.md`.

## Reproduction

Public/portable:

```bash
python -m unittest discover -s tests -v
python model.py
python real_model.py --fixture fixtures/sample_sessions.json
python task_economics.py --receipts fixtures/run_receipts.json --control no-compression --treatment aggressive-compression
python adaptive_control.py telemetry --events fixtures/context_access_events.json
python adaptive_control.py budget --state fixtures/context_budget_state.json
python runtime_experiment.py --manifest fixtures/runtime_experiment_manifest.json --receipts fixtures/runtime_ab_receipts.json --events fixtures/runtime_context_events.json --require-complete
```

Private trace replay:

```bash
python real_model.py --db profile=/path/to/state.db
```

The latter is a trace replay. Unless the task outcome itself is re-executed, it is not a runtime A/B.

## Change discipline

When modifying formulas or model semantics:

- update unit tests first or in the same commit;
- update README numeric claims in the same commit;
- do not silently repurpose a parameter name from upstream software;
- keep provider prices out of timeless "laws";
- add exact version/provenance when a claim depends on implementation details.

## PR #4 correctness recovery successor

Authoritative predecessor main: `1c9afadac48f32bfbd34df5c148d17702d60aaf6`,
tree `e61ce919b36f815cd57ddc10650bab6892fc6f53`. Successor branch:
`work/context-runtime-correctness-recovery-20260907`, PR #5.
Predecessor architecture is retained; correctness acceptance was pending.

Recovery covers all six review defects plus TTFT, metric direction, evidence
eligibility, complete experiment orchestration and run wall-time bounds.
Public evidence remains simulation / contract E2E. Local socket billing is
estimated from a synthetic price, and the local arms are identical. No real
provider credential run, runtime-A/B superiority or task-economic claim is made.
Final review, CI IDs, successor SHA/tree and merge/main verification are recorded
in PR #5's closeout; this file does not self-certify a future commit or review.


Successor independent review identified three further issues, now forward-fixed:
common credential keys, unauthenticated self-declared origins, and partial
artifact publication. Structural evidence readiness remains available; formal
promotion is disabled without an independent attestation verifier. Engineering
correctness acceptance does not enable a production promotion path.

## Real-runtime successor after PR #5

Remote main independently confirmed as `79447daafd365edb228c4864fc630f6265dc6287`, tree `a3eba4099fb8abd24c686ceb16b2ae34fae7aa66`. Prior provenance is retained. New engineering, pricing sources and partial structural evidence boundaries are recorded in REAL-RUNTIME-CAMPAIGN.md; final PR/CI/review identity belongs in the successor closeout. No credential-backed runtime evidence or observed billing was obtained.
