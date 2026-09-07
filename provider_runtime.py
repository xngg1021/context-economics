"""Thin non-streaming provider executor. No credential or response text artifacts."""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import context_runtime as rt

ENDPOINTS = {'openai': 'https://api.openai.com/v1/chat/completions',
             'anthropic': 'https://api.anthropic.com/v1/messages'}
CREDENTIALS = {'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY'}


class ProviderError(ValueError):
    """Public message is a bounded category, never a native exception/body."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class Capabilities:
    provider: str
    model: str
    model_revision: str
    supports_usage: bool = True
    supports_cached_input: bool = True
    supports_cache_write: bool = False
    supports_service_tier: bool = False
    supports_response_id: bool = True
    supports_streaming_ttft: bool = False
    supports_observed_bill: bool = False
    supports_tool_receipt: bool = False
    supports_provider_cache_key: bool = False

    def to_mapping(self):
        row = asdict(self)
        row['unsupported_fields'] = [k.removeprefix('supports_') for k,v in row.items()
                                     if k.startswith('supports_') and v is False]
        return row


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError('redirect_refused')


def send(provider, body, timeout=30, *, model_lookup=None):
    """Credentials only from named environment variables; fixed HTTPS destinations."""
    key = os.environ.get(CREDENTIALS[provider])
    if not key:
        raise ProviderError('credential_unavailable')
    headers = {'Content-Type': 'application/json'}
    if provider == 'openai':
        headers['Authorization'] = 'Bearer ' + key
    else:
        headers.update({'x-api-key': key, 'anthropic-version': '2023-06-01'})
    endpoint = ENDPOINTS[provider]
    if model_lookup is not None:
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', model_lookup):
            raise ProviderError('invalid_model_identity')
        endpoint = {'openai': 'https://api.openai.com/v1/models/',
                    'anthropic': 'https://api.anthropic.com/v1/models/'}[provider] + model_lookup
    request = urllib.request.Request(endpoint, data=None if model_lookup else json.dumps(body).encode(), headers=headers)
    # Never follow a redirect with authentication. Standard TLS verification stays on.
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ProviderError('response_too_large')
        return json.loads(raw)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        category = {401: 'credential', 403: 'credential', 429: 'rate_limit'}.get(code, 'provider_http_error')
        if code == 404 and model_lookup:
            category = 'model_unavailable'
        raise ProviderError(category) from None
    except (TimeoutError, socket.timeout):
        raise ProviderError('timeout') from None
    except json.JSONDecodeError:
        raise ProviderError('response_parse') from None
    except (OSError, ValueError, urllib.error.URLError) as exc:
        category = str(exc) if isinstance(exc, ProviderError) else 'transport'
        raise ProviderError(category) from None


def verify_model(provider, revision):
    """Authenticated exact Models endpoint check, no alias substitution or text storage."""
    payload = send(provider, None, model_lookup=revision)
    if not isinstance(payload, dict) or payload.get('id') != revision:
        raise ProviderError('model_unavailable')
    return {'provider': provider, 'model_revision': revision, 'available': True,
            'verified_at': datetime.now(timezone.utc).isoformat(), 'source': 'official-models-api'}


def native_response(provider, payload, revision):
    """Return usage observations + ephemeral answer. Reject unsupported semantics."""
    if not isinstance(payload, dict) or payload.get('model') != revision:
        raise ProviderError('model_revision_mismatch')
    if 'billing' in payload:
        raise ProviderError('unreviewed_billing_extension')
    u = payload.get('usage')
    if not isinstance(u, dict):
        raise ProviderError('usage_unavailable')
    if provider == 'openai':
        total = rt._int(u.get('prompt_tokens'), 'input_tokens')
        output = rt._int(u.get('completion_tokens'), 'output_tokens')
        details = u.get('prompt_tokens_details', {})
        if not isinstance(details, dict):
            raise ProviderError('invalid_cache_usage')
        cached = details.get('cached_tokens')
        legacy = u.get('cached_prompt_tokens')
        if legacy is not None and legacy != cached:
            raise ProviderError('conflicting_cache_usage')
        cached = None if cached is None else rt._int(cached, 'cached_input_tokens')
        write = None
        choices = payload.get('choices')
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise ProviderError('unsupported_choices')
        msg = choices[0].get('message')
        if not isinstance(msg, dict) or msg.get('tool_calls') or msg.get('function_call'):
            raise ProviderError('tool_protocol_unsupported')
        answer = msg.get('content')
        finished = choices[0].get('finish_reason') == 'stop'
        tier = payload.get('service_tier')
        if tier not in (None, 'default'):
            raise ProviderError('unpriced_service_tier')
    else:
        uncached = rt._int(u.get('input_tokens'), 'input_tokens')
        output = rt._int(u.get('output_tokens'), 'output_tokens')
        cached = u.get('cache_read_input_tokens')
        write = u.get('cache_creation_input_tokens')
        cached = None if cached is None else rt._int(cached, 'cached_input_tokens')
        write = None if write is None else rt._int(write, 'cache_write_tokens')
        total = uncached + (cached or 0) + (write or 0)
        blocks = payload.get('content')
        if not isinstance(blocks, list) or not blocks or any(not isinstance(b, dict) or b.get('type') != 'text' for b in blocks):
            raise ProviderError('nontext_response_unsupported')
        if any(not isinstance(b.get('text'), str) for b in blocks):
            raise ProviderError('invalid_answer')
        answer = ''.join(b['text'] for b in blocks)
        finished = payload.get('stop_reason') == 'end_turn'
        tier = None
    if not isinstance(answer, str):
        raise ProviderError('invalid_answer')
    if cached is not None and cached > total:
        raise ProviderError('cache_exceeds_input')
    # Hash native IDs; arbitrary provider echoes cannot expose private text.
    response_id = payload.get('id')
    observations = {'input_tokens': total, 'output_tokens': output,
                    'cached_input_tokens': cached, 'cache_write_tokens': write,
                    'service_tier': tier, 'response_id': None if response_id is None else digest(response_id)}
    return observations, answer, finished


@dataclass(frozen=True)
class Price:
    """USD / million text tokens, standard tier only; exact source ref required."""
    provider: str
    model_revision: str
    input: float
    output: float
    cached_read: float
    source: str
    max_input_tokens: int = 200000

    def __post_init__(self):
        for name in ('input', 'output', 'cached_read'):
            rt._num(getattr(self, name), name)
        rt._int(self.max_input_tokens, 'max_input_tokens')
        if not self.source.startswith('sha256:') or not re.fullmatch(r'sha256:[a-f0-9]{64}', self.source):
            raise ProviderError('pricing_requires_snapshot_digest')

    def estimate(self, usage):
        cached = usage['cached_input_tokens']
        if cached is None:
            raise ProviderError('cache_usage_unavailable_for_pricing')
        # This first executor never requests cache creation. Chargeable writes need
        # a TTL-specific pricing extension, not a guessed multiplier.
        if usage['cache_write_tokens'] not in (None, 0):
            raise ProviderError('cache_write_pricing_unsupported')
        if usage['input_tokens'] > self.max_input_tokens:
            raise ProviderError('long_context_tier_unpriced')
        return ((usage['input_tokens'] - cached) * self.input + cached * self.cached_read
                + usage['output_tokens'] * self.output) / 1_000_000


class ProviderExecutor:
    evidence_origin = 'real-provider'  # Informational only; never authenticates promotion.

    def __init__(self, provider, revision, price, *, history_limit=None):
        if provider not in ENDPOINTS or not re.search(r'(?:\d{4}-\d{2}-\d{2}|\d{8})$', revision):
            raise ProviderError('dated_model_revision_required')
        if price.provider != provider or price.model_revision != revision:
            raise ProviderError('pricing_model_mismatch')
        if history_limit is not None:
            rt._int(history_limit, 'history_limit')
        self.provider, self.revision, self.price = provider, revision, price
        self.history_limit = history_limit
        self.capabilities = Capabilities(provider, revision, revision,
                                        supports_cache_write=provider == 'anthropic',
                                        supports_service_tier=provider == 'openai')

    def execute(self, task, *, run_id, policy_id, manifest):
        if (manifest.provider, manifest.model, manifest.model_revision) != (self.provider, self.revision, self.revision):
            raise ProviderError('manifest_provider_pin_mismatch')
        history = task.get('history', [])
        if not isinstance(history, list) or any(not isinstance(x, str) for x in history):
            raise ProviderError('invalid_history')
        if self.history_limit is not None:
            history = history[-self.history_limit:] if self.history_limit else []
        text = '\n'.join(history + [rt._text(task.get('input'), 'task_input')])
        expected = rt._text(task.get('expected_answer'), 'expected_answer')
        # Unique prefix reduces cross-arm prefix reuse; cache coldness remains unknown.
        text = 'Experiment isolation ' + digest(run_id) + '\n' + text
        body = {'model': self.revision, 'messages': [{'role': 'user', 'content': text}]}
        body['max_completion_tokens' if self.provider == 'openai' else 'max_tokens'] = 256
        if self.provider == 'openai':
            body['service_tier'] = 'default'
        started = datetime.now(timezone.utc).isoformat()
        before = time.perf_counter()
        payload = send(self.provider, body)
        elapsed = (time.perf_counter() - before) * 1000
        ended = datetime.now(timezone.utc).isoformat()
        usage, answer, finished = native_response(self.provider, payload, self.revision)
        amount = self.price.estimate(usage)
        base = {'run_id': run_id, 'task_id': task['task_id'], 'policy_id': policy_id, 'occurred_at': ended}
        cached = usage['cached_input_tokens']
        event = {**base, 'event_id': run_id+'-request', 'event_kind': 'request', 'payload': {
            'request_id': usage['response_id'] or digest(run_id), 'sequence_index': 0,
            'provider': self.provider, 'model': self.revision, 'model_revision': self.revision,
            'request_start': started, 'request_end': ended, 'input_tokens': usage['input_tokens'],
            'cached_input_tokens': cached, 'uncached_input_tokens': usage['input_tokens']-cached,
            'cache_write_tokens': usage['cache_write_tokens'] or 0, 'output_tokens': usage['output_tokens'],
            'provider_bill_usd': amount, 'provider_bill_source': self.price.source, 'billing_status': 'estimated',
            'ttft_ms': None, 'request_wall_time_ms': elapsed,
            'context_length_before': usage['input_tokens'],
            'context_length_after': usage['input_tokens']+usage['output_tokens'],
            'compression_triggered': False,
            'usage_observations': usage}}
        yield event
        yield {**base, 'event_id': run_id+'-context', 'event_kind': 'context',
               'payload': {'kind': 'context_hit', 'asset_id': 'submitted-task-input'}}
        success = finished and answer.strip() == expected
        yield {**base, 'occurred_at': datetime.now(timezone.utc).isoformat(),
               'event_id': run_id+'-outcome', 'event_kind': 'outcome',
               'payload': {'success': success, 'task_score': float(success),
                           'scorer_id': 'public-exact-match', 'scorer_version': 'v1',
                           'scoring_provenance': 'benchmark', 'harness_revision': manifest.harness_revision}}
