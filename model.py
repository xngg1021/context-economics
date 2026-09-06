# -*- coding: utf-8 -*-
"""
大模型上下文经济学 —— 定量模型
================================
研究问题:一个 agent 会话的总成本如何随 (会话长度、缓存命中率、压缩阈值、摘要保留率) 变化?

模型抽象(每一轮 = 一次 LLM 调用):
  上下文 C_k = 固定前缀 S + 滚动历史(用户输入 u + 助手输出 o + 工具输出 t)
  缓存:前缀命中比例 ρ,命中部分按缓存读价 p_r 计费,未命中按输入价 p_i
  输出:按输出价 p_o 计费
  压缩:上下文超过 θ·W 时,中间区 M 被一次摘要调用压成 r·M(保留率 r),
        摘要调用本身消耗 p_i·M + p_o·r·M(摘要输入大概率部分命中缓存,近似按 p_i 全价,偏保守)

关键理论结果(本脚本验证):
  1. 不压缩时总成本随轮数 N 呈平方增长(每轮重发全部历史:ΣC_k ≈ N·S + d·N²/2)
  2. 压缩把成本曲线切成锯齿:阈值 θ 越低,锯齿越密但平台越低 —— 存在最优 θ*
  3. 压缩盈亏平衡:把中间区 M 压成 r·M,每轮省 (1-r)·p_eff·M,
     一次性成本 p_i·M + p_o·r·M,回本轮数 = 一次性成本 / 每轮节省
"""

from dataclasses import dataclass, field

# ---------------- 定价(每百万 token,美元) ----------------
@dataclass(frozen=True)
class Pricing:
    name: str
    p_in: float      # 常规输入
    p_cache: float   # 缓存读
    p_out: float     # 输出

KIMI_K3   = Pricing("kimi-k3",   3.00, 0.30, 15.00)   # 本机实测配置
DEEPSEEK  = Pricing("deepseek",  0.28, 0.006, 0.42)   # 官方核实:磁盘缓存命中≈输入价1/50(-98%)
GEMINI_FL = Pricing("gemini-flash-aux", 0.30, 0.075, 2.50)  # 辅助模型参考量级

# ---------------- 会话形态参数 ----------------
@dataclass(frozen=True)
class SessionShape:
    window: int = 1_000_000     # 模型上下文窗口 (kimi-k3 = 1M)
    S: int = 14_000             # 固定前缀:系统提示+工具定义
    u: int = 300                # 每轮用户输入
    o: int = 800                # 每轮助手输出
    t: int = 4_000              # 每轮工具输出(均值;批量调用时更大)
    turns: int = 120            # 会话轮数

    @property
    def d(self) -> int:         # 每轮净增上下文
        return self.u + self.o + self.t

# ---------------- 模拟器 ----------------
@dataclass
class SimResult:
    theta: float
    total_cost: float
    input_cost: float
    output_cost: float
    compress_calls: int
    compress_cost: float
    cost_per_turn: float

def simulate(price: Pricing, shape: SessionShape, theta: float,
             rho: float, summary_ratio: float) -> SimResult:
    """模拟一个会话:阈值 θ(占窗口比例)触发压缩,摘要保留率 r,前缀命中率 ρ。"""
    trigger = theta * shape.window
    ctx = shape.S                      # 当前上下文(token)
    cost_in = cost_out = cost_cmp = 0.0
    n_cmp = 0
    p_eff = (1 - rho) * price.p_in + rho * price.p_cache   # 有效输入价

    for _ in range(shape.turns):
        ctx += shape.u                                  # 用户消息进入
        cost_in += ctx * p_eff / 1e6                    # 本轮输入(整个上下文重发)
        ctx += shape.o
        cost_out += shape.o * price.p_out / 1e6         # 助手输出
        ctx += shape.t                                  # 工具输出进入
        if ctx > trigger:                               # 触发压缩
            M = max(0.0, ctx - shape.S - 0.1 * ctx)     # 中间区 ≈ 上下文 - 前缀 - 保护尾(10%)
            cost_cmp += (M * price.p_in + summary_ratio * M * price.p_out) / 1e6
            ctx = shape.S + 0.1 * ctx + summary_ratio * M
            n_cmp += 1
    total = cost_in + cost_out + cost_cmp
    return SimResult(theta, total, cost_in, cost_out, n_cmp, cost_cmp,
                     total / shape.turns)

# ---------------- 盈亏平衡解析解 ----------------
def breakeven_turns(price: Pricing, rho: float, r: float) -> float:
    """把中间区 M 压成 r·M 的回本轮数(与 M 无关,可约去)。"""
    p_eff = (1 - rho) * price.p_in + rho * price.p_cache
    once = price.p_in + r * price.p_out          # 一次性压缩成本 / M
    per_turn_save = (1 - r) * p_eff              # 每轮节省 / M
    return once / per_turn_save

# ---------------- 主程序 ----------------
def main():
    shp = SessionShape()
    print("=" * 78)
    print("一、压缩盈亏平衡(解析解):压缩中间区,多少轮回本?")
    print("=" * 78)
    print(f"{'模型':<18}{'命中率ρ':>8}{'保留率r':>8}{'回本轮数':>10}")
    for price in (KIMI_K3, DEEPSEEK):
        for rho in (0.0, 0.5, 0.85, 0.95):
            for r in (0.1, 0.2, 0.3):
                print(f"{price.name:<18}{rho:>8.2f}{r:>8.2f}"
                      f"{breakeven_turns(price, rho, r):>10.1f}")

    print()
    print("=" * 78)
    print(f"二、会话模拟:kimi-k3,{shp.turns} 轮,每轮净增 {shp.d} tok,前缀 {shp.S} tok")
    print("=" * 78)
    for rho in (0.0, 0.85):
        print(f"\n--- 前缀命中率 ρ={rho} ---")
        print(f"{'θ':>6}{'总成本$':>10}{'输入$':>10}{'输出$':>9}{'压缩$':>9}"
              f"{'压缩次数':>9}{'$/轮':>8}")
        rows = []
        for theta in (None, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.75, 0.9):
            if theta is None:      # 不压缩:θ=∞(窗口永不触发)
                res = simulate(KIMI_K3, shp, theta=10.0, rho=rho, summary_ratio=0.2)
                rows.append((0.0, res)); continue
            rows.append((theta, simulate(KIMI_K3, shp, theta, rho, 0.2)))
        base = rows[0][1].total_cost
        for theta, res in rows:
            tag = "不压缩" if theta == 0.0 else f"{theta:.2f}"
            saving = (1 - res.total_cost / base) * 100
            print(f"{tag:>6}{res.total_cost:>10.3f}{res.input_cost:>10.3f}"
                  f"{res.output_cost:>9.3f}{res.compress_cost:>9.3f}"
                  f"{res.compress_calls:>9}{res.cost_per_turn:>8.4f}  "
                  f"省 {saving:5.1f}%")
        best = min(rows[1:], key=lambda x: x[1].total_cost)
        print(f"最优 θ* = {best[0]:.2f}(相对不压缩省 {(1-best[1].total_cost/base)*100:.1f}%)")

    print()
    print("=" * 78)
    print("三、缓存的经济价值:有效输入价 vs 命中率(每百万 token 美元)")
    print("=" * 78)
    print(f"{'ρ':>6}{'kimi-k3':>10}{'deepseek':>10}")
    for rho in (0.0, 0.5, 0.7, 0.85, 0.9, 0.95, 0.99):
        row = f"{rho:>6.2f}"
        for price in (KIMI_K3, DEEPSEEK):
            p_eff = (1 - rho) * price.p_in + rho * price.p_cache
            row += f"{p_eff:>10.3f}"
        print(row)
    print("\n注:kimi 缓存读价 $0.3 是 deepseek $0.006 的约 50 倍 —— 缓存命中≠免费,")
    print("    高命中率下 kimi 的有效输入价下限就是 $0.3,这是'前缀稳定'策略的价值上限。")

if __name__ == "__main__":
    main()
