# ---------------------------------------------------------------------------
# analyst/radar.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-CA0E9CDC
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""全币信号雷达：扫描深研池+全品种，输出最强信号榜（含计算过程与历史背书）"""
from collector import db
from collector.universe import deep_pool
from indicators import ta
from indicators.backtest import signal_backtest, make_rsi_signal, make_boll_signal, make_cross_signal
from analyst.calc import rsi_calc, boll_calc, macd_calc

def scan_radar(interval="4h", limit=20):
    """扫描深研池全品种 → 信号榜"""
    pool = deep_pool()
    results = []
    for sym in pool:
        raw = db.get_klines(sym, interval, 200)
        klines = [{"ts": r["ts"], "o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"], "v": r["vol"]} for r in raw]
        if len(klines) < 60: continue
        closes = [k["c"] for k in klines]
        highs = [k["h"] for k in klines]
        lows = [k["l"] for k in klines]
        r = ta.rsi(closes)
        up, mid, dn = ta.bollinger(closes)
        e20, e50 = ta.ema(closes, 20), ta.ema(closes, 50)
        sigs = []
        # RSI 超卖/超买（含温和区）
        if r is not None and r < 40:
            bt = signal_backtest(sym, interval, "rsi_os", make_rsi_signal(14, 30, True))
            sigs.append({"name": "RSI偏弱", "dir": "bullish", "val": round(r, 1),
                         "back": bt, "calc": rsi_calc(closes)})
        if r is not None and r > 60:
            bt = signal_backtest(sym, interval, "rsi_ob", make_rsi_signal(14, 70, False))
            sigs.append({"name": "RSI偏强", "dir": "bearish", "val": round(r, 1),
                         "back": bt, "calc": rsi_calc(closes)})
        # 布林突破
        if up and closes[-1] >= up:
            bt = signal_backtest(sym, interval, "boll_up", make_boll_signal(20, False))
            sigs.append({"name": "突破布林上轨", "dir": "bullish", "val": round(closes[-1], 2),
                         "back": bt, "calc": boll_calc(closes)})
        if dn and closes[-1] <= dn:
            bt = signal_backtest(sym, interval, "boll_dn", make_boll_signal(20, True))
            sigs.append({"name": "跌破布林下轨", "dir": "bullish", "val": round(closes[-1], 2),
                         "back": bt, "calc": boll_calc(closes)})
        # EMA 多头/空头排列
        if e20 and e50:
            dist = (e20 - e50) / e50 * 100
            if dist > 0.8:
                sigs.append({"name": f"多头排列({dist:.1f}%)", "dir": "bullish", "val": round(dist, 2),
                             "back": None, "calc": {"name": "EMA排列", "steps": [
                                 f"EMA20 {round(e20,2)} 在 EMA50 {round(e50,2)} 上方 {dist:.1f}%"], "result": "多头"}})
            if dist < -0.8:
                sigs.append({"name": f"空头排列({dist:.1f}%)", "dir": "bearish", "val": round(dist, 2),
                             "back": None, "calc": {"name": "EMA排列", "steps": [
                                 f"EMA20 {round(e20,2)} 在 EMA50 {round(e50,2)} 下方 {abs(dist):.1f}%"], "result": "空头"}})
        # 布林位置 %B
        if up and dn and up > dn:
            pb = (closes[-1] - dn) / (up - dn) * 100
            if pb < 15:
                sigs.append({"name": f"贴下轨(%B={pb:.0f})", "dir": "bullish", "val": round(pb, 1),
                             "back": None, "calc": boll_calc(closes)})
            if pb > 85:
                sigs.append({"name": f"贴上轨(%B={pb:.0f})", "dir": "bearish", "val": round(pb, 1),
                             "back": None, "calc": boll_calc(closes)})
        # 量价异动
        vols = [k["v"] for k in klines]
        if len(vols) > 25:
            avg = sum(vols[-26:-1]) / 20
            vr = vols[-1] / avg if avg > 0 else 1
            if vr > 2:
                d = "bullish" if closes[-1] > closes[-2] else "bearish"
                sigs.append({"name": f"放量{vr:.1f}x", "dir": d, "val": round(vr, 1),
                             "back": None, "calc": {"name": "量比", "steps": [
                                 f"最新量 {round(vols[-1],2)} / 前20根均值 {round(avg,2)} = {round(vr,2)}"],
                                 "result": f"{vr:.1f}x"}})
        for s in sigs:
            s["symbol"] = sym
            s["price"] = closes[-1]
            s["interval"] = interval
            s["score"] = _score(s)
        results.extend(sigs)
    results.sort(key=lambda s: -s["score"])
    return results[:limit]

def _score(s):
    """信号强度：方向分 + 历史胜率分"""
    d = 3 if s["dir"] == "bullish" else 3  # 方向权重（多空同权）
    bt = s.get("back") or {}
    wr = bt.get("win_rate", 50) or 50
    return round(d * (wr / 50), 1) if bt.get("count", 0) >= 10 else round(d * 0.8, 1)

def radar_text(limit=10):
    rows = scan_radar(limit=limit)
    if not rows:
        return "雷达暂无信号（数据积累中）"
    lines = ["📡 【比格信号雷达】全池扫描结果"]
    for s in rows:
        emoji = "🟢" if s["dir"] == "bullish" else "🔴"
        bt = s.get("back") or {}
        bt_s = f"·历史{bt.get('count', 0)}次胜率{bt.get('win_rate', '-')}%" if bt.get("count") else ""
        lines.append(f"{emoji} {s['symbol'].replace('USDT','')} {s['name']} ({s['val']}) {bt_s}")
    return "\n".join(lines)
