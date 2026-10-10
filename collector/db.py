# ---------------------------------------------------------------------------
# collector/db.py - crypto-analyst key data logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-9C170A12
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""SQLite 数据仓库（WAL，幂等 UPSERT）"""
import sqlite3, time
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS klines (
    symbol TEXT, interval TEXT, ts INTEGER,
    open REAL, high REAL, low REAL, close REAL,
    vol REAL, quote_vol REAL, trades INTEGER,
    taker_buy REAL DEFAULT 0,
    PRIMARY KEY (symbol, interval, ts)
);
CREATE INDEX IF NOT EXISTS idx_klines ON klines(symbol, interval, ts);
CREATE TABLE IF NOT EXISTS ticker_snap (
    symbol TEXT, ts INTEGER, price REAL, chg24h REAL,
    vol24h REAL, quote_vol24h REAL, high24h REAL, low24h REAL,
    PRIMARY KEY (symbol, ts)
);
CREATE TABLE IF NOT EXISTS oi_snap (
    symbol TEXT, ts INTEGER, oi_usd REAL, PRIMARY KEY (symbol, ts)
);
CREATE TABLE IF NOT EXISTS funding (
    symbol TEXT, ts INTEGER, rate REAL, next_funding INTEGER,
    PRIMARY KEY (symbol, ts)
);
CREATE TABLE IF NOT EXISTS collect_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task TEXT, symbol TEXT, ts INTEGER, ok INTEGER, ms INTEGER
);
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER, symbol TEXT, direction TEXT, confidence REAL,
    entry REAL, stop REAL, target1 REAL, target2 REAL,
    verdict TEXT DEFAULT 'pending',      -- hit_stop | hit_t1 | hit_t2 | pending | expired
    notes TEXT
);
CREATE TABLE IF NOT EXISTS analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER, symbol TEXT, market_state TEXT,
    report TEXT, full JSON
);
"""

def get_db():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    return db

def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    # 兼容旧表：补 taker_buy 列
    try:
        db.execute("ALTER TABLE klines ADD COLUMN taker_buy REAL DEFAULT 0")
        db.commit()
    except Exception:
        pass
    db.close()

def upsert_klines(rows):
    """rows: [(symbol, interval, ts, o,h,l,c,v,qv,trades, taker_buy)]"""
    if not rows: return
    db = get_db()
    db.executemany("""INSERT OR REPLACE INTO klines
        (symbol,interval,ts,open,high,low,close,vol,quote_vol,trades,taker_buy)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""", rows)
    db.commit(); db.close()

def insert_snaps(table, rows):
    if not rows: return
    db = get_db()
    if table == "ticker_snap":
        db.executemany("INSERT OR REPLACE INTO ticker_snap (symbol,ts,price,chg24h,vol24h,quote_vol24h,high24h,low24h) VALUES (?,?,?,?,?,?,?,?)", rows)
    elif table == "oi_snap":
        db.executemany("INSERT OR REPLACE INTO oi_snap (symbol,ts,oi_usd) VALUES (?,?,?)", rows)
    elif table == "funding":
        db.executemany("INSERT OR REPLACE INTO funding (symbol,ts,rate,next_funding) VALUES (?,?,?,?)", rows)
    db.commit(); db.close()

def log_health(task, symbol, ok, ms):
    db = get_db()
    db.execute("INSERT INTO collect_health (task,symbol,ts,ok,ms) VALUES (?,?,?,?,?)",
               (task, symbol, int(time.time()), 1 if ok else 0, int(ms)))
    db.commit(); db.close()

def get_klines(symbol, interval, limit=500):
    db = get_db()
    rows = db.execute("""SELECT * FROM klines WHERE symbol=? AND interval=?
        ORDER BY ts DESC LIMIT ?""", (symbol, interval, limit)).fetchall()
    db.close()
    return list(reversed(rows))

def max_ts(symbol, interval):
    db = get_db()
    r = db.execute("SELECT MAX(ts) FROM klines WHERE symbol=? AND interval=?", (symbol, interval)).fetchone()
    db.close()
    return r[0] if r and r[0] else 0

def cleanup_old():
    """按保留策略清理过期数据"""
    db = get_db()
    now = int(time.time())
    for iv, keep in [("15m", 90*86400), ("1h", 180*86400)]:
        if keep:
            db.execute("DELETE FROM klines WHERE interval=? AND ts<?", (iv, now-keep))
    db.commit(); db.close()
