# ---------------------------------------------------------------------------
# analyst/risk.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-8DF187BD
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""风险计价器：ATR 驱动的止损/目标/盈亏比/仓位建议"""
from indicators import ta

def build_plan(symbol, klines, direction, confidence, account_risk_pct=1.0):
    """生成完整作战计划：入场/止损/双目标/RR/仓位建议"""
    if len(klines) < 20:
        return None
    closes = [k["c"] for k in klines]
    highs = [k["h"] for k in klines]
    lows = [k["l"] for k in klines]
    last = closes[-1]
    atr = ta.atr(highs, lows, closes, 14)
    if not atr or atr <= 0:
        atr = last * 0.02

    if direction == "bullish":
        entry = last
        stop = last - atr * 1.5
        t1 = last + atr * 2.0
        t2 = last + atr * 3.5
    elif direction == "bearish":
        entry = last
        stop = last + atr * 1.5
        t1 = last - atr * 2.0
        t2 = last - atr * 3.5
    else:
        return None

    risk = abs(entry - stop)
    rr1 = abs(t1 - entry) / risk if risk > 0 else 0
    rr2 = abs(t2 - entry) / risk if risk > 0 else 0

    # 仓位建议：风险预算 / 单笔风险（%）
    pos_pct = round(account_risk_pct * 100 / (risk / entry * 100), 1) if risk > 0 else 0
    pos_pct = max(1.0, min(30.0, pos_pct))  # 1%~30% 封顶

    # 置信度修正：低于 50% 建议减半仓
    if confidence < 50:
        pos_pct = round(pos_pct * 0.5, 1)

    return {
        "symbol": symbol, "direction": direction, "confidence": confidence,
        "entry": round(entry, 4), "stop": round(stop, 4),
        "target1": round(t1, 4), "target2": round(t2, 4),
        "rr1": round(rr1, 2), "rr2": round(rr2, 2),
        "atr_pct": round(atr / entry * 100, 2),
        "risk_pct": round(risk / entry * 100, 2),
        "position_pct": pos_pct,
        "notes": "置信度<50%已自动减半仓" if confidence < 50 else "",
    }

def plan_to_text(p):
    if not p: return ""
    d = "做多" if p["direction"] == "bullish" else "做空"
    return (f"【作战计划】{p['symbol']} {d} 置信{p['confidence']}%\n"
            f"入场: {p['entry']} | 止损: {p['stop']}（风险 {p['risk_pct']}%）\n"
            f"目标1: {p['target1']} (RR {p['rr1']}) | 目标2: {p['target2']} (RR {p['rr2']})\n"
            f"建议仓位: ≤{p['position_pct']}% 资金（ATR波动 {p['atr_pct']}%）"
            + (f"\n{p['notes']}" if p.get("notes") else ""))
