# ---------------------------------------------------------------------------
# analyst/opportunity.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-1246FFE1
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""智能机会榜：评级 + 共振 + 信号 + AI 观点 → 今日机会（Top N）"""
import time
from collector import db
from collector.universe import deep_pool
from analyst.composite import rate_symbol
from analyst.resonance import resonance

# AI 观点缓存（1 小时）
_opinion_cache = {"ts": 0, "data": {}}
OPINION_TTL = 3600

def _llm_opinion(symbol, r, rating):
    """比格一句话点评（缓存 1h）"""
    global _opinion_cache
    now = time.time()
    if now - _opinion_cache["ts"] > OPINION_TTL:
        _opinion_cache["ts"] = now
        _opinion_cache["data"] = {}
    if symbol in _opinion_cache["data"]:
        return _opinion_cache["data"][symbol]
    try:
        from analyst.llm import llm_chat
        res = resonance_text(r) if r and "error" not in r else ""
        grade = rating.get("grade", "") if rating else ""
        opinion = llm_chat(
            f"用 40 字以内一句话点评 {symbol.replace('USDT','')}：\n"
            f"评级: {grade}（{rating.get('score', 0)}分）\n共振: {res}\n"
            f"要求：有明确态度（值得关注/回避/观望+一句理由），像分析师口吻。",
            temperature=0.5)
        opinion = opinion.strip()[:120]
        _opinion_cache["data"][symbol] = opinion
        return opinion
    except Exception:
        return ""

def resonance_text(r):
    if not r or "error" in r:
        return ""
    return f"{r['resonance']}分 {r['direction']}"

def opportunity_board(limit=12):
    """机会榜：深研池评分 = 评级分 × 0.5 + 共振分 × 0.3 + 信号加分"""
    pool = deep_pool()[:40]
    items = []
    for sym in pool:
        try:
            rating = rate_symbol(sym)
            if not rating:
                continue
            res = resonance(sym)
            if "error" in res:
                continue
            # 综合机会分（0-100）
            opp = rating["score"] * 0.55 + res["resonance"] * 0.35
            if res["direction"] != "neutral":
                opp += 8  # 共振方向明确加分
            if res.get("divergences"):
                opp -= 8  # 背离减分
            opp = round(max(0, min(100, opp)), 1)
            items.append({
                "symbol": sym, "score": opp,
                "rating": rating["score"], "grade": rating["grade"],
                "resonance": res["resonance"], "direction": res["direction"],
                "tf": res["tf_scores"], "divergences": res.get("divergences", []),
            })
        except Exception:
            continue
    items.sort(key=lambda x: -x["score"])
    items = items[:limit]
    # 批量生成 AI 观点（Top 6，避免过多 LLM 调用）
    for it in items[:6]:
        it["opinion"] = _llm_opinion(it["symbol"], it, it)
    return items

if __name__ == "__main__":
    import sys, os; sys.path.insert(0, ".")
    zshrc = open(os.path.expanduser("~/.zshrc")).read()
    for line in zshrc.splitlines():
        if "DEEPSEEK_API_KEY" in line and "=" in line:
            os.environ["DEEPSEEK_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
    board = opportunity_board(6)
    for b in board:
        print(f"{b['symbol']:10s} 机会{b['score']:5.1f} 评级{b['rating']:.0f}({b['grade']}) 共振{b['resonance']} {b['direction']} | {b.get('opinion','')[:60]}")
