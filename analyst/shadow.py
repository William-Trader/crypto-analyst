# ---------------------------------------------------------------------------
# analyst/shadow.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-D1A067F9
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""模拟账户：按系统建议虚拟执行 → 权益曲线 + 与 BTC 对比"""
import time
from collector import db
from analyst.risk import build_plan
from analyst.council_quick import quick_plan

def _equity_series():
    """根据历史预测（已验证）构造模拟权益：按每笔已验证预测的 PnL 累计"""
    dbh = db.get_db()
    rows = dbh.execute("""SELECT ts, symbol, direction, entry, stop, target1, target2, verdict
        FROM predictions WHERE verdict IN ('hit_t1','hit_t2','hit_stop')
        ORDER BY ts ASC""").fetchall()
    dbh.close()
    if not rows:
        return [], {}
    capital = 10000.0
    pos_pct = 0.2
    equity = []
    bal = capital
    for r in rows:
        entry = r["entry"] or 0
        if entry <= 0:
            continue
        if r["verdict"] == "hit_stop":
            exit_price = r["stop"] or 0
        elif r["verdict"] == "hit_t2":
            exit_price = r["target2"] or 0
        elif r["verdict"] == "hit_t1":
            exit_price = r["target1"] or 0
        else:
            continue
        direction = 1 if r["direction"] == "bullish" else -1
        ret = (exit_price - entry) / entry * direction
        bal += bal * pos_pct * ret
        equity.append({"ts": r["ts"], "balance": round(bal, 2)})
    if not equity:
        return [], {}
    # 指标
    balances = [e["balance"] for e in equity]
    total_return = (balances[-1] - capital) / capital * 100
    peak, max_dd = balances[0], 0.0
    for b in balances:
        peak = max(peak, b)
        dd = (peak - b) / peak * 100
        max_dd = max(max_dd, dd)
    daily = {}
    for e in equity:
        daily[e["ts"] // 86400000] = e["balance"]
    ds = sorted(daily)
    rets = []
    for a, b in zip(ds, ds[1:]):
        if daily[a] > 0:
            rets.append(daily[b] / daily[a] - 1)
    mean = sum(rets) / len(rets) if rets else 0
    std = (sum((x - mean) ** 2 for x in rets) / len(rets)) ** 0.5 if rets else 0
    sharpe = mean / std * (365 ** 0.5) if std else 0
    metrics = {
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe": round(sharpe, 3),
        "trades": len(equity),
        "capital": capital,
    }
    return equity, metrics

def _benchmark():
    """BTC 同期权益（基准）"""
    eq, _ = _equity_series()
    if not eq:
        return []
    dbh = db.get_db()
    rows = dbh.execute("SELECT ts, close FROM klines WHERE symbol='BTCUSDT' AND interval='1d' ORDER BY ts").fetchall()
    dbh.close()
    if not rows:
        return []
    start_ts, end_ts = eq[0]["ts"], eq[-1]["ts"]
    btcs = [r for r in rows if start_ts <= r["ts"] <= end_ts]
    if len(btcs) < 2:
        return []
    base = 10000.0
    start_price = btcs[0]["close"]
    out = []
    for r in btcs:
        bal = base * r["close"] / start_price
        out.append({"ts": r["ts"], "balance": round(bal, 2)})
    return out

def shadow_account():
    eq, metrics = _equity_series()
    bench = _benchmark()
    return {"equity": eq, "benchmark": bench, "metrics": metrics}

if __name__ == "__main__":
    import sys; sys.path.insert(0, ".")
    s = shadow_account()
    print("模拟账户:", s["metrics"])
    print("权益点数:", len(s["equity"]), "基准点数:", len(s["benchmark"]))
