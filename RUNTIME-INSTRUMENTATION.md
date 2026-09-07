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

