# L4 记忆与档案的上下文经济学

> 2026-08-19 · SJF × Hermes。本模块是 THM（xngg1021/thm-tiered-hot-memory，设计理论）与
> context-economics（定价与缓存机制）两套研究的交叉补全：把 THM 目标函数
> `E[任务成功率] − λ1·注入成本 − λ2·注意力稀释 − λ3·干扰税` 中的 λ 从符号标定为数字。
> 数据来源：三 profile 本地实测（profile 已匿名化）+ Hermes 源码 + Kimi 官方文档。token 换算沿用 real_model.py
> 校准值 2.13 字符/token；定价 kimi-k3：输入 $3/M、缓存读 $0.3/M、输出 $15/M。

## 一、λ1 标定：T0 热层的驻留租金

实测（2026-08-19，三 profile memories/ 目录）：

| profile | MEMORY.md | USER.md | 合计字符 | 合计 token | 每轮租金(命中) | 每轮租金(未命中) |
|---|---|---|---|---|---|---|
| P1（主 profile） | 3,744 | 1,201 | 4,945 | ≈2,322 | $0.00070 | $0.00697 |
| P2 | 0 | 541 | 541 | ≈254 | $0.00008 | $0.00076 |
| P3 | 0 | 211 | 211 | ≈99 | $0.00003 | $0.00030 |

租金公式（每轮）：`rent = T0_tokens × p_eff`，p_eff 命中时 $0.3/M、未命中 $3/M。

- default 热层 100 轮租金：$0.070（全程命中）~ $0.697（全程未命中）。
- 量级判断：相对会话本体（30-45 万 token 峰值）的平方项成本，T0 租金是小数——
  **热层"装满"本身不是经济问题**，3,750 字符预算不构成需要节省的对象。
  λ1 的真正事件成本不在驻留，在写入（见下节）。
- 落地缺口（非研究问题）：P2/P3 的 MEMORY.md 为 0 字符，THM 框架已同步但热层无内容。

## 二、记忆写入的缓存断点成本（本模块核心新结论）

### 机制

Kimi Context Caching 官方文档（platform.kimi.com/docs/guide/use-context-caching-feature-of-kimi-api）：
对所有请求自动启用，识别重复的**初始上下文**（system prompt、工具定义等），
要求逐字节一致的前缀，≥256 token 才可命中；无需管理 TTL（系统管理）。
Kimi 论坛官方答复补充：后端多集群，未指定 `prompt_cache_key` 时负载均衡可能路由到
不持有该 KV 的集群造成随机 miss。

记忆写入改变 volatile 尾带的字节 → 最长匹配前缀从"全长"退化为"稳定头" →
**下一轮把整个尾带 + 全部对话历史按全价 re-prefill 一次**（再往后恢复正常命中）。

### 定价

```
W ≈ (S + H) × (p_in − p_cache) ≈ H × $2.7/M     (H≫S，H=对话历史 token)
```

| 会话规模 H | 一次中途写入的隐形成本 | 相当于 default 整个 T0 块的驻留轮数 |
|---|---|---|
| 10 万 | $0.27 | ≈390 轮 |
| 20 万 | $0.54 | ≈775 轮 |
| 45 万（本机历史峰值） | $1.22 | ≈1,750 轮 |

**一次随手中途写入，烧掉的热层租金当量以"百轮"计。**

### 写入时机守则（由此推出的操作纪律）

1. **批量写**：memory 工具的 operations 数组一次完成全部增删改（其官方设计即如此），
   N 条变更只付一次断点费，不是 N 次。
2. **早写或末写**：会话早期 H 小（断点费低）；最后一轮之后没有下一轮（断点费为零）。
   长会话（H>10 万）中途避免零散单条写。
3. **正确性优先**：重要纠正（用户明确纠偏、事故级事实）不因省断点费而拖延——
   该守则约束的是"随手记"，不是"该记的"。
4. 上限声明：若该轮缓存反正要 miss（集群路由/TTL 驱逐），写入的增量成本为零；
   W 是"缓存本可命中"情形下的机会成本。

## 三、注入位置：源码级实证（结论：已经最优，无需改动）

Hermes 源码直接证据：

- `agent/system_prompt.py:20-21`（模块头注释）：系统提示显式分两层——
  stable（身份、工具说明、行为准则）+ **volatile（skills 索引、memory 快照、USER.md、
  外部记忆块、时间戳/会话/模型行）**。第 347-348 行重申同一分层。
- `agent/system_prompt.py:782-789`：memory 块与 user 块渲染进 volatile 尾带。
- `agent/prompt_cache_boundary.py`：Hermes 已为 Anthropic 显式缓存做"稳定前缀注册 +
  断点放置在稳定/易变边界"的工程（#81867），设计意图与上述分层一致。

两个推论：

1. **缓存友好**：记忆变更只使改动点之后失效，静态大头（工具/skills/准则）仍然命中——
   断点费的大头是对话历史 H，不是系统提示本身。
2. **位置即性能**：volatile 尾带恰好位于上下文的近因优势区（lost-in-the-middle，
   arXiv:2307.03172），热层记忆放在全提示词尾部对召回是有利位置。
   THM 综述担心的"系统提示内部位置效应"在现有布局下是自然解，免费获得。

## 四、开放问题#3 结题：跨 profile 前缀共享

原问题：P1/P2/P3 三个 bot 系统提示若对齐，可否共享缓存前缀？

核实与评估：

- Kimi 官方文档未明示缓存是否跨 API key 隔离（行业惯例为账户级隔离，未证实）。
- 即使同 key 且缓存账户级共享，可共享的只有**逐字节相同的头部**；三 profile 的
  身份段、AGENTS.md/SOUL、技能集存在差异，分歧点出现得相当早，共享上限有限。
- 为对齐提示词而改动三 profile 的内容，会牺牲各 profile 的个性化（语气守则、
  家庭边界条款），代价确定、收益依赖未核实假设。

**结论：关闭此开放问题——不追求跨 profile 前缀对齐。** 若未来 Kimi 公布缓存隔离粒度
或提供 `prompt_cache_key` 语义的官方说明，可重估。

## 五、待数据积累后才能做的标定（记录备查）

1. **λ2/λ3 与容量预算优化**：巩固 cron（每周一，首跑 2026-08-24）积累 index.json
   events（hit/create/confirm）后，可计算每条记忆的"单位 token 提取收益"
   = 激活分 / 条目 token 数，据此在 3,750 字符预算内做条目级优胜劣汰——
   这是 THM 驱逐策略的经济学升级版。验证点：8-24 后检查 THM 部署的报告目录
   是否产出首份巩固报告。
2. ~~**prompt_cache_key**~~ **已落地（2026-08-19）**：源码核实——Hermes 对 Codex/Responses 传输默认
   派生 prompt_cache_key（内容寻址 + 会话作用域，#78941/#79017）；chat_completions 传输支持
   但需 provider profile 的 `supports_prompt_cache_key=true`（providers/base.py 默认 False，
   内置 kimi-coding 插件未开启），而自定义 provider 的 config.yaml 字段里无此开关。
   **落地路径**：自定义 provider 支持 `extra_body` 字段且随每请求注入
   （agent_init.py::_custom_provider_extra_body_for_agent 按 base_url 匹配），
   三 profile 已设置 `providers.kimi.extra_body.prompt_cache_key`
   = hermes-p1-v1 / hermes-p2-v1 / hermes-p3-v1（示例键名，实际值按 profile 部署）（静态键=把该 profile 全部流量钉到同一
   缓存桶，消除 Kimi 官方答复中提到的集群路由随机 miss；分 profile 用不同键避免串桶）。
   生效条件：gateway 重启后（CLI 新会话自动生效）。预期收益：gateway 长会话缓存命中率提升，
   直接降 p_eff 里的全价占比。验证方法：对比重启前后 state.db 账单里的 cached_tokens 占比。

---

来源声明：Kimi 缓存机制引自 platform.kimi.com 官方文档与 forum.moonshot.ai 官方答复
（2026-08-19 检索）；注入位置引自本机 hermes-agent 源码行号；租金/断点数字为
本地实测字符量 × 校准换算 × 官方定价的推算，非厂商账单实测。
