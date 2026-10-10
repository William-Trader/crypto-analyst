# ---------------------------------------------------------------------------
# analyst/monitor.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-1CED9E13
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""异动雷达：量价异常检测 + 事件归因"""
import time
from collector import db
from config import SYMBOLS

ALERT_HYSTERESIS = 600  # 同一币 10 分钟内不重复告警

def detect_alerts(now=None):
    """扫描 ticker_snap 找异动，返回告警列表"""
    now = now or int(time.time())
    dbh = db.get_db()
    alerts = []
    for sym in SYMBOLS:
        rows = dbh.execute("""SELECT * FROM ticker_snap WHERE symbol=?
            ORDER BY ts DESC LIMIT 4""", (sym,)).fetchall()
        if len(rows) < 4: continue
        cur, prev = rows[0], rows[1]
        # 5 分钟价格变动
        if prev["price"] <= 0: continue
        chg_5m = (cur["price"] - prev["price"]) / prev["price"] * 100
        # 24h 高低位
        hi24 = max(r["high24h"] for r in rows)
        lo24 = min(r["low24h"] for r in rows)
        # 量能（当前 24h 量 vs 前一条）
        vol_ratio = cur["quote_vol24h"] / prev["quote_vol24h"] if prev["quote_vol24h"] else 1

        reasons = []
        if abs(chg_5m) >= 1.5:
            reasons.append(f"5分钟{'涨' if chg_5m > 0 else '跌'}{abs(chg_5m):.1f}%")
        if cur["price"] >= hi24 * 0.999 and chg_5m > 0:
            reasons.append("突破24h高点")
        if cur["price"] <= lo24 * 1.001 and chg_5m < 0:
            reasons.append("跌破24h低点")
        if vol_ratio > 1.3:
            reasons.append(f"成交额骤增{vol_ratio:.1f}x")
        if not reasons: continue

        # 归因：联动检查
        related = []
        for sym2 in SYMBOLS:
            if sym2 == sym: continue
            r2 = dbh.execute("SELECT * FROM ticker_snap WHERE symbol=? ORDER BY ts DESC LIMIT 2", (sym2,)).fetchall()
            if len(r2) >= 2 and r2[0]["price"] and r2[1]["price"]:
                c2 = (r2[0]["price"] - r2[1]["price"]) / r2[1]["price"] * 100
                if abs(c2) >= 0.8:
                    related.append(f"{sym2.replace('USDT','')}{c2:+.1f}%")
        cause = f"（联动: {', '.join(related[:3])}）" if related else "（独立行情）"

        alerts.append({
            "symbol": sym, "ts": now, "price": cur["price"],
            "chg_5m": round(chg_5m, 2), "reasons": reasons, "cause": cause,
        })
    dbh.close()
    return alerts

def check_and_store():
    """检查异动并入库（10 分钟去重）"""
    dbh = db.get_db()
    try:
        dbh.execute("CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, symbol TEXT, price REAL, chg_5m REAL, reasons TEXT, cause TEXT)")
        dbh.commit()
    except Exception:
        pass
    now = int(time.time())
    alerts = detect_alerts(now)
    stored = []
    for a in alerts:
        # 去重：同币 10 分钟内已告警则跳过
        dup = dbh.execute("""SELECT id FROM alerts WHERE symbol=? AND ts>?""",
                          (a["symbol"], now - ALERT_HYSTERESIS)).fetchone()
        if dup: continue
        dbh.execute("INSERT INTO alerts (ts,symbol,price,chg_5m,reasons,cause) VALUES (?,?,?,?,?,?)",
                    (a["ts"], a["symbol"], a["price"], a["chg_5m"],
                     "、".join(a["reasons"]), a["cause"]))
        stored.append(a)
    dbh.commit(); dbh.close()
    return stored

def daily_brief():
    """每日晨报/晚报：大盘概览 + 异动 + 涨跌榜"""
    dbh = db.get_db()
    try:
        dbh.execute("CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, symbol TEXT, price REAL, chg_5m REAL, reasons TEXT, cause TEXT)")
        dbh.commit()
    except Exception:
        pass
    rows = dbh.execute("""SELECT symbol, price, chg24h FROM ticker_snap t1
        WHERE ts=(SELECT MAX(ts) FROM ticker_snap t2 WHERE t2.symbol=t1.symbol)""").fetchall()
    al = dbh.execute("SELECT * FROM alerts ORDER BY ts DESC LIMIT 5").fetchall()
    dbh.close()
    lines = [f"📰 【分析师日报 {time.strftime('%Y-%m-%d %H:%M')}】"]
    if rows:
        srt = sorted(rows, key=lambda r: r["chg24h"], reverse=True)
        up = sum(1 for r in rows if r["chg24h"] > 0)
        lines.append(f"大盘：{len(rows)}币 {up}涨{len(rows)-up}跌")
        lines.append(f"领涨 {srt[0]['symbol'].replace('USDT','')} {srt[0]['chg24h']:+.2f}% | 领跌 {srt[-1]['symbol'].replace('USDT','')} {srt[-1]['chg24h']:+.2f}%")
    if al:
        lines.append("近期异动：")
        for a in al[:3]:
            lines.append(f"  {a['symbol'].replace('USDT','')} {a['reasons']} {a['cause']}")
    return "\n".join(lines)
