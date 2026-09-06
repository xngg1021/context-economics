# L4 记忆、档案与持久状态的上下文经济学

> 原始研究：2026-08-19 · SJF × Hermes  
> correctness hardening：2026-09-07  
> 本层连接 THM 的常驻/按需记忆问题与 Context Economics 的 provider/harness 成本模型。

本文件保留 2026-08-19 的本机测量，但把“本机测量”“当前 Hermes 源码行为”“provider 文档”和“模型推导”严格分开。旧版最重要的勘误是：**普通 mid-session memory write 不再被视为必然触发当前会话 prompt-cache 失效。**

## 一、T0 的驻留租金：保留原测量，但不把“租金小”解释成“容量不重要”

2026-08-19 三 profile 本地测量：

| profile | MEMORY.md | USER.md | 合计字符 | 估算 token | 每轮租金（$0.3/M 命中） | 每轮租金（$3/M 未命中） |
|---|---:|---:|---:|---:|---:|---:|
| P1 | 3,744 | 1,201 | 4,945 | ≈2,322 | $0.00070 | $0.00697 |
| P2 | 0 | 541 | 541 | ≈254 | $0.00008 | $0.00076 |
| P3 | 0 | 211 | 211 | ≈99 | $0.00003 | $0.00030 |

这里的 token 是按当时 `real_model.py` 的 2.13 chars/token aggregate calibration 推算，不是 tokenizer ground truth。

局部租金公式仍成立：

```text
rent_per_turn = resident_tokens * p_eff
p_eff = (1-rho)*p_in + rho*p_cache
```

但“热层美元租金很小”只回答 **billing**。它没有回答：

- 条目是否过期；
- 是否与别的 profile/环境冲突；
- 是否挤占更有价值的事实；
- 是否制造注意力干扰；
- 是否让模型错误泛化；
- 用户明确禁止/偏好是否被保真。

因此，**T0 容量约束仍然重要，只是它主要是认知与正确性约束，而不一定是美元约束。**

### 预算来源

Hermes 上游默认值曾为 `MEMORY.md 2200 chars / USER.md 1375 chars`，可被配置覆盖；本机配置历史上出现过更高运行时预算。公开文档不得把某次本机 override 写成 universal default。

具体运行预算应由当时版本的 memory tool / config 读取，并与 exact Hermes revision 一起记录。

## 二、关键勘误：普通 memory write ≠ 当前 session prompt rebuild

当前 Hermes 文档/源码说明：

> `MEMORY.md` 与 `USER.md` 在 session start 被捕获成 frozen system-prompt snapshot。中途 memory tool 写入会立即落盘，但不会改写当前 session 已冻结的 system prompt；新的快照在之后的 session start（以及会重新构建 prompt 的特定路径）生效。

所以旧版链条：

```text
memory write
 -> volatile system-prompt bytes change
 -> next request prefix changes
 -> all conversation history re-prefill
```

对当前 Hermes **不成立**。

当前应写成两条独立链：

```text
A. ordinary mid-session memory write
   -> persistent memory changes
   -> current frozen prompt bytes unchanged
   -> no cache-break claim can be inferred

B. prompt rebuild event
   -> system prompt / summarized history may change
   -> provider cache boundary may change
   -> cache impact must be measured from actual request/usage telemetry
```

典型 B 类事件包括：新 session、compaction 后的 prompt rebuild、明确的 prompt config/toolset/model change，或其他会改变 serialized request prefix 的 runtime 行为。

### 历史 `$0.27 / $0.54 / $1.22` 表怎么处理？

旧版用：

```text
opportunity_cost ~= H * (p_in - p_cache)
```

计算 100K / 200K / 450K 历史重新 prefill 的机会成本。

这个算式可以保留为一个**假设整段 dynamic context 从 cached -> uncached 时的 scenario upper-bound**；它不能再标注为“写一次 memory 的成本”。

如果以后取得真实 provider trace，可以做：

```text
same-session control
vs
prompt-rebuild treatment
```

直接比较 `cache_read_tokens / uncached_input_tokens / total bill / TTFT`。

## 三、Hermes prompt assembly：stable / volatile 是 cache 设计，不等于全局 recency 优势

Hermes 的 system prompt 具有 stable 与 volatile 分层，memory/user 块属于 volatile 部分。这有两个可以安全保留的结论：

1. **cache boundary 价值**：稳定的大块放在前面，使一部分静态 prefix 更容易复用。
2. **memory 是 prompt 的明确组成部分**：它不是散落在磁盘但从不进入模型的旁路状态。

旧版第三个推论需要撤回：

> “memory 在全提示词尾部，所以自然获得 lost-in-the-middle 的近因优势。”

memory 位于 **system prompt 的 volatile 尾部**，后面仍然可以有很长的 conversation history。它在整个 model input 中未必接近末端，因此不能仅凭 system-prompt 内部位置推出全局 recency advantage。

正确的验证方式是对具体 request serialization 记录 token offset，再跑位置敏感任务 A/B。

## 四、`prompt_cache_key`：routing/caching hint，不是命中保证

Kimi 当前 Chat API 文档说明：

- `prompt_cache_key` 用于缓存相似请求、优化缓存命中；
- coding agent 通常使用 session id 或 task id；
- 恢复同一 session 时应保持不变；
- 对 Kimi Code Plan 为必填，对其他多轮 agent 也建议使用。

来源：https://platform.kimi.com/docs/api/chat

因此：

```text
profile-static-key
```

可以作为一个实验策略，但不能描述成：

> “把全部流量钉进同一缓存桶，消除随机 miss”。

它更准确的表述是：

> “给 provider 一个稳定的相似请求 key，期望提高路由/cache locality；真实增益必须由 usage telemetry A/B 验证。”

而且 key 粒度过粗可能把不相关 session 混进同一个 routing bucket，所以优先候选通常应是 session/task identity，而非永久 profile identity。

## 五、Memory 与 THM：把租金、活跃度、正确性和任务价值分开

Context Economics 不应该把 THM 的 activity score 直接当成“价值”。

建议四个量分开：

| 量 | 问题 |
|---|---|
| `resident_cost` | 常驻它每轮花多少钱/token |
| `activity` | 最近是否被读取/使用/确认 |
| `validity` | 当前时间、版本、对象、环境下是否仍成立 |
| `task_value` | 缺少它会不会显著降低任务成功或增加重取成本 |

一个极少被复述的禁止事项可能 activity 很低，但 task_value 很高；一条经常出现的旧路径可能 activity 高、validity 已为零。

因此容量优化更合适的目标是：

```text
expected_net_value(item)
= expected_task_value
- resident_cost
- interference_cost
- stale/error_risk
```

其中 task value 最终需要 L5 的受控任务或真实结果 telemetry，而不能只由 hit count 自循环生成。

## 六、认知科学：保留设计类比，收窄推导强度

### Cowan (2001)

Cowan 对短时/工作记忆容量的经典讨论常被概括为约 `4±1` chunks。对本系统最稳妥的启发是：

> 持续占据前景的独立信息单元有限，结构化与组块化可能提高有效利用率。

它不能推出：

- Hermes 应该恰好有几个字符预算；
- LLM system prompt 的“chunk”与人类 working-memory chunk 等价；
- 只要把多个事实合并成一条就一定提高模型正确率。

### Peterson & Peterson (1959)

经典短时保持实验表明，在阻断复述的任务条件下，人类对材料的保持会快速下降。它可以支持“近因和复核频率值得研究”的启发，但不能直接给 agent memory 的 decay 参数或驱逐周期。

因此这两项继续作为 `design analogy`，不作为配置参数的实证标定。

## 七、当前可执行的 L4 实验

### 1. prompt rebuild cache A/B

记录同一 provider / model / toolset：

- control：连续普通 turn；
- treatment A：mid-session memory write，但不重建 session；
- treatment B：触发实际 prompt rebuild；
- treatment C：新 session 读取新 memory snapshot。

比较：

```text
cached_input_tokens
uncached_input_tokens
cache_write_tokens (if billed)
bill
TTFT
```

### 2. memory position A/B

同一事实分别放在：

- stable/volatile system section；
- recent conversation tail；
- retrieved on demand；

控制 token budget，测事实 QA 与任务成功，而不是只测“模型有没有复述”。

### 3. profile key A/B

比较：

- no prompt_cache_key；
- session/task key；
- profile-static key；

按 session 长度分桶，观察 cache hit、p95 TTFT、错误率和账单。未测之前不宣布哪个 key 粒度最优。

## 八、与 L5 的接口

L4 负责“长期状态该不该常驻/如何进入上下文”，L5 负责把实际后果计价：

```text
memory omission
 -> tool/file/database reacquisition
 -> extra turns
 -> extra token/tool/latency cost

stale memory
 -> wrong action / retry / correction
 -> failure cost
```

所以最终 T0 决策不应只优化 resident token 数，而应优化 **success-adjusted task cost**。

参见：`L5-task-economics.md`。

---

## 来源与版本说明

- Hermes memory frozen snapshot：当前上游文档 `website/docs/user-guide/which-file-does-what.md` 与 memory/system-prompt 实现；本轮 code search 观察到的上游代码快照记录于 `PROVENANCE.md`。
- Kimi `prompt_cache_key`：https://platform.kimi.com/docs/api/chat
- Cowan, N. (2001), *The magical number 4 in short-term memory: A reconsideration of mental storage capacity*.
- Peterson, L. R. & Peterson, M. J. (1959), *Short-term retention of individual verbal items*.
- 本机 2026-08-19 profile 字符量是历史 `runtime-measured` 数据；私人原始 memory/state.db 未进入公开仓库。
