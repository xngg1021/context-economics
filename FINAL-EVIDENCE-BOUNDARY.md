# PR #6 final evidence boundary — 2026-09-07

This is an engineering successor, not real-runtime evidence completion.
Real execution is **BLOCKED by missing authorized runtime credentials**.
The broader requested full Hermes compressor replay also remains incomplete.
Do not label the entire real-evidence closeout complete or promote a policy.

## Identity and review

Repository: `xngg1021/context-economics`; PR #6;
branch `work/context-real-runtime-evidence-20260907`.
Predecessor main: `79447daafd365edb228c4864fc630f6265dc6287`,
tree `a3eba4099fb8abd24c686ceb16b2ae34fae7aa66`.
Entry feature head: `36f3262215570cd7170731fb03a7b873983d233c`,
tree `38e0b2eefefc60a65a8adde3776295b77ba032a6`.
Both were independently verified against remote. No shared history rewritten.

Code/evidence source: `eb83c41e992be44c11c84027aed9d139b04447ea`,
tree `5dd963eab3a49e46733c793ca7c9a783830195b3`.
Seven semantic successor commits add offline attestation, model preflight and
partial failures, deterministic content tasks, Hermes components, Git credential
isolation, scorer/preflight failure binding and finalization failure retention.
Local and connector commits differ in authoring identity; corresponding trees
were checked equal. Final documentation HEAD/tree, review outcome and final CI
are recorded in the PR body after publication, avoiding a self-referential SHA.

Entry Code Review completed clean on 36f3262. Renewed independent security
request returned a P1 on Git subprocess credential inheritance (thread
`PRRT_kwDOUQclMc6f9d5V`); fixed in `f6fd49479fdbde2213e54cc0ee98a0800ebd28c1`
with regression. The follow-up review found two additional P1s: inherited Git repository-location
overrides and caller-rehashed tasks exceeding the prepared workload bound. Both
are forward-fixed: Git uses a minimal environment/trusted executable and explicit
source-directory cwd; run reconstructs 2–40 canonical tasks (holdout at least 24)
and the exact reviewed policy before network. A real two-checkout regression and
rehashed workload/policy mutations cover both findings.
A further P1 identified local module/ignored bytecode execution before validation.
The successor adds a trusted isolated bootstrap, credential-free validation and
imports, exact Git-blob snapshots and post-import pipe delivery. Five process
regressions cover dirty source, forged timestamp-valid pyc, nonisolated invocation
caller attempts to authorize an unreviewed commit, and consistently rehashed
model/price substitution against an independently pinned campaign digest. The operator-provided
reviewed commit and installed launcher/Python are explicit trust prerequisites.
New review requests target successor code; a request is not a
clean security result. CI 34132270992 passed entry HEAD; 34137446215 passed
successor de160a4, both Python 3.11/3.13. All 18 local workflow validation commands
passed after the finalization fix; suite now contains 146 tests. Final exact-head
review/CI and unresolved-thread status must be checked in PR #6 before merge.
Independent security completion remains a hard merge gate. No merge claimed.

## Secure runtime entrypoint

The original direct credentialed CLI is no longer supported. Prepare without
credentials, then execute through a trusted installed copy of
`trusted_runtime_bootstrap.py` with `python -I -S`, `--source`,
`--expected-commit REVIEWED_SHA`, `--expected-campaign-digest REVIEWED_DIGEST`,
`--campaign` and `--output-root`.
The reviewed SHA and campaign digest must come from the trusted deployment/operator,
not from the mutable campaign file at runtime. The independent campaign digest
closes the fifth review P1: rehashed provider/model/pricing substitutions cannot
change the authorized spend plan before credential selection/delivery.
The launcher never imports repository modules: it validates clean source and
exports Git blobs without credentials, starts an isolated secret-free child,
imports validated snapshot modules and only then delivers the selected key via
stdin. Ignored pyc and local startup modules cannot enter that snapshot.
The launcher/OS/Python remain the explicitly trusted computing base; this does
not authenticate provider evidence or defend a compromised host/launcher.

## Completed bounded engineering

- Exact dated model lookup through fixed official HTTPS endpoints before paid
  completion requests; alias mismatch and redirects refused. Holdout preparation
  requires at least 24 pairs. Scorer source is rechecked at run time.
- Git identity subprocesses omit the five provider secret variables, disable
  filesystem monitors and ignore global/system Git configuration. All repository
  discovery overrides are absent, Git runs in the module source directory and
  run revalidates canonical task count/content and the reviewed policy. Parent secrets
  remain available solely to the provider request code.
- Failed runs retain already validated request events, classified errors,
  attempted-run success denominator and unattempted counts. Model preflight and
  post-collection finalization failures are retained separately. No guessed bill.
- Offline attestation verifies complete artifact bytes and exact evidence files
  against a provisioned external reference, with self-attestation, revocation,
  stale-time, missing-root and digest-mismatch rejection. Shipped roots are empty;
  no caller boolean/root file creates trust. Acceptance remains disabled.
- Deterministic content operations use an independent solver that receives no
  expected answer. Exact lookup/reacquisition is a separate experiment.
- Historical pinned Hermes replay extends to decaying head protection, supplied
  summary assembly, summary template and state reset helpers. Source hash checked
  before AST; no upstream import/module initializer runs.

## Observations and missing real evidence

| Field | Result |
|---|---|
| Credential presence | OPENAI / ANTHROPIC / GEMINI / GOOGLE / MOONSHOT API key variables absent |
| Staged providers | OpenAI and Anthropic; both fixture-tested only |
| Staged exact revisions | gpt-4.1-mini-2025-04-14; claude-haiku-4-5-20251001 |
| Actual authenticated completion requests / task pairs | 0 / 0 |
| Actual Models API calls | 0; public documentation is not account-level availability |
| Real smoke / pilot / holdout IDs | none; preparation is not execution |
| Control / treatment | full history / last 4 history messages; counterbalanced AB/BA |
| Success rate / task score / cost per success | unavailable for real runtime |
| Provider money / billing status | unavailable; implemented calculator is estimated only |
| Input / output / cached / cache-write tokens | unavailable for real runtime |
| Wall latency p50/p95/p99 / TTFT | unavailable; nonstreaming TTFT remains null |
| Real reacquisition / retry / failures / context metrics | unavailable; zero requests does not mean a measured 0% failure rate |
| L6 calibration / optional task-economic objective | not run; no real train data, original objective retained, shadow only |
| Cache × compression main effects / interaction | unavailable; no real cached usage or compressor campaign |
| real_model fitted proxy / residual / uncertainty | unavailable; no real outcomes; original proxy unchanged |
| Second provider / coding-agent harness | not executed; first real API campaign prerequisite unmet |
| performance_candidate | not evaluated for real data |
| evidence_structurally_eligible | not established for real data |
| evidence_eligible / candidate_for_promotion | false / false |
| production mutation / THM touched | false / NO |

## Per-content-type deterministic outcomes

These are **fixture** results, not model retention probabilities. Each type has
2 tasks, one early and one late. Provider tokens, bill and latency are null.
Local solver timing and UTF-8 byte counts are present in the JSON records and
must not be relabeled provider token usage or runtime latency.

| Content type | n | Full success | Tail-8 success | Tail-4 success | Tail + lookup success | Reacquisitions per tail policy |
|---|---:|---:|---:|---:|---:|---:|
| path | 2 | 100% | 50% | 50% | 100% | 1 |
| identifier | 2 | 100% | 50% | 50% | 100% | 1 |
| number | 2 | 100% | 50% | 50% | 100% | 1 |
| date | 2 | 100% | 50% | 50% | 100% | 1 |
| negation | 2 | 100% | 50% | 50% | 100% | 1 |
| constraint | 2 | 100% | 50% | 50% | 100% | 1 |
| intent | 2 | 100% | 50% | 50% | 100% | 1 |
| tool_protocol | 2 | 100% | 50% | 50% | 100% | 1 |
| structured_id | 2 | 100% | 50% | 50% | 100% | 1 |
| retrievable_output | 2 | 100% | 50% | 50% | 100% | 1 |
| reasoning_state | 2 | 100% | 50% | 50% | 100% | 1 |
| social_intent | 2 | 100% | 50% | 50% | 100% | 1 |

Failure mode is required-record-missing. Literal presence is 100% full and 50%
for each bounded tail. The arithmetic/decision scorer establishes deterministic
operations, not general language understanding. Actual Hermes compression has
not been added as a measured arm. No fixture data trains a real retention curve.

Records: [retention](evidence/closeout-20260907/retention-outcomes.json),
[reacquisition](evidence/closeout-20260907/reacquisition-outcomes.json),
[Hermes](evidence/closeout-20260907/hermes-components.json).

## Hermes boundary

Upstream current HEAD was independently observed as
`d9833c5615b80e199a174cd67d90ab430695a972`. Preserve historical replay at
`f17f18cd11e0dc203e683ab2b77b6a5aafe5afa7`, source SHA256
`454bf3779ca3ad8c5b07f7a093eeb5f13f77ddec4a64ffc18b2168989813bec0`.
At context 200000, lean/legacy tail budgets are 10000/20000, summary budget
10000. Protected head goes 3→1 across repeated compression; supplied-summary
assembly goes 7→5 messages, preserving system content and tool pair IDs.
Summary template and session compaction/micro state reset helpers execute.

Full `compress()`, actual summary generation, memory/profile injection, host
prompt reconstruction, tool schema placement, host session boundary and provider
transport are NOT completed. Upstream orphan sanitizer needs an additional
runtime helper; dependency retrieval encountered GitHub HTTP 429. The existing
component loader deliberately refuses those imports. No substitute summarizer,
free compression bill, measured token ratio or full-compressor claim is made.

## Official pricing and billing check

Rechecked 2026-09-07. Snapshot
`pricing/official-20260907-runtime-stage.json` remains immutable, digest
`7a9d94955f246255f76ecdd6d17393f3d812dd62d31680386def3d52e31c93d0`.

[OpenAI GPT-4.1 Mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
still lists the dated revision and USD/MTok input 0.40, cached input 0.10,
output 1.60. The runner's 200k ceiling is a conservative execution cap, not the
model's advertised 1,047,576 context limit. Automatic cache state is not controlled
by this harness; explicit cache write price/TTL remain unavailable here.

[Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)
lists Haiku 4.5 input 1.00, output 5.00, read 0.10, 5-minute write 1.25 and
1-hour write 2.00 USD/MTok. First-party standard pricing only; the executor refuses
nonzero cache writes until a TTL-aware adapter is reviewed. No changed rate was
found, so no historical snapshot or experiment price was rewritten.

[OpenAI Costs](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/costs)
returns time-bucketed monetary totals with project/key/line-item dimensions.
[Anthropic Cost Report](https://platform.claude.com/docs/en/api/admin/cost_report/retrieve)
returns daily monetary reporting grouped by description/workspace. Neither
reviewed schema supplies an exact individual request-ID-to-cost mapping.
This is a schema-based assessment, not a live authorized ledger fetch. Without
credentials or exact linkage, no observed-billing adapter or allocation of a
bucket total to individual requests is justified. `task-economic` always rejects
estimated bills, including with `allow_estimated=True`.

## Remaining gates

1. Exact final-head Code Review, independent Security Review and green CI; no
   unresolved P1/P2. Existing security finding is fixed but must be re-reviewed.
2. Authorized runtime provider credential for smoke → pilot → frozen 24+ holdout.
3. Reviewed request-level observed monetary evidence and independent trust root
   for any task-economic eligibility.
4. Complete pinned Hermes dependency/host replay, actual compressor summary cost
   and outcomes; real train data for L6/retention calibration and observable cache
   usage for the factorial. Second-provider and coding-agent experiments follow
   the first real provider campaign.

No automatic production change or THM write is authorized by a good experiment.

Final review follow-up: Git execution now requires the fixed trusted POSIX installation `/usr/bin/git`; Windows and installations without that path fail closed. No PATH, current-directory or os.defpath executable search remains. Event payload validation is shared by collection and normalization, so malformed/private fields are rejected before entering retained telemetry, including aborted campaigns; prior valid receipts survive. Two regressions cover poisoned executable search and invalid partial payload persistence.

Replacement-ref follow-up: every Git identity/export command uses `--no-replace-objects`, and export names the already-checked tree. A process regression creates a malicious replacement commit ref after identity verification, immediately before export, and confirms the approved source still executes.
