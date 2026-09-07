# Context Economics

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md)

**Context Economics は、LLM / Agent のコンテキスト経済性を測定・比較・実験し、証拠に基づいて有界制御するための再現可能なフレームワークです。**

> Token 削減は、そのまま総コスト削減を意味しません。最適化すべき単位は「成功したタスク」です。

現在のリポジトリ版は **0.6.1** です。詳細な履歴は [`CHANGELOG.md`](CHANGELOG.md)、バージョニング方針は [`VERSIONING.md`](VERSIONING.md) にあります。トップページは現在の製品/研究面だけを説明し、過去のデバッグ記録や Review の逐次ログは置きません。

## 何を解決するのか

長時間動作する Agent は、コンテキストを繰り返し保持、キャッシュ、圧縮、再取得、再構築し、ときには失います。入力 token を減らす施策でも、再試行、検索、遅延、失敗、cache write、タスクエラーが増えれば、最終的に高コストで低信頼になる可能性があります。

Context Economics はコンテキストを単なる token 数ではなく、運用コストを持つ資産として扱います。判断は主に次の三つのコストに分解できます。

```text
Carry Cost
  input bill / cache read-write-storage / prefill / latency / mutation amplification

Transformation Cost
  compression / summarization / indexing / serialization / transformation-induced quality loss

Absence Cost
  reacquisition / retry / tool calls / latency / failure / wrong answer / constraint violation
```

明示した品質下限を守りつつ、ある context action の総期待タスクコストが代替案より低い場合にのみ、その施策を経済的に正当化します。

## 7 層の研究・工学モデル

| Layer | 対象 |
| --- | --- |
| **L0 Pricing** | Provider の input/output、cached read、cache write/storage、long-context tier、service class |
| **L1 Serving & KV** | Prefill、KV/prefix reuse、cache stability、serving-side reuse |
| **L2 Compression** | Truncation、summary、externalization、RAG、content-type retention と変換損失 |
| **L3 Harness** | Prompt assembly、tool schema、compaction、subagent、repo map、scheduling、reacquisition |
| **L4 Memory & Profile** | Persistent context、frozen session snapshot、scope、residency cost、source/version semantics |
| **L5 Task Economics & Observability** | Provider bill、tool、external cost、latency、failure、task success、`cost_per_success` |
| **L6 Adaptive Context Control** | Admission、residency、locator、prefetch、bounded vector budget、mutation amplification、shared immutable base |

Context Economics の `L0–L6` は **Layer** です。THM の `T0–T3` memory residency/access **Tier** とは別体系で、taxonomy は統合しません。miss、locator、prefetch、budget、task economics など重なる計測面だけを共有します。

## 現在実装されているもの

### 決定論的モデルと Task Economics

- `model.py`：再現可能なコスト/感度モデル。非線形 long-context pricing に対応。
- `real_model.py`：公開 fixture またはユーザー提供 trace を replay。モデル仮定は proxy として明示。
- `task_economics.py`：run receipt から success、provider bill、additive cost、latency、retry、retrieval/reacquisition、`cost_per_success` を集計。
- 有限グリッドは **`lowest-cost point in THIS GRID`** とだけ報告し、global optimum とは呼びません。

### Runtime instrumentation と experiment contract

- `context_runtime.py`：request/tool/context/compression/outcome event の厳密 schema、収集、検証、redaction、normalization。
- `runtime_experiment.py`：exact run/task/policy identity と version pin の下で L5 receipt と L6 telemetry を結合。
- `experiment_runner.py`：paired-fixed / counterbalanced AB/BA 実験と atomic artifact publication。
- `experiment_analysis.py`：paired statistics、deterministic bootstrap、coverage、candidate gate。
- `controller_calibration.py`：calibration と held-out acceptance を分離。

### Shadow Adaptive Context Control

`adaptive_control.py` は、決定論的で advisory-only の以下の面を持ちます。

- `context_hit / soft_miss / hard_miss / stale_hit / planned_retrieval / prefetch` telemetry
- miss cost / counterfactual value
- resource-bounded exact 0/1 admission/residency packing
- locator-token economics
- anti-self-training speculative prefetch metrics
- bounded vector budget feedback
- context mutation amplification
- immutable shared base + scoped delta economics

Production の provider / harness / budget / cache / compression を自動変更しません。

### Real-provider campaign engineering

0.6.x では、実 Provider 実験向けの制御された実行経路を追加しました。

- OpenAI Chat Completions / Anthropic Messages の native parser/executor
- frozen smoke / pilot / train / holdout public-task campaign
- exact dated model preflight
- pricing / task / policy / scorer / source commit-tree の固定
- source と campaign の検証後にのみ provider key を渡す trusted isolated bootstrap
- aborted campaign と partial validated telemetry の immutable record
- offline external-reference attestation verifier

Trusted credential path は現在、Review 済み POSIX deployment path のみを対象とし、未対応環境では fail closed します。

### Hermes component replay と retention fixtures

指定した Hermes upstream revision の exact-source/hash-pinned component replay と deterministic retention/reacquisition fixture を含みます。これは構造挙動の検証であり、完全な Hermes `compress()` 実行や実モデル品質の証明ではありません。

## 現在の Evidence 状態

| 項目 | 状態 |
| --- | --- |
| Deterministic cost/accounting/contract tests | **実装済み・CI 済み** |
| Local HTTP contract E2E | **実装済み** |
| OpenAI / Anthropic native adapters | **Fixture-tested** |
| Credential-backed smoke / pilot / holdout | **公開 evidence では未実行** |
| Request-level observed monetary bill | **未確立**。Estimator は estimated と明示 |
| Real L6 train/holdout calibration | **未確立** |
| Real cache × compression factorial | **未確立** |
| Full Hermes compressor + host prompt replay | **未完了** |
| Independent external trust root | **未配置** |
| `evidence_eligible` / promotion | **False** |
| Automatic production mutation | **Disabled** |

現在の公開 evidence ceiling は simulation / deterministic contract E2E と exact-source component trace-replay です。詳細は [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) と [`PROVENANCE.md`](PROVENANCE.md) を参照してください。

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

Version-pinned joint contract の検証：

```bash
python runtime_experiment.py \
  --manifest artifacts/local-e2e/manifest.json \
  --receipts artifacts/local-e2e/l5-receipts.json \
  --events artifacts/local-e2e/l6-events.json \
  --require-complete
```

Credential を CLI や repository に置かずに real-provider smoke campaign を準備：

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

Credentialed execution は [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md) の trusted-bootstrap 手順に従ってください。API key を issue、command argument、commit、artifact に保存しないでください。

## Experiment discipline

解釈可能な比較では task、model、revision、harness、scorer、task set を固定し、一度に一つの context policy だけを変更します。

Formal campaign では必要に応じて以下を要求します。

- exact control/treatment pairing
- counterbalanced AB/BA
- frozen policy と frozen task set
- calibration と held-out acceptance の分離
- `observed` / `estimated` billing の明示
- cost と task success/score の併記
- retry、reacquisition、latency、failure の保持
- caller declaration だけでは promotion しない

`performance_candidate`、structural readiness、independently authenticated evidence、production promotion は別状態です。

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

`reacquisition` と `retry` は重複する attribution subset として追跡できますが、additive ledger に二重加算しません。

Task value を金額化できない場合でも、少なくとも次を並列報告します。

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

| Document / module | 目的 |
| --- | --- |
| [`CHANGELOG.md`](CHANGELOG.md) | Version ごとの履歴。旧施工/Review/debug chronology はここに置く |
| [`VERSIONING.md`](VERSIONING.md) | Version policy と milestone map |
| [`PROVENANCE.md`](PROVENANCE.md) | Evidence class、source identity、research provenance |
| [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) | 0.6.x の exact closeout boundary |
| [`RUNTIME-INSTRUMENTATION.md`](RUNTIME-INSTRUMENTATION.md) | Canonical runtime telemetry |
| [`RUNTIME-EXPERIMENT-CONTRACT.md`](RUNTIME-EXPERIMENT-CONTRACT.md) | Version-pinned experiment contract |
| [`EXPERIMENT-ACCEPTANCE.md`](EXPERIMENT-ACCEPTANCE.md) | Statistical/evidence acceptance |
| [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md) | Provider campaign と security boundary |
| [`RESEARCH-ADDENDUM-2026-09-07.md`](RESEARCH-ADDENDUM-2026-09-07.md) | Dated research/source updates |
| `L0-pricing.md` … `L6-adaptive-context-control.md` | Layer 別詳細 |
| `context_runtime.py` | Event collection/normalization |
| `task_economics.py` | Task-level cost ledger |
| `adaptive_control.py` | Deterministic shadow control |
| `experiment_runner.py` | Paired experiment orchestration |
| `runtime_campaign.py` | Frozen real-provider campaign |
| `trusted_runtime_bootstrap.py` | Isolated credential boundary |

## Project boundaries

Context Economics は memory database、compressor 実装、Agent harness そのものではありません。外部システムの context policy を**測定・比較・評価する**ための研究/実験基盤です。

Hermes、Claude Code、Codex、Gemini CLI、OpenAI Agents、LangGraph、THM などを研究対象にできますが、文書で扱っていることと live adapter が存在することは同義ではありません。実装済みと呼ぶのは、対応コードと検証がある場合だけです。

Hermes の通常の mid-session memory write は disk に永続化されても、現在セッションの **frozen** system-prompt snapshot を書き換えません。したがって cache 影響は実際の serialized runtime behavior から観測すべきで、file write から推定しません。

## Validation

0.6.0 engineering milestone は merge 後に Python 3.11 / 3.13 の full validation matrix を通過しました。0.6.1 は homepage、version history、localization の productization patch であり、同じ CI を通過してから受理します。

## Version history

トップページには current release line だけを置きます。詳細な変更履歴、PR mapping、Review finding、forward fix、evidence-boundary の推移は [`CHANGELOG.md`](CHANGELOG.md) に集約します。

Current version: **0.6.1**.

---

Context Economics は 1.0 前の research software です。Version number は evidence class の代わりにはなりません。
