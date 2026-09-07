# 大模型上下文经济学（Context Economics）

> 起始研究：2026-08-19，SJF × Hermes  
> correctness hardening：2026-09-07  
> 当前研究对象：LLM / agent 在输入、缓存、压缩、工具、记忆、重取、重试、延迟、任务成功与自适应上下文控制之间的成本—质量权衡。

本仓库把上下文视为一种会被反复携带、缓存、压缩、重取和重新计算的运行资产。目标不是单纯“省 token”，而是把 **provider 定价 → serving/KV → 压缩算法 → harness 调度 → 持久记忆 → 任务经济学 → shadow adaptive control** 放进同一个可验证框架，并提供从 runtime instrumentation 到 version-pinned A/B acceptance 的可执行路径。

## 0. 证据纪律

从 2026-09-07 起，仓库统一区分以下证据等级：

| 标签 | 含义 |
|---|---|
| `runtime-measured` | 真实 runtime / provider bill / trace 直接观测；必须记录时间、版本、口径 |
| `source-code` | 从指定软件 revision 的源码确认的行为 |
| `provider-doc` | 厂商官方定价/API/机制说明；属于快衰减信息 |
| `paper-result` | 论文在其特定实验条件下报告的结果 |
| `model-proxy` | 本仓库模型假设推导出的代理指标；不能冒充真实正确率、召回率或生产效果 |

当前最高公开证据仍是 `simulation` / deterministic local HTTP contract E2E；尚无凭据支持的真实 provider bill trace、真实 provider runtime A/B 或 task-economic promotion 结论。

`PROVENANCE.md` 固定本轮版本身份和来源边界；`pricing-snapshot.json` 保存机器可读的定价快照。L0–L3 的 2026-08-19 文档作为历史研究快照保留，9 月 7 日的新材料和勘误汇总在 `RESEARCH-ADDENDUM-2026-09-07.md`。

## 1. 七层结构

```text
L0 Pricing
   uncached input / cached input / cache write / storage / output /
   long-context tier / batch / priority / time-of-day

L1 Serving & KV
   prefill、KV cache、prefix/non-prefix reuse、HBM/DRAM/SSD、schema/resource reuse

L2 Compression
   文本删减、摘要、soft token、外部化、RAG、内容类型化保真

L3 Harness
   prompt assembly、tool schema、subagent、compaction、cache-stable scheduling、
   prompt rebuild / reacquisition

L4 Memory & Profile
   frozen memory snapshot、长期驻留租金、版本/来源、profile 隔离、持久状态

L5 Task Economics & Observability
   billed cost + tool/reacquisition/retry/latency/failure + task success

L6 Adaptive Context Control
   admission / residency / locator / prefetch / vector budget feedback /
   mutation amplification / shared immutable base
```

Context Economics 的 L0–L6 是分析/控制 Layer；THM 的 T0–T3 是独立仓库的 memory residency/access Tier。两者只能通过 telemetry/contract 交换 miss、locator、prefetch、budget 等证据，taxonomy 不合并。

## 2. Runtime evidence pipeline

`context_runtime.py` 提供严格、版本化的 request/tool/context/compression/outcome schema、collector 和 normalizer；`runtime_http.py` 提供最小 OpenAI-compatible HTTP adapter；`experiment_analysis.py` 提供 AB/BA counterbalance、paired descriptive statistics、deterministic bootstrap 和 hard gate；`controller_calibration.py` 提供 train/holdout 分离的 offline replay sweep。

详见 `RUNTIME-INSTRUMENTATION.md`、`RUNTIME-EXPERIMENT-CONTRACT.md` 与 `EXPERIMENT-ACCEPTANCE.md`。所有 public fixture 均为 synthetic。`performance_candidate` 与 `evidence_eligible` 分开判断；只有两者都通过才允许 `candidate_for_promotion`。当前尚未实现独立证据认证，因此正式 promotion 保持 false；调用方声明只决定 `evidence_structurally_eligible`，不会自动启用生产 controller。

`experiment_runner.py` 把 task set → paired-fixed / AB/BA → injectable executor → raw telemetry → L5/L6 → joint report → statistics → acceptance 串成完整执行链：

```bash
python experiment_runner.py --local-demo --output-root artifacts
python runtime_experiment.py --manifest artifacts/local-e2e/manifest.json --receipts artifacts/local-e2e/l5-receipts.json --events artifacts/local-e2e/l6-events.json --require-complete
```

标准 HTTP adapter 支持 `choices[0].message.content`、标准 cached usage 和旧 fixture。端点不提供账单时必须提供带定价来源的 estimator，结果明确为 estimated；非流式 TTFT 为 null，完整响应耗时单独记录。完整本地 E2E 已覆盖实际 socket、十份产物和重放确定性，公开证据仍为 simulation / contract E2E。

PR #5 engineering pipeline 已验收：main `79447daafd365edb228c4864fc630f6265dc6287`，post-merge validate `34109557962` 成功。真实 provider evidence pending/staged；task-economic evidence 尚未建立；production controller mutation disabled。

## 3. 核心成本模型

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

因此，**在这些条件成立时**，累计输入携带量含 `O(N^2)` 项。固定窗口截断、RAG、分页、非线性长上下文定价、失败重试和模型路由都会改变曲线，所以本仓库不再把它写成无条件“平方定律”。

### 缓存与压缩的局部替代关系

把中间区 `M` 压成 `r*M`，在固定价格和固定命中率近似下：

```text
N* = (p_in + r*p_out) / ((1-r)*p_eff)
```

在这个局部账单模型里 cache 越便宜，携带原文的边际价格越低，压缩回本越慢。进入 L5 后，压缩造成的状态丢失、reacquisition、工具失败和重试会改变关系，因此缓存与压缩在任务层可能互补，也可能出现非单调最优点。

## 4. `model.py`：确定性成本模型

运行：

```bash
python model.py
```

当前代码完成了三项关键修正：

1. Hermes `target_ratio` 只用于 recent-tail budget：

   ```text
   tail_budget = target_ratio * threshold * context_window
   ```

   不再同时冒充“摘要大小比例”。摘要大小由独立参数 `summary_ratio_of_middle` 建模。

2. 有限 grid 的最小端点不再叫全局 `theta*`。输出只声明：

   ```text
   lowest-cost point in THIS GRID
   ```

   因为不计质量/重取/失败成本时，纯 token 模型经常持续偏好更激进压缩。

3. `Pricing` 支持非线性长上下文档位。例如 2026-09-07 的 OpenAI GPT-5.6 Sol 官方页对 >272K input 的请求采用不同倍率，因此真实 provider cost 不能永久抽象成一个常数 `p_in`。

历史 Kimi `$3 / $0.3 / $15` 继续作为 2026-08-19 study snapshot 用于复现，不自动代表 live quote。

## 5. `real_model.py`：真实 trace + 明示代理质量模型

公开可复现：

```bash
python real_model.py --fixture fixtures/sample_sessions.json
```

对本机 Hermes SQLite 做只读重放：

```bash
python real_model.py \
  --db default=/path/to/state.db \
  --db other=/path/to/other/state.db
```

脚本不再硬编码私人 Windows 路径。

真实部分可以包括 message 顺序/长度、模型标签、aggregate input/cache token；以下仍是模型假设：字符/token 校准、摘要保留率、长上下文退化函数、回指概率和 failure line。因此输出统一命名为：

```text
proxy_final_recall
proxy_integrity
proxy_persistence_turns
proxy_ux_failures
```

旧版 README 中“0.998 终态召回”“30–45 万上下文已经被压缩反向提质”等说法，现统一降级为给定假设下的 sensitivity result。只有真实 task/runtime A/B 才能升级为 `runtime-measured`。

## 6. `task_economics.py`：把 L5 变成可运行代码

合成 receipt 示例：

```bash
python task_economics.py \
  --receipts fixtures/run_receipts.json \
  --control no-compression \
  --treatment aggressive-compression
python adaptive_control.py telemetry \
  --events fixtures/context_access_events.json
python adaptive_control.py budget \
  --state fixtures/context_budget_state.json
```

它按 policy 聚合：

```text
success_rate
total / mean observed cost
provider bill
cost_per_success
tool calls
retrieval calls
reacquisition calls
retry count
compression calls
wall time
```

并对具有唯一 control/treatment 配对的 task 输出逐任务 delta。缺失或重复 arm 会被跳过，不偷偷平均成看似干净的结论。

`cost_ledger_version=2` 的 `observed_cost_usd` 按以下互不重复费用相加；estimated bill 仍保留 estimated 标签：

```text
provider_bill
+ tool_cost
+ external_cost
+ latency_cost
+ failure_cost
```

`reacquisition_cost_usd` / `retry_cost_usd` 是可重叠的归因子集，不再次相加；external_cost 必须是账本其他项尚未包含的独立费用。旧版非零分类费用需要显式声明 ledger v1 或迁移到 v2，不能静默猜测。

它不负责替实验设计推断因果；真正的结论仍需要 pinned model/provider/harness 和配对任务。

## 7. Hermes 行为勘误

2026-09-07 核查的 Hermes 上游文档/源码表明：`MEMORY.md` / `USER.md` 在 session start 形成 **frozen system-prompt snapshot**；中途 memory write 会立即持久化，但不会改写当前会话已冻结的 system prompt。

因此旧 L4 的：

```text
mid-session memory write
 -> current prompt prefix changes
 -> next request full dynamic history re-prefill
```

已撤回。

当前模型是：

```text
ordinary mid-session memory write
 -> disk state changes
 -> current frozen prompt unchanged
 -> current-session cache break: not implied

prompt rebuild / compaction / new session / toolset/model/prompt mutation
 -> serialized prompt may change
 -> cache impact must be observed from actual telemetry
```

历史 `$0.27 / $0.54 / $1.22` 可以保留为“若 100K/200K/450K dynamic context 从 cached 变为 uncached”的 scenario upper bound，不能再称为写一次 memory 的既定成本。详见 `L4-memory-profile.md`。

Kimi 的 `prompt_cache_key` 也从“消除随机 miss”修正为 provider 的 routing/caching hint；session/task key 是当前官方文档更自然的 coding-agent 粒度，profile-static key 只作为待测实验。

## 8. 2026-09-07 研究增补

不改写 L0–L3 的历史快照，新增材料集中记录在 `RESEARCH-ADDENDUM-2026-09-07.md`：

- **L0**：OpenAI 长上下文非线性价格；Anthropic 0.025x cache-read 例外；Kimi `prompt_cache_key` 语义。
- **L1**：ReCache（arXiv:2608.19662）与 resource/schema-level KV reuse；标准 KV 大小公式的 MLA/量化/local attention 等适用边界。
- **L2**：The Sleeping Agent（arXiv:2608.11775）说明压缩损失具有类型结构，尤其 temporal information 不能被一个总 recall 数字覆盖。
- **L3/L5**：Token Reduction Is Not Cost Reduction（2607.12161）、What Does Context Compression Cost an Agent?（2608.16370）、Control Under Compression（2608.01056）共同说明 token reduction、provider bill、reacquisition、runtime reliability 和 task success 必须分账。

## 8. L5：真正的目标函数

```text
J(policy) =
    E[task_value]
  - E[token_bill
      + cache_write/storage
      + tool_cost
      + external_cost
      + latency_cost
      + failure_cost]
```

如果 task value 暂时无法货币化，至少并列报告：

```text
success_rate
cost_per_success
provider_bill
p50/p95 latency
tool/retrieval/reacquisition calls
retry/compression counts
cache-hit share
```

真正有意义的 `theta*` 应该在这一层产生。

## 9. `adaptive_control.py`：L6 变成可运行 shadow control plane

L6 将前面各层的观测量变成一组**有界、非自动执行**的 context-control 建议。它不使用 THM 的 T0–T3 作为自己的层级；Context Economics 的 `L0–L6` 是分析/控制 Layer，THM 的 `T0–T3` 是独立 memory residency/access Tier。

当前控制面覆盖：

```text
context_hit / soft_miss / hard_miss / stale_hit
admission / residency
locator-token economics
speculative prefetch
vector budget feedback
context mutation amplification
immutable shared base + private delta
```

其中核心控制向量是：

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

运行 synthetic reference：

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
  --budget 4

python adaptive_control.py budget \
  --state fixtures/context_budget_state.json
```

完整定义与边界见 `L6-adaptive-context-control.md`。当前 L6 的证据等级仍是 `analytic + simulation/contract`；没有真实 held-out runtime/task A/B 时，不把 shadow proposal 称为生产最优，也不自动写回 harness/provider 配置。

## 10. `runtime_experiment.py`：version-pinned L5/L6 join contract

L5 receipts 与 L6 context telemetry 现在有独立的运行实验数据合同：`runtime_experiment.py` 要求 experiment manifest 固定 provider/model/model revision/harness revision/repository commit/runtime environment/task set/pricing snapshot/policy bundle，并将每个 L6 event 通过 `run_id + policy_id + task_id` 与 L5 receipt 对齐。

它显式报告 missing/duplicate arms、没有 context events 的 run、paired coverage，并可用 `--require-complete` 把结构不完整直接变成失败。Runtime receipt 中时间戳、token/cache、provider bill、各类成本、interaction counts、TTFT/wall time 等字段必须显式提供，不能靠默认零掩盖缺失。

`declared_evidence_class` 仍只是 experiment producer 的声明。即使报告显示 `runtime_design_structurally_ready=true`，validator 也不会推断 provider 真正被调用、账单真实、任务分配随机或 treatment 具有因果优势；输出固定保留 `causal_claim = not inferred by this validator`。完整合同见 `RUNTIME-EXPERIMENT-CONTRACT.md`。

公开 fixtures 只用于 synthetic contract CI，不能升级为 runtime benchmark。

## 11. 可复现性与 CI

仓库核心验证只依赖 Python 标准库：

```bash
python -m unittest discover -s tests -v
python model.py
python real_model.py --fixture fixtures/sample_sessions.json
python task_economics.py \
  --receipts fixtures/run_receipts.json \
  --control no-compression \
  --treatment aggressive-compression
python adaptive_control.py telemetry --events fixtures/context_access_events.json
python runtime_experiment.py --manifest fixtures/runtime_experiment_manifest.json --receipts fixtures/runtime_ab_receipts.json --events fixtures/runtime_context_events.json --require-complete
```

GitHub Actions 在 Python 3.11 / 3.13 上执行同一套单测与 smoke tests。

公开 fixture 全部是 synthetic；仓库不包含私人 `state.db`、原始 conversation、MEMORY/USER 原文、API key 或账户身份。

## 12. 仓库结构

```text
README.md
CHANGELOG.md
PROVENANCE.md
pricing-snapshot.json
RESEARCH-ADDENDUM-2026-09-07.md

L0-pricing.md
L1-systems.md
L2-compression.md
L3-harness.md
L4-memory-profile.md
L5-task-economics.md
L6-adaptive-context-control.md
RUNTIME-EXPERIMENT-CONTRACT.md
RUNTIME-INSTRUMENTATION.md
EXPERIMENT-ACCEPTANCE.md

model.py
real_model.py
task_economics.py
adaptive_control.py
runtime_experiment.py
context_runtime.py
runtime_http.py
experiment_analysis.py
experiment_runner.py
controller_calibration.py

fixtures/sample_sessions.json
fixtures/run_receipts.json
fixtures/context_access_events.json
fixtures/context_assets.json
fixtures/context_budget_state.json
fixtures/runtime_experiment_manifest.json
fixtures/runtime_ab_receipts.json
fixtures/runtime_context_events.json

tests/test_model.py
tests/test_real_model.py
tests/test_task_economics.py
tests/test_adaptive_control.py
tests/test_runtime_experiment.py
tests/test_docs.py

.github/workflows/validate.yml
```

## 13. 当前仍未解决的问题

1. 为当前 Hermes compressor 做 **exact-version replay**：固定 summary budget、tail mode、protected messages、prompt rebuild 与 provider transport。
2. 保存 per-request billing trace，而不是只使用 session aggregate。
3. 用 `runtime_experiment.py` 的 contract 真正执行 version-pinned held-out task A/B，并用真实 task outcome 校准 `real_model.py` 中的 proxy retention curve。
4. Collector、normalizer、runner 已聚合 canonical events；尚需真实 provider/harness adapters 自动映射 native tool/reacquisition/retry/latency 与 L6 telemetry。
5. 研究按内容类型的 retention policy：路径、数字、时间、否定约束、用户意图、tool protocol、可重取 tool output 应区别处理。
6. 对 L0 pricing snapshot 做定期刷新；快衰减信息不能永久写死在“定律”里。
7. 在不同 provider/cache tier 上做 `cache × compression` factorial A/B，检验任务层是替代还是互补。

## 12. 主要新增来源（2026-09-07 hardening）

- OpenAI GPT-5.6 Sol: https://developers.openai.com/api/docs/models/gpt-5.6-sol
- Anthropic pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Kimi Chat API: https://platform.kimi.com/docs/api/chat
- LongMemEval: https://arxiv.org/abs/2410.10813
- ReCache: https://arxiv.org/abs/2608.19662
- Token Reduction Is Not Cost Reduction: https://arxiv.org/abs/2607.12161
- What Does Context Compression Cost an Agent?: https://arxiv.org/abs/2608.16370
- Control Under Compression: https://arxiv.org/abs/2608.01056
- The Sleeping Agent: https://arxiv.org/abs/2608.11775

更早文献继续保留在 L0–L3 原始底稿中；来源与版本边界见 `PROVENANCE.md`。
