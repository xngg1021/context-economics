# Context Economics（上下文經濟學）

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md)

**Context Economics 是一套用於研究 LLM / Agent 上下文經濟性的可重現實驗、量測與有界控制框架。**

> Token 變少，不等於總成本變低。真正應該優化的單位是「成功完成一次任務」。

目前倉庫版本：**0.6.1**。完整版本歷史見 [`CHANGELOG.md`](CHANGELOG.md)，版本規則見 [`VERSIONING.md`](VERSIONING.md)。首頁只介紹目前產品/研究能力，不再堆疊舊版本施工紀錄、Review 修復過程或 debug 流水。

## 它解決什麼問題？

長任務中的 Agent 會不斷攜帶、快取、壓縮、重新取得、重建甚至遺失上下文。一個「省了很多 input token」的策略，完全可能因為增加重試、檢索、延遲、失敗、cache write 或任務錯誤，最後更貴、更慢，甚至更不可靠。

因此，本倉庫把上下文視為一種持續產生營運成本的資產，而不是靜態 token 數字。核心決策可拆成三類成本：

```text
Carry Cost（繼續攜帶）
  輸入帳單 / cache read-write-storage / prefill / 延遲 / mutation amplification

Transformation Cost（變形/壓縮）
  壓縮 / 摘要 / 索引 / 序列化 / 變形造成的資訊損失

Absence Cost（不在上下文）
  重取 / 重試 / 工具呼叫 / 延遲 / 失敗 / 錯答 / 違反約束
```

只有當某種 context action 在明確品質底線下，使完整任務的期望總成本低於替代方案時，它才具有經濟意義。

## 七層研究與工程模型

Context Economics 使用七個彼此獨立的分析/控制 Layer：

| Layer | 研究範圍 |
| --- | --- |
| **L0 Pricing** | Provider input/output 價格、cached read、cache write/storage、長上下文級距、服務等級 |
| **L1 Serving & KV** | Prefill、KV/prefix reuse、cache 穩定性、serving 側重用與資源成本 |
| **L2 Compression** | 截斷、摘要、外部化、RAG、不同內容類型的保真與變形損失 |
| **L3 Harness** | Prompt assembly、tool schema、compaction、subagent、repo map、排程與重取 |
| **L4 Memory & Profile** | 持久上下文、frozen session snapshot、profile scope、駐留租金、來源/版本語義 |
| **L5 Task Economics & Observability** | Provider bill、工具、外部費用、延遲、失敗、任務成功、`cost_per_success` |
| **L6 Adaptive Context Control** | Admission、residency、locator、prefetch、有界向量預算、mutation amplification、共享 immutable base |

Context Economics 的 `L0–L6` 是 **Layer**；THM 的 `T0–T3` 是另一獨立倉庫的 memory residency/access **Tier**。兩套 taxonomy 不合併，只在 miss、locator、prefetch、budget、task economics 等重疊研究問題上交換 telemetry/contract。

## 目前已經實作什麼？

### 1. 確定性成本模型與任務經濟學

- `model.py`：可重現的成本/敏感度模型，支援非線性長上下文定價。
- `real_model.py`：可回放公開 fixture 或使用者提供的 trace；所有模型假設輸出明確標為 proxy，不冒充真實品質指標。
- `task_economics.py`：把 run receipt 聚合成 success、provider bill、additive cost、latency、retry、retrieval/reacquisition 與 `cost_per_success`。
- 有限參數網格只報告 **`lowest-cost point in THIS GRID`**，不把網格端點包裝成全域最優。

### 2. Runtime instrumentation 與實驗合同

- `context_runtime.py`：嚴格的 request/tool/context/compression/outcome event schema、收集、驗證、脫敏與標準化。
- `runtime_experiment.py`：依精確 run/task/policy identity 與版本 pin 串接 L5 receipt 和 L6 context telemetry。
- `experiment_runner.py`：執行 paired-fixed 或 counterbalanced AB/BA 實驗，並原子化發佈 artifact 集。
- `experiment_analysis.py`：paired descriptive statistics、deterministic bootstrap、coverage 與 candidate gate。
- `controller_calibration.py`：明確分離 calibration 與 held-out acceptance。

### 3. Shadow Adaptive Context Control

`adaptive_control.py` 目前提供確定性、僅 advisory 的控制面：

- `context_hit / soft_miss / hard_miss / stale_hit / planned_retrieval / prefetch` telemetry；
- miss cost 與 counterfactual value；
- 有資源上限的 exact 0/1 admission/residency packing；
- locator-token economics；
- 防自回饋的 speculative prefetch 指標；
- 有界向量預算回饋；
- context mutation amplification；
- immutable shared base + scoped delta economics。

目前不會自動修改 production provider、harness、budget、cache 或 compression 設定。

### 4. Real-provider campaign 工程

0.6.x 已加入可用於真實 provider 實驗的受控執行路徑：

- OpenAI Chat Completions 與 Anthropic Messages 原生 parser/executor；
- 可凍結的 smoke / pilot / train / holdout public-task campaign；
- exact dated model preflight；
- pricing、task、policy、scorer、source commit/tree 全部綁定；
- trusted isolated credentialed bootstrap：先驗證 source 與 campaign，再向已載入的隔離 child 投遞 provider key；
- aborted campaign 與部分成功 telemetry 的不可變紀錄；
- offline external-reference attestation verifier。

目前 trusted credential 路徑只對已審閱的 POSIX 部署路徑開放；未支援的平台會 fail closed，而不是降低 source-integrity 檢查。

### 5. Hermes component replay 與 retention fixtures

倉庫包含對指定 Hermes upstream revision 的 exact-source/hash-pinned component replay，以及 deterministic content-retention / reacquisition fixtures。它們可驗證結構行為，但**不等於完整 Hermes `compress()` 執行，也不等於真實模型品質證據**。

## 目前證據狀態

我們刻意把「工程能力已存在」與「現實世界已證明有效」分開。

| 問題 | 目前狀態 |
| --- | --- |
| 確定性成本/會計/合同測試 | **已實作並通過 CI** |
| Local HTTP contract E2E | **已實作** |
| OpenAI / Anthropic 原生 adapter | **Fixture-tested** |
| Credential-backed provider smoke / pilot / holdout | **目前公開 evidence 中尚未執行** |
| 單請求 observed monetary bill | **尚未建立**；估算器始終標記 estimated |
| Real L6 train/holdout calibration | **尚未建立** |
| Real cache × compression factorial | **尚未建立** |
| 完整 Hermes compressor + host prompt replay | **未完成** |
| 獨立 external trust root | **未配置** |
| `evidence_eligible` / promotion | **False** |
| Production controller 自動變更 | **Disabled** |

目前公開 evidence ceiling 是 simulation / deterministic contract E2E + exact-source component trace-replay。完整邊界請見 [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) 與 [`PROVENANCE.md`](PROVENANCE.md)。

## 快速開始

核心路徑盡量維持標準函式庫友善：

```bash
python model.py
python real_model.py --fixture fixtures/sample_sessions.json

python task_economics.py \
  --receipts fixtures/run_receipts.json \
  --control no-compression \
  --treatment aggressive-compression

python experiment_runner.py --local-demo --output-root artifacts
```

檢查 version-pinned joint contract：

```bash
python runtime_experiment.py \
  --manifest artifacts/local-e2e/manifest.json \
  --receipts artifacts/local-e2e/l5-receipts.json \
  --events artifacts/local-e2e/l6-events.json \
  --require-complete
```

不把 credential 寫入命令列或倉庫，先準備 real-provider smoke campaign：

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

帶 credential 的正式執行必須遵循 [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md) 中已經 Review 的 trusted-bootstrap 流程。不要把 API key 貼到 issue、命令參數、commit 或 experiment artifact。

## 實驗紀律

可解釋的對照實驗應固定 task、model、revision、harness、scorer 與 task set，只改變一個 context policy。

Formal campaign 在適用時要求：

- 精確 control/treatment pairing；
- counterbalanced AB/BA；
- frozen policy 與 frozen task set；
- calibration 和 held-out acceptance 資料分離；
- 明確區分 `observed` 與 `estimated` billing；
- 成本與任務 success/score 同時報告；
- retry、reacquisition、latency、failure 不可被靜默刪除；
- caller 自己聲稱「真實 evidence」不能觸發 promotion。

`performance_candidate`、structural evidence readiness、independent authenticated evidence 與 production promotion 是不同狀態。

## 核心目標函數

本倉庫優化的不是「token 最少」，而是任務價值減去完整營運成本：

```text
J(policy) =
    E[task_value]
  - E[provider/cache bill
      + tool cost
      + external cost
      + latency cost
      + failure cost]
```

`reacquisition` 與 `retry` 可作為重疊歸因子集統計，但不能再被偷偷當成新的 additive ledger 項重複計費。

如果 task value 暫時不能貨幣化，至少並列報告：

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

## 文件與程式導航

| 文件 / 模組 | 作用 |
| --- | --- |
| [`CHANGELOG.md`](CHANGELOG.md) | 按版本記錄歷史；舊版本施工、Review 與修復 chronology 放這裡，不放首頁 |
| [`VERSIONING.md`](VERSIONING.md) | 版本規則與 milestone 映射 |
| [`PROVENANCE.md`](PROVENANCE.md) | Evidence class、source identity、research provenance |
| [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) | 0.6.x exact closeout 邊界與剩餘實證缺口 |
| [`RUNTIME-INSTRUMENTATION.md`](RUNTIME-INSTRUMENTATION.md) | Canonical runtime telemetry schema 與收集語義 |
| [`RUNTIME-EXPERIMENT-CONTRACT.md`](RUNTIME-EXPERIMENT-CONTRACT.md) | Version-pinned experiment join 與 completeness contract |
| [`EXPERIMENT-ACCEPTANCE.md`](EXPERIMENT-ACCEPTANCE.md) | 統計/evidence acceptance gate |
| [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md) | 分階段 provider 實驗與安全執行邊界 |
| [`RESEARCH-ADDENDUM-2026-09-07.md`](RESEARCH-ADDENDUM-2026-09-07.md) | 不改寫歷史 snapshot 的研究/來源更新 |
| `L0-pricing.md` … `L6-adaptive-context-control.md` | 各 Layer 的詳細研究與設計 |
| `context_runtime.py` | Runtime event collection/normalization |
| `task_economics.py` | 任務級成本帳本 |
| `adaptive_control.py` | Deterministic shadow-control surfaces |
| `experiment_runner.py` | Paired experiment orchestration |
| `runtime_campaign.py` | Frozen real-provider campaign |
| `trusted_runtime_bootstrap.py` | 隔離 credential 邊界 |

## 專案邊界

Context Economics 不是 memory database、不是 compressor 實作，也不是新的 Agent harness。它的工作是**量測、比較與評估不同系統中的 context policy**。

倉庫可把 Hermes、Claude Code、Codex、Gemini CLI、OpenAI Agents、LangGraph、THM 或其他系統當作外部 runtime/policy 研究對象。文件裡研究過某個系統，不代表已存在對應 live adapter；只有程式碼與明確驗證紀錄才算實作。

Hermes 一般 mid-session memory write 會持久化到磁碟，但不會改寫目前 session 已經 **frozen** 的 system-prompt snapshot。因此 cache 影響必須從真實 serialized runtime behavior 觀測，不能由「寫了 memory 檔案」直接推導。

## 驗證

0.6.0 engineering milestone 在 merge 後通過 Python 3.11 / 3.13 完整 validation matrix。現在 0.6.1 只做首頁、版本歷史與本地化產品化整理，同樣必須通過倉庫 CI 才能接受。

## 版本歷史

首頁只展示目前版本線。詳細版本變更、PR 映射、Review finding、forward-fix 與 evidence-boundary 變化統一放在 [`CHANGELOG.md`](CHANGELOG.md)。

目前版本：**0.6.1**。

---

Context Economics 仍是 1.0 之前的研究軟體。公共 contract 與 evidence interface 仍可能演進；版本號永遠不能替代 evidence class。
