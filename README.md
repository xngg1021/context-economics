# 大模型上下文经济学（Context Economics）

> 起始研究：2026-08-19，SJF × Hermes  
> correctness hardening：2026-09-07  
> 当前研究对象：LLM / agent 在“输入、缓存、压缩、工具、记忆、重试、延迟和任务成功”之间的成本—质量权衡。

本仓库把上下文视为一种会被反复携带、缓存、压缩、重取和重新计算的运行资产。它不是单纯的“省 token 指南”，目标是把 **provider 定价 → serving/KV → 压缩算法 → harness 调度 → 持久记忆 → 任务经济学** 放进同一个可验证框架。

## 0. 证据纪律

仓库从 2026-09-07 起统一区分五类证据：

| 标签 | 含义 |
|---|---|
| `runtime-measured` | 本机或 provider 真实运行测量；必须记录时间、版本、口径 |
| `source-code` | 从指定软件版本源码确认的行为 |
| `provider-doc` | 厂商官方定价/API/机制说明；属于快衰减信息 |
| `paper-result` | 论文在其特定实验条件下报告的结果 |
| `model-proxy` | 本仓库模型假设推导出的代理指标；不能冒充真实正确率/召回率 |

`PROVENANCE.md` 记录本轮版本身份和来源边界；`pricing-snapshot.json` 保存定价快照。历史底稿中的旧数字继续保留，但不得无时间戳地当作实时价格。

## 1. 六层结构

```text
L0 Pricing
   厂商如何收费：uncached input / cached input / cache write / storage / output /
   long-context tier / batch / priority / time-of-day

L1 Serving & KV
   prefill、KV cache、prefix/non-prefix reuse、HBM/DRAM/SSD、schema/resource reuse

L2 Compression
   文本删减、摘要、soft token、外部化、RAG、内容类型化保真

L3 Harness
   prompt assembly、tool schema、subagent、compaction、cache-stable scheduling、
   context rebuild / reacquisition

L4 Memory & Profile
   frozen memory snapshot、长期驻留租金、版本/来源、profile 隔离、持久状态

L5 Task Economics & Observability
   billed cost + tool/reacquisition/retry/latency/failure + task success
```

L0–L3 文件是 2026-08-19 的原始研究底稿；L4 已在 2026-09-07 按当前 Hermes 行为校正；L5 是本轮新增的闭环层。

## 2. 核心成本模型

在最简单的固定价、固定 cache-hit share `rho` 条件下，第 `k` 轮：

```text
cost_k = C_k * p_eff + o_k * p_out
p_eff  = (1-rho) * p_in + rho * p_cache
```

若每轮新增历史近似为常数 `d`，且请求每轮重发全部历史：

```text
C_k ~= S + k*d
sum(C_k) = N*S + d*N*(N+1)/2
```

因此，**在这些条件成立时**，不管理历史的累计输入携带量含 `O(N^2)` 项。这里的“平方项”是工作负载性质，不应扩写成所有 agent、所有 provider、所有窗口策略的无条件定律：固定窗口截断、RAG、分页、非线性长上下文定价、失败重试和模型路由都会改变曲线。

### 缓存与压缩的局部替代关系

把中间区 `M` 压成 `r*M`，在固定价格和固定命中率近似下：

```text
N* = (p_in + r*p_out) / ((1-r)*p_eff)
```

`M` 可以约掉，所以在这个**局部模型**里 cache 越便宜，携带原文的边际价格越低，压缩的账单回本越慢。

这不代表缓存与压缩在任务层永远互为替代。压缩可能减少 lost-in-the-middle，也可能删除 action-critical state、导致更多工具重取和重试；到 L5 后两者可以出现互补或非单调关系。

## 3. `model.py`：确定性成本模型

直接运行：

```bash
python model.py
```

当前代码做了三项 correctness 修正：

1. `target_ratio` 按 Hermes legacy 语义只用于 recent-tail budget：

   ```text
   tail_budget = target_ratio * threshold * context_window
   ```

   不再把它同时当成“摘要大小比例”。

2. “成本最优 theta”不再由有限 grid 的最小端点冒充全局 optimum。当前成本模型在质量成本为零时往往偏好更激进压缩，所以输出只报告：

   > lowest-cost point in THIS GRID

3. `Pricing` 支持长上下文非线性档位。以 2026-09-07 OpenAI GPT-5.6 Sol 官方页为例，输入超过 272K tokens 后整个请求使用 2x input / 1.5x output 价格，因此真实 provider cost 不能永远写成一个常数 `p_in`。

历史 Kimi study snapshot 仍保留 `$3 / $0.3 / $15`，用于复现 2026-08-19 的研究结果，不自动代表今天的 live quote。

## 4. `real_model.py`：真实 trace + 代理质量模型

### 可公开复现

```bash
python real_model.py --fixture fixtures/sample_sessions.json
```

### 对本机 Hermes SQLite 做只读重放

```bash
python real_model.py \
  --db default=/path/to/state.db \
  --db other=/path/to/other/state.db
```

脚本不再硬编码私人 Windows 路径。

重要边界：

- message 顺序、长度、模型标签、账单累计 input/cache token 可以来自真实 trace；
- 字符/token 校准、摘要信息保留率、长上下文退化、回指概率、failure line 仍然是模型假设；
- 所以输出字段明确命名为 `proxy_final_recall`、`proxy_integrity`、`proxy_ux_failures`。

旧 README 中“0.998 终态召回”“30–45 万上下文已经被压缩反向提质”等表述，现统一降格为**给定假设下的 sensitivity result**。要升级成 `runtime-measured`，必须在相同模型、相同任务、相同预算上跑真实 A/B。

## 5. Hermes 语义修正

2026-09-07 核查到的当前 Hermes 上游文档/源码表明：

> `MEMORY.md` / `USER.md` 在 session start 形成 frozen system-prompt snapshot；中途写入立即持久化，但不会改写当前会话已冻结的 system prompt。

因此旧 L4 中：

> “中途 memory write → 下一轮整个历史重新 prefill → 20 万 token 约 $0.54”

不能继续作为当前 Hermes 的既定事实。

现在的正确模型是：

```text
ordinary mid-session memory write
    -> disk state changes
    -> current frozen prompt unchanged
    -> current-session prompt-cache break: not implied

session rebuild / compaction / new session / other prompt rebuild
    -> prompt bytes may change
    -> cache impact depends on provider + exact serialized request
```

所以“批量写 memory”仍可能有一致性/维护价值，但不能再以“每次写都会烧掉整段 KV cache”为理由。

此外，Kimi 的 `prompt_cache_key` 官方 API 文档把它描述为提高相似请求缓存命中率的 routing/caching hint，并建议 coding agent 使用 session id 或 task id；固定 profile key 可以作为实验，但不能声明“消除随机 miss”。

详见 `L4-memory-profile.md`。

## 6. L0：定价层的新边界

原 L0 的 8 家厂商表保留为 **2026-08-19 snapshot**。2026-09-07 已经出现足以否定“单一倍率永远成立”的新例子：

- OpenAI GPT-5.6 Sol：`$4 input / $0.4 cached / $20 output`；输入 >272K 时整个请求 2x input、1.5x output；cache write 1.25x。
- Anthropic Claude Fable 5.1 / Mythos 5.1：cache read 为 base input 的 **0.025x**，而其他当前模型通常仍是 0.1x。
- 部分 provider 还叠加 cache storage、Batch、Priority、区域或时间档位。

所以 L0 后续的正确抽象应接近：

```text
p = f(provider, model, input_length, cache_state, cache_write,
      storage_time, service_tier, region, time)
```

而不是一张永久静态价表。

当前可机器读取的示例放在 `pricing-snapshot.json`。

## 7. L1：系统层补充

标准 KV 大小公式：

```text
2 * layers * kv_heads * head_dim * dtype_bytes
```

对传统 MHA/GQA/MQA 是很好的 reference formula，但不能被当作现代所有模型的普适 KV 成本。现代 serving 还要考虑：

- MLA / latent KV；
- KV quantization；
- sliding/local attention；
- token/head/layer selective retention；
- cross-layer KV sharing；
- resource/schema 级独立复用。

2026-08-20 的 **ReCache**（arXiv:2608.19662）直接针对 agent 工具/skill schema 在不同组合、不同顺序下导致普通 prefix cache 无法复用的问题：resource-wise attention 让资源产生 composition-invariant KV blocks，论文报告 3.655x TTFT speedup，并进一步压缩 KV tensor memory。这个工作应与 Prompt Cache / CacheBlend 一起看，而不是只把工具 schema 当“固定前缀租金”。

来源：https://arxiv.org/abs/2608.19662

## 8. L2：压缩层补充

压缩质量不应只用一个总 recall 数字表示。

**The Sleeping Agent: What Gist-Based Context Compression Loses and Why**（arXiv:2608.11775）给出了很直接的失败类型：gist compression 可以保存事件/关系结构，却大量丢失日期和时间；仅修改一句保留 temporal expressions 的 prompt，就显著提高时间表达保留和 temporal QA。

这说明：

```text
quality_loss != one scalar
```

至少要分：

- exact identifiers / paths / numbers；
- dates / ordering / temporal constraints；
- user intent / prohibitions；
- tool protocol / arguments；
- causal / relational structure；
- raw evidence / edit anchors。

来源：https://arxiv.org/abs/2608.11775

## 9. L5：从 token economics 闭环到 task economics

新增 `L5-task-economics.md`。

2026 年的三组研究已经直接指出“少 token”与“少钱/高成功率”之间没有一一对应关系：

- **Token Reduction Is Not Cost Reduction**（arXiv:2607.12161）：2,848 个 provider-billed 配对 coding-agent runs 中，某一方案减少约 38% raw tool-output tokens，却使配对账单成本增加约 6.8%；作者建议用 success-adjusted billed cost。
- **What Does Context Compression Cost an Agent?**（arXiv:2608.16370）：task completion 可能近似不变，但被压掉的执行状态会通过更多 retrieval/reacquisition tool calls 重新买回来。
- **Control Under Compression**（arXiv:2608.01056）：agent control context 压缩存在明显 reliability frontier，低保留率时失败主要表现为 tool execution / action parsing。

因此最终目标函数升级为：

```text
J(policy) =
    E[task_value]
  - E[token_bill
      + tool_cost
      + reacquisition_cost
      + retry_cost
      + latency_cost
      + failure_cost]
```

真正有意义的 `theta*` 应该在这个层面出现。

## 10. L4：记忆层的当前结论

T0 长期驻留租金仍然可以按：

```text
rent_per_turn = resident_tokens * effective_input_price
```

计算；但“装满是否值得”是 **注意力、正确性、冲突、可更新性、隐式遵循和缺失代价**共同决定的问题，不能因为美元租金小就忽略容量约束。

Cowan / Peterson 的人类认知研究只作为“工作记忆有限、组块化可能提高有效利用率”的设计类比；它们不提供 Hermes 的具体字符预算，也不证明 agent 的最优 T0 容量。

## 11. 可复现性与 CI

仓库不依赖第三方 Python 包。

```bash
python -m unittest discover -s tests -v
python model.py
python real_model.py --fixture fixtures/sample_sessions.json
```

GitHub Actions 在 Python 3.11 / 3.13 上执行同一套检查。

公开 fixture 是合成数据，不包含私人 `state.db`、记忆内容或 profile 原文。

## 12. 仓库结构

```text
README.md
L0-pricing.md
L1-systems.md
L2-compression.md
L3-harness.md
L4-memory-profile.md
L5-task-economics.md

model.py
real_model.py
pricing-snapshot.json
PROVENANCE.md

fixtures/sample_sessions.json
tests/test_model.py
tests/test_real_model.py
.github/workflows/validate.yml
```

## 13. 当前仍未解决的问题

1. 为 Hermes 当前 compressor 做 **exact-version replay**：不能只复刻 threshold/tail 数字，还要固定 summary budget、tail mode、protected messages 和 prompt rebuild 路径。
2. 对真实 Kimi / 其他 provider 记录 per-request billing trace，而不是只用 session aggregate。
3. 用真实任务 A/B 校准 `quality_loss`，替换 `real_model.py` 中的 proxy retention curve。
4. 将 tool/reacquisition/retry/latency 纳入同一 run ledger。
5. 研究不同内容类型的 retention policy，而不是单一 `r`。
6. 对 L0 pricing snapshot 做定期刷新；快衰减信息不能永久写死在理论结论里。

---

## 主要新增来源（2026-09-07 hardening）

- OpenAI GPT-5.6 Sol model/pricing: https://developers.openai.com/api/docs/models/gpt-5.6-sol
- Anthropic pricing / prompt caching: https://platform.claude.com/docs/en/about-claude/pricing
- Kimi Chat API (`prompt_cache_key`): https://platform.kimi.com/docs/api/chat
- LongMemEval: https://arxiv.org/abs/2410.10813
- ReCache: https://arxiv.org/abs/2608.19662
- Token Reduction Is Not Cost Reduction: https://arxiv.org/abs/2607.12161
- What Does Context Compression Cost an Agent?: https://arxiv.org/abs/2608.16370
- Control Under Compression: https://arxiv.org/abs/2608.01056
- The Sleeping Agent: https://arxiv.org/abs/2608.11775

更早 L0–L3 文献继续保留在各层底稿中。
