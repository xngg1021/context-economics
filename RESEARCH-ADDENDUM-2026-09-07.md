# Research Addendum — 2026-09-07

> 本文件只记录 2026-08-19 原始 L0–L3 研究之后的新证据、时效变化和适用边界。  
> **不回写历史快照。** 原文保留“当时知道了什么”，本增补记录“截至 2026-09-07 哪些地方需要更新或收窄”。

## A. L0 Pricing：从静态价表升级到价格函数

### A1. OpenAI：长上下文已经出现请求级非线性定价

2026-09-07 官方 GPT-5.6 Sol 页面给出的基础价格：

- input: `$4 / 1M tokens`
- cached input: `$0.4 / 1M tokens`
- output: `$20 / 1M tokens`
- cache write: 基础 input 的 `1.25x`

当 input 超过 `272K` tokens 时，官方注明整个请求采用：

- `2x` input price
- `1.5x` output price

来源：https://developers.openai.com/api/docs/models/gpt-5.6-sol

这意味着 L0 不能长期只维护：

```text
provider -> (p_in, p_cache, p_out)
```

更一般的形式应为：

```text
price = f(provider, model, input_length, cache_state,
          cache_write, storage_time, service_tier, region, time)
```

`model.py` 已加入一个可选的 long-context tier 结构，用于表达这一类非线性，不声称覆盖所有 provider 的全部阶梯。

### A2. Anthropic：cache-read 0.1x 已出现模型级例外

当前 Anthropic pricing 表中，Claude Fable 5.1 / Mythos 5.1 的 cache read 为基础输入的 `0.025x`，而 Sonnet 5 等当前模型通常仍为 `0.1x`；5m/1h cache-write 倍率继续按 1.25x / 2x 计。

来源：https://platform.claude.com/docs/en/about-claude/pricing

所以旧 L0 的“Anthropic 全线 0.1x”只能视为旧 snapshot，不再作为今天的统一规则。

### A3. Kimi `prompt_cache_key`：cache locality hint，不是命中保证

Kimi Chat API 当前文档将 `prompt_cache_key` 描述为用于缓存相似请求、优化命中率；coding agents 通常使用 session id 或 task id，恢复同一 session 时保持 key 不变。

来源：https://platform.kimi.com/docs/api/chat

这支持“稳定 session/task identity 有利于 cache locality”，但不支持：

> “固定 profile key 可以把请求钉在某个缓存桶并消除随机 miss。”

因此 L4 已将 profile-static key 降为待测策略。

---

## B. L1 Serving & KV：复用粒度继续下沉

### B1. 标准 KV 字节公式的适用边界

原 L1：

```text
2 * layers * kv_heads * head_dim * dtype_bytes
```

仍适合作为传统 MHA/GQA/MQA 的 reference formula。

但新模型/serving 体系还需要至少标注以下维度：

- Multi-head Latent Attention / latent KV；
- KV quantization；
- sliding/local attention；
- selective token/head/layer retention；
- cross-layer KV sharing；
- non-prefix / resource-level reuse。

因此不能从一个 LLaMA-family 例子直接外推所有现代模型的实际 cache footprint。

### B2. ReCache：agent tool/skill schema 的 resource-level KV reuse

**ReCache: Resource-Level KV Cache Reuse for Multi-Turn LLM Agents**（arXiv:2608.19662，2026-08-20）针对一个很具体的 agent 问题：

- tool / skill resources 在不同 turn 中可能选择不同子集、不同顺序；
- 普通 prefix caching 因 composition/order 变化而失去复用；
- ReCache 用 resource-wise attention 让每个资源的 KV 表征尽量与组合无关，再跨 turn 重组使用。

论文在其 Qwen/benchmark 设置下报告：

- invocation F1 基本维持（82.3 vs 82.4）；
- TTFT 最高/主要报告约 `3.655x` speedup；
- 完整系统还报告大幅降低 allocated KV tensor memory，并提高 attention speed。

来源：https://arxiv.org/abs/2608.19662

经济学意义：工具 schema 的优化不只有“删工具”和“稳定整个 prefix”两条路，还存在**独立资源复用**这一层。

---

## C. L2 Compression：质量损失不是一个标量

### C1. The Sleeping Agent：时间信息是独立脆弱维度

**The Sleeping Agent: What Gist-Based Context Compression Loses and Why**（arXiv:2608.11775）研究 gist-based context compression 的结构化损失。

论文的重要启示不是“gist compression 一定不好”，而是：

- 事件与关系可以被保留；
- 日期/时间表达可能被系统性丢失；
- 只在 compression prompt 中明确要求保留 temporal expressions，就能明显改善时间表达保留与 temporal QA。

来源：https://arxiv.org/abs/2608.11775

因此旧 `real_model.py` 用单一角色级 `q` 表示全部信息保留，只适合作为 sensitivity proxy。

后续质量至少按以下类别分桶：

```text
identifier/path/hash
number/unit
temporal/order
negative constraint
user intent
tool protocol
evidence/edit anchor
causal/relational structure
```

---

## D. L3 Harness → L5 Task Economics：少 token 可能更贵

### D1. Token Reduction Is Not Cost Reduction

arXiv:2607.12161 使用 provider-billed、配对 coding-agent runs 直接比较 context/tool-output reduction 与实际账单。

论文分析 2,848 个 runs、103 tasks、7 repos、3 models；其中一条实验臂虽然减少约 38% raw tool-output tokens，配对 provider cost 反而约增加 6.8%。论文同时指出 prompt cache creation/read 和 edit anchors 等机制会改变最终经济性。

来源：https://arxiv.org/abs/2607.12161

结论边界：这是论文特定 agent/任务/模型条件下的结果；本仓库只吸收方法论——**不要把 token removed 当 bill saved 的代理。**

### D2. What Does Context Compression Cost an Agent?

arXiv:2608.16370 将注意力放在 execution-state reacquisition：task completion 可能统计上相近，但被压缩掉的工作状态会通过额外 retrieval/tool calls 重新获取。

来源：https://arxiv.org/abs/2608.16370

因此 L5 单独记录：

```text
retrieval_calls
reacquisition_calls
retry_count
```

不能只记录压缩后的 prompt 长度。

### D3. Control Under Compression

arXiv:2608.01056 在 15,525 个 agent runs 上研究 control context 的压缩可靠性。低保留率下，主要失败包括 tool execution 和 action parsing；不同 control context 的容忍度差异很大。

来源：https://arxiv.org/abs/2608.01056

这进一步反驳“一个全局 r/theta 对所有内容都最优”的假设。

---

## E. Hermes runtime 勘误：memory snapshot 与 compaction 要分开

2026-09-07 对 Hermes 当前上游文档/源码的核查显示：

- `MEMORY.md` / `USER.md` 在 session start 形成 frozen system-prompt snapshot；
- mid-session memory write 持久化到磁盘，但当前 session system prompt 不立即变化；
- compaction / session rebuild 等路径会重新构造上下文，属于另一个 cache-impact 问题。

因此旧 L4 的“每次中途写 memory 都使下一轮整段 history re-prefill”已经撤回。

本轮观察的 Hermes code-search source snapshot 与路径记录在 `PROVENANCE.md`。

---

## F. 研究层级的新验收规则

从本增补起，所有“策略更好”的声明按以下顺序升级：

```text
analytic
 -> simulation
 -> trace-replay
 -> runtime-A/B
 -> task-economic
```

其中：

- `analytic` 只证明公式在假设下成立；
- `simulation` 可以使用 synthetic data；
- `trace-replay` 可以使用真实历史流量，但策略和质量仍可能是模拟；
- `runtime-A/B` 要真实重跑 provider/harness；
- `task-economic` 还必须同时记录 task success、账单、interaction/retry/latency。

这也是新增 `task_economics.py` 与 run-receipt schema 的原因。
