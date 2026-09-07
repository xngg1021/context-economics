# KV Cache 复用与推理系统层研究综述（大模型上下文经济学·系统侧基础）

> Runtime successor status (2026-09-07): provider adapters are fixture-tested; credential-backed evidence is BLOCKED by runtime authorization. Partial Hermes trace-replay and synthetic retention do not establish runtime-A/B or task-economic results. Production mutation remains disabled. See [REAL-RUNTIME-CAMPAIGN.md](REAL-RUNTIME-CAMPAIGN.md).

调研日期：2026-08-19；所有 arXiv 编号与量化结论均经检索核实。

## 0. KV cache 基础经济学公式

- **每 token KV cache 字节数** = `2 × layers × kv_heads × head_dim × dtype_bytes`
  - 因子 2 = K 和 V 两份；GQA/MQA 模型用 `kv_heads`（而非 query heads），可大幅降低缓存量。
  - 例：LLaMA-7B（32 层、32 头、head_dim=128、FP16）→ 2×32×32×128×2 = **524,288 B ≈ 512 KB/token/序列**。
  - 例：Llama-3-70B 类 GQA（80 层、8 KV 头、128、BF16）→ 2×80×8×128×2 = 327,680 B ≈ 320 KB/token；4096 token × batch 8 ≈ 10 GiB。
  - 来源（工程向推导，非论文）：mbrenndoerfer.com/writing/kv-cache-memory-calculation-llm-inference-gpu；systemdesignacademy.com/blog/kv-cache-llm-inference-memory；lyceum.technology/magazine/kv-cache-memory-calculation-llm
- **商业 prompt caching 定价（存储 vs 重算的现实定价）**：Anthropic 缓存写 ≈ 1.25× 基础输入价、缓存读 ≈ 0.1×，TTL 5 分钟，5 分钟内复用即回本；OpenAI 自动前缀缓存折扣更低。来源：tmls.nyc/research/ai-caching-strategies（二手汇总，2026）；edony.ink/en/the-physics-of-inference-a-deep-dive-into-kv-and-prompt-caching。**注意：定价为供应商页面口径，会随时间变化，引用时需回查官网。**

## 1. vLLM / PagedAttention（SOSP 2023）

- 论文：*Efficient Memory Management for Large Language Model Serving with PagedAttention*，Kwon et al.，**arXiv:2309.06180**，SOSP 2023（Koblenz）。https://arxiv.org/abs/2309.06180
- 核心：借鉴 OS 虚拟内存分页，KV cache 按固定大小 block 存储 + block table 间接寻址，消除连续显存预留；内部/外部碎片化接近零（near-zero waste）；copy-on-write 支持 beam search/并行采样共享。
- **Prefix caching（Automatic Prefix Caching, APC）**：后续版本加入，按 block 哈希共享前缀 KV，是多请求前缀复用的工程标准实现（vLLM 文档，论文本身未含 APC，需注明这一点）。
- 量化结论（论文摘要）：吞吐较 FasterTransformer/Orca 等 SOTA 提升 **2–4×**；同实验下较 HuggingFace Transformers 最高约 24×（vLLM 官方博客口径）。

## 2. SGLang / RadixAttention（NeurIPS 2024）

- 论文：*SGLang: Efficient Execution of Structured Language Model Programs*，Zheng et al.，**arXiv:2312.07104**，NeurIPS 2024。https://arxiv.org/abs/2312.07104；会议页：https://proceedings.neurips.cc/paper_files/paper/2024/hash/724be4472168f31ba1c9ac630f15dec8-Abstract-Conference.html
- 核心：RadixAttention——用**基数树（radix tree）**管理 KV cache，多请求间自动共享任意可匹配前缀（不限于单次生成的系统提示）；LRU 驱逐 + cache-aware 调度；配合压缩有限状态机加速结构化输出。
- 量化结论（论文/NeurIPS 摘要）：吞吐最高提升 **6.4×**、延迟最高降低 **3.7×**（对比 Guidance、vLLM 等基线；LMSYS 博客口径为最高 5× 吞吐）。
- 博客：https://www.lmsys.org/blog/2024-01-17-sglang

## 3. CacheBlend（EuroSys 2025）

- 论文：*CacheBlend: Fast Large Language Model Serving for RAG with Cached Knowledge Fusion*，Yao et al.，**arXiv:2405.16444**，EuroSys 2025。https://arxiv.org/abs/2405.16444
- 核心：**非前缀 KV 复用**——RAG 场景下多个已缓存文本块按任意顺序拼接进 prompt 时，直接复用各块预计算 KV，仅选择性重算一小部分 token（5%–18%，按注意力“汇”token 选取）修复跨块注意力偏差。
- 量化结论：TTFT 降低 **2.2–3.3×**，吞吐提升 **2.8–5×**，质量与全量重算差距仅 0.01–0.03（三个开源模型 × 四个 benchmark）。来源：arxiv.org/html/2405.16444v3；ucm.readthedocs.io（vLLM UCM 文档）。

## 4. Prompt Cache（Princeton，MLSys 2024）

- 论文：*Prompt Cache: Modular Attention Reuse for Low-Latency Inference*，Gim et al.（Princeton/CMU/Yale），**arXiv:2311.04934**，MLSys 2024。https://arxiv.org/abs/2311.04934
- 核心：Prompt Markup Language（PML）把常见 prompt 段（system prompt、文档、few-shot 示例）声明为**模块**，预计算其注意力状态并存储，跨 prompt、**允许段出现在非前缀位置**（通过位置编码处理）地复用。
- 量化结论（MLSys 摘要）：TTFT 延迟改善 **GPU 上 8×、CPU 上 60×**，精度无损，无需改模型参数。来源：https://proceedings.mlsys.org/paper_files/paper/2024/hash/a66caa1703fe34705a4368c3014c1966-Abstract-Conference.html

## 5. 分层 KV cache 存储/卸载（HBM→DRAM→SSD）

### 5.1 Mooncake（FAST 2025 最佳论文，Moonshot AI / Kimi 生产系统）
- 论文：*Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving*，Qin et al.，**arXiv:2407.00079**，FAST 2025 最佳论文。https://arxiv.org/abs/2407.00079
- 核心：以 KVCache 为中心的 **prefill/decode 分离（disaggregation）**架构；调度以 KVCache 块为对象；利用集群闲置 CPU/DRAM/SSD 构建分布式 KVCache 池（Mooncake Store）；基于预测的早期拒绝应对过载。
- 量化结论：在满足相同 TTFT/TBT SLO 前提下吞吐提升 **50%–525%**（真实负载+模拟过载场景，A800 集群、LLaMA2-70B 规格）。来源：arxiv.org/html/2407.00079v1。
- 开源：https://github.com/kvcache-ai/Mooncake

### 5.2 LMCache（MLSys 2026 invited talk；生产级 KV 缓存层）
- 论文：*LMCache: An Efficient KV Cache Layer for Enterprise-Scale LLM Inference*，Cheng et al.，**arXiv:2510.09665**（2025-10）。https://arxiv.org/abs/2510.09665
- 核心：从 serving 引擎（vLLM/SGLang）抽取 KV cache，跨 **GPU HBM → 本地/远端 CPU DRAM → 磁盘 → 对象存储（S3）** 多层存储与并行存取；支持非前缀 chunk 复用、跨实例 P2P 传输、与 CacheBlend 类选择性重算结合；多轮 QA/RAG 显著降低 TTFT、节省 GPU 算力。
- 来源：arxiv.org/html/2510.09665v2；docs.lmcache.ai；github.com/lmcache/lmcache。注：这是 2025 年系统论文，不是 2410.xxxx（调研中未发现该编号的 LMCache 论文，正确编号为 2510.09665）。

### 5.3 FlexGen（ICML 2023；单 GPU 高吞吐 offloading 先驱）
- 论文：*FlexGen: High-Throughput Generative Inference of Large Language Models with a Single GPU*，Sheng et al.，**arXiv:2303.06865**，ICML 2023。https://arxiv.org/abs/2303.06865
- 核心：把权重/激活/**KV cache 统一纳入 GPU–CPU–Disk 三级 offloading**，用线性规划搜索张量放置与计算调度（zig-zag block schedule）以最大化吞吐；权重与 KV cache 4-bit 压缩且精度损失可忽略。
- 量化结论：单块 16GB T4 可跑 OPT-175B；吞吐较 HuggingFace Accelerate / DeepSpeed Zero-Inference 等 offloading 系统高**数量级**（官方口径 "sometimes by orders of magnitude"，OPT-175B 上约 100× 量级）；KV cache 4-bit 压缩直接减半以上显存。来源：github.com/FMInference/FlexGen README + 论文。

## 6. 其他相关（调研中发现的补充）

- *Can I Buy Your KV Cache?*（arXiv:2606.13361，2026，arxiv.org/html/2606.13361v1）：分析 KV cache 交易/托管经济学——KV 几乎不可压缩，跨站传输 egress 成本高于其省下的 prefill 成本，故托管在 provider 侧（如现有 prompt caching 定价）才成立。**该文为新近预印本，结论未独立复核，仅作线索。**
- 供应商定价即最现实的“存储成本 vs 重算成本”权衡实证：写 1.25× / 读 0.1×（Anthropic），隐含 KV 存储+命中判定成本 ≈ 重算成本的 10%。

## 未核实/需注意

- vLLM “24× vs HuggingFace”为官方博客口径，论文摘要只声明 2–4×（vs FasterTransformer/Orca）。
- vLLM 的 Automatic Prefix Caching 属工程后续，不在 SOSP 论文正文；引用时应区分论文与文档。
- FlexGen “100×” 为社区转述量级，论文表述为 "orders of magnitude"，引用建议用后者或注明场景。
- 商业 prompt caching 价格（1.25×/0.1×）随时间变动，正式引用需回查供应商当日报价。
