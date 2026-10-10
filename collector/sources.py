# ---------------------------------------------------------------------------
# collector/sources.py - crypto-analyst key data logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-EEBE2DAB
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""多数据源层：Binance(主) + Gate.io(备) + KuCoin(尝鲜)
统一接口：get_all_tickers() -> {symbol: {price, vol24h, quote_vol, chg24h, source}}
"""
import json, time, urllib.request, ssl
ctx = ssl._create_unverified_context()

def _get(url, timeout=15, retries=3):
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout, context=ctx) as r:
                return json.loads(r.read())
        except Exception as e:
            last = e
            time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"GET {url[:60]} failed: {last}")

# ---------- Binance（主源，现货公开 API） ----------
def binance_tickers():
    """全部交易对价格（小响应，weight=2）"""
    try:
        data = _get("https://data-api.binance.vision/api/v3/ticker/price")
    except Exception:
        return {}
    return {d["symbol"]: {"price": float(d["price"])} for d in data if d.get("symbol", "").endswith("USDT")}

def binance_24h(symbols):
    """Top 品种 24h 详情（带成交量排序）"""
    out = {}
    try:
        data = _get("https://data-api.binance.vision/api/v3/ticker/24hr")
    except Exception:
        return out
    for d in data:
        s = d.get("symbol", "")
        if not s.endswith("USDT"): continue
        out[s] = {
            "price": float(d["lastPrice"]), "chg24h": float(d["priceChangePercent"]),
            "vol24h": float(d["volume"]), "quote_vol": float(d["quoteVolume"]),
            "high24h": float(d["highPrice"]), "low24h": float(d["lowPrice"]),
            "source": "BINANCE",
        }
    return out

def binance_universe():
    """品种列表（ticker/price 全量，过滤 USDT）"""
    ts = binance_tickers()
    return sorted(ts.keys())

# ---------- Gate.io（备源） ----------
def gate_tickers():
    """Gate 现货全部 tickers（支持批量）"""
    out = {}
    try:
        data = _get("https://api.gateio.ws/api/v4/spot/tickers")
    except Exception:
        return out
    for d in data:
        pair = d.get("currency_pair", "")
        if not pair.endswith("_USDT"): continue
        sym = pair.replace("_USDT", "USDT")
        try:
            out[sym] = {
                "price": float(d.get("last", 0) or 0),
                "chg24h": float(d.get("change_percentage", 0) or 0),
                "quote_vol": float(d.get("quote_volume", 0) or 0),
                "vol24h": float(d.get("base_volume", 0) or 0),
                "high24h": float(d.get("high_24h", 0) or 0),
                "low24h": float(d.get("low_24h", 0) or 0),
                "source": "GATE",
            }
        except Exception:
            continue
    return out

# ---------- KuCoin（尝试源） ----------
def kucoin_tickers():
    out = {}
    try:
        data = _get("https://api.kucoin.com/api/v1/market/allTickers")
    except Exception:
        return out
    for d in data.get("data", {}).get("ticker", []):
        sym = d.get("symbol", "")
        if not sym.endswith("-USDT"): continue
        s = sym.replace("-USDT", "USDT")
        try:
            out[s] = {
                "price": float(d.get("last", 0) or 0),
                "chg24h": float(d.get("changeRate", 0) or 0) * 100,
                "quote_vol": float(d.get("volValue", 0) or 0),
                "vol24h": float(d.get("vol", 0) or 0),
                "source": "KUCOIN",
            }
        except Exception:
            continue
    return out

# ---------- 统一入口 ----------
def get_all_tickers():
    """多源合并：Binance 优先，Gate 补充缺失，KuCoin 补充"""
    merged = {}
    try:
        merged.update(binance_24h(None))
    except Exception:
        pass
    gate = gate_tickers()
    for s, t in gate.items():
        if s not in merged:
            merged[s] = t
        elif merged[s].get("source") == "BINANCE":
            merged[s]["gate_quote_vol"] = t.get("quote_vol", 0)
    ku = kucoin_tickers()
    for s, t in ku.items():
        if s not in merged:
            merged[s] = t
    return merged

def source_status():
    """数据源健康状态"""
    status = {}
    for name, fn in [("BINANCE", binance_tickers), ("GATE", gate_tickers), ("KUCOIN", kucoin_tickers)]:
        try:
            t0 = time.time()
            d = fn()
            status[name] = {"ok": True, "pairs": len(d), "ms": int((time.time() - t0) * 1000)}
        except Exception as e:
            status[name] = {"ok": False, "pairs": 0, "error": str(e)[:80]}
    return status
