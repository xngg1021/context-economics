# L5 Task Economics & Observability：从“省 token”到“单位成功任务成本”

## Runtime receipt addendum — 2026-09-07

`context_runtime.py` now derives L5 receipts from request-, tool-, compression-,
and outcome-level events. Each provider bill carries a source and an explicit
`observed` or `estimated` status; scorer identity/version and human/automatic/
benchmark provenance are preserved. Token totals, request order, timestamps,
IDs, and run/task/policy isolation fail closed. See `RUNTIME-INSTRUMENTATION.md`.

`experiment_analysis.py` reports paired distributions rather than only mean
deltas and evaluates cost per success jointly with quality, reacquisition,
latency, pollution, and staleness gates. These gates nominate a candidate only.

账本 v2 仅把 provider/tool/external/latency/failure 的互斥费用相加。重取与重试费用是归因子集；若已经在 provider/tool 中计费，不重复加入总成本。历史 v1 必须显式声明；public fixtures 已将旧独立分类费用迁移到 external。实验 gate 的所有性能聚合仅使用 exact paired cohort，覆盖率单独约束证据资格。

> 新增：2026-09-07  
> 本层是 Context Economics 的闭环层。L0–L4 描述价格、KV、压缩、harness 和 memory；L5 回答最终问题：**一个 context policy 是否真的让任务更便宜、更快、更可靠。**

## 一、为什么 token reduction 不是目标函数

agent 的真实成本不止是 prompt tokens。

一个过度压缩的 agent 可能：

- 少发 30% tool output；
- 但重新 `read_file` / `search` / `grep` 更多次；
- 多走几轮 tool loop；
- 丢掉 edit anchor 后 patch 失败；
- 触发重试；
- 最后 provider bill 更高。

所以：

```text
tokens_removed > 0
```

不推出：

```text
bill_saved > 0
```

更不推出：

```text
cost_per_success_saved > 0
```

### 2026 年直接证据

**Token Reduction Is Not Cost Reduction**（arXiv:2607.12161）：

- 预注册、hash-frozen、provider-billed 的 Claude Code 配对实验；
- 分析 2,848 runs、103 tasks、7 repos、3 models；
- 一条实验臂减少约 38% raw tool-output tokens，但配对成本反而增加约 6.8%；
- prompt-cache creation/read 是账单的重要组成；
- 压缩 edit anchors 还会伤害 patch application。

来源：https://arxiv.org/abs/2607.12161

**What Does Context Compression Cost an Agent?**（arXiv:2608.16370）：

- completion rate 可以统计上近似不变；
- 但压掉 execution-relevant state 会让 agent 增加 retrieval / reacquisition calls；
- 这种“把状态重新买回来”的成本，单看 completion 看不见；
- 论文也观察到环境依赖：并非所有任务都出现同样 reacquisition surge。

来源：https://arxiv.org/abs/2608.16370

**Control Under Compression**（arXiv:2608.01056）：

- 把 agent control context 当可执行协议而非普通文本；
- 15,525 runs 显示明显 reliability frontier；
- 低 retained-context budget 时，失败主要表现为 tool execution 与 action parsing；
- 不同 control context 的容忍度差异很大，因此不存在一个全局万能压缩率。

来源：https://arxiv.org/abs/2608.01056

## 二、目标函数

对 policy `pi`，推荐使用：

```text
J(pi) =
    E[task_value]
  - E[C_token
      + C_cache_write
      + C_cache_storage
      + C_tool
      + C_external
      + C_latency
      + C_failure]
```

如果任务价值很难货币化，可以先保持多目标报告，不强行把所有维度换成美元：

```text
success_rate
cost_per_success
mean_bill
p50 / p95 latency
tool_calls
reacquisition_calls
retry_count
compression_calls
cache_hit_share
```

### `cost_per_success`

一组 runs 的最简单定义：

```text
cost_per_success = sum(observed_cost) / number_of_successes
```

它比：

```text
mean_cost_per_run
```

更能揭示“便宜但失败”的策略。

如果 success=0，`cost_per_success` 不应返回一个漂亮有限数字，应报告 undefined / infinity。

## 三、真正的 theta* 在这里产生

旧的纯 token 模型中：

```text
lower theta
 -> earlier/more compression
 -> less repeated context
```

如果完全不给信息损失、reacquisition、tool failure 定价，那么最优点很容易一路向更激进压缩移动；在有限 grid 中把最小测试点叫 `theta*` 是错误的。

加入 L5 后：

```text
theta too high
 -> repeated-context bill / long-context degradation

theta too low
 -> compression calls
 -> state loss
 -> reacquisition
 -> tool protocol loss
 -> retries / failures
```

总成本曲线才有机会出现内部最优点。

所以后续任何“最优 threshold”都至少要同时报告：

```text
token bill
task success
reacquisition
retry
latency
```

## 四、Observability：必须记录什么

建议每次真实 agent run 生成一个结构化 receipt。

最小 schema：

```json
{
  "run_id": "...",
  "task_id": "...",
  "policy_id": "...",
  "provider": "...",
  "model": "...",
  "model_revision": "...",
  "harness_revision": "...",
  "started_at": "...",
  "ended_at": "...",

  "success": true,
  "task_score": 1.0,

  "input_tokens": 0,
  "cached_input_tokens": 0,
  "cache_write_tokens": 0,
  "output_tokens": 0,
  "provider_bill_usd": 0.0,

  "tool_calls": 0,
  "retrieval_calls": 0,
  "reacquisition_calls": 0,
  "retry_count": 0,
  "compression_calls": 0,

  "ttft_ms": null,
  "wall_time_ms": 0,

  "failure_class": null,
  "notes": []
}
```

### 为什么要保存 revision

下面四个变化都会让历史数字失去可比性：

- model revision；
- harness compression algorithm；
- provider caching semantics；
- pricing tier。

所以 run receipt 必须和 `PROVENANCE.md` / `pricing-snapshot.json` 一样版本化。

### 当前 receipt parser 的故障安全边界

`task_economics.py` 现在把上面的 schema 当作数据合同，而不是宽松 JSON：

- `success` 必须是真正 boolean，字符串 `"false"` 不会被 Python truthiness 错算为成功；
- 未知字段直接失败，避免 `provider_bil_usd` 之类 typo 被静默丢弃；
- `run_id` 必须唯一；
- token、call、cost、latency 必须是有限且非负的对应类型；
- 当前 schema 下 `cached_input_tokens <= input_tokens`；
- `reacquisition_calls <= retrieval_calls`；
- pairing report 显式报告 missing arm、duplicate arm 与 paired coverage，不把未配对任务静默藏掉。

聚合结果同时给出 token/cache、task score、p50/p95 TTFT/wall time 和 failure-class 计数。CLI 输出仍标记为 `observed-run-receipts-not-causal-inference`：严格 schema 只能提高数据完整性，不能替代实验设计。

## 五、reacquisition 怎么定义

不能把所有 retrieval 都算成“压缩造成的重取”。

建议分：

```text
planned retrieval
    任务本来就需要的查找

reacquisition
    某状态此前已经存在于 agent working context，
    因截断/压缩/会话迁移缺失后再次获取

retry retrieval
    前一次读取/调用失败或返回不完整后再次获取
```

最好用 deterministic task/environment instrumentation 标记；无法判断时记录 `unknown`，不要靠模型事后自报硬判。

## 六、质量损失必须类型化

**The Sleeping Agent**（arXiv:2608.11775）显示 gist compression 的信息损失具有结构：事件/关系可能保留，时间表达却严重丢失；一个针对 temporal expression 的 prompt 修改可以显著修复 temporal QA。

来源：https://arxiv.org/abs/2608.11775

因此 quality loss 至少按内容类型拆分：

| 类型 | 典型故障 |
|---|---|
| identifiers / paths / hashes | patch / lookup 找不到对象 |
| numbers / units | 参数或计算错误 |
| temporal | 版本先后、截止日期、事件顺序错误 |
| negative constraints | 把“不要做 X”压成“做 X” |
| user intent | 任务目标漂移 |
| tool protocol | argument / sequencing / schema 失败 |
| evidence | 无法回到原文或 edit anchor |

一个单一 `q=0.85` 可以做 sensitivity analysis，但不能代表真实 compressor 的统一保真率。

## 七、缓存本身也要进入 task economics

L0 的 `p_eff` 是起点，不是终点。

例如：

- cache read 很便宜，可能让保留长 context 比频繁 summary 更划算；
- cache write 收费，短 session 可能来不及摊销；
- 进入 long-context tier 后整个请求突然变贵，阈值会出现价格不连续；
- compaction 改写 prompt 后可能破坏部分缓存；
- provider 可能用 `prompt_cache_key` / implicit routing 做 best-effort locality。

因此真实实验应记录 provider 返回的：

```text
cached_input
uncached_input
cache_creation/write
storage (if explicit)
```

不要用“假设 rho=0.85”替代最终验收。

## 八、工具/schema 不是只有 token 租金

L3 已观察到 tool/MCP schema 可能成为固定前缀的重要组成。

2026-08-20 **ReCache**（arXiv:2608.19662）进一步说明：agent 的 tool/skill schema 经常以不同组合和顺序出现，普通 prefix cache 因此无法复用；resource-wise independent encoding 可以构造可复用 KV blocks。论文报告在其 Qwen/benchmark 条件下 3.655x TTFT speedup，并显著降低 KV tensor memory。

来源：https://arxiv.org/abs/2608.19662

这给 L3/L5 一个新决策轴：

```text
不是只有“删不删工具”
还包括“能否独立缓存/路由/按需暴露工具”
```

## 九、推荐实验设计

### A. compression threshold sweep

固定：

- tasks；
- provider/model revision；
- temperature/seed（若接口支持）；
- toolset；
- cache policy；
- max turns。

比较：

```text
no compression
theta 0.50
theta 0.30
theta 0.20
theta 0.15
theta 0.12
theta 0.08
```

每档至少报告：

```text
success
provider bill
tool calls
reacquisition
retry
latency
```

### B. cache × compression factorial

不要只单独扫 theta。

至少：

```text
cache high / low
x
compression on / off
```

用于检查缓存与压缩在**任务层**究竟是替代还是互补。

### C. content-type stress suite

人为构造：

- 路径和 commit SHA；
- 数字/单位；
- 时间线；
- 多 profile 同名事实；
- 否定约束；
- tool argument protocol；
- 可重取的大 tool output；
- 不可重取的用户意图。

测哪些内容可以激进压、哪些必须保留。

## 十、验收等级

| 等级 | 可以声称什么 |
|---|---|
| `analytic` | 公式在假设下成立 |
| `simulation` | synthetic model/fixture 结果 |
| `trace-replay` | 真实历史 trace + 模拟 policy |
| `runtime-A/B` | 同环境真实 provider/harness 对照 |
| `task-economic` | 同时覆盖 success + billed cost + interaction/retry/latency |

只有最后两级才能支持：

> “这个策略在当前生产负载下更省钱/更可靠。”

---

## 主要来源

- Token Reduction Is Not Cost Reduction — https://arxiv.org/abs/2607.12161
- What Does Context Compression Cost an Agent? — https://arxiv.org/abs/2608.16370
- Control Under Compression — https://arxiv.org/abs/2608.01056
- The Sleeping Agent — https://arxiv.org/abs/2608.11775
- ReCache — https://arxiv.org/abs/2608.19662
