# Context Economics（上下文经济学）

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Deutsch](README.de.md) · [Français](README.fr.md) · [Español](README.es.md)

**Context Economics 是一套用于研究 LLM / Agent 上下文经济性的可复现实验、测量与有界控制框架。**

> Token 变少，不等于总成本变低。真正应该优化的单位是“成功完成一次任务”。

当前仓库版本：**0.6.1**。完整版本历史见 [`CHANGELOG.md`](CHANGELOG.md)，版本规则见 [`VERSIONING.md`](VERSIONING.md)。首页只介绍当前产品/研究能力，不再堆叠旧版本施工记录、Review 修复过程或调试流水。

## 它解决什么问题？

长任务中的 Agent 会不断携带、缓存、压缩、重新获取、重建甚至丢失上下文。一个“省了很多 input token”的策略，完全可能因为增加了重试、检索、延迟、失败、cache write 或任务错误，最终更贵、更慢，甚至更不可靠。

因此，本仓库把上下文视为一种持续产生运营成本的资产，而不是一个静态 token 数字。核心决策可以拆成三类成本：

```text
Carry Cost（继续携带）
  输入账单 / cache read-write-storage / prefill / 延迟 / mutation amplification

Transformation Cost（变形/压缩）
  压缩 / 摘要 / 索引 / 序列化 / 变形导致的信息损失

Absence Cost（不在上下文）
  重取 / 重试 / 工具调用 / 延迟 / 失败 / 错答 / 违反约束
```

只有当某种 context action 在明确质量底线下，使完整任务的期望总成本低于替代方案时，它才有经济意义。

## 七层研究与工程模型

Context Economics 使用七个相互独立的分析/控制 Layer：

| Layer | 研究范围 |
| --- | --- |
| **L0 Pricing** | Provider input/output 价格、cached read、cache write/storage、长上下文档位、服务等级 |
| **L1 Serving & KV** | Prefill、KV/prefix reuse、cache 稳定性、serving 侧复用与资源成本 |
| **L2 Compression** | 截断、摘要、外部化、RAG、不同内容类型的保真与变形损失 |
| **L3 Harness** | Prompt assembly、tool schema、compaction、subagent、repo map、调度与重取 |
| **L4 Memory & Profile** | 持久上下文、frozen session snapshot、profile scope、驻留租金、来源/版本语义 |
| **L5 Task Economics & Observability** | Provider bill、工具、外部费用、延迟、失败、任务成功、`cost_per_success` |
| **L6 Adaptive Context Control** | Admission、residency、locator、prefetch、有界向量预算、mutation amplification、共享 immutable base |

Context Economics 的 `L0–L6` 是 **Layer**；THM 的 `T0–T3` 是另一独立仓库的 memory residency/access **Tier**。两套 taxonomy 不合并，只在 miss、locator、prefetch、budget、task economics 等重叠研究问题上交换 telemetry/contract。

## 当前已经实现什么？

### 1. 确定性成本模型与任务经济学

- `model.py`：可复现的成本/敏感性模型，支持非线性长上下文定价。
- `real_model.py`：可以回放公开 fixture 或用户提供的 trace；所有模型假设输出明确标为 proxy，不冒充真实质量指标。
- `task_economics.py`：把 run receipt 聚合成 success、provider bill、additive cost、latency、retry、retrieval/reacquisition 和 `cost_per_success`。
- 有限参数网格只报告 **`lowest-cost point in THIS GRID`**，不再把网格端点包装成全局最优。

### 2. Runtime instrumentation 与实验合同

- `context_runtime.py`：严格的 request/tool/context/compression/outcome event schema、收集、校验、脱敏和标准化。
- `runtime_experiment.py`：按精确 run/task/policy identity 和版本 pin 连接 L5 receipt 与 L6 context telemetry。
- `experiment_runner.py`：执行 paired-fixed 或 counterbalanced AB/BA 实验，并原子化发布 artifact 集。
- `experiment_analysis.py`：paired descriptive statistics、deterministic bootstrap、coverage 和 candidate gate。
- `controller_calibration.py`：明确分离 calibration 与 held-out acceptance。

### 3. Shadow Adaptive Context Control

`adaptive_control.py` 当前提供确定性、仅 advisory 的控制面：

- `context_hit / soft_miss / hard_miss / stale_hit / planned_retrieval / prefetch` telemetry；
- miss cost 与 counterfactual value；
- 有资源上限的 exact 0/1 admission/residency packing；
- locator-token economics；
- 防自反馈的 speculative prefetch 指标；
- 有界向量预算反馈；
- context mutation amplification；
- immutable shared base + scoped delta economics。

当前不会自动修改 production provider、harness、budget、cache 或 compression 设置。

### 4. Real-provider campaign 工程

0.6.x 已经加入可用于真实 provider 实验的受控执行路径：

- OpenAI Chat Completions 和 Anthropic Messages 原生 parser/executor；
- 可冻结的 smoke / pilot / train / holdout public-task campaign；
- exact dated model preflight；
- pricing、task、policy、scorer、source commit/tree 全部绑定；
- trusted isolated credentialed bootstrap：先验证 source 与 campaign，再向已加载的隔离 child 投递 provider key；
- aborted campaign 与部分成功 telemetry 的不可变记录；
- offline external-reference attestation verifier。

当前 trusted credential 路径只对已审阅的 POSIX 部署路径开放；未支持的平台会 fail closed，而不是降低 source-integrity 检查。

### 5. Hermes component replay 与 retention fixtures

仓库包含对指定 Hermes upstream revision 的 exact-source/hash-pinned component replay，以及 deterministic content-retention / reacquisition fixtures。它们可以验证结构行为，但**不等于完整 Hermes `compress()` 运行，也不等于真实模型质量证据**。

## 当前证据状态

我们刻意把“工程能力已经存在”和“现实世界已经证明有效”分开。

| 问题 | 当前状态 |
| --- | --- |
| 确定性成本/会计/合同测试 | **已实现并通过 CI** |
| Local HTTP contract E2E | **已实现** |
| OpenAI / Anthropic 原生 adapter | **Fixture-tested** |
| Credential-backed provider smoke / pilot / holdout | **当前公开 evidence 中尚未执行** |
| 单请求 observed monetary bill | **尚未建立**；估算器始终标记 estimated |
| Real L6 train/holdout calibration | **尚未建立** |
| Real cache × compression factorial | **尚未建立** |
| 完整 Hermes compressor + host prompt replay | **未完成** |
| 独立 external trust root | **未配置** |
| `evidence_eligible` / promotion | **False** |
| Production controller 自动变更 | **Disabled** |

当前公开 evidence ceiling 是 simulation / deterministic contract E2E + exact-source component trace-replay。完整边界请看 [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) 与 [`PROVENANCE.md`](PROVENANCE.md)。

## 快速开始

核心路径尽量保持标准库友好：

```bash
python model.py
python real_model.py --fixture fixtures/sample_sessions.json

python task_economics.py \
  --receipts fixtures/run_receipts.json \
  --control no-compression \
  --treatment aggressive-compression

python experiment_runner.py --local-demo --output-root artifacts
```

检查 version-pinned joint contract：

```bash
python runtime_experiment.py \
  --manifest artifacts/local-e2e/manifest.json \
  --receipts artifacts/local-e2e/l5-receipts.json \
  --events artifacts/local-e2e/l6-events.json \
  --require-complete
```

不把 credential 写入命令行或仓库，先准备一个 real-provider smoke campaign：

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

带 credential 的正式执行必须遵循 [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md) 中已经 Review 的 trusted-bootstrap 流程。不要把 API key 粘贴到 issue、命令参数、commit 或 experiment artifact。

## 实验纪律

一个可解释的对照实验应当固定 task、model、revision、harness、scorer 和 task set，只改变一个 context policy。

Formal campaign 在适用时要求：

- 精确 control/treatment pairing；
- counterbalanced AB/BA；
- frozen policy 与 frozen task set；
- calibration 和 held-out acceptance 数据分离；
- 明确区分 `observed` 与 `estimated` billing；
- 成本和任务 success/score 同时报告；
- retry、reacquisition、latency、failure 不能被静默删除；
- caller 自己声明“真实 evidence”不能触发 promotion。

`performance_candidate`、structural evidence readiness、independent authenticated evidence 和 production promotion 是不同状态。

## 核心目标函数

本仓库优化的不是“token 最少”，而是任务价值减去完整运营成本：

```text
J(policy) =
    E[task_value]
  - E[provider/cache bill
      + tool cost
      + external cost
      + latency cost
      + failure cost]
```

`reacquisition` 和 `retry` 可以作为重叠归因子集统计，但不能再被偷偷作为新的 additive ledger 项重复计费。

如果 task value 暂时不能美元化，至少并列报告：

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

## 文档与代码导航

| 文档 / 模块 | 作用 |
| --- | --- |
| [`CHANGELOG.md`](CHANGELOG.md) | 按版本记录历史；旧版本施工、Review 与修复 chronology 放这里，不放首页 |
| [`VERSIONING.md`](VERSIONING.md) | 版本规则与 milestone 映射 |
| [`PROVENANCE.md`](PROVENANCE.md) | Evidence class、source identity、research provenance |
| [`FINAL-EVIDENCE-BOUNDARY.md`](FINAL-EVIDENCE-BOUNDARY.md) | 当前 0.6.x evidence boundary 与剩余实证缺口 |
| [`RUNTIME-INSTRUMENTATION.md`](RUNTIME-INSTRUMENTATION.md) | Canonical runtime telemetry schema 与收集语义 |
| [`RUNTIME-EXPERIMENT-CONTRACT.md`](RUNTIME-EXPERIMENT-CONTRACT.md) | Version-pinned experiment join 与 completeness contract |
| [`EXPERIMENT-ACCEPTANCE.md`](EXPERIMENT-ACCEPTANCE.md) | 统计/evidence acceptance gate |
| [`REAL-RUNTIME-CAMPAIGN.md`](REAL-RUNTIME-CAMPAIGN.md) | 分阶段 provider 实验与安全执行边界 |
| [`RESEARCH-ADDENDUM-2026-09-07.md`](RESEARCH-ADDENDUM-2026-09-07.md) | 不改写历史 snapshot 的研究/来源更新 |
| `L0-pricing.md` … `L6-adaptive-context-control.md` | 各 Layer 的详细研究与设计 |
| `context_runtime.py` | Runtime event collection/normalization |
| `task_economics.py` | 任务级成本账本 |
| `adaptive_control.py` | Deterministic shadow-control surfaces |
| `experiment_runner.py` | Paired experiment orchestration |
| `runtime_campaign.py` | Frozen real-provider campaign |
| `trusted_runtime_bootstrap.py` | 隔离 credential 边界 |

## 项目边界

Context Economics 不是 memory database、不是 compressor 实现，也不是一个新的 Agent harness。它的工作是**测量、比较和评估不同系统中的 context policy**。

仓库可以把 Hermes、Claude Code、Codex、Gemini CLI、OpenAI Agents、LangGraph、THM 或其他系统作为外部 runtime/policy 研究对象。文档里研究过某个系统，不代表已经存在对应 live adapter；只有代码和明确验证记录才算实现。

Hermes 普通 mid-session memory write 会持久化到磁盘，但不会改写当前 session 已经 **frozen** 的 system-prompt snapshot。因此 cache 影响必须从真实 serialized runtime behavior 观测，不能从“写了 memory 文件”直接推导。

## 验证

仓库在 Python 3.11 与 3.13 上验证当前支持的标准库工程表面。各版本的具体 CI identity、Review 与 acceptance chronology 统一记录在 [`CHANGELOG.md`](CHANGELOG.md)，不再放在首页。

## 版本历史

首页只展示当前版本线。详细的版本变更、PR 映射、Review finding、forward-fix 和 evidence-boundary 变化统一放在 [`CHANGELOG.md`](CHANGELOG.md)。

当前版本：**0.6.1**。

---

Context Economics 仍是 1.0 之前的研究软件。公共 contract 与 evidence interface 仍可能演进；版本号永远不能替代 evidence class。
