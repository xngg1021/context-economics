# Runtime instrumentation contract

Observed at: 2026-09-07 UTC. Schema: `context_runtime.py`, version 1.

The runtime pipeline is:

```text
provider/harness -> redacted adapter event -> strict Collector
 -> normalized run bundle -> L5 receipt + L6 context events
 -> version-pinned experiment join
```

Five event envelopes are accepted: `request`, `tool`, `context`, `compression`,
and `outcome`. Every envelope carries a globally unique event ID plus exact
run/task/policy identity and a timezone-aware timestamp. Unknown fields fail;
booleans are not integers; non-finite numbers fail; request sequence indexes
must be unique and increasing; cached plus uncached input must equal total input;
and every run must retain one provider/model/revision pin.

Request telemetry distinguishes `billing_status=observed|estimated` and records
the bill source. Cache routing hints remain hints. A cache break is recorded only
as observed false/true/unknown; compression or a memory write does not imply it.
Provider-specific metadata is namespaced and rejects credentials, authorization,
cookies, account IDs, prompts, and completions.

`runtime_http.py` is a minimal OpenAI-compatible HTTP adapter. CI runs it against
a deterministic loopback HTTP server, exercising a real request/response path
without credentials. This proves the adapter/capture/normalization contract. It
does not prove provider billing, production cache behavior, or model quality.

```bash
python context_runtime.py --input raw-events.json --output normalized.json
python -m unittest tests.test_runtime_http -v
```

Future OpenAI, Anthropic, Gemini, Kimi, Hermes, and coding-agent adapters should
map native receipts into these semantics without pretending every provider has
cache-write tokens, storage fees, cache keys, or identical long-context tiers.


Cost ledger v2 adds provider_bill_usd, tool_cost_usd, external_cost_usd,
latency_cost_usd and failure_cost_usd exactly once. Reacquisition/retry costs
are overlapping attribution subsets and are never added again. External costs
must be independent charges absent from provider/tool costs. Estimated provider
billing retains its label; the historical observed_cost_usd property name is
not a claim that an estimated bill was observed. Explicit ledger v1 preserves
legacy additive semantics for replay only. Unversioned nonzero classified costs
fail with a migration error; zero-classification old receipts remain readable.
Public fixtures explicitly migrate their legacy independent charges to external
costs. Runtime normalization always emits v2.

Metadata validation recursively copies JSON mappings/lists/tuples, rejecting
case-insensitive explicit private keys with hyphens/underscores normalized.
Limits are 16 levels, 4096 nodes, and 64 KiB per payload. Values must be JSON-safe
and finite. Returned bundles do not alias collector state. This is a forbidden-key
policy, not semantic detection of secrets hidden under arbitrary safe names;
adapters must still emit redacted identifiers and metadata.

Tool categories are retrieval/filesystem/search/database/web/compute/action/other.
`is_retrieval` controls accounting independently of category. For old envelopes,
reacquisition automatically implies retrieval; explicitly setting it false for
reacquisition fails. All normalized L5 receipts are reparsed before returning.

HTTP support is non-streaming text chat-completions (`message.content`) plus
legacy `choices[0].text`; one choice and prompt/completion usage are required.
Standard extra response fields are ignored, never copied into telemetry. Cached
usage accepts prompt_tokens_details.cached_tokens or cached_prompt_tokens;
conflicts fail. Missing cache-write usage is marked unavailable in metadata,
with zero as the additive token projection only. Without endpoint billing a
caller-supplied estimator must return amount_usd and a pinned source reference;
its result is always labeled estimated. Missing both fails actionably.
Non-streaming TTFT is unknown/null. request_wall_time_ms measures full body
receipt; it is not first-token latency. Streaming and tool-call answers are
outside this minimal adapter's support.

Run timestamps must be ordered, request/tool events cannot precede completion,
and outcome is last. Run wall time spans the earliest request/tool start through
the outcome, including post-request tool/scoring time. Request wall time remains
a separate full-response transport measurement. Seeded stdlib invariant tests
exercise monetary conservation, retrieval/cache bounds and L5/L6 round trips.
