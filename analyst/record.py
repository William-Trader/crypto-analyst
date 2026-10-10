# ---------------------------------------------------------------------------
# analyst/record.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-D55CA82E
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""预测记录仪 v2：自动保存预测 + 定时验证 + 周复盘纠偏"""
import time, json
from collector import db

def save_prediction(symbol, direction, confidence, entry, stop, target1, target2, notes=""):
    dbh = db.get_db()
    dbh.execute("""INSERT INTO predictions (ts,symbol,direction,confidence,entry,stop,target1,target2,notes)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (int(time.time()), symbol, direction, confidence, entry, stop, target1, target2, notes))
    dbh.commit(); dbh.close()

def save_from_plan(plan, notes=""):
    if not plan: return None
    save_prediction(plan["symbol"], plan["direction"], plan["confidence"],
                    plan["entry"], plan["stop"], plan["target1"], plan["target2"], notes)

def verify_pending(max_age_hours=168):
    """验证所有 pending 预测（用最新价），超过 7 天标 expired"""
    dbh = db.get_db()
    rows = dbh.execute("SELECT * FROM predictions WHERE verdict='pending'").fetchall()
    now = int(time.time())
    updated = 0
    for p in rows:
        tick = dbh.execute("SELECT price FROM ticker_snap WHERE symbol=? ORDER BY ts DESC LIMIT 1", (p["symbol"],)).fetchone()
        if tick:
            price = tick[0]
            v = None
            if p["direction"] == "bullish":
                if p["stop"] and price <= p["stop"]: v = "hit_stop"
                elif p["target2"] and price >= p["target2"]: v = "hit_t2"
                elif p["target1"] and price >= p["target1"]: v = "hit_t1"
            else:
                if p["stop"] and price >= p["stop"]: v = "hit_stop"
                elif p["target2"] and price <= p["target2"]: v = "hit_t2"
                elif p["target1"] and price <= p["target1"]: v = "hit_t1"
            if v:
                dbh.execute("UPDATE predictions SET verdict=? WHERE id=?", (v, p["id"]))
                updated += 1
        elif now - p["ts"] > max_age_hours * 3600:
            dbh.execute("UPDATE predictions SET verdict='expired' WHERE id=?", (p["id"],))
            updated += 1
    dbh.commit(); dbh.close()
    return updated

def stats():
    dbh = db.get_db()
    rows = dbh.execute("SELECT * FROM predictions WHERE verdict!='pending' AND verdict!='expired'").fetchall()
    dbh.close()
    if not rows: return {"total": 0}
    wins = sum(1 for r in rows if r["verdict"] in ("hit_t1", "hit_t2"))
    losses = sum(1 for r in rows if r["verdict"] == "hit_stop")
    return {"total": len(rows), "wins": wins, "losses": losses,
            "win_rate": round(wins / len(rows) * 100, 1) if rows else 0}

def weekly_review():
    """周复盘：统计近 7 天验证预测的方向命中，检测系统性偏差"""
    dbh = db.get_db()
    rows = dbh.execute("""SELECT * FROM predictions WHERE ts>?
        AND verdict IN ('hit_t1','hit_t2','hit_stop')""", (int(time.time()) - 7*86400,)).fetchall()
    dbh.close()
    if len(rows) < 5:
        return None
    bull = [r for r in rows if r["direction"] == "bullish"]
    bear = [r for r in rows if r["direction"] == "bearish"]
    def rate(rs):
        if not rs: return None
        w = sum(1 for r in rs if r["verdict"] in ("hit_t1", "hit_t2"))
        return round(w / len(rs) * 100, 1)
    br, rr = rate(bull), rate(bear)
    total_rate = rate(rows)
    issues = []
    if br is not None and br < 40:
        issues.append(f"本周看多命中率仅 {br}%（{len(bull)}次）——存在系统性乐观偏差，震荡市勿追多")
    if rr is not None and rr < 40:
        issues.append(f"本周看空命中率仅 {rr}%（{len(bear)}次）——存在系统性悲观偏差，强趋势市勿摸顶")
    if not issues:
        issues.append(f"本周总命中率 {total_rate}%（样本 {len(rows)}），无明显偏差")
    return {
        "period": "7d", "total": len(rows), "total_rate": total_rate,
        "bull_rate": br, "bear_rate": rr, "issues": issues,
    }
