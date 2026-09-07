# 上下文压缩/上下文管理学术研究前沿调研（截至 2026-08-19）

> Runtime successor status (2026-09-07): provider adapters are fixture-tested; credential-backed evidence is BLOCKED by runtime authorization. Partial Hermes trace-replay and synthetic retention do not establish runtime-A/B or task-economic results. Production mutation remains disabled. See [REAL-RUNTIME-CAMPAIGN.md](REAL-RUNTIME-CAMPAIGN.md).

> 用途：「大模型上下文经济学」研究的算法侧基础。所有指标以论文/官方表述为准；标注「未逐项核实」者为本轮搜索未能核对原始表格。

## 1. 软压缩 / 提示压缩（hard text，token 删除/选择）

- **LLMLingua**（EMNLP 2023，arXiv:2310.05736）：用小模型困惑度评估 token 冗余并删除。GSM8K 9 步 CoT 提示最高 20x 压缩，EM 降幅 <2 点；2400 token 压到 115 仍对齐 full-shot；额外节省 20–30% 输出 token。经济学含义：输入计费直接下降 ~95%，且推理类任务对压缩最不敏感。
  来源：https://arxiv.org/abs/2310.05736；https://github.com/microsoft/LLMLingua
- **LongLLMLingua**（arXiv:2310.06839）：面向长文档，问题感知式重排+压缩。官方口径：4x 压缩下性能不降反升 17.1%（LongBench 多文档 QA 场景）。经济学含义：压缩可作为「去噪」手段，省 token 的同时提升长上下文利用率。
  来源：https://www.llmlingua.com
- **LLMLingua-2**（ACL 2024，arXiv:2403.12968）：BERT 级 encoder 做 token 分类，任务无关。压缩速度比 LLMLingua 快 3–6x；典型 2–5x 压缩下性能损失极小（具体各比率保留率未逐项核实）。经济学含义：压缩器本身开销降到可忽略，使「压缩前置」在在线服务里具备正的净收益。

## 2. 硬压缩 / 激活压缩（压成软 token / 记忆槽）

- **Gist tokens**（NeurIPS 2023，arXiv:2304.08467）：指令蒸馏为 gist token。最高 26x 压缩、40% FLOPs 削减（短指令场景）。经济学含义：系统提示/少样本模板等重复前缀的边际成本趋近于零。
- **AutoCompressor**（arXiv:2307.06950）：递归将段落折叠为 summary vectors，序列实验最长 30,720 token；压缩倍率多在 4x–30x 区间（未逐项核实）。经济学含义：递归式软压缩=以固定小内存换任意长历史，是「无限上下文」的廉价近似。
- **ICAE**（ICLR 2024，arXiv:2307.06945）：LoRA 编码器+冻结解码器，<1% 额外参数实现 4x 压缩；缓存槽加速最高 >7x。经济学含义：压缩模块成本与主模型解耦，一次预训练可复用于多任务。
- **Activation Beacon**（ICLR 2025，arXiv:2401.03462）：渐进式蒸馏上下文为一小组激活；推荐 x8（保留绝大部分信息），论文报告在显著高于 x8 的比率下仍优于 ICAE/AutoCompressor；仅在 <20K 上训练即可泛化到 128K。经济学含义：软 token 数量可随预算连续调节，形成「上下文-成本」连续前沿。
- **COCOM**（WSDM 2025，arXiv:2407.09252，注意非 2407.03408）：RAG 专用，把检索段落压成少量 context embeddings，压缩率 4x–128x 可配置，显著加快解码（各比率下 EM 保留率未逐项核实）。经济学含义：RAG 的检索成本与生成成本解耦，压缩嵌入可离线预计算并复用。
- **500xCompressor**（arXiv:2408.03094）：追求极端比率（名义最高 ~500x），2026 年综述将其列入 KV-carried 路线；指标未核实。

## 3. 递归/流式摘要与记忆

- **MemGPT / Letta**（arXiv:2310.08560）：OS 式虚拟上下文管理，主存/外存分页换入换出；Letta 为其工程化延续。经济学含义：把「上下文长度」从模型约束变为存储层级问题，按访问频率付不同的价。
- **LoCoMo**（ACL 2024，arXiv:2402.17753）：超长对话记忆基准（QA/事件摘要/多模态对话）。
- **LongMemEval**（ICLR 2025，arXiv:2410.10813）：500 题、5 类记忆能力；~115K token/场景（S），M 版达 1.5M；商用助手与长上下文模型均有 ~30% 准确率下滑。经济学含义：单纯扩大窗口不足以解决记忆，必须引入管理机制——为「记忆即服务」定价提供依据。
- **LongMemEval-V2**（arXiv:2605.12493）：>100M token 的 web-agent 历史记忆基准，提出 AgentRunbook-R 记忆池方法。
- **Mem0**（arXiv:2504.19413，ECAI 2025）与 **Zep**（arXiv:2501.13956）：外部记忆层产品化；注意 Letta 官方博客公开质疑 Mem0 在 LoCoMo 上的对比数字可复现性——引用其经济性声明需谨慎。
- 递归摘要基准：**BookSum**（arXiv:2105.08209，长篇叙事）为经典基线；**Recurrent Context Compression**（arXiv:2406.14059，宣称 ~32x 循环压缩）本轮未核实。

## 4. RAG vs 长上下文 vs 压缩的经济学对比

- **Self-Route**（EMNLP 2024 Industry，arXiv:2407.16833）：LC 稳定优于 RAG（Gemini-1.5-Pro +7.6%、GPT-4o +13.1%、GPT-3.5 +3.6%），但 RAG 成本低得多；按模型自评把查询路由给 RAG 或 LC，成本降 65%（Gemini-1.5-Pro）/39%（GPT-4o）且性能与纯 LC 相当（差异 -2.2%~+1.7%）。经济学含义：存在可计算的「查询级路由」套利空间，成本-性能前沿可用混合策略逼近。
  来源：https://arxiv.org/abs/2407.16833
- **ACC-RAG**（arXiv:2507.22931）：自适应选择压缩率的 RAG 压缩器；其对照表统一比较了 AutoCompressor/COCOM/xRAG/ICAE 在 ×4/×128 等比率下的 EM 与解码 token 数，是压缩率-性能权衡的现成数据表。
- Databricks 基准（2024 博客）：o1 在长上下文 RAG 上 SOTA，Gemini-1.5 在 2M token 内性能稳定——说明「长窗口+检索」在头部模型上仍在融合而非替代。

## 5. 2025–2026 新进展（综述与 agent 场景）

- **A Survey of Context Engineering for LLMs**（arXiv:2507.13334，2025-07）：上下文工程全景综述，压缩为三大主线之一。
- **Context Compression for LLM Agents: A Survey**（preprints.org 202605.2065，2026）：专论 agent 上下文压缩，划分 硬文本/软嵌入/KV-cache/互补（文件系统、记忆层级）/RL 学习式 五大族，并给出 2023–2026 方法时间线（含 Obs-Masking、ACON、SWE-Pruner、EDU 等 agent 专用压缩器）。
- **Agentic Context Engineering (ACE)**（arXiv:2510.04618）：提出「context collapse」失效模式（反复重写上下文导致信息塌缩）；ReAct+ACE 在 AppWorld 达 59.4%，以小模型追平 GPT-4.1 生产级系统（60.3%）。经济学含义：上下文工程可替代模型升级，直接改写「智力/美元」曲线。
- **MemAgent**（arXiv:2507.02259）：RL 训练的记忆式动态压缩。
- **Context as a Tool**（arXiv:2512.22087）：面向长程 SWE-agent 的上下文管理。

## 总体经济学脉络
硬文本压缩（20x 内近似无损）→ 软 token 压缩（4x–128x 可调前沿）→ 记忆分层/外部化（窗口上限解除）→ 查询级路由与自适应压缩率选择（单位任务成本最优）。研究重心已从「压缩单条提示」转向「agent 长程任务中动态管理整个上下文预算」。
