# Agent Harness 上下文工程与成本优化调研（2026-08-19）

标注：[官方] 官方文档/博文；[逆向] 社区逆向分析；[实测] 实测数据；[社区] 社区讨论/第三方总结。已知基线（无需重复核实）：arXiv 2601.06007《Don't Break the Cache》（500+ 会话实测：稳定前缀+动态内容置尾，成本降 41-80%、TTFT 降 13-31%）；MemGPT arXiv 2310.08560。

## 1. Claude Code 的上下文压缩机制

### 官方
- 《Claude Code Best Practices》[官方]：主动用 `/clear` 重置上下文、`/compact` 在任务边界压缩；CLAUDE.md 作为持久化指令层。https://www.anthropic.com/engineering/claude-code-best-practices
- 监控与归因：`/cost`（API 用户）给出 input/output/cache read/cache write 分项；`/usage` 按 skills、subagents、MCP server 归因占比；本地日志默认只保留 30 天（cleanupPeriodDays 可调）。[官方+第三方解读] https://www.faros.ai/blog/claude-code-token-usage

### 社区逆向
- vicnaum 的逆向 X 线程（经 Hermes Agent issue #525 转引）[逆向]：Claude Code 是三层体系——微压缩（microcompact）/自动压缩/手动压缩；微压缩可无 LLM 地外科式剥离工具调用对与 thinking 块。https://github.com/NousResearch/hermes-agent/issues/525
- DecodeClaude《Inside Claude Code's Compaction System》（逆向已发布 bundle）[逆向]：三层机制——①微压缩：尽早卸载庞大 tool result；②自动压缩：接近满时总结为结构化"working state"，再 rehydrate 最近文件、todos、continuation 指令；③手动压缩在任务边界触发。https://decodeclaude.com/compaction-deep-dive
- Hyperdev 观察 [社区/实测性观察]：Claude Code 在持续下调 auto-compact 触发阈值、更早压缩以保留工作记忆；旧版曾触发过晚导致连压缩本身的空间都不足；建议现在让 auto-compact 自己工作而非禁用。https://hyperdev.matsuoka.com/p/how-claude-code-got-better-by-protecting
- MindStudio [社区实践]：`/compact` 应在约 60% 占用时主动运行并附带保留指令（架构决策、进行中的 bug、文件范围、约束），而非等警告出现。https://www.mindstudio.ai/blog/claude-code-compact-command-context-management

## 2. Anthropic 官方 Context Engineering 系列

- 《Effective context engineering for AI agents》（2025-09-29）[官方]：核心定义——"在推理期间策划并维持最优 token 集合"；上下文是有限且边际收益递减的资源，目标是"最小高信号 token 集"；三大手段：压缩（compaction）、结构化笔记/agentic memory（如 Claude 玩宝可梦的步数台账）、sub-agent 架构隔离上下文；配套发布 Sonnet 4.5 文件式 memory tool（public beta）。https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Claude Cookbook《Context engineering: memory, compaction, and tool clearing》[官方教程]：三原语——compaction 压缩对话历史、tool-result clearing 丢弃可重取的工具输出（file read/API 查询不必逐轮携带原文）、memory tool 跨会话持久化。https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools
- 配套机制：Context Editing API（服务端、缓存友好的 tool/thinking 清理），见 Hermes issue #526 转引 [官方 API+社区转引]。https://github.com/NousResearch/hermes-agent/issues/525

## 3. Cursor / Windsurf / Cline / Aider

### Cursor
- 官方实践（Cursor 团队演讲转录）[官方]：长 tool response 落盘成文件而非塞进上下文；达到窗口或手动 `/summarize`/`/compact` 时把聊天历史存为文件并给 agent 文件引用——agent 可按需回溯原文，而非只依赖有损摘要；to-do list 由 agent 自管理以避免浪费 token。https://www.youtube.com/watch?v=Lwbk_h0l4Kk
- 社区最佳实践 [社区]：Research→Plan→Execute 分阶段、每阶段结果存 markdown 供下一阶段；`.cursorrules` 管静态上下文；大项目即使有 1M 窗口仍应分阶段。https://forum.cursor.com/t/how-to-handle-large-projects-with-limited-context/148049
- 官方文档《Large Codebases》入口 [官方]：https://docs.cursor.com（经上述论坛帖引用，具体页未单独核实）

### Windsurf
- 第三方梳理 [社区]：Cascade 双模式（Chat/Agent）；上下文由 workspace index + Rules 文件 + Memories（持久记忆）+ @ 命令显式注入组合；Flow 范式追踪"怎么工作"而不只是"改了哪些文件"。https://iceberglakehouse.com/posts/2026-03-context-windsurf
- 实测对比 [实测-第三方测评]：同一 10 文件重构，Windsurf token 消耗比 Cursor 低约 22%（各自 usage dashboard 读数）。https://tech-insider.org/windsurf-vs-cursor-2026

### Cline
- 官方博文 [官方]：上下文进度条与智能截断——缓冲公式 `max(contextWindow-40000, contextWindow*0.8)`；Haiku 类模型 27k 固定缓冲、128k 标准模型 30k 缓冲；截断非随机删消息而是保关键上下文的算法。https://cline.bot/blog/understanding-the-new-context-window-progress-bar-in-cline
- 第三方源码剖析 [逆向-开源代码分析]：`ContextManager` 维护 `contextHistoryUpdates` 增量修改映射（文本改动、文件内容替换、时间戳）；`FileContextTracker`/`ModelContextTracker` 分层；去重优化减少冗余。https://medium.com/@balajibal/dissecting-cline-cline-context-management-260aec3d84cb

### Aider
- 官方文档《Repository map》[官方]：全仓库 tree-sitter 符号级 map（类/函数/签名）；PageRank 式图排序算法在 `--map-tokens` 预算（默认 1k tokens）内选最相关部分；无文件加入会话时会动态放大 map 以理解全仓。https://aider.chat/docs/repomap.html
- 官方文档《Token limits》[官方]：aider 不强制 token 限制，只上报 API 错误；`/tokens` 分项显示 system/repo map/各文件占用。https://aider.chat/docs/troubleshooting/token-limits.html
- 已知缺陷 [社区 issue]：v0.40.6 时期 `--map-tokens 1024` 未被遵守、repo map 实际用 16k+ tokens（issue #752）。https://github.com/Aider-AI/aider/issues/752

## 4. Manus 的上下文工程经验

- 《Context Engineering for AI Agents: Lessons from Building Manus》（Yichao "Peak" Ji，2025-07-18）[官方-一手]：① KV-cache 命中率是生产 agent 唯一最重要指标——agent 输入:输出 token 约 100:1，Claude Sonnet 缓存输入 $0.30/MTok vs 未缓存 $3/MTok（10 倍差）；② 保缓存三招：稳定前缀、append-only 上下文、确定性序列化；③ 工具不删只 mask——用状态机+logit masking 约束动作空间，避免改工具定义打爆缓存和引用已删工具导致幻觉；④ 文件系统当外部记忆，128k 窗口对长任务不够，observation 可丢弃但留可恢复引用；⑤ 用复述 todo 操控注意力；⑥ 保留错误与失败轨迹供模型自我修正；⑦ 警惕 few-shot 同质化。https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
- ZenML LLMOps 数据库条目 [社区总结]：四次框架重写换来的经验；logit masking+状态机细节；要点与上文一致。https://www.zenml.io/llmops-database/context-engineering-strategies-for-production-ai-agents

## 5. 实测 token 消耗结构/成本构成

- arXiv 2601.06007《Don't Break the Cache》[实测-学术]（已知基线）：500+ 真实 agent 会话，稳定前缀+动态内容置尾，成本降 41-80%、TTFT 降 13-31%。https://arxiv.org/abs/2601.06007
- Firecrawl《12 Ways to Cut Token Consumption in Claude Code》[实测]：每个 MCP server 会话开局注入 1-2 万 token schema，多 server 静默加 5-7 万 token 且逐轮随行；`.claudeignore` 纪律实测降上下文 85.5%；引 MindStudio benchmark：五阶段结构化流程比非结构化会话省 14% token、9% 成本。https://www.firecrawl.dev/blog/claude-code-token-efficiency
- claude-code-usage-analyzer [实测工具]：基于 ccusage + 本地 jsonl 原始数据，按 input/output/cache creation/cache read 四类分项给日均成本、P95、每模型缓存效率、单请求 token 分布（P75/P95/P99）。https://github.com/aarora79/claude-code-usage-analyzer
- dev.to 三方横评 [实测-第三方测评]：有效代码上下文 Cursor ≈60-80k tokens、Windsurf ≈50-70k、Claude Code 150k+（按需读文件）；Claude Code API 重度使用单次大重构 $5-15。https://dev.to/pockit_tools/cursor-vs-windsurf-vs-claude-code-in-2026-the-honest-comparison-after-using-all-three-3gof
- YouTube《10 Tricks to Optimise Token Usage》[实测-小规模]：本地 SQLite+向量索引经 MCP 供上下文，explore 阶段 token 降约 29%、pre-agent 降约 37%、tool call 数降 25%（单作者自测，样本小）。https://www.youtube.com/watch?v=XB6iJvrLFmE

## 未核实/缺口
- vicnaum 原始 X 线程直链未取到（仅经 GitHub issue 转引）；Claude Code 官方 auto-compact 具体阈值百分比未见官方公布数字（Hyperdev 为行为观察推测）。
- Cursor《Large Codebases》官方文档具体 URL 未单独核实；Cursor/Windsurf 内部检索排序细节无一手逆向文章。
- Anthropic Context Editing API 官方文档页未单独打开（经 cookbook 与 issue 转引确认存在）。
