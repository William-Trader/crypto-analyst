# ---------------------------------------------------------------------------
# collector/binance_client.py - crypto-analyst key data logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-2BFF3DAD
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""Binance 公开 API 客户端（免费端点，断点续拉）"""
import json, time, urllib.request, ssl
from config import BASE_URL

ctx = ssl._create_unverified_context()

def _get(path, params=None, retries=4):
    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    last_err = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=20, context=ctx) as r:
                return json.loads(r.read())
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"GET {path} failed: {last_err}")

def fetch_klines(symbol, interval, start_ms=None, limit=1000):
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    if start_ms: params["startTime"] = start_ms
    return _get("/api/v3/klines", params)

def fetch_ticker24h(symbol):
    return _get("/api/v3/ticker/24hr", {"symbol": symbol})

def fetch_open_interest(symbol):
    return _get("/api/v3/openInterest", {"symbol": symbol})

def fetch_funding(symbol, limit=10):
    return _get("/api/v3/fundingRate", {"symbol": symbol, "limit": limit})

def incremental_klines(symbol, interval, last_ts_ms, retry_holes=True):
    """从 last_ts_ms 增量拉 K 线，返回标准化行（含主动买量）；last_ts_ms=0 拉全量"""
    rows, cursor = [], last_ts_ms
    while True:
        data = fetch_klines(symbol, interval, start_ms=cursor)
        if not data: break
        for k in data:
            rows.append((symbol, interval, k[0], float(k[1]), float(k[2]),
                         float(k[3]), float(k[4]), float(k[5]), float(k[7]), int(k[8]),
                         float(k[9]) if len(k) > 9 else 0.0))  # k[9]=takerBuyBaseVolume
        if len(data) < 1000: break
        cursor = data[-1][0] + 1
        time.sleep(0.15)
    return rows
