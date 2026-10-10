# ---------------------------------------------------------------------------
# analyst/composite.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-13998B98
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""多因子综合评级：技术面 + 资金面 + 情绪面 → 每币综合评分（机构级）"""
from collector import db
from indicators import ta
from analyst.sentiment import market_sentiment

def rate_symbol(symbol):
    """单币综合评级 0-100：技术 40 + 资金 30 + 情绪 20 + 位置 10"""
    raw = db.get_klines(symbol, "4h", 150)
    if len(raw) < 80:
        return None
    k4h = [{"ts": r["ts"], "o": r["open"], "close": r["close"], "high": r["high"], "low": r["low"], "vol": r["vol"]} for r in raw]
    closes = [r["close"] for r in k4h]
    highs = [r["high"] for r in k4h]
    lows = [r["low"] for r in k4h]
    vols = [r["vol"] for r in k4h]
    last = closes[-1]

    score = {}
    # --- 技术面 40 分 ---
    tech = 0
    r = ta.rsi(closes)
    if r is not None:
        tech += 8 if r < 35 else (6 if r < 45 else (3 if r < 55 else (4 if r < 65 else 2)))
    e20, e50 = ta.ema(closes, 20), ta.ema(closes, 50)
    if e20 and e50:
        if last > e20 > e50: tech += 10
        elif last > e50: tech += 6
        elif last > e20: tech += 4
        else: tech += 1
    macd_l, dea, hist = ta.macd(closes)
    if macd_l is not None and hist is not None:
        tech += 6 if hist > 0 else 2
    adx = ta.adx(highs, lows, closes)
    if adx is not None:
        tech += 6 if adx > 25 else 3
    up, mid, dn = ta.bollinger(closes)
    if up and dn:
        pb = (last - dn) / (up - dn) * 100
        tech += 6 if pb < 20 else (5 if pb < 35 else (3 if pb < 65 else (4 if pb < 80 else 2)))
    tech += 4 if sum(1 for k in k4h[-3:] if k["close"] > k["o"]) >= 2 else 1
    score["tech"] = round(min(40, tech), 1)

    # --- 资金面 30 分（量能 + 资金流向近似） ---
    fund = 0
    vr = ta.volume_ratio(vols)
    if vr is not None:
        fund += 10 if vr > 1.5 else (7 if vr > 1.2 else (4 if vr > 0.9 else 5))
    # 量价配合：放量上涨/缩量下跌
    v_up = sum(1 for i in range(-5, 0) if k4h[i]["close"] > k4h[i-1]["close"] and k4h[i]["vol"] > vols[i-1])
    v_dn = sum(1 for i in range(-5, 0) if k4h[i]["close"] < k4h[i-1]["close"] and k4h[i]["vol"] > vols[i-1])
    fund += min(10, v_up * 2) - min(6, v_dn)
    # 资金费率（若有）
    f = db.get_db().execute("SELECT rate FROM funding WHERE symbol=? ORDER BY ts DESC LIMIT 1", (symbol,)).fetchone()
    db.get_db().close()
    if f and f["rate"] is not None:
        fund += 6 if f["rate"] < 0.0005 else (3 if f["rate"] < 0.001 else 1)
    else:
        fund += 3
    fund += 4 if last > ta.ema(closes, 20) else 1
    score["fund"] = round(max(0, min(30, fund)), 1)

    # --- 情绪面 20 分（大盘情绪联动） ---
    s = market_sentiment()
    score["senti"] = round(s["score"] / 5, 1)  # 0-20

    # --- 位置 10 分（区间位置，低位加分） ---
    hi = max(highs[-60:]); lo = min(lows[-60:])
    pos = (last - lo) / (hi - lo) if hi > lo else 0.5
    score["pos"] = round(max(0, 10 - pos * 10), 1)

    total = round(score["tech"] + score["fund"] + score["senti"] + score["pos"], 1)
    if total >= 75: grade = "A 强烈关注"
    elif total >= 60: grade = "B 值得观察"
    elif total >= 45: grade = "C 中性"
    elif total >= 30: grade = "D 偏弱"
    else: grade = "E 回避"
    return {"symbol": symbol, "score": total, "grade": grade, "parts": score}

def rate_top(n=20):
    """深研池批量评级，返回 Top N（按综合分排序）"""
    from collector.universe import deep_pool
    out = []
    for sym in deep_pool()[:40]:
        try:
            r = rate_symbol(sym)
            if r: out.append(r)
        except Exception:
            continue
    out.sort(key=lambda x: -x["score"])
    return out[:n]
