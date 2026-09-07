# -*- coding: utf-8 -*-
"""Minimal OpenAI-compatible HTTP adapter used by the deterministic E2E.

It records only usage, timing, billing fields supplied by the endpoint, and a
small allowlisted metadata namespace.  It deliberately does not persist prompt
or completion payloads.
"""
from __future__ import annotations

import json
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Mapping, Callable

import context_runtime as rt


def _now() -> str: return datetime.now(timezone.utc).isoformat()


class OpenAICompatibleHTTPAdapter:
    adapter_id = "openai-compatible-http-v1"

    def adapt(self, native_event: Mapping[str, object]):
        # The HTTP harness constructs an already-redacted canonical envelope.
        yield dict(native_event)


def run_request(*, url: str, run_id: str, task_id: str, policy_id: str,
                model: str, model_revision: str, sequence_index: int,
                input_text: str, timeout: float = 10.0,
                pricing_estimator: Callable[[Mapping[str, int]], Mapping[str, object]] | None = None) -> tuple[dict, str]:
    """Call an endpoint and return a redacted request event plus answer text."""
    started = _now(); before = time.perf_counter()
    body = json.dumps({"model": model, "messages": [{"role":"user","content":input_text}]}).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    elapsed = (time.perf_counter()-before)*1000; ended = _now()
    if not isinstance(payload, dict):
        raise rt.TelemetryError("provider response must be an object")
    # Standard endpoints may include object/created/system_fingerprint/etc.
    # Only explicitly extracted fields enter public telemetry.
    usage = payload.get("usage"); billing = payload.get("billing")
    if not isinstance(usage, dict):
        raise rt.TelemetryError("provider response requires a usage object")
    prompt = rt._int(usage.get("prompt_tokens"), "prompt_tokens")
    completion = rt._int(usage.get("completion_tokens"), "completion_tokens")
    details = usage.get("prompt_tokens_details") or {}
    if not isinstance(details, dict):
        raise rt.TelemetryError("prompt_tokens_details must be an object")
    native_cached = usage.get("cached_prompt_tokens")
    standard_cached = details.get("cached_tokens")
    if native_cached is not None and standard_cached is not None and native_cached != standard_cached:
        raise rt.TelemetryError("conflicting cached token counts")
    cached = rt._int(native_cached if native_cached is not None else standard_cached if standard_cached is not None else 0, "cached_tokens")
    if cached > prompt:
        raise rt.TelemetryError("cached tokens exceed prompt tokens")
    write = rt._int(usage.get("cache_write_tokens", 0), "cache_write_tokens")
    if billing is None:
        if pricing_estimator is None:
            raise rt.TelemetryError("no observed billing: supply pricing_estimator with a pinned snapshot source")
        estimate = pricing_estimator({"input_tokens":prompt, "cached_input_tokens":cached,
                                      "output_tokens":completion, "cache_write_tokens":write})
        if not isinstance(estimate, Mapping):
            raise rt.TelemetryError("pricing_estimator must return amount_usd and source")
        billing = {"amount_usd":estimate.get("amount_usd"), "source":estimate.get("source"), "status":"estimated"}
    if not isinstance(billing, dict):
        raise rt.TelemetryError("billing must be an object")
    amount = rt._num(billing.get("amount_usd"), "billing.amount_usd")
    source = rt._text(billing.get("source"), "billing.source")
    status = billing.get("status")
    if status not in {"observed", "estimated"}:
        raise rt.TelemetryError("billing.status must be observed or estimated")
    choices = payload.get("choices")
    if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict):
        raise rt.TelemetryError("provider response requires one choice")
    message = choices[0].get("message")
    answer = message.get("content") if isinstance(message,dict) else choices[0].get("text")
    if not isinstance(answer,str):
        raise rt.TelemetryError("choice message.content (or legacy text) must be a string")
    event = {
        "event_id":"req-"+uuid.uuid4().hex, "event_kind":"request", "run_id":run_id,
        "task_id":task_id, "policy_id":policy_id, "occurred_at":ended,
        "payload": {"request_id":str(payload.get("id","unknown")), "sequence_index":sequence_index,
          "provider":"openai-compatible", "model":str(payload.get("model",model)),
          "model_revision":str(payload.get("model_revision",model_revision)),
          "request_start":started,"request_end":ended,"input_tokens":prompt,
          "cached_input_tokens":cached,"uncached_input_tokens":prompt-cached,
          "cache_write_tokens":write,"output_tokens":completion,
          "provider_bill_usd":amount,
          "provider_bill_source":source,"billing_status":status,
          "ttft_ms":None,"request_wall_time_ms":elapsed,
          "context_length_before":prompt,"context_length_after":prompt+completion,
          "compression_triggered":False,
          "provider_metadata":{"response_id":str(payload.get("id","unknown")),
                               "cache_write_usage_available":"cache_write_tokens" in usage}},
    }
    # Parse immediately so malformed numeric/type fields fail at the boundary.
    rt.Envelope.parse(event)
    return event, answer
