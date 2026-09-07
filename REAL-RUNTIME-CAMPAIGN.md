# Real runtime campaign: staged engineering, evidence blocked

Authoritative predecessor: main `79447daafd365edb228c4864fc630f6265dc6287`,
tree `a3eba4099fb8abd24c686ceb16b2ae34fae7aa66`. PR #5 engineering accepted;
post-merge validate run `34109557962` succeeded. Successor acceptance is tracked
in its PR, not self-certified here.

The new `ProviderExecutor` implements the existing `RuntimeExecutor` seam.
OpenAI chat completions and Anthropic Messages use distinct native parsers and
one canonical collector/normalizer/paired analysis. These adapters are fixture
validated only. No credential-backed provider request was performed in this
workspace: the five named OpenAI/Anthropic/Gemini/Google/Moonshot environment
credentials were absent. No alternative account credentials were harvested.

## Evidence status

| Work | Status | Boundary |
|---|---|---|
| PR #5 pipeline | accepted predecessor | simulation / contract E2E |
| OpenAI/Anthropic executors | fixture tested | real-provider smoke BLOCKED by authorization |
| 2–4 smoke, 10 pilot, 24–40 holdout pairs | preparable | zero actual provider pairs |
| Per-request billing | estimated from immutable pricing snapshot | no observed money / exact billing linkage |
| L6 real calibration | BLOCKED | no real train/holdout outcomes; original replay objective retained |
| Hermes replay | expanded exact-source component trace-replay | budgets, head decay, assembly, summary template and state reset; full compressor outstanding |
| Cache × compression | descriptive four-cell analyzer | no real four-arm campaign or cache-control evidence |
| Content-type retention | 12-category deterministic task-success fixtures | independent solver; no real-model or full-compressor claim |
| Multi-provider generalization | two native fixture parsers | no cross-provider empirical generalization |
| Production mutation | disabled | no automatic budget, cache, model or harness changes |

All runtime campaign success rates, task scores, monetary costs, token/cache
deltas, retries/reacquisition, latency percentiles, context miss/stale metrics
and prefetch results are unavailable until an actual successful campaign.
Performance candidate is not established; authenticated evidence eligibility
and promotion remain false. A local fixture invoking a provider parser is still
synthetic. Task value, latency and failure are not dollar-calibrated in the first
microtask harness; legacy zero cost projections are not measured free services.

## Prepare and execute

Use a clean checkout at the source commit to be measured. Preparation freezes
source SHA/tree, task/policy/pricing/scorer digests, gates and AB/BA ordering.
The generated task bundle is public synthetic text and may be inspected before
execution; raw private task text is not supported by this CLI.

```bash
python runtime_campaign.py prepare --provider openai \
  --revision gpt-4.1-mini-2025-04-14 \
  --pricing pricing/official-20260907-runtime-stage.json \
  --output artifacts/staged-smoke --experiment-id runtime-smoke-UNIQUE \
  --split smoke --count 2
python runtime_campaign.py run \
  --campaign artifacts/staged-smoke/campaign.json --output-root artifacts
```

Supply credentials through the runtime's secret environment facility
(`OPENAI_API_KEY` or `ANTHROPIC_API_KEY`), never chat, CLI arguments, committed
files or artifacts. Endpoints are fixed HTTPS; redirects are refused. Ordinary
PR CI uses fixtures only and needs no credential. No credential workflow is
installed/dispatched without verified protected-environment configuration.
The CLI emits a bounded BLOCKED result rather than printing native exceptions.
Before a paid completion, it queries the official Models endpoint and requires
the exact dated ID; alias substitution is rejected. Git identity subprocesses
receive no provider credential variables, disable fsmonitor and ignore global/system
Git config. The scorer source digest is checked again at execution. Git uses a minimal
environment, trusted executable and explicit module-source cwd, so repository
discovery overrides cannot mask a dirty checkout. Execution regenerates the
canonical 2–40 tasks (holdout at least 24) and requires the reviewed policy;
recomputing caller JSON digests cannot substitute an arbitrary paid workload.

Run smoke first, then a new `--split pilot --count 10` bundle. A formal
`--split holdout --count 24` bundle must follow successful smoke/pilot review;
run one frozen candidate once. Independent splits have distinct task IDs, but
share synthetic templates: this is not evidence about real-user workloads.
This CLI does not enforce a cross-machine campaign registry or certify holdout
novelty. Publication refuses an existing experiment directory; repeated holdout
execution elsewhere remains an operational constraint, not an authenticated gate.

Control retains full history; treatment retains the last four history messages.
This is history bounding, not an LLM compressor. Critical facts are balanced
across early/tail placement within every content type. The question, model,
output cap and exact-match scorer remain fixed. Calls run sequentially in AB/BA
order. A unique per-run prefix reduces cross-arm prefix reuse; cold cache is
unknown, and this is not an official cache disable switch.

A finished campaign adds capabilities, environment, pricing/scorer references,
frozen campaign reference and measurement boundaries to the existing ten-file
artifact set. A SHA-256 index covers all other rendered artifact files. Run ID
and source identity are not a provider attestation. No attestation.json is
manufactured. Caller digests ensure consistency, not independent authenticity.

Executor failure aborts and atomically preserves already captured canonical events,
including request usage yielded before a later scorer/executor failure,
attempted assignments, expected-task denominator and bounded failure status.
Unknown usage/bill is never replaced by a fabricated zero-cost receipt. Such a
campaign has no valid performance aggregate and cannot be promoted. This is
classified partial failure accounting; attempted failures remain in the attempted-run
success denominator, while unattempted runs are explicitly counted. Model-lookup
failures have separate aborted records and zero completion requests. Economic inference remains blocked when failed
requests have no authentic usage/billing receipt. No automatic paid retries.

## Native usage and economics

Request `usage_observations` contains explicit nullable cache-write/read,
service-tier and response-ID observations. Normalization preserves it.
The legacy integer ledger still projects unavailable cache-write tokens to zero;
consult observations/capabilities before interpreting that projection. Missing
cached-read usage blocks estimation rather than assuming a zero cache hit.
Anthropic total input is uncached + cache-read + cache-creation; OpenAI input
already includes cached input. Nonzero Anthropic writes require a future
TTL-aware pricing extension and fail closed in this first text executor.
Unsupported service tiers, tool replies, response model mismatch and unreviewed
billing extensions fail. Non-streaming TTFT is null; wall time ends after full
body receipt. Text and native errors never enter canonical artifacts; native
response identifiers are hashed. Unknown provider fields are ignored, not copied.

`provider_bill_usd` is always estimated here. Only a reviewed per-request money
source or exact authorized billing linkage can add observed billing. The five
additive ledger components remain provider/tool/external/latency/failure;
reacquisition/retry remain overlapping attribution subsets.

## Structural work and pending extensions

`hermes_structural_replay.py --source PATH` verifies the full upstream source
SHA-256 before compiling selected original methods, without upstream imports.
Pinned commit: `f17f18cd11e0dc203e683ab2b77b6a5aafe5afa7`.
At a 200k context window the replay reports lean tail 10k, configured legacy
tail 20k (100k threshold × 0.2), and summary budget 10k. Tool-group boundaries
move backward to the assistant call and forward past its tool result.
`hermes_component_replay.py --source PATH` extends this without copying upstream
code into the repository: exact head protection decays from three messages to
one on repeated compression; supplied-summary assembly reduces seven messages
to five with the system content and tool-call/reply IDs preserved; original
summary template and per-session state reset helpers execute. The supplied
summary is a fixture, not an LLM result. Loaded methods are not all claimed as
executed. Full compress(), summary model, memory/profile injection, host prompt
reconstruction, tool schema placement and provider transport remain outstanding.
Upstream HEAD independently observed as `d9833c5615b80e199a174cd67d90ab430695a972`;
that newer code was not executed. Historical pin and source hash remain intact.
Additional dependency retrieval reached GitHub HTTP 429; no unpinned dependency
or replacement implementation was executed to claim a full replay.

`research_evaluations.py --retention` reports literal critical-fact presence
separately for twelve content types. Full history retains all fixture facts;
bounded tails retain half for each type. This deliberately position-balanced
fixture does not establish a type-specific semantic loss curve or justify a
new type-aware policy. Existing compressor comparison and proxy fitting need
real outcomes. No holdout was used to tune a curve.

`python retention_tasks.py` adds deterministic task success for all 12 types:
path construction, alias resolution, arithmetic, date calculation, exclusions,
constraint/intent decisions, tool correlation, nested IDs, table aggregation,
rejected-choice selection and send-consent state. The solver never receives
expected answers. Each type has n=2: full history 100%, tail-8/tail-4 50%.
`python retention_tasks.py --reacquire` is a separate public exact-lookup experiment:
tails recover to 100% with one reacquisition per type. Provider tokens/bill/latency
remain null. Local byte counts and solver timings are explicitly local metrics.
These fixture outcomes cannot calibrate real_model.py or real L6 policies.

`factorial(rows, expected_task_ids)` requires every expected task in all four
unique cells; reports compression/cache averaged effects and within-task
interaction D−C−B+A. It is descriptive scalar math, not a performed provider
experiment or a causal designation of cache control.

`pricing_refresh.py --snapshot pricing/official-20260907-runtime-stage.json`
validates official source hosts, units, finite prices and freshness; it does not
fetch/rewrite source pages or change historical estimates. Refresh manually to
a new filename after checking official text. Snapshot digest is distinct from
source-page digest. The stage snapshot has selected OpenAI, Anthropic, Gemini
and Kimi rates; it is not an exhaustive provider/tier catalog. Kimi uses CNY;
no inferred exchange rate or legacy USD study conversion is applied.

## Offline external attestation verifier

`attestation_verifier.py --artifacts DIR --attestation FILE` recomputes the
artifact directory digest and manifest/receipt/provider/scorer file digests.
The attestation file lives outside DIR. A verified external reference must bind
the entire attestation to a provisioned independent root, authorized non-producer
attester, valid issuance interval and non-revoked authority. Symlinks and extra
or changed files cannot silently escape the directory digest. There is no caller
trust-root path, verifier callback, boolean switch, key or clock parameter.

The reviewed deployment root registry is EMPTY. Repository-owner self-attestation
is refused. No independent authentication is currently possible. Verification is
a separate offline interface; the economic acceptance gate remains closed and
no production mutation is enabled even by an independently verified reference.

See [FINAL-EVIDENCE-BOUNDARY.md](FINAL-EVIDENCE-BOUNDARY.md) for the current
source/review/evidence closeout and official pricing/billing-source check.

L0–L6 remain measurement/economics/control layers. No THM package, code, docs,
controller or runtime dependency is imported. THM T0–T3 are independent tiers.
