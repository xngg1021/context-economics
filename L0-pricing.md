# 全球主流 LLM 服务商 Prompt/Context Caching 定价与机制对比（截至 2026-08-19）

> Runtime successor status (2026-09-07): provider adapters are fixture-tested; credential-backed evidence is BLOCKED by runtime authorization. Partial Hermes trace-replay and synthetic retention do not establish runtime-A/B or task-economic results. Production mutation remains disabled. See [REAL-RUNTIME-CAMPAIGN.md](REAL-RUNTIME-CAMPAIGN.md).

> 所有条目均以官方文档/定价页为准，附来源 URL；个别细节未能从官方页核实的已标注「未核实」。
>
> 时效提醒：本表数据截至 2026-08-19，价格与 TTL 属快衰减信息，引用前请核对官方最新定价页。

## 1. Anthropic Claude — Prompt Caching
- **价格倍率**：5 分钟缓存写入 = 基础输入价 1.25×；1 小时缓存写入 = 2×；缓存读取 = 0.1×（即读命中 90% 折扣）。倍率全线模型一致。
- **TTL**：默认 5 分钟（每次命中免费续期）；可选 `ttl: "1h"` 延长至 1 小时。仅支持 `ephemeral` 类型。
- **最小命中前缀**：1,024 tokens（Opus 4.8 / Sonnet 5 / Sonnet 4.6 / Sonnet 4.5 等）；2,048 tokens（Claude Mythos Preview、Opus 4.7、已退役的 Haiku 3.5）。低于最小值静默不缓存、不报错。
- **命中判定**：精确前缀匹配——断点处及之前所有文本/图像 100% 逐字节一致，改动任一字符即失配（缓存键为前缀累计 hash）。
- **自动/显式**：两者皆可。显式 `cache_control` 断点（每请求最多 4 个，精细控制）；也支持 automatic caching（自动在最后一个可缓存块放置断点，20 块回溯窗口）。
- 来源：https://platform.claude.com/docs/en/build-with-claude/prompt-caching ；https://aws.amazon.com/about-aws/whats-new/2026/01/amazon-bedrock-one-hour-duration-prompt-caching

## 2. OpenAI — Prompt Caching（自动为主，GPT-5.6+ 支持显式断点）
- **价格倍率**：
  - GPT-5.6 及更新：缓存写入 1.25×，缓存读取 0.1×（90% 折扣）。
  - 更早模型：缓存写入无额外费用；缓存读取按各模型 cached-input 价计费，折扣约 50%（GPT-4o 时代）到 75–90%（GPT-5.x，随模型而异）。
- **TTL**：
  - GPT-5.6+：`prompt_cache_options.ttl` 设置精确 30 分钟 TTL（到期后可能仍保留更久，但不保证）。
  - 更早模型：`prompt_cache_retention` 两档——`in_memory`（闲置 5–10 分钟失效，最长 1 小时）与 `24h`（最长 24 小时，非保证）；支持 24h 的模型包括 gpt-5.5/5.4/5.2/5.1 系、gpt-5、gpt-4.1 等。无 ZDR 的组织默认 24h。
- **最小命中前缀**：GPT-5.6+ 严格 1,024 tokens；更早模型 1,024–2,048（因模型而异），以 128 tokens 为增量阶梯。
- **命中判定**：精确前缀匹配。GPT-5.6+ 在「合格断点」处精确匹配 + 需相同 `prompt_cache_key`（用于路由）；更早模型自动 best-effort 复用最长匹配前缀，不保证命中。
- **自动/显式**：更早模型全自动（无需改动代码）；GPT-5.6+ 默认 implicit（自动在最后一条 user/tool 消息放隐式断点），也支持显式 `prompt_cache_breakpoint` 与 `mode: "explicit"`。缓存 token 仍计入 TPM 限流。
- 来源：https://developers.openai.com/api/docs/guides/prompt-caching ；https://openai.com/index/api-prompt-caching

## 3. DeepSeek — Context Caching on Disk（硬盘上下文缓存）
- **价格倍率**：缓存命中输入价约为未命中输入价的 1/50（V4 Flash：$0.0028 vs $0.14；V4 Pro 优惠价：$0.003625 vs $0.435，即约 98% 折扣）。写入/存储无额外费用。另有峰谷分时价（UTC 01:00–04:00、06:00–10:00 为高峰）。
- **TTL**：系统自动管理；缓存不再使用后自动清除，官方称通常「几小时到几天」内清理。用户无 TTL 参数。
- **最小命中前缀**：官方文档未给出固定最小 token 数（未核实到官方最小值）；机制为「缓存前缀单元」需被完整匹配，长输入会按固定 token 间隔切分缓存单元。
- **命中判定**：前缀级匹配但非纯「最长公共前缀」——每个持久化的缓存前缀是独立完整单元，后续请求须**完整复用某个已持久化的前缀单元**才能命中（受 Sliding Window Attention 影响）。持久化时机：请求边界（用户输入末尾、模型输出末尾）、跨请求公共前缀检测、固定 token 间隔切分。best-effort，不保证 100% 命中。
- **自动/显式**：全自动，默认对所有用户开启，无需改代码；`usage` 中返回 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`。
- 来源：https://api-docs.deepseek.com/guides/kv_cache ；https://api-docs.deepseek.com/quick_start/pricing ；https://api-docs.deepseek.com/news/news0802

## 4. Google Gemini — Context Caching（隐式 + 显式）
- **价格倍率**：命中部分按输入价的 10% 计费（Gemini 2.5+ 保证 90% 折扣；Gemini 2.0 为 75% 折扣）。创建缓存的输入 token 按标准输入价计费（无写入溢价）。显式缓存另收**存储费**（如 Gemini 3 系 $0.50/M tokens/小时，2026-12-31 前优惠价；2027-01-01 起 $1.00；隐式缓存无存储费）。
- **TTL**：隐式缓存由系统管理（短期）。显式缓存创建时指定 TTL，默认 1 小时；最短 1 分钟，**无最大时长上限**；按存储时长计费。
- **最小命中前缀**：Gemini 3 系 4,096 tokens；Gemini 3.0 Flash Preview / 3.1 Pro Preview（隐式）6,144 tokens；Gemini 2 系 2,048 tokens（Firebase 文档口径：Pro 4,096 / Flash 1,024）。
- **命中判定**：精确前缀匹配（隐式为自动 best-effort 前缀复用；显式为引用 cache 名称确定性命中）。
- **自动/显式**：隐式缓存默认开启、不可关闭（2.5+ 自动生效）；显式缓存需调用 `CachedContent` API 创建并指定 TTL。
- 来源：https://ai.google.dev/gemini-api/docs/pricing ；https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/context-cache/context-cache-overview ；https://firebase.google.com/docs/ai-logic/context-caching ；https://cloud.google.com/blog/products/ai-machine-learning/vertex-ai-context-caching

## 5. Moonshot Kimi — Context Caching
- **现状（新版自动模式）**：对所有模型请求自动启用，无需创建/传 cache_id/管 TTL；prompt tokens > 256 才会被缓存（< 256 直接丢弃）。命中机制为系统自动识别高频重复的初始上下文（system prompt、知识文档、工具定义），建议固定内容放 messages 最前。命中部分的具体折扣价见定价页（第三方口径 Kimi K2.6 输入 $0.95/M、缓存命中约 $0.16/M，≈83% 折扣——非官方页核实，仅供参考）。
- **旧版显式 Context Cache API（公测时计费，仍可见于文档）**：创建费 24 元/M tokens；存储费 10 元/M tokens/分钟；命中调用费 0.02 元/次 + 增量 token 按模型原价；显式创建时可指定 TTL（如 3600 秒），调用时传 `cache_id`。
- **TTL**：新版系统自动管理；旧版显式缓存由用户创建时指定 TTL（可 reset_ttl 续期）。
- **最小命中前缀**：新版 > 256 tokens。
- **自动/显式**：新版全自动；旧版显式创建（`/v1/caching` 接口）。
- 来源：https://platform.kimi.com/docs/guide/use-context-caching-feature-of-kimi-api ；https://platform.kimi.com/blog/posts/context-caching ；https://platform.kimi.com/blog/posts/enhance-kimi-api-bot-with-context-caching ；（第三方价：https://artificialanalysis.ai/models/caching ）

## 6. xAI Grok — Prompt Caching
- **价格倍率**：缓存命中价随模型而异，折扣约 75–84%：grok-4.3 / grok-4.20 全系 cached input $0.20/M（标准 $1.25/M，84% off）；grok-4.6 cached $0.50/M（标准 $2.00/M，75% off）；grok-4.1 Fast cached $0.05/M（标准 $0.20/M，75% off，第三方口径）。长上下文（≥200k tokens）档 cached 价更高（如 grok-4.6 长上下文 $1.00/M）。Priority Processing 的 2× 溢价在缓存折扣之后叠加。
- **TTL**：官方文档未公布具体存活时间（未核实）；自动缓存、无需配置。
- **最小命中前缀**：未公布（未核实）。
- **命中判定**：重复/近似相同请求的前缀自动缓存（精确前缀细节未公布）；`usage` 对象返回 cached token 数。
- **自动/显式**：全自动，默认启用，无配置项。
- 来源：https://docs.x.ai/developers/pricing ；（第三方综述：https://mem0.ai/blog/xai-grok-api-pricing ）

## 7. 阿里通义千问（阿里云百炼）— Context Cache
- **价格倍率**：隐式缓存命中 = 输入价 20%（80% 折扣），无写入费；显式缓存创建 token 按输入价 125% 计费，命中按 10% 计费（90% 折扣）——明显对标 Anthropic 模式。
- **TTL**：显式缓存有效期 5 分钟（命中后重置）；隐式缓存由系统管理。
- **最小命中前缀**：官方页有「缓存最少 Token 数」表项（具体数值随模型，本次提取未取到确切数字——未核实）。
- **命中判定**：公共前缀匹配；隐式自动识别、命中率不保证；显式确定性命中。隐式/显式互斥，单请求只用一种。OpenAI 兼容 Batch 调用不享受缓存折扣。
- **自动/显式**：两者皆有——隐式全自动且不可关闭；显式需主动创建。
- 来源：https://help.aliyun.com/zh/model-studio/context-cache

## 8. 字节豆包（火山引擎）— 前缀缓存 / Session 缓存
- **价格倍率**：以 Doubao-1.5-pro-32k 为例：输入 0.8 元/M tokens，缓存命中 0.16 元/M（即 20%，80% 折扣），缓存存储 0.017 元/M tokens/小时。新一代 doubao-seed-2.x 系列：缓存命中约为输入价的 20%（如 seed-2.1-pro：输入 12 元/M、命中 2.4 元/M；存储 0.034 元/M/小时）。
- **TTL**：按小时计存储费，过期自动删除（具体默认有效期未核实到官方数字）。
- **最小命中前缀**：未核实。
- **命中判定**：前缀缓存 = 公共前缀复用（写入后不可更改）；Session 缓存 = 可更新/删除任意轮次、沿用缓存 ID。前缀缓存仅文本；Session 缓存支持多模态与 FunctionCall。
- **自动/显式**：显式——通过 Response API 创建前缀缓存或 Session 缓存。
- 来源：https://www.volcengine.com/docs/6492/1544808 ；（集成参考：https://www.cnblogs.com/yfceshi/p/19081498 ）

---

## 速查表

| 厂商 | 读命中价 vs 输入价 | 写入价 vs 输入价 | TTL | 最小前缀 | 命中判定 | 自动/显式 |
|---|---|---|---|---|---|---|
| Anthropic | 0.1×（-90%） | 1.25×(5m)/2×(1h) | 5min（命中续期）或 1h | 1,024–2,048 tok | 精确前缀 | 两者皆可 |
| OpenAI (GPT-5.6+) | 0.1×（-90%） | 1.25× | 30min 精确 TTL | 1,024 tok | 精确前缀+cache_key | 默认自动+可显式 |
| OpenAI (旧模型) | 各模型 0.1–0.5× | 免费 | 5–10min 闲置，最长 1h/24h | 1,024–2,048 tok | 精确前缀 best-effort | 全自动 |
| DeepSeek | ~0.02×（-98%） | 免费 | 自动管理（小时–天） | 未公布（前缀单元） | 完整复用前缀单元 | 全自动 |
| Google Gemini | 0.1×（2.5+，-90%） | 无溢价；显式收存储费 | 显式 1min–无上限（默认 1h） | 1,024–6,144 tok | 精确前缀 | 隐式自动+显式 API |
| Kimi (新) | 见定价页（≈-83% 第三方口径） | 无 | 系统管理 | >256 tok | 前缀自动识别 | 全自动（旧版可显式） |
| xAI Grok | 0.16–0.25×（-75~84%） | 无 | 未公布 | 未公布 | 前缀自动 | 全自动 |
| 阿里通义 | 隐式 0.2× / 显式 0.1× | 隐式无 / 显式 1.25× | 显式 5min（命中重置） | 随模型（未取到数值） | 公共前缀 | 两者皆可 |
| 字节豆包 | 0.2×（-80%） | 存储按小时计费 | 过期自动删（未核实） | 未核实 | 公共前缀/Session | 显式 |
