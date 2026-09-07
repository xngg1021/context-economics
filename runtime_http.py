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
from typing import Mapping

import context_runtime as rt


def _now() -> str: return datetime.now(timezone.utc).isoformat()


class OpenAICompatibleHTTPAdapter:
    adapter_id = "openai-compatible-http-v1"

    def adapt(self, native_event: Mapping[str, object]):
        # The HTTP harness constructs an already-redacted canonical envelope.
        yield dict(native_event)


def run_request(*, url: str, run_id: str, task_id: str, policy_id: str,
                model: str, model_revision: str, sequence_index: int,
                input_text: str, timeout: float = 10.0) -> tuple[dict, str]:
    """Call an endpoint and return a redacted request event plus answer text."""
    started = _now(); before = time.perf_counter()
    body = json.dumps({"model": model, "messages": [{"role":"user","content":input_text}]}).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    elapsed = (time.perf_counter()-before)*1000; ended = _now()
    allowed = {"id","model","model_revision","usage","billing","choices","cache"}
    if not isinstance(payload, dict) or set(payload)-allowed:
        raise rt.TelemetryError("provider response contains unknown top-level fields")
    usage = payload.get("usage"); billing = payload.get("billing")
    if not isinstance(usage, dict) or not isinstance(billing, dict):
        raise rt.TelemetryError("provider response requires usage and billing objects")
    prompt = usage.get("prompt_tokens"); cached = usage.get("cached_prompt_tokens",0)
    completion = usage.get("completion_tokens"); write = usage.get("cache_write_tokens",0)
    choices = payload.get("choices")
    if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict):
        raise rt.TelemetryError("provider response requires one choice")
    answer = choices[0].get("text")
    if not isinstance(answer,str): raise rt.TelemetryError("choice text must be a string")
    event = {
        "event_id":"req-"+uuid.uuid4().hex, "event_kind":"request", "run_id":run_id,
        "task_id":task_id, "policy_id":policy_id, "occurred_at":ended,
        "payload": {"request_id":str(payload.get("id","unknown")), "sequence_index":sequence_index,
          "provider":"openai-compatible", "model":str(payload.get("model",model)),
          "model_revision":str(payload.get("model_revision",model_revision)),
          "request_start":started,"request_end":ended,"input_tokens":prompt,
          "cached_input_tokens":cached,"uncached_input_tokens":prompt-cached,
          "cache_write_tokens":write,"output_tokens":completion,
          "provider_bill_usd":billing.get("amount_usd"),
          "provider_bill_source":billing.get("source"),"billing_status":billing.get("status"),
          "ttft_ms":elapsed,"request_wall_time_ms":elapsed,
          "context_length_before":prompt,"context_length_after":prompt+completion,
          "compression_triggered":False,
          "provider_metadata":{"response_id":str(payload.get("id","unknown"))}},
    }
    # Parse immediately so malformed numeric/type fields fail at the boundary.
    rt.Envelope.parse(event)
    return event, answer
