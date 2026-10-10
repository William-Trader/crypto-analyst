# ---------------------------------------------------------------------------
# collector/universe.py - crypto-analyst key data logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-8A952B86
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""品种宇宙：全 USDT 交易对 + 深研池管理（按成交量排序）"""
import time
from collector import db
from collector.sources import get_all_tickers

DEEP_POOL_SIZE = 30   # 深研池：Top 30 品种获得完整 K 线
SNAP_LIMIT = 400      # 快照上限：全部品种行情快照
STABLES = {"USDC", "USDT", "USD1", "FDUSD", "DAI", "TUSD", "RLUSD", "PYUSD", "USDE", "USDY", "BUSD", "EURI"}

def _is_stable(sym):
    base = sym.replace("USDT", "")
    return base in STABLES or base.endswith("USD")

def update_universe():
    """拉取全品种行情 → 更新 universe 表 + ticker_snap（全品种）"""
    tickers = get_all_tickers()
    if not tickers:
        return {"count": 0, "error": "所有数据源不可用"}
    now_ms = int(time.time() * 1000)
    dbh = db.get_db()
    try:
        dbh.execute("""CREATE TABLE IF NOT EXISTS universe (
            symbol TEXT PRIMARY KEY, base TEXT, quote TEXT DEFAULT 'USDT',
            source TEXT, quote_vol REAL DEFAULT 0, rank INTEGER DEFAULT 9999,
            first_seen INTEGER, last_seen INTEGER)""")
        dbh.commit()
    except Exception:
        pass

    # 按成交额排序（Binance 优先口径），排除稳定币
    ranked = [kv for kv in sorted(tickers.items(), key=lambda kv: -(kv[1].get("quote_vol") or 0)) if not _is_stable(kv[0])]
    snap_rows, uni_rows = [], []
    for i, (sym, t) in enumerate(ranked[:SNAP_LIMIT]):
        snap_rows.append((sym, now_ms, t.get("price", 0), t.get("chg24h", 0),
                          t.get("vol24h", 0), t.get("quote_vol", 0),
                          t.get("high24h", 0), t.get("low24h", 0)))
        uni_rows.append((sym, sym.replace("USDT", ""), "USDT", t.get("source", "?"),
                         t.get("quote_vol", 0), i + 1, now_ms, now_ms))
    if snap_rows:
        dbh.executemany("""INSERT OR REPLACE INTO ticker_snap
            (symbol,ts,price,chg24h,vol24h,quote_vol24h,high24h,low24h) VALUES (?,?,?,?,?,?,?,?)""", snap_rows)
    if uni_rows:
        dbh.executemany("""INSERT INTO universe (symbol,base,quote,source,quote_vol,rank,first_seen,last_seen)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol) DO UPDATE SET quote_vol=excluded.quote_vol, rank=excluded.rank,
            source=excluded.source, last_seen=excluded.last_seen""", uni_rows)
    dbh.commit(); dbh.close()
    return {"count": len(snap_rows), "top": ranked[0][0] if ranked else None}

def deep_pool():
    """深研池候选：非稳定币按 rank 取前 N（K 线由采集器补齐）"""
    dbh = db.get_db()
    rows = dbh.execute("""SELECT symbol FROM universe WHERE rank<=?
        ORDER BY rank""", (DEEP_POOL_SIZE * 2,)).fetchall()
    dbh.close()
    pool = []
    for r in rows:
        sym = r["symbol"]
        if _is_stable(sym):
            continue
        pool.append(sym)
        if len(pool) >= DEEP_POOL_SIZE:
            break
    return pool

def universe_stats():
    dbh = db.get_db()
    total = dbh.execute("SELECT COUNT(*) c FROM universe").fetchone()["c"]
    by_src = dbh.execute("SELECT source, COUNT(*) c FROM universe GROUP BY source").fetchall()
    dbh.close()
    return {"total": total, "by_source": {r["source"]: r["c"] for r in by_src}}

if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    r = update_universe()
    print("universe 更新:", r)
    print("深研池:", deep_pool()[:8])
    print(universe_stats())
