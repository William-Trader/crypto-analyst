# ---------------------------------------------------------------------------
# analyst/calc.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-8ABD0533
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""计算过程引擎：每个指标输出 公式→代入→结果，供前端点击查看计算过程"""
from indicators import ta

def _fmt(v, nd=4):
    if v is None: return "—"
    return f"{v:.{nd}f}"

def rsi_calc(closes, period=14):
    if len(closes) < period + 1:
        return {"name": "RSI", "error": "数据不足"}
    wins, losses = [], []
    for i in range(-period, 0):
        d = closes[i] - closes[i-1]
        wins.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(wins) / period; al = sum(losses) / period
    rs = ag / al if al > 0 else float('inf')
    rsi = 100 - 100 / (1 + rs) if al > 0 else 100.0
    return {
        "name": "RSI(14)", "formula": "RSI = 100 − 100/(1+RS), RS = 平均涨幅/平均跌幅",
        "steps": [
            f"取最近 {period} 根收盘价变化：{_fmt(closes[-period-1])} → {_fmt(closes[-1])}",
            f"平均涨幅 = {_fmt(ag, 3)}，平均跌幅 = {_fmt(al, 3)}",
            f"RS = {_fmt(ag, 3)} / {_fmt(al, 3)} = {_fmt(rs, 3)}",
            f"RSI = 100 − 100/(1+{_fmt(rs, 3)}) = {_fmt(rsi, 1)}",
        ],
        "result": _fmt(rsi, 1),
        "interpret": "超卖(<30)偏多 / 超买(>70)偏空",
    }

def boll_calc(closes, n=20, k=2.0):
    if len(closes) < n:
        return {"name": "BOLL", "error": "数据不足"}
    mid = sum(closes[-n:]) / n
    var = sum((c - mid) ** 2 for c in closes[-n:]) / n
    sd = var ** 0.5
    return {
        "name": f"BOLL({n},{k})", "formula": "中轨=MA20, 上/下轨=MA±k×σ",
        "steps": [
            f"MA{n} = {_fmt(mid)}（最近{n}根收盘均值）",
            f"方差 σ² = {_fmt(var, 3)} → σ = {_fmt(sd, 3)}",
            f"上轨 = {_fmt(mid)} + {k}×{_fmt(sd)} = {_fmt(mid + k*sd)}",
            f"下轨 = {_fmt(mid)} − {k}×{_fmt(sd)} = {_fmt(mid - k*sd)}",
            f"最新收盘 {_fmt(closes[-1])} 位于{'上轨外' if closes[-1] > mid+k*sd else ('下轨外' if closes[-1] < mid-k*sd else '轨道内')}",
        ],
        "result": f"上{_fmt(mid+k*sd)} 中{_fmt(mid)} 下{_fmt(mid-k*sd)}",
        "interpret": "触下轨偏多 / 触上轨偏空 / 收口=变盘前兆",
    }

def macd_calc(closes, fast=12, slow=26, sig=9):
    if len(closes) < slow + sig:
        return {"name": "MACD", "error": "数据不足"}
    def ema_series(vals, n):
        k = 2/(n+1); out = [sum(vals[:n])/n]
        for v in vals[n:]: out.append(v*k + out[-1]*(1-k))
        return out
    ef = ema_series(closes, fast); es = ema_series(closes, slow)
    diff = [a-b for a, b in zip(ef, es)]
    dea = ema_series(diff, sig)
    hist = diff[-1] - dea[-1]
    return {
        "name": f"MACD({fast},{slow},{sig})", "formula": "DIF=EMA12−EMA26, DEA=EMA(DIF,9), 柱=DIF−DEA",
        "steps": [
            f"EMA{fast} = {_fmt(ef[-1])}，EMA{slow} = {_fmt(es[-1])}",
            f"DIF = {_fmt(ef[-1])} − {_fmt(es[-1])} = {_fmt(diff[-1])}",
            f"DEA = {_fmt(dea[-1])}",
            f"柱 = {_fmt(diff[-1])} − {_fmt(dea[-1])} = {_fmt(hist)}（{'红柱' if hist>0 else '绿柱'}）",
        ],
        "result": f"DIF {_fmt(diff[-1])} / DEA {_fmt(dea[-1])} / 柱 {_fmt(hist)}",
        "interpret": "金叉红柱偏多 / 死叉绿柱偏空",
    }

def atr_calc(highs, lows, closes, n=14):
    if len(highs) < n + 1:
        return {"name": "ATR", "error": "数据不足"}
    trs = []
    for i in range(-n, 0):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    atr = sum(trs)/n
    return {
        "name": f"ATR({n})", "formula": "TR=max(H−L,|H−C前|,|L−C前|), ATR=均值(TR)",
        "steps": [
            f"最近3根TR: {_fmt(trs[-3])}, {_fmt(trs[-2])}, {_fmt(trs[-1])}",
            f"ATR = {_fmt(atr)}（≈价格 {_fmt(atr/closes[-1]*100, 2)}%）",
        ],
        "result": _fmt(atr),
        "interpret": "波动率指标：止损常用 1.5×ATR",
    }

def ema_calc(closes, n=20):
    if len(closes) < n:
        return {"name": "EMA", "error": "数据不足"}
    k = 2/(n+1)
    e = sum(closes[:n])/n
    for v in closes[n:]:
        e = v*k + e*(1-k)
    return {
        "name": f"EMA({n})", "formula": "EMA = 收盘×k + 前EMA×(1−k), k=2/(n+1)",
        "steps": [
            f"k = 2/{n+1} = {_fmt(k, 4)}",
            f"EMA{'{'+str(n)+'}'} = {_fmt(e)}（最新收盘 {_fmt(closes[-1])} {'站上' if closes[-1] > e else '跌破'}）",
        ],
        "result": _fmt(e),
        "interpret": "趋势线：站上偏多 / 跌破偏空",
    }

def all_calcs(klines, indicators=("rsi", "boll", "macd", "atr", "ema")):
    closes = [k["c"] for k in klines]
    highs = [k["h"] for k in klines]
    lows = [k["l"] for k in klines]
    fns = {
        "rsi": lambda: rsi_calc(closes),
        "boll": lambda: boll_calc(closes),
        "macd": lambda: macd_calc(closes),
        "atr": lambda: atr_calc(highs, lows, closes),
        "ema": lambda: ema_calc(closes),
    }
    out = {}
    for name in indicators:
        try:
            out[name] = fns[name]()
        except Exception as e:
            out[name] = {"name": name, "error": str(e)}
    return out
