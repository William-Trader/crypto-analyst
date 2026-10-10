# ---------------------------------------------------------------------------
# analyst/council_quick.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-1983DA5B
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""轻量快速分析（供建筑缩略面板/合议厅/作战室秒开，无 LLM）"""
from collector import db
from indicators import signals as se, ta
from analyst import state_machine, schools, risk

def _klines(symbol, interval="4h", n=150):
    raw = db.get_klines(symbol, interval, n)
    if len(raw) < 80:
        return None
    return [{"ts": r["ts"], "o": r["open"], "h": r["high"], "l": r["low"],
             "c": r["close"], "v": r["vol"]} for r in raw]

def quick_council(symbol="BTCUSDT"):
    k4h = _klines(symbol)
    if not k4h:
        return {"error": "数据不足"}
    sig = se.analyze_symbol(k4h)
    closes = [k["c"] for k in k4h]
    highs = [k["h"] for k in k4h]
    lows = [k["l"] for k in k4h]
    state, reason, _ = state_machine.classify(k4h, ta.rsi(closes), ta.adx(highs, lows, closes),
                                              ta.atr(highs, lows, closes))
    verdicts, direction, score, agreement = schools.convene(sig, k4h, state)
    return {"symbol": symbol, "market_state": state, "state_reason": reason,
            "direction": direction, "agreement": agreement,
            "schools": [v.to_dict() for v in verdicts]}

def quick_plan(symbol="BTCUSDT"):
    k4h = _klines(symbol)
    if not k4h:
        return {"error": "数据不足"}
    sig = se.analyze_symbol(k4h)
    plan = risk.build_plan(symbol, k4h, sig.get("direction", "neutral"), sig.get("confidence", 50))
    return {"symbol": symbol, "direction": sig.get("direction"),
            "confidence": sig.get("confidence"),
            "signal_count": len(sig.get("signals", [])), "plan": plan}
