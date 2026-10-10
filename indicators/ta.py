# ---------------------------------------------------------------------------
# indicators/ta.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-CAF0A790
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""指标引擎：技术指标 + K线形态 + 关键位（纯 pandas/numpy，无 ta-lib）"""
import math

def sma(vals, n):
    if len(vals) < n: return None
    return sum(vals[-n:]) / n

def ema(vals, n):
    if len(vals) < n: return None
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    for v in vals[n:]:
        e = v * k + e * (1 - k)
    return e

def rsi(closes, n=14):
    if len(closes) < n + 1: return None
    gains = losses = 0
    for i in range(-n, 0):
        d = closes[i] - closes[i-1]
        gains += max(d, 0); losses += max(-d, 0)
    if losses == 0: return 100.0
    rs = (gains / n) / (losses / n)
    return 100 - 100 / (1 + rs)

def macd(closes, fast=12, slow=26, sig=9):
    if len(closes) < slow + sig: return None, None, None
    # 简化 EMA 序列
    def ema_series(vals, n):
        k = 2 / (n + 1)
        out = [sum(vals[:n]) / n]
        for v in vals[n:]:
            out.append(v * k + out[-1] * (1 - k))
        return out
    ef = ema_series(closes, fast)
    es = ema_series(closes, slow)
    diff = [a - b for a, b in zip(ef, es)]
    dea = ema_series(diff, sig)
    hist = diff[-1] - dea[-1]
    return diff[-1], dea[-1], hist

def bollinger(closes, n=20, k=2.0):
    if len(closes) < n: return None, None, None
    mid = sma(closes, n)
    var = sum((c - mid) ** 2 for c in closes[-n:]) / n
    sd = math.sqrt(var)
    return mid + k * sd, mid, mid - k * sd

def atr(highs, lows, closes, n=14):
    if len(highs) < n + 1: return None
    trs = []
    for i in range(-n, 0):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        trs.append(tr)
    return sum(trs) / n

def adx(highs, lows, closes, n=14):
    if len(highs) < 2 * n + 1: return None
    plus_dm = minus_dm = 0
    tr_sum = 0
    for i in range(-2*n, -1):
        up = highs[i] - highs[i-1]; dn = lows[i-1] - lows[i]
        p = up if (up > dn and up > 0) else 0
        m = dn if (dn > up and dn > 0) else 0
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_sum += tr
        if i < -n:  # 只累加后 n 根
            plus_dm += p; minus_dm += m
    if tr_sum == 0: return None
    pdi = 100 * plus_dm / tr_sum
    mdi = 100 * minus_dm / tr_sum
    if pdi + mdi == 0: return None
    return abs(pdi - mdi) / (pdi + mdi) * 100

def kdj(highs, lows, closes, n=9):
    if len(closes) < n + 3: return None, None
    k = d = 50.0
    for i in range(len(closes) - n - 2, len(closes)):
        hh = max(highs[i:i + n]); ll = min(lows[i:i + n])
        rsv = (closes[i] - ll) / (hh - ll) * 100 if hh > ll else 50
        k = 2/3 * k + 1/3 * rsv
        d = 2/3 * d + 1/3 * k
    j = 3 * k - 2 * d
    return k, d

def obv(closes, vols):
    o = 0
    for i in range(1, len(closes)):
        o += vols[i] if closes[i] > closes[i-1] else (-vols[i] if closes[i] < closes[i-1] else 0)
    return o

def volume_ratio(vols, n=20):
    """量比：最新量 / 前 n 根均量"""
    if len(vols) < n + 1: return None
    avg = sum(vols[-n-1:-1]) / n
    return vols[-1] / avg if avg > 0 else None

def pivot_points(high, low, close):
    p = (high + low + close) / 3
    return {
        "r1": 2 * p - low, "s1": 2 * p - high,
        "r2": p + (high - low), "s2": p - (high - low),
    }

def fib_levels(high, low):
    diff = high - low
    return {f"fib_{k}": low + diff * k for k in (0.236, 0.382, 0.5, 0.618, 0.786)}

def vpvr(closes, vols, bins=40):
    """成交量分布（筹码密集区）"""
    lo, hi = min(closes), max(closes)
    if hi == lo: return {}
    step = (hi - lo) / bins
    vols_by_bin = [0.0] * bins
    for c, v in zip(closes, vols):
        b = min(int((c - lo) / step), bins - 1)
        vols_by_bin[b] += v
    peak = max(vols_by_bin) if vols_by_bin else 0
    dense = [(lo + i * step, lo + (i + 1) * step) for i, v in enumerate(vols_by_bin) if peak and v >= peak * 0.6]
    return {"dense_zones": dense, "poc": lo + step * vols_by_bin.index(peak) if peak else None}
