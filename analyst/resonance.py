# ---------------------------------------------------------------------------
# analyst/resonance.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-887AD362
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""多周期共振引擎：15m/1h/4h/1d 四周期信号加权 → 共振指数 + 背离检测
共振高 = 多周期同向（强信号）；背离 = 周期方向冲突（警告）"""
from collector import db
from indicators import ta

TIMEFRAMES = ["15m", "1h", "4h", "1d"]
# 各周期权重（周期越长权重越高）
TF_WEIGHT = {"15m": 0.15, "1h": 0.25, "4h": 0.35, "1d": 0.25}

def tf_signal(klines, n=120):
    """单周期方向打分：-100 ~ +100（多指标综合）"""
    if len(klines) < 60:
        return None
    closes = [k["c"] for k in klines]
    highs = [k["h"] for k in klines]
    lows = [k["l"] for k in klines]
    last = closes[-1]
    score = 0.0
    # EMA 趋势 ±40
    e20, e50 = ta.ema(closes, 20), ta.ema(closes, 50)
    if e20 and e50:
        if last > e20 > e50: score += 40
        elif last < e20 < e50: score -= 40
        elif last > e50: score += 10
        else: score -= 10
    # RSI ±20
    r = ta.rsi(closes)
    if r is not None:
        if r < 30: score += 20
        elif r > 70: score -= 20
        elif r < 45: score += 8
        elif r > 55: score -= 8
    # MACD ±20
    macd_l, dea, hist = ta.macd(closes)
    if macd_l is not None and hist is not None:
        score += 20 if hist > 0 else -20
    # 布林位置 ±20
    up, mid, dn = ta.bollinger(closes)
    if up and dn:
        pb = (last - dn) / (up - dn) * 100
        if pb < 15: score += 20
        elif pb > 85: score -= 20
        elif pb < 40: score += 6
        elif pb > 60: score -= 6
    return max(-100, min(100, score))

def resonance(symbol):
    """四周期共振计算：共振指数 0-100 + 方向 + 背离信息"""
    tf_scores = {}
    for iv in TIMEFRAMES:
        raw = db.get_klines(symbol, iv, 120)
        if len(raw) < 60:
            continue
        klines = [{"o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"], "v": r["vol"]} for r in raw]
        s = tf_signal(klines)
        if s is not None:
            tf_scores[iv] = round(s, 1)
    if not tf_scores:
        return {"symbol": symbol, "error": "数据不足"}

    # 加权总分
    total_w = sum(TF_WEIGHT[iv] for iv in tf_scores)
    weighted = sum(tf_scores[iv] * TF_WEIGHT[iv] for iv in tf_scores) / total_w
    # 共振指数：方向一致性（同向越多越高）
    signs = [1 if s > 12 else (-1 if s < -12 else 0) for s in tf_scores.values()]
    aligned = sum(1 for sg in signs if sg != 0 and sg == (1 if weighted > 0 else -1))
    active = sum(1 for sg in signs if sg != 0)
    resonance_score = int(50 + weighted * 0.45 + (aligned / max(1, active) - 0.5) * 30) if active else 50
    resonance_score = max(0, min(100, resonance_score))

    # 背离：周期方向冲突
    divergences = []
    majors = {iv: s for iv, s in tf_scores.items() if iv in ("4h", "1d")}
    minors = {iv: s for iv, s in tf_scores.items() if iv in ("15m", "1h")}
    if majors and minors:
        m_dir = 1 if sum(majors.values()) > 0 else -1
        n_dir = 1 if sum(minors.values()) > 0 else -1
        if m_dir != n_dir:
            divergences.append(f"短周期与长周期背离（4h/1d {'多' if m_dir>0 else '空'} vs 15m/1h {'多' if n_dir>0 else '空'}）")

    direction = "bullish" if resonance_score >= 58 else ("bearish" if resonance_score <= 42 else "neutral")
    return {
        "symbol": symbol, "tf_scores": tf_scores,
        "resonance": resonance_score, "direction": direction,
        "divergences": divergences,
    }

def resonance_text(r):
    if not r or "error" in r:
        return ""
    tfs = " | ".join(f"{iv}:{'🟢' if s>12 else ('🔴' if s<-12 else '⚪')}{s:+.0f}" for iv, s in r["tf_scores"].items())
    return f"共振 {r['resonance']}（{r['direction']}）[{tfs}]"
