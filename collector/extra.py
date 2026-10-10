# ---------------------------------------------------------------------------
# collector/extra.py - crypto-analyst key data logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-759E55C1
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""扩展数据源：FGI 恐惧贪婪指数 + Gate 合约资金费率（免费，W1 级数据维度）"""
import json, time, urllib.request, ssl
from collector import db

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

def fetch_fgi():
    """FGI 恐惧贪婪指数（alternative.me 免费）"""
    try:
        d = _get("https://api.alternative.me/fng/?limit=2")
        rows = d.get("data", [])
        if not rows:
            return None
        cur = rows[0]
        return {"value": int(cur["value"]), "label": cur.get("value_classification", ""),
                "ts": int(time.time() * 1000),
                "prev": int(rows[1]["value"]) if len(rows) > 1 else None}
    except Exception:
        return None

def save_fgi(fgi):
    if not fgi:
        return
    dbh = db.get_db()
    try:
        dbh.execute("CREATE TABLE IF NOT EXISTS fgi_snap (ts INTEGER PRIMARY KEY, value INTEGER, label TEXT)")
        dbh.execute("INSERT OR REPLACE INTO fgi_snap (ts, value, label) VALUES (?,?,?)",
                    (fgi["ts"], fgi["value"], fgi["label"]))
        dbh.commit()
    finally:
        dbh.close()

def fetch_gate_funding(symbols=None):
    """Gate 合约资金费率（免费）"""
    from config import SYMBOLS
    syms = symbols or SYMBOLS
    out = {}
    for sym in syms:
        contract = sym.replace("USDT", "_USDT")
        try:
            d = _get(f"https://api.gateio.ws/api/v4/futures/usdt/funding_rate?contract={contract}&limit=1")
            if d:
                out[sym] = {"rate": float(d[0]["r"]), "ts": int(d[0]["t"])}
        except Exception:
            continue
        time.sleep(0.15)
    return out

def save_funding(data):
    if not data:
        return
    dbh = db.get_db()
    try:
        dbh.execute("CREATE TABLE IF NOT EXISTS funding (symbol TEXT, ts INTEGER, rate REAL, next_funding INTEGER, PRIMARY KEY (symbol, ts))")
        for sym, f in data.items():
            dbh.execute("INSERT OR REPLACE INTO funding (symbol, ts, rate, next_funding) VALUES (?,?,?,0)",
                        (sym, int(time.time() * 1000), f["rate"]))
        dbh.commit()
    finally:
        dbh.close()

def fetch_gate_tickers():
    """Gate 合约 24h 行情（免费）"""
    try:
        data = _get("https://api.gateio.ws/api/v4/futures/usdt/tickers")
        out = {}
        for t in data:
            c = t.get("contract", "")
            if c.endswith("_USDT"):
                out[c.replace("_USDT", "USDT")] = {
                    "price": float(t.get("last", 0) or 0),
                    "chg24h": float(t.get("change_percentage", 0) or 0),
                    "vol24h": float(t.get("volume_24h_quote", 0) or 0),
                    "funding": float(t.get("funding_rate", 0) or 0),
                }
        return out
    except Exception:
        return {}

def run_extra_collect():
    """采集器扩展入口：FGI + Gate 合约费率"""
    fgi = fetch_fgi()
    save_fgi(fgi)
    if fgi:
        print(f"[FGI] {fgi['value']} {fgi['label']}", flush=True)
    funding = fetch_gate_funding()
    save_funding(funding)
    if funding:
        print(f"[FUNDING] {len(funding)} 币费率已更新", flush=True)
    return {"fgi": fgi, "funding": len(funding)}
