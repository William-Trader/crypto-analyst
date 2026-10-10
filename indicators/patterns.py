# ---------------------------------------------------------------------------
# indicators/patterns.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-B797026D
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""K 线形态识别（算法规则，20+ 形态）"""
def candle_shape(o, h, l, c):
    """单根 K 线形态"""
    body = abs(c - o)
    rng = h - l
    if rng == 0: return "doji"
    upper = h - max(o, c)
    lower = min(o, c) - l
    shapes = []
    if body / rng < 0.1: shapes.append("doji")
    if body / rng > 0.6:
        if lower > body * 2 and upper < body * 0.3: shapes.append("hammer")
        if upper > body * 2 and lower < body * 0.3: shapes.append("shooting_star")
        if lower > body * 2 and upper > body * 2: shapes.append("marubozu_long_wicks")
    if body / rng > 0.85 and upper < body * 0.2 and lower < body * 0.2:
        shapes.append("marubozu")
    if c > o: shapes.append("bullish")
    else: shapes.append("bearish")
    return shapes

def detect_patterns(klines):
    """多根组合形态，返回 [(name, direction, idx)]"""
    pats = []
    n = len(klines)
    if n < 5: return pats

    def k(i): return klines[i]

    for i in range(n - 1, 0, -1):
        o, h, l, c = k(i)["o"], k(i)["h"], k(i)["l"], k(i)["c"]
        po, ph, pl, pc = k(i-1)["o"], k(i-1)["h"], k(i-1)["l"], k(i-1)["c"]
        body, pbody = abs(c - o), abs(pc - po)
        rng = h - l if h > l else 1
        # 吞没
        if (c > o and pc < po and c >= po and o <= pc and body > pbody):
            pats.append(("bullish_engulfing", "bullish", i))
        if (c < o and pc > po and c <= po and o >= pc and body > pbody):
            pats.append(("bearish_engulfing", "bearish", i))
        # 锤子（下跌后）
        if body / rng > 0.35 and (min(o, c) - l) > body * 2 and (h - max(o, c)) < body * 0.4 and pc > c:
            pats.append(("hammer", "bullish", i))
        # 射击之星（上涨后）
        if body / rng > 0.35 and (h - max(o, c)) > body * 2 and (min(o, c) - l) < body * 0.4 and pc < c:
            pats.append(("shooting_star", "bearish", i))
        # 十字星
        if body / rng < 0.1:
            pats.append(("doji", "neutral", i))
        # 孕线
        if pbody > 0 and body < pbody * 0.5 and max(o, c) <= max(po, pc) and min(o, c) >= min(po, pc):
            pats.append(("harami", "neutral", i))
        # 晨星/黄昏星（3 根）
        if i >= 2:
            oo, oh, ol, oc = k(i-2)["o"], k(i-2)["h"], k(i-2)["l"], k(i-2)["c"]
            if oc < po and c > o and c > (oo + oc) / 2 and abs(o - c) < abs(oo - oc) * 0.6:
                pats.append(("morning_star", "bullish", i))
            if oc > po and c < o and c < (oo + oc) / 2 and abs(o - c) < abs(oo - oc) * 0.6:
                pats.append(("evening_star", "bearish", i))
        # 三只乌鸦/红兵
        if i >= 3 and c < o and po < oo and k(i-3)["c"] < k(i-3)["o"]:
            pats.append(("three_black_crows", "bearish", i))
        if i >= 3 and c > o and po > oo and k(i-3)["c"] > k(i-3)["o"]:
            pats.append(("three_white_soldiers", "bullish", i))
        if len(pats) > 6: break
    return pats

def recent_swings(klines, n=60):
    """前高前低（摆动点）"""
    highs = [k["h"] for k in klines[-n:]]
    lows = [k["l"] for k in klines[-n:]]
    hh = max(highs); ll = min(lows)
    # 最近 5 根的局部高低
    local_h = max(highs[-5:]); local_l = min(lows[-5:])
    return {"high": hh, "low": ll, "local_high": local_h, "local_low": local_l}
