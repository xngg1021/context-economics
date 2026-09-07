# L6 Adaptive Context Control：Admission、Residency、Prefetch 与 Budget Control

> Runtime successor status (2026-09-07): provider adapters are fixture-tested; credential-backed evidence is BLOCKED by runtime authorization. Expanded Hermes component trace-replay and deterministic retention-task fixtures do not establish runtime-A/B or task-economic results. Production mutation remains disabled. See [REAL-RUNTIME-CAMPAIGN.md](REAL-RUNTIME-CAMPAIGN.md).

## Calibration addendum — 2026-09-07

`controller_calibration.py` adds offline replay calibration for the existing
shadow vector controller. A parameter grid is selected only on `train` task IDs
and evaluated on disjoint `holdout` task IDs; overlap fails and small samples
return `insufficient evidence`. The replay objective measures distance to a
caller-supplied target budget, so even a low holdout loss is not evidence that
the target improves task success or cost. There is no auto-enable path.

ARC and TinyLFU remain systems analogies: ARC is an online adaptive replacement
algorithm, not ML training; TinyLFU's transferable principle is that admission
and replacement are separate decisions. Neither paper establishes an LLM law.

Calibration 的每个 grid candidate 均走生产 `ControllerPolicy.from_mapping`；step fractions、deadband 必须在 [0,1] 且 base <= max。任何非法候选 fail-fast，不通过跳过候选隐藏输入错误。性能 gate 与证据资格分离，synthetic/loopback 的好指标只可作为 shadow candidate。完整执行链见 `experiment_runner.py`。

> 新增：2026-09-07  
> 当前实现：`adaptive_control.py`，标准库、deterministic、**shadow/advisory only**。  
> 本层把 L0–L5 的价格、缓存、压缩、harness、持久状态与 task economics 变成可观测的控制问题，但不在缺少真实 runtime/task A/B 时自动修改生产策略。

## 0. 层级边界：L6 不是 THM 的 T0–T3

Context Economics 的 `L0–L6` 是研究/控制 **Layer**：

```text
L0 Pricing
L1 Serving / KV
L2 Compression
L3 Harness / Scheduling
L4 Memory / Persistent State
L5 Task Economics / Observability
L6 Adaptive Context Control
```

THM 的 `T0–T3` 是另一套独立的 memory residency/access **Tier**。THM 不是 Context Economics 的子模块，Context Economics 也不是 THM 的设计规范。

二者只在以下问题上交换测量和实验方法：

- context/memory miss cost；
- residency/admission；
- locator；
- prefetch；
- budget；
- task-economic outcome。

L6 的控制对象还包括 conversation history、repo map、tool schema、RAG evidence、文档、网页研究结果和其他可重取上下文，因此不能把 L6 公式直接写成 THM 的生产 tier policy。

## 1. 为什么需要 L6

L5 已经把目标从“少 token”改成：

```text
task success
+ provider bill
+ tool/retrieval/reacquisition
+ retry
+ latency
+ failure
```

但只做事后计量还不够。真实 agent 每一轮都要决定：

```text
哪些内容继续携带？
哪些只保留 locator？
哪些需要检索？
哪些值得预取？
哪些 schema / repo map 应该暴露？
什么时候更激进压缩？
各类 context budget 应该是多少？
```

因此 L6 的核心不是寻找一个永远不变的 `theta*`，而是把控制变量写成向量，并根据观测状态产生**有界建议**。

## 2. Context miss taxonomy

L6 使用通用访问事件，而不借用 THM tier 名称：

| 事件 | 含义 | 是否 demand | 是否 miss |
|---|---|---:|---:|
| `context_hit` | 所需状态已在 working context | 是 | 否 |
| `soft_miss` | 不在当前上下文，但 locator 已知，可廉价取回 | 是 | 是 |
| `hard_miss` | 连位置/入口都未知，需要 search / grep / vector / exploration | 是 | 是 |
| `stale_hit` | 内容在上下文中，但已过期或错误 | 是 | 否；属于正确性风险 |
| `planned_retrieval` | policy 本来就设计为按需取回 | 否 | 否 |
| `prefetch` | speculative fetch 的结果 | **不训练 demand** | 否 |

`soft_miss` / `hard_miss` 还要显式标记：

```text
avoidable = true / false
```

它只回答一个窄问题：

> 如果该资产在当前 policy 下被常驻或提前取回，这次 miss 是否 plausibly 可避免？

没有该标签时，raw miss 只能作为诊断，不能自动转成 residency benefit。

### 期望上下文成本

概念上可以写成：

```text
E[C_context] =
    P(hit)       * C_carry
  + P(soft_miss) * C_fetch
  + P(hard_miss) * C_search
  + P(stale_hit) * C_error
```

实际实现不强迫这些成本都以美元计价。`extra_cost_units` 是 caller 明确给出的实验单位；provider bill、额外 token、tool call 和 latency 另外保留，避免假装存在一个普适换算率。

## 3. Admission 与 Residency：不能把“没 miss”当成“没价值”

对资产 `i`，最小 shadow value 可写成：

```text
V_i =
    expected_avoidable_miss_cost_i
  - expected_stale_cost_i
  - carry_cost_i
  - interference_cost_i
```

实现提供两种 counterfactual value 来源：

1. **observed avoidable miss penalty**：资产不在 working context 时真实记录到的可避免 miss；
2. **explicit counterfactual miss cost**：调用者通过 catalog 明确提供。

第二条非常重要。一个长期 resident 的资产可能产生大量 `context_hit`，恰恰因为它一直常驻，所以观察不到 miss。若把“0 observed miss”解释成“0 miss cost”，controller 会形成破坏性反馈：先常驻 → 没 miss → 判定无价值 → 淘汰。

因此当前实现规定：

```text
resident hits + no counterfactual value
=> keep/review
=> 不自动 evict
```

只有同时满足全局 demand 样本门槛、资产级 demand 门槛和 counterfactual value basis，才允许生成 `admit` / `evict`。

### 固定预算选择

当多个正价值资产竞争容量时，公开 reference implementation 使用有明确资源上限的 exact 0/1 packing，而不是 value-density greedy。原因是不同 context asset 大小不等，greedy 会在固定 budget 下给出错误组合。

公开资源保护线：

```text
budget units <= 100000
candidate assets <= 1024
DP work <= 5,000,000
```

超过边界直接失败，调用者必须先做 bucket/coarsening，不静默切换成看似“精确”的近似算法。

## 4. Locator token：正式资产类别

很多 agent 不需要每轮携带全文，只需要一个稳定入口：

```text
full content
   ↓
compact locator
   ↓
working context
   ↓
on-demand expansion
```

典型 locator：

```text
repo architecture -> repo map entry
file             -> path + role
long-term memory -> topic/scope/revision/locator
tool capability  -> compact manifest
history          -> timeline/index
evidence         -> citation/source locator
```

`locator_economics()` 单独计算：

```text
expected_search_avoided
= P(fetch) * search_avoided_cost

net_locator_value
= expected_search_avoided
- expected_fetch_cost
- resident_locator_carry_cost
```

以及 benefit/cost ratio。

这里的 locator 是访问入口，不是 evidence 本身。一个 locator 可以帮助找到原文，但不能因“它被常驻”就推导原文已经进入模型、已经被使用或已经正确。

## 5. Speculative Context Prefetch

L6 的 prefetch 目标不是把下一步所有可能内容塞进 prompt，而是优先预取：

```text
locator
metadata
tiny excerpt
resource handle
```

再按实际需求展开。

训练信号只来自真实 demand 事件：

```text
context_hit
soft_miss
hard_miss
stale_hit
```

历史 `prefetch` 和 `planned_retrieval` 不能回流进 co-demand 统计。否则会形成：

```text
我预取了 A
→ telemetry 看见 A
→ 证明 A 经常需要
→ 继续预取 A
```

这种自证循环。

对于 seed `s` 和候选 `i`：

```text
confidence_i =
joint_demand_tasks(s, i) / seed_demand_tasks(s)

NetPrefetchValue_i =
confidence_i * explicit_prefetch_value_i
- prefetch_cost_i
```

在 prefetch budget 内再次做有界 exact packing。

运行后应持续报告：

```text
prefetch_accuracy
= used_prefetches / all_prefetches

prefetch_coverage
= observed_avoided_misses / all_misses   # 仅在有可靠 avoided_miss 标签时

pollution
= unused_prefetched_units / total_prefetched_units

net_prefetch_value
= observed_avoided_cost - prefetch_cost
```

`avoided_miss` 仍是 caller/runtime instrumentation 的标签，不由模型自行判因果。

## 6. Vector Context Budget Controller

预算不再抽象成单个“600 token”或固定 `0.5 × window`。

当前控制向量：

```text
u_t = (
  B_history,
  B_retrieval,
  B_memory,
  B_tools,
  B_repo_map,
  B_prefetch,
  r_compression_retained
)
```

观测向量包含：

```text
miss_rate
hard_miss_rate
reacquisition_cost
dependency_depth
cache_hit_share
context_pressure
TTFT
prefetch_pollution
interference_rate
```

方向性规则：

```text
miss / hard miss / reacquisition / dependency depth ↑
=> 倾向增加能避免缺页的相关预算
=> 倾向保留更多原始内容

context pressure / TTFT / pollution / interference ↑
=> 倾向收缩相应预算
=> 倾向减少无效携带/预取
```

cache-hit share 作为 carrying economics 的一部分进入 feedback：低 cache locality 会降低长期携带同一大块 context 的经济吸引力。

当前 `suggest_budget()` 是**bounded heuristic feedback step**：

- 每维都有 caller-supplied min/max；
- 每次变化受 `base_step_fraction` / `max_step_fraction` 限制；
- deadband 内保持不动；
- 输出 proposed vector；
- **不写回 harness/provider 配置**。

它不是 TCP AIMD 的照搬，也不是 universal optimal controller。

## 7. Context mutation amplification

已撤回的旧错误链条：

```text
ordinary mid-session memory write
=> 当前 frozen prompt 必然变化
=> 下一轮整段历史必然 cache miss
```

不会在 L6 复活。

但更一般的 context mutation amplification 仍值得计量。一次 semantic source change 可能触发：

```text
file write
index update
embedding update
summary regeneration
directory update
backup/version write
prompt rebuild（若真的发生）
cache invalidation（若真的观察到）
```

当前实现分开报告：

```text
storage_amplification
token_recompute_amplification
compute_ms_per_semantic_unit
cache_invalidation_amplification
derived_write_fanout
```

没有真实 cache invalidation telemetry 时，该项必须保持 0/unknown 的实验口径，不能从“发生写入”自动推导。

## 8. Shared immutable base + private delta

COW 思路只保留干净部分：

```text
immutable/content-addressed shared base
+
consumer/profile/session private delta
```

适用对象可能包括：

- 公共 system instructions + session delta；
- 共享 tool schema + agent-specific enabled subset；
- 共享 repo snapshot + branch diff；
- 共享文档 + profile annotation。

不允许因为“共享省空间”就把 user/profile-specific state 合并成公共状态。

`shared_immutable_context_economics()` 只计算 duplicated units 与 shared-base + private-delta units 的差值，并在输出里固定这一隔离边界。

## 9. 与 L5 的接口

L6 生成的是 shadow policy recommendation；L5 判断它值不值得。

真正的闭环：

```text
L6 proposed policy
→ controlled runtime/task experiment
→ L5 run receipts
→ success / bill / cache / reacquisition / retry / latency
→ paired deltas
→ next L6 calibration
```

因此任何“L6 更优”的声明至少需要：

```text
runtime-A/B
```

若还要声称“单位成功任务更便宜/更可靠”，必须达到：

```text
task-economic
```

当前仓库的 L6 fixture 和 tests 只属于：

```text
analytic + simulation/contract
```

## 10. 可运行 reference implementation

合成 fixture：

```text
fixtures/context_access_events.json
fixtures/context_assets.json
fixtures/context_budget_state.json
```

命令：

```bash
python adaptive_control.py telemetry \
  --events fixtures/context_access_events.json

python adaptive_control.py residency \
  --events fixtures/context_access_events.json \
  --catalog fixtures/context_assets.json \
  --budget 14 \
  --min-demand-tasks 4 \
  --min-asset-demands 2

python adaptive_control.py prefetch \
  --events fixtures/context_access_events.json \
  --catalog fixtures/context_assets.json \
  --seed repo-map \
  --budget 4 \
  --min-seed-demands 3 \
  --min-joint-tasks 2

python adaptive_control.py budget \
  --state fixtures/context_budget_state.json

python adaptive_control.py locator \
  --locator-units 20 \
  --carry-cost 0.1 \
  --fetch-probability 0.4 \
  --search-avoided 8 \
  --fetch-cost 0.5

python adaptive_control.py amplification \
  --mutation-id demo \
  --semantic-source-units 2 \
  --storage-bytes-changed 20 \
  --recomputed-tokens 10 \
  --compute-ms 30 \
  --invalidated-cache-tokens 40 \
  --derived-writes 5

python adaptive_control.py share \
  --base-units 100 \
  --consumers 3 \
  --private-delta-units 10
```

所有 fixture 都是 synthetic，不包含私人 conversation、repo 内容、memory、provider trace 或账户信息。

## 11. 当前验收边界

当前可以声称：

- L6 的 miss taxonomy、admission/residency、locator economics、co-demand prefetch、vector budget feedback、mutation amplification、shared immutable base 都有 executable reference implementation；
- schema/telemetry 对 typo、重复 ID、非法布尔/数值、未知 asset 等采用 fail-fast；
- prefetch 不训练自己的 demand；
- current resident 若缺 counterfactual value，不会因为“0 observed miss”被自动淘汰；
- exact packing 有明确资源保护边界；
- controller 只输出有界 shadow proposal。

当前不能声称：

- 某个 budget vector 是生产最优；
- 某个 admission/prefetch policy 已提高真实任务成功率；
- locator 一定降低 provider bill；
- cache 命中/TTFT 会按 synthetic model 变化；
- L6 可以替 THM 决定 T0–T3；
- 自动控制应该直接写回生产 harness。

`runtime_experiment.py` 现已完成这一步的**结构化数据合同**：它把 version-pinned L5 receipts 与 run-linked L6 telemetry 对齐，并检查 arm completeness，但公开 fixture 仍是 synthetic。下一阶段仍是执行真实、版本固定的 runtime/task A/B，再决定哪些 shadow recommendation 可以升级。详见 [Runtime Experiment Contract](RUNTIME-EXPERIMENT-CONTRACT.md)。
