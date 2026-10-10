# ---------------------------------------------------------------------------
# analyst/state_machine.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-E4BFDFD8
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""市场状态机：先诊断市场状态，再选择分析模板"""
from indicators import ta

def classify(klines, rsi_val, adx_val, atr_pct, fgi=None):
    """
    输入：K线、RSI、ADX、ATR%（波动率百分位）、恐惧贪婪指数
    输出：(state, reason, params)
    states: trend_up / trend_down / range / accumulation / distribution / panic / greed
    """
    if len(klines) < 80: return "unknown", "数据不足", {}
    closes = [k["c"] for k in klines]
    last = closes[-1]
    ema50 = ta.ema(closes, 50)
    ema200 = ta.ema(closes, 200) if len(closes) > 200 else None
    n = len(klines)

    # 趋势强度
    strong_trend = adx_val is not None and adx_val > 25
    above50 = ema50 is not None and last > ema50
    below50 = ema50 is not None and last < ema50

    # 波动率百分位（ATR 相对 60 日）
    atrs = []
    for i in range(max(1, n - 60), n):
        h, l, c, pc = klines[i]["h"], klines[i]["l"], klines[i]["c"], klines[i-1]["c"]
        atrs.append(max(h - l, abs(h - pc), abs(l - pc)))
    vol_pct = None
    if len(atrs) > 20:
        cur = atrs[-1]; hist = sorted(atrs)
        vol_pct = hist.index(cur) / len(hist)

    # 恐慌/贪婪
    if fgi is not None:
        if fgi <= 15 and vol_pct and vol_pct > 0.7:
            return "panic", f"FGI={fgi} 极度恐慌+高波动", {"template": "panic"}
        if fgi >= 85 and vol_pct and vol_pct > 0.7:
            return "greed", f"FGI={fgi} 极度贪婪+高波动", {"template": "greed"}

    # 趋势
    if strong_trend and above50:
        return "trend_up", f"ADX={adx_val:.0f} 强趋势+站上50日线", {"template": "trend"}
    if strong_trend and below50:
        return "trend_down", f"ADX={adx_val:.0f} 强趋势+跌破50日线", {"template": "trend"}

    # 震荡区间
    if not strong_trend:
        # 近 60 根高低点距离 < 20% 视为区间
        hi = max(k["h"] for k in klines[-60:])
        lo = min(k["l"] for k in klines[-60:])
        if lo > 0 and (hi - lo) / lo < 0.20:
            return "range", f"区间震荡({(hi-lo)/lo*100:.1f}%幅度)", {"template": "range", "range_hi": hi, "range_lo": lo}

    # 吸筹/派发（威科夫简化：量价+位置）
    # 低波动 + 缩量 + 价格在区间低位 → 吸筹候选
    vol_ratio = ta.volume_ratio([k["v"] for k in klines])
    if vol_pct and vol_pct < 0.4 and vol_ratio and vol_ratio < 0.9:
        hi = max(k["h"] for k in klines[-60:])
        lo = min(k["l"] for k in klines[-60:])
        pos = (last - lo) / (hi - lo) if hi > lo else 0.5
        if pos < 0.35:
            return "accumulation", "低位缩量整理（吸筹候选）", {"template": "accumulation"}
        if pos > 0.65:
            return "distribution", "高位缩量滞涨（派发候选）", {"template": "distribution"}

    if above50: return "trend_up", "站上50日线（弱多头）", {"template": "trend"}
    if below50: return "trend_down", "跌破50日线（弱空头）", {"template": "trend"}
    return "range", "方向不明", {"template": "range"}
