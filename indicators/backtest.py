# ---------------------------------------------------------------------------
# indicators/backtest.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-D3371B07
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""历史胜率背书：信号在历史 K 线上的出现频率与后续表现统计"""
from collector import db
from indicators import ta

def _signal_occurrences(klines, sig_fn, min_idx=30):
    """扫描历史 K 线，返回所有触发点索引（跳过前 min_idx 根预热）"""
    hits = []
    for i in range(min_idx, len(klines) - 5):
        if sig_fn(klines, i):
            hits.append(i)
    return hits

def _forward_stats(klines, idx, fwd=5, win_pct=2.0, loss_pct=2.0):
    """从 idx 起未来 fwd 根：最高涨幅/最大回撤/触达 +/-pct"""
    entry = klines[idx]["c"]
    if entry <= 0: return None
    max_up = 0.0; max_dn = 0.0
    for k in klines[idx+1:idx+1+fwd]:
        up = (k["h"] - entry) / entry * 100
        dn = (entry - k["l"]) / entry * 100
        max_up = max(max_up, up); max_dn = max(max_dn, dn)
    return {"win": max_up >= win_pct, "loss": max_dn >= loss_pct,
            "max_up": max_up, "max_dn": max_dn}

def signal_backtest(symbol, interval, name, sig_fn, fwd=5, win_pct=2.0, loss_pct=2.0, max_hits=400):
    """通用信号回测：返回出现次数 + 胜率统计"""
    raw = db.get_klines(symbol, interval, 3000)
    klines = [{"ts": r["ts"], "o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"], "v": r["vol"]} for r in raw]
    if len(klines) < 100:
        return None
    hits = _signal_occurrences(klines, sig_fn)[-max_hits:]
    if not hits:
        return {"signal": name, "symbol": symbol, "interval": interval, "count": 0}
    stats = [r for r in (_forward_stats(klines, i, fwd, win_pct, loss_pct) for i in hits) if r]
    if not stats:
        return {"signal": name, "symbol": symbol, "interval": interval, "count": len(hits)}
    n = len(stats)
    return {
        "signal": name, "symbol": symbol, "interval": interval,
        "count": len(hits),
        "win_rate": round(sum(1 for s in stats if s["win"]) / n * 100, 1),
        "loss_rate": round(sum(1 for s in stats if s["loss"]) / n * 100, 1),
        "avg_max_up": round(sum(s["max_up"] for s in stats) / n, 2),
        "avg_max_dn": round(sum(s["max_dn"] for s in stats) / n, 2),
        "fwd": fwd, "win_pct": win_pct, "loss_pct": loss_pct,
    }

# ---------- 常用信号模板 ----------
def make_rsi_signal(period=14, threshold=30, below=True):
    def fn(klines, i):
        closes = [k["c"] for k in klines[:i+1]]
        if len(closes) < period + 2: return False
        r = ta.rsi(closes[-period*2:], period)
        if r is None: return False
        return r < threshold if below else r > threshold
    return fn

def make_boll_signal(n=20, below=True):
    def fn(klines, i):
        closes = [k["c"] for k in klines[:i+1]]
        if len(closes) < n + 2: return False
        up, mid, dn = ta.bollinger(closes[-n*3:], n)
        if up is None: return False
        return klines[i]["c"] <= dn if below else klines[i]["c"] >= up
    return fn

def make_vol_signal(mult=2.0, bullish=True):
    def fn(klines, i):
        vols = [k["v"] for k in klines[:i+1]]
        if len(vols) < 25: return False
        avg = sum(vols[-26:-1]) / 20
        if avg <= 0: return False
        vol_ok = vols[-1] > avg * mult
        if not vol_ok: return False
        if bullish: return klines[i]["c"] > klines[i-1]["c"]
        return klines[i]["c"] < klines[i-1]["c"]
    return fn

def make_cross_signal(bullish=True):
    def fn(klines, i):
        closes = [k["c"] for k in klines[:i+1]]
        if len(closes) < 60: return False
        e20a, e50a = ta.ema(closes[:-1], 20), ta.ema(closes[:-1], 50)
        e20b, e50b = ta.ema(closes, 20), ta.ema(closes, 50)
        if None in (e20a, e50a, e20b, e50b): return False
        if bullish: return e20a <= e50a and e20b > e50b
        return e20a >= e50a and e20b < e50b
    return fn

def backtest_all(symbol, interval="4h"):
    """对常用信号批量回测，返回全部结果（供分析注入）"""
    results = []
    tests = [
        ("RSI超卖(<30)", make_rsi_signal(14, 30, True)),
        ("RSI超买(>70)", make_rsi_signal(14, 70, False)),
        ("跌破布林下轨", make_boll_signal(20, True)),
        ("突破布林上轨", make_boll_signal(20, False)),
        ("放量阳线(>2x)", make_vol_signal(2.0, True)),
        ("放量阴线(>2x)", make_vol_signal(2.0, False)),
        ("EMA20金叉50", make_cross_signal(True)),
        ("EMA20死叉50", make_cross_signal(False)),
    ]
    for name, fn in tests:
        try:
            r = signal_backtest(symbol, interval, name, fn)
            if r and r.get("count", 0) > 0:
                results.append(r)
        except Exception:
            pass
    return results
