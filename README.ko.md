# Context Economics

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md)

**Context Economics는 LLM/Agent 컨텍스트의 경제성을 측정하고 비교하며, 재현 가능한 실험과 근거 기반의 제한적 제어를 수행하기 위한 프레임워크입니다.**

> Token 감소가 곧 총비용 감소를 뜻하지는 않습니다. 최적화 단위는 ‘성공한 작업’입니다.

현재 저장소 버전은 **0.6.1**입니다. 전체 변경 이력은 [`CHANGELOG.md`](CHANGELOG.md), 버전 정책은 [`VERSIONING.md`](VERSIONING.md)에 있습니다. 이 홈페이지는 현재의 제품/연구 표면만 설명하며 과거 디버그 로그와 Review 수정 기록을 나열하지 않습니다.

## 무엇을 해결하나요?

장시간 동작하는 Agent는 컨텍스트를 반복해서 운반하고, 캐시하고, 압축하고, 다시 가져오고, 재구성하며 때로는 잃어버립니다. 입력 token을 줄인 정책도 재시도, 검색, 지연, 실패, cache write, 작업 오류를 늘리면 전체적으로 더 비싸고 느리며 불안정할 수 있습니다.

따라서 Context Economics는 컨텍스트를 단순한 token 수가 아니라 운영비용을 발생시키는 자산으로 봅니다. 핵심 의사결정은 세 종류의 비용으로 나눌 수 있습니다.

```text
Carry Cost
  input bill / cache read-write-storage / prefill / latency / mutation amplification

Transformation Cost
  compression / summarization / indexing / serialization / transformation-induced quality loss

Absence Cost
  reacquisition / retry / tool calls / latency / failure / wrong answer / constraint violation
```

명시된 품질 하한을 유지하면서 어떤 context action의 총 기대 작업비용이 대안보다 낮을 때만 경제적으로 정당화됩니다.

## 7개 Layer 연구/공학 모델

| Layer | 범위 |
| --- | --- |
| **L0 Pricing** | Provider input/output 가격, cached read, cache write/storage, long-context tier, service class |
| **L1 Serving & KV** | Prefill, KV/prefix reuse, cache 안정성, serving-side reuse |
| **L2 Compression** | Truncation, summary, externalization, RAG, content-type retention 및 변환 손실 |
| **L3 Harness** | Prompt assembly, tool schema, compaction, subagent, repo map, scheduling, reacquisition |
| **L4 Memory & Profile** | Persistent context, frozen session snapshot, scope, residency cost, source/version semantics |
| **L5 Task Economics & Observability** | Provider bill, tool, external cost, latency, failure, task success, `cost_per_success` |
| **L6 Adaptive Context Control** | Admission, residency, locator, prefetch, bounded vector budget, mutation amplification, shared immutable base |

Context Economics의 `L0–L6`는 **Layer**입니다. THM의 `T0–T3` memory residency/access **Tier**와는 별도 체계이며 taxonomy를 합치지 않습니다. 두 프로젝트는 miss, locator, prefetch, budget, task economics처럼 겹치는 측정 계약만 교환합니다.

## 현재 구현된 기능

### 결정론적 비용 모델과 Task Economics

- `model.py`: 재현 가능한 비용/민감도 모델과 비선형 long-context pricing 지원.
- `real_model.py`: 공개 fixture 또는 사용자 제공 trace replay. 모델 가정값은 proxy로 명시.
- `task_economics.py`: run receipt를 success, provider bill, additive cost, latency, retry, retrieval/reacquisition, `cost_per_success`로 집계.
- 유한 grid는 **`lowest-cost point in THIS GRID`**만 보고하며 global optimum으로 표현하지 않습니다.

### Runtime instrumentation과 experiment contract

- `context_runtime.py`: request/tool/context/compression/outcome event의 엄격한 schema, 수집, 검증, redaction, normalization.
- `runtime_experiment.py`: exact run/task/policy identity와 version pin 아래 L5 receipt와 L6 telemetry 결합.
- `experiment_runner.py`: paired-fixed / counterbalanced AB/BA 실행 및 atomic artifact publication.
- `experiment_analysis.py`: paired statistics, deterministic bootstrap, coverage, candidate gate.
- `controller_calibration.py`: calibration과 held-out acceptance 분리.

### Shadow Adaptive Context Control

`adaptive_control.py`는 결정론적이고 advisory-only인 다음 표면을 제공합니다.

- `context_hit / soft_miss / hard_miss / stale_hit / planned_retrieval / prefetch` telemetry
- miss cost / counterfactual value
- resource-bounded exact 0/1 admission/residency packing
- locator-token economics
- anti-self-training speculative prefetch metrics
- bounded vector budget feedback
- context mutation amplification
- immutable shared base + scoped delta economics

Production provider/harness/budget/cache/compression 설정을 자동 변경하지 않습니다.

### Real-provider campaign engineering

0.6.x에는 실제 Provider 실험을 위한 통제된 실행 경로가 추가되었습니다.

- OpenAI Chat Completions / Anthropic Messages native parser/executor
- frozen smoke / pilot / train / holdout public-task campaign
- exact dated model preflight
- pricing/task/policy/scorer/source commit-tree binding
- source와 campaign을 검증한 뒤에만 provider key를 전달하는 trusted isolated bootstrap
- aborted campaign 및 validated partial telemetry의 immutable record
- offline external-reference attestation verifier

Trusted credential path는 현재 Review된 POSIX deployment path만 지원하며, 미지원 환경에서는 검증을 약화하지 않고 fail closed 합니다.

### Hermes component replay와 retention fixtures

특정 Hermes upstream revision의 exact-source/hash-pinned component replay와 deterministic retention/reacquisition fixture를 포함합니다. 이는 구조 동작에 대한 evidence이지 완전한 Hermes `compress()` 실행이나 실제 모델 품질 증명은 아닙니다.

## 현재 Evidence 상태

| 항목 | 상태 |
| --- | --- |
| Deterministic cost/accounting/contract tests | **구현 및 CI 검증 완료** |
| Local HTTP contract E2E | **구현 완료** |
| OpenAI / Anthropic native adapters | **Fixture-tested** |
| Credential-backed smoke / pilot / holdout | **공개 evidence에서 아직 미실행** |
| Request-level observed monetary bill | **미확립**; estimator는 estimated로 표시 |
| Real L6 train/holdout calibration | **미확립** |
| Real cache × compression factorial | **미확립** |
| Full Hermes compressor + host prompt replay | **미완료** |
| Independent external trust root | **미설정** |
| `evidence_eligible` / promotion | **False** |
| Automatic production mutation | **Disabled** |

현재 공개 evidence ceiling은 simulation / deterministic contract E2E와 exact-source component trace-replay입니다. 세부 경계는 [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) 및 [`PROVENANCE.md`](PROVENANCE.md)를 참조하세요.

## Quick start

```bash
python model.py
python real_model.py --fixture fixtures/sample_sessions.json

python task_economics.py \
  --receipts fixtures/run_receipts.json \
  --control no-compression \
  --treatment aggressive-compression

python experiment_runner.py --local-demo --output-root artifacts
```

Version-pinned joint contract 확인:

```bash
python runtime_experiment.py \
  --manifest artifacts/local-e2e/manifest.json \
  --receipts artifacts/local-e2e/l5-receipts.json \
  --events artifacts/local-e2e/l6-events.json \
  --require-complete
```

Credential을 CLI나 repository에 넣지 않고 real-provider smoke campaign 준비:

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

Credentialed execution은 [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md)의 trusted-bootstrap 절차를 따릅니다. API key를 issue, command argument, commit 또는 artifact에 저장하지 마세요.

## Experiment discipline

해석 가능한 비교에서는 task, model, revision, harness, scorer, task set을 고정하고 한 번에 하나의 context policy만 변경합니다.

Formal campaign은 해당되는 경우 다음을 요구합니다.

- exact control/treatment pairing
- counterbalanced AB/BA
- frozen policy와 frozen task set
- calibration과 held-out acceptance 분리
- `observed` / `estimated` billing 명시
- cost와 task success/score 동시 보고
- retry, reacquisition, latency, failure 보존
- caller declaration만으로 promotion하지 않음

`performance_candidate`, structural readiness, independently authenticated evidence, production promotion은 서로 다른 상태입니다.

## Core objective

```text
J(policy) =
    E[task_value]
  - E[provider/cache bill
      + tool cost
      + external cost
      + latency cost
      + failure cost]
```

`reacquisition`과 `retry`는 중첩 attribution subset으로 추적할 수 있지만 additive ledger에서 이중 계산하지 않습니다.

Task value를 금액화할 수 없다면 최소한 다음을 함께 보고합니다.

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

| 문서 / 모듈 | 목적 |
| --- | --- |
| [`CHANGELOG.md`](CHANGELOG.md) | Version별 역사. 과거 Review/debug chronology는 여기에 기록 |
| [`VERSIONING.md`](VERSIONING.md) | Version policy와 milestone map |
| [`PROVENANCE.md`](PROVENANCE.md) | Evidence class, source identity, provenance |
| [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) | 0.6.x exact closeout boundary |
| [`RUNTIME-INSTRUMENTATION.md`](RUNTIME-INSTRUMENTATION.md) | Canonical runtime telemetry |
| [`RUNTIME-EXPERIMENT-CONTRACT.md`](RUNTIME-EXPERIMENT-CONTRACT.md) | Version-pinned experiment contract |
| [`EXPERIMENT-ACCEPTANCE.md`](EXPERIMENT-ACCEPTANCE.md) | Statistical/evidence acceptance |
| [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md) | Provider campaign/security boundary |
| [`RESEARCH-ADDENDUM-2026-09-07.md`](RESEARCH-ADDENDUM-2026-09-07.md) | Dated research/source updates |
| `L0-pricing.md` … `L6-adaptive-context-control.md` | Layer별 상세 연구 |
| `context_runtime.py` | Event collection/normalization |
| `task_economics.py` | Task-level cost ledger |
| `adaptive_control.py` | Deterministic shadow control |
| `experiment_runner.py` | Paired experiment orchestration |
| `runtime_campaign.py` | Frozen real-provider campaign |
| `trusted_runtime_bootstrap.py` | Isolated credential boundary |

## Project boundaries

Context Economics는 memory database, compressor 구현, 또는 새로운 Agent harness가 아닙니다. 외부 시스템의 context policy를 **측정·비교·평가**하는 연구/실험 기반입니다.

Hermes, Claude Code, Codex, Gemini CLI, OpenAI Agents, LangGraph, THM 등을 연구할 수 있지만 문서에 언급된 것과 live adapter가 구현된 것은 다릅니다. 대응 코드와 명시적 검증이 있는 경우에만 구현됐다고 봅니다.

Hermes의 일반적인 mid-session memory write는 disk에는 반영되지만 현재 session의 **frozen** system-prompt snapshot을 다시 쓰지 않습니다. 따라서 cache 영향은 실제 serialized runtime behavior에서 관측해야 합니다.

## Validation

0.6.0 engineering milestone은 merge 후 Python 3.11 / 3.13 full validation matrix를 통과했습니다. 0.6.1은 homepage/version history/localization productization patch이며 동일한 CI를 통과한 뒤 수용합니다.

## Version history

홈페이지에는 current release line만 둡니다. 상세 변경 내역, PR mapping, Review finding, forward fix, evidence-boundary 변화는 [`CHANGELOG.md`](CHANGELOG.md)에 모읍니다.

Current version: **0.6.1**.

---

Context Economics는 아직 1.0 이전의 research software입니다. Version number는 evidence class를 대신하지 않습니다.
