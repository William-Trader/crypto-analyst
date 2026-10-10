# ---------------------------------------------------------------------------
# indicators/signals.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-E9332092
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""信号综合引擎：多指标打分 → 多空倾向 + 置信度"""
from indicators import ta

def analyze_symbol(klines):
    """klines: [{ts,o,h,l,c,v,...}] → 信号报告 dict"""
    if len(klines) < 60: return {"error": "数据不足"}
    closes = [k["c"] for k in klines]
    highs = [k["h"] for k in klines]
    lows = [k["l"] for k in klines]
    vols = [k["v"] for k in klines]
    last = klines[-1]
    signals = []  # (name, direction, weight, note)

    # --- 趋势 ---
    ema20, ema50 = ta.ema(closes, 20), ta.ema(closes, 50)
    if ema20 and ema50:
        if last["c"] > ema20 > ema50: signals.append(("EMA排列", "bullish", 2, "多头排列"))
        elif last["c"] < ema20 < ema50: signals.append(("EMA排列", "bearish", 2, "空头排列"))
        else: signals.append(("EMA排列", "neutral", 0.5, "均线纠缠"))
    adx = ta.adx(highs, lows, closes)
    if adx:
        trend = "强趋势" if adx > 25 else "弱趋势/震荡"
        signals.append(("ADX", None, 0, f"{trend} ({adx:.0f})"))

    # --- 震荡指标 ---
    r = ta.rsi(closes)
    if r:
        if r < 30: signals.append(("RSI", "bullish", 1.5, f"超卖 {r:.0f}"))
        elif r > 70: signals.append(("RSI", "bearish", 1.5, f"超买 {r:.0f}"))
        else: signals.append(("RSI", "neutral", 0.5, f"{r:.0f}"))
    k, d = ta.kdj(highs, lows, closes)
    if k is not None:
        if k < 20 and k > d: signals.append(("KDJ", "bullish", 1, f"低位金叉 K{k:.0f}"))
        elif k > 80 and k < d: signals.append(("KDJ", "bearish", 1, f"高位死叉 K{k:.0f}"))
    macd_line, dea, hist = ta.macd(closes)
    if macd_line is not None:
        if macd_line > dea and hist > 0: signals.append(("MACD", "bullish", 1.5, "金叉红柱"))
        elif macd_line < dea and hist < 0: signals.append(("MACD", "bearish", 1.5, "死叉绿柱"))

    # --- 布林带 ---
    up, mid, dn = ta.bollinger(closes)
    if up:
        if last["c"] <= dn: signals.append(("布林", "bullish", 1, "触及下轨"))
        elif last["c"] >= up: signals.append(("布林", "bearish", 1, "触及上轨"))
        elif abs(last["c"] - mid) / (up - dn) < 0.2: signals.append(("布林", "neutral", 0.5, "中轨附近"))

    # --- 量价 ---
    vr = ta.volume_ratio(vols)
    if vr and vr > 1.5:
        d = "bullish" if last["c"] > klines[-2]["c"] else "bearish"
        signals.append(("量能", d, 1.5, f"放量{vr:.1f}倍"))

    # --- 综合 ---
    bull = sum(w for _, d, w, _ in signals if d == "bullish")
    bear = sum(w for _, d, w, _ in signals if d == "bearish")
    total = bull + bear
    if total == 0: return {"signals": signals, "direction": "neutral", "score": 0, "confidence": 0}
    score = (bull - bear) / total
    direction = "bullish" if score > 0.15 else ("bearish" if score < -0.15 else "neutral")
    confidence = min(95, abs(bull - bear) * 12 + 40)

    return {
        "last": {"ts": last["ts"], "close": last["c"], "high": last["h"], "low": last["l"]},
        "signals": signals, "direction": direction, "score": round(score, 2),
        "confidence": int(confidence), "bull": bull, "bear": bear,
    }
