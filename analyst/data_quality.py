# ---------------------------------------------------------------------------
# analyst/data_quality.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-7ED2C0B1
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""数据质量层：价格跳变/成交量异常/数据漂移检测 → 标记与告警"""
import time, statistics
from collector import db

def detect_anomalies(symbol="BTCUSDT", interval="15m"):
    """检测最近 K 线的异常：价格跳变 z-score / 成交量 z-score / 影线异常"""
    raw = db.get_klines(symbol, interval, 200)
    if len(raw) < 60:
        return {"symbol": symbol, "anomalies": []}
    klines = [{"ts": r["ts"], "o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"], "v": r["vol"]} for r in raw]
    anomalies = []
    n = len(klines)
    last = klines[-1]

    # 1. 收盘变动 z-score
    rets = []
    for i in range(1, n):
        prev = klines[i-1]["c"]
        if prev:
            rets.append((klines[i]["c"] - prev) / prev * 100)
    if len(rets) > 30:
        mean = statistics.mean(rets[:-1])
        std = statistics.stdev(rets[:-1]) or 1e-6
        z = (rets[-1] - mean) / std
        if abs(z) > 4:
            anomalies.append({"type": "price_jump", "z": round(z, 1),
                              "detail": f"收盘变动 {rets[-1]:+.2f}%（{abs(z):.1f}σ 异常）"})

    # 2. 成交量 z-score
    vols = [k["v"] for k in klines]
    if len(vols) > 30:
        vmean = statistics.mean(vols[:-1])
        vstd = statistics.stdev(vols[:-1]) or 1e-6
        vz = (vols[-1] - vmean) / vstd
        if vz > 4:
            anomalies.append({"type": "volume_spike", "z": round(vz, 1),
                              "detail": f"成交量 {vols[-1]/vmean:.1f}× 均值（{vz:.1f}σ）"})

    # 3. 影线异常（插针特征）
    rng = last["h"] - last["l"]
    body = abs(last["c"] - last["o"])
    if rng > 0 and body / rng < 0.15 and rng / (klines[-2]["h"] - klines[-2]["l"] or 1) > 2:
        anomalies.append({"type": "wick_spike", "z": None,
                          "detail": "长影线十字星（疑似插针）"})

    return {"symbol": symbol, "interval": interval, "ts": last["ts"],
            "anomalies": anomalies}

def scan_all_anomalies(symbols=None, interval="15m"):
    """扫描全部品种异常（采集器调用）"""
    from collector.universe import deep_pool
    syms = symbols or deep_pool()[:20]
    found = []
    for sym in syms:
        try:
            r = detect_anomalies(sym, interval)
            for a in r.get("anomalies", []):
                a["symbol"] = sym
                found.append(a)
        except Exception:
            continue
    return found

if __name__ == "__main__":
    import sys; sys.path.insert(0, ".")
    print(detect_anomalies("BTCUSDT", "15m"))
