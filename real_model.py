# -*- coding: utf-8 -*-
"""
真实会话重放模型 —— 压缩阈值的多目标选择
==========================================
数据源: 三个 profile 的 state.db(只读) —— 真实消息流、真实调用次数、真实缓存命中率。

模拟维度:
  1. 经济: 每个真实会话在不同压缩阈值 θ 下的总成本(真实增长曲线,非线性假设)
  2. 召回率: 压缩质量衰减(q)与长上下文退化(lost-in-the-middle, LongMemEval 锚点)的净效果
  3. 持续性: 一条用户事实保持"可召回"(recall>0.5)的平均轮数
  4. UX/记忆感知: 用户回指旧内容时模型"已经忘了"的期望失败次数/会话

关键假设(均有出处,标注于下):
  RATIO  : 字符→token 换算,由无压缩会话的账单反推校准(脚本内自动计算中位数)
  q      : 单次压缩后的信息保留率,按角色分级(压缩器 prompt 强制逐字保留标识符)
  L0/slope: 长上下文退化,LongMemEval(arXiv 2410.10813): 商用助手 115K-1.5M 区间掉 ~30%
  P_REF  : 用户每轮回指 12 轮以前内容的概率(UX 感知参数,做敏感性)
"""
import sqlite3, os, sys
from dataclasses import dataclass

# ---------- 定价($/M token) ----------
PRICES = {
    "kimi":     (3.00, 0.30, 15.00),
    "deepseek": (0.28, 0.006, 0.42),
    "gemini":   (0.30, 0.075, 2.50),
}
def price_of(model: str):
    m = (model or "").lower()
    if "kimi" in m: return PRICES["kimi"]
    if "deepseek" in m: return PRICES["deepseek"]
    if "gemini" in m: return PRICES["gemini"]
    return PRICES["kimi"]

W = 1_000_000          # 当前主模型窗口
S = 15_000             # 固定前缀
R_SUMMARY = 0.2        # target_ratio: 压缩保留率(与配置一致)
L0, DROP, LMAX = 115_000, 0.30, 1_500_000   # LongMemEval 锚点
SLOPE = DROP / (LMAX - L0)                   # 每 token 的召回退化率
Q = {"user": 0.95, "assistant": 0.85, "tool": 0.70}   # 单次压缩保留率(按角色)
W_IMP = {"user": 3.0, "assistant": 2.0, "tool": 1.0}  # 重要性权重
P_REF, REF_AGE, FAIL_LINE = 0.25, 12, 0.6    # UX 参数: 回指概率/回指年龄/遗忘判定线

DBS = {
    "default": os.path.expandvars(r"%LOCALAPPDATA%\hermes\state.db"),
    "dad":  os.path.expandvars(r"%LOCALAPPDATA%\hermes\profiles\dad\state.db"),
    "mom":  os.path.expandvars(r"%LOCALAPPDATA%\hermes\profiles\mom\state.db"),
}

# ---------- 数据加载 ----------
def load_sessions():
    out = []
    for prof, p in DBS.items():
        con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        ids = [r[0] for r in con.execute(
            "SELECT id FROM sessions WHERE message_count >= 8")]
        for sid in ids:
            msgs = con.execute(
                """SELECT role, LENGTH(COALESCE(content,''))+LENGTH(COALESCE(tool_calls,''))
                            +LENGTH(COALESCE(reasoning_content,''))
                   FROM messages WHERE session_id=? ORDER BY timestamp, id""", (sid,)).fetchall()
            row = con.execute(
                """SELECT model, api_call_count, input_tokens, cache_read_tokens
                   FROM sessions WHERE id=?""", (sid,)).fetchone()
            if not msgs or not row: continue
            model, calls, itok, crtok = row
            rho = (crtok or 0) / max(1, (itok or 0) + (crtok or 0))
            out.append(dict(prof=prof, sid=sid, model=model, msgs=msgs,
                            calls=calls or len(msgs), rho=min(rho, 0.99),
                            chars=sum(m[1] for m in msgs)))
        con.close()
    return out

def calibrate(sessions):
    """用无压缩会话校准 字符/token: C_peak≈2×tot/calls−S (线性增长假设) """
    rats = []
    for s in sessions:
        con = sqlite3.connect(f"file:{DBS[s['prof']]}?mode=ro", uri=True)
        cmpc = con.execute("SELECT COALESCE(SUM(compacted),0) FROM messages WHERE session_id=?",
                           (s["sid"],)).fetchone()[0]
        con.close()
        if cmpc == 0 and s["calls"] >= 8 and s["chars"] > 80_000:
            cpeak = 2 * (s.get("tot_in", 0)) / s["calls"] - S
            if cpeak > S * 2:
                rats.append(s["chars"] / cpeak)
    rats.sort()
    return rats[len(rats)//2] if rats else 2.3

# ---------- 单会话重放 ----------
@dataclass
class Msg:
    role: str
    tok: float
    recall: float = 1.0
    age_born: int = 0     # 出生轮

def replay(sess, ratio, theta, p_ref=P_REF):
    p_in, p_cache, p_out = price_of(sess["model"])
    rho = sess["rho"]
    p_eff = (1 - rho) * p_in + rho * p_cache
    # 长上下文退化是"环境因子": 测量时刻生效,不写进消息的固有召回
    lenf = lambda c: max(0.5, 1.0 - SLOPE * max(0.0, c - L0))
    live = [Msg("sys", S)]          # 前缀永不压缩
    ctx = S
    turn = 0
    cost = compressions = 0.0
    n_cmp = 0
    ux_fail = 0.0
    recall_integral = 0.0           # 全程记忆完整度积分
    persist_samples = []            # 用户事实可召回轮数

    for role, chars in sess["msgs"]:
        tok = max(1.0, chars / ratio)
        mrole = "tool" if role == "tool" else role
        if role == "user":
            turn += 1
            # UX: 用户回指旧内容,检验是否还记得
            old = [m for m in live[1:] if turn - m.age_born >= REF_AGE]
            if old:
                w = sum(W_IMP.get(m.role, 1) for m in old)
                r_old = lenf(ctx) * sum(m.recall * W_IMP.get(m.role, 1) for m in old) / w
                if r_old < FAIL_LINE:
                    ux_fail += p_ref
        if role == "assistant":
            cost += ctx * p_eff / 1e6          # 这次调用的输入
            cost += tok * p_out / 1e6          # 输出
            # 全程记忆完整度(调用时刻快照)
            if len(live) > 1:
                w = sum(W_IMP.get(m.role, 1) for m in live[1:])
                recall_integral += lenf(ctx) * sum(m.recall * W_IMP.get(m.role, 1)
                                                   for m in live[1:]) / w
        live.append(Msg(mrole, tok, 1.0, turn))
        ctx += tok

        # 触发压缩
        if ctx > theta * W:
            n_cmp += 1
            tail_tok = 0.10 * ctx
            acc, cut = 0.0, len(live)
            for i in range(len(live) - 1, 0, -1):
                acc += live[i].tok
                if acc >= tail_tok: cut = i; break
            middle = live[1:cut]
            M = sum(m.tok for m in middle)
            cost += (M * p_in + R_SUMMARY * M * p_out) / 1e6     # 摘要调用
            # 用户事实在进摘要前的持续轮数采样
            for m in middle:
                if m.role == "user":
                    persist_samples.append(turn - m.age_born + (m.recall > 0.5) * 0)
            summary = Msg("tool", R_SUMMARY * M,
                          min(Q.values()) , turn)                # 摘要本身
            # 被压消息的信息按角色保留率折进摘要: 摘要召回=加权平均
            if middle:
                w = sum(W_IMP.get(m.role, 1) for m in middle)
                summary.recall = sum(m.recall * Q.get(m.role, 0.7) * W_IMP.get(m.role, 1)
                                     for m in middle) / w
            live = [live[0], summary] + live[cut:]
            ctx = S + summary.tok + tail_tok
            # 缓存断点成本: 摘要插入改变了前缀,下一次调用只有稳定头 S 命中,
            # 其余部分按全价 re-prefill 一次(此后增长的前缀重新命中)
            cost += (ctx - S) * rho * (p_in - p_cache) / 1e6

    # 收尾指标
    if len(live) > 1:
        w = sum(W_IMP.get(m.role, 1) for m in live[1:])
        final_recall = lenf(ctx) * sum(m.recall * W_IMP.get(m.role, 1) for m in live[1:]) / w
    else:
        final_recall = 1.0
    # 持续性: 仍存活用户消息的当前年龄均值(未被压掉=全程可召回) + 被压样本
    alive_user_ages = [turn - m.age_born for m in live[1:] if m.role == "user"]
    persist = (sum(alive_user_ages) + sum(persist_samples)) / max(1, len(alive_user_ages) + len(persist_samples))
    n_assist = max(1, sum(1 for r, _ in sess["msgs"] if r == "assistant"))
    return dict(cost=cost, n_cmp=n_cmp, recall=final_recall,
                mem_integ=recall_integral / n_assist,
                persist=persist, ux_fail=ux_fail, turns=max(1, turn))

# ---------- 主程序 ----------
def main():
    sessions = load_sessions()
    # 校准需要的 tot_in
    for s in sessions:
        con = sqlite3.connect(f"file:{DBS[s['prof']]}?mode=ro", uri=True)
        r = con.execute("SELECT input_tokens+cache_read_tokens FROM sessions WHERE id=?",
                        (s["sid"],)).fetchone()
        s["tot_in"] = r[0] if r and r[0] else 0
        con.close()
    ratio = calibrate(sessions)
    print(f"校准: 字符/token = {ratio:.2f} (由无压缩会话账单反推)")
    print(f"样本: {len(sessions)} 个真实会话(消息数≥8)\n")

    thetas = [None, 0.08, 0.12, 0.15, 0.2, 0.3, 0.5]
    print(f"{'θ':>6}{'总成本$':>10}{'压缩次数':>9}{'终态召回':>9}{'全程记忆':>9}"
          f"{'持续轮数':>9}{'UX失败/会话':>12}{'$/质量轮':>10}")
    base_cost = None
    for th in thetas:
        agg = dict(cost=0, n_cmp=0, rec=[], mem=[], per=[], ux=[], qturn=0, turns=0)
        for s in sessions:
            r = replay(s, ratio, th if th else 99.0)
            agg["cost"] += r["cost"]; agg["n_cmp"] += r["n_cmp"]
            agg["rec"].append(r["recall"]); agg["mem"].append(r["mem_integ"])
            agg["per"].append(r["persist"]); agg["ux"].append(r["ux_fail"])
            agg["turns"] += r["turns"]
            agg["qturn"] += r["turns"] * r["mem_integ"]          # 质量调整轮
        if base_cost is None: base_cost = agg["cost"]
        n = len(sessions)
        tag = "不压缩" if th is None else f"{th:.2f}"
        cpt = agg["cost"] / max(1e-9, agg["qturn"])              # 每质量调整轮成本
        print(f"{tag:>6}{agg['cost']:>10.2f}{agg['n_cmp']:>9.0f}"
              f"{sum(agg['rec'])/n:>9.3f}{sum(agg['mem'])/n:>9.3f}"
              f"{sum(agg['per'])/n:>9.1f}{sum(agg['ux'])/n:>12.2f}"
              f"{cpt*1000:>9.3f}‰  (省{(1-agg['cost']/base_cost)*100:>4.1f}%)")

    print("\nUX 参数敏感性(P_REF=用户每轮回指旧内容概率, θ=0.12):")
    for pr in (0.1, 0.25, 0.4):
        tot = sum(replay(s, ratio, 0.12, pr)["ux_fail"] for s in sessions)
        print(f"  P_REF={pr:.2f}: 全会话库期望遗忘事件 = {tot:.1f} 次")

if __name__ == "__main__":
    main()
