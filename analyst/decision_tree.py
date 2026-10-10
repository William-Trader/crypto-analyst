# ---------------------------------------------------------------------------
# analyst/decision_tree.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-A1056F48
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""决策树：分析结论的完整证据链（数据→特征→信号→合议→结论）"""
import time
from analyst.council_quick import quick_council, quick_plan
from analyst.resonance import resonance
from analyst.composite import rate_symbol
from collector import db
from indicators import ta

def decision_tree(symbol="BTCUSDT"):
    sym = symbol.upper()
    if not sym.endswith("USDT"):
        sym += "USDT"
    raw = db.get_klines(sym, "4h", 150)
    if len(raw) < 80:
        return {"symbol": sym, "error": "数据不足"}
    k4h = [{"ts": r["ts"], "o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"], "v": r["vol"]} for r in raw]
    closes = [k["c"] for k in k4h]
    highs = [k["h"] for k in k4h]
    lows = [k["l"] for k in k4h]
    last = closes[-1]

    tree = []

    # L1 数据层
    data_items = [
        {"name": "最新价", "value": f"{last:.2f}"},
        {"name": "24h 高/低", "value": f"{max(k['h'] for k in k4h[-6:]):.2f} / {min(k['l'] for k in k4h[-6:]):.2f}"},
        {"name": "数据源", "value": "Binance 4h · " + str(len(k4h)) + " 根"},
    ]
    tree.append({"layer": "数据快照", "items": data_items})

    # L2 特征层
    r = ta.rsi(closes)
    e20, e50 = ta.ema(closes, 20), ta.ema(closes, 50)
    macd_l, dea, hist = ta.macd(closes)
    adx = ta.adx(highs, lows, closes)
    up, mid, dn = ta.bollinger(closes)
    feat = [
        {"name": "RSI(14)", "value": f"{r:.1f}" if r else "—", "note": "超卖<30 / 超买>70"},
        {"name": "EMA20/50", "value": f"{e20:.2f} / {e50:.2f}" if e20 and e50 else "—",
         "note": "排列判定趋势"},
        {"name": "MACD 柱", "value": f"{hist:.4f}" if hist is not None else "—", "note": "红柱偏多/绿柱偏空"},
        {"name": "ADX", "value": f"{adx:.1f}" if adx else "—", "note": ">25 强趋势"},
        {"name": "布林 %B", "value": f"{((last-dn)/(up-dn)*100):.0f}%" if up and dn and up > dn else "—",
         "note": "<15 贴下轨"},
    ]
    tree.append({"layer": "特征计算", "items": feat})

    # L3 信号层
    from analyst.resonance import resonance as res_fn
    res = res_fn(sym)
    sig_items = [{"name": "多周期共振", "value": f"{res.get('resonance')}分 {res.get('direction')}",
                  "note": str(res.get("tf_scores", {}))}]
    for d in res.get("divergences", []):
        sig_items.append({"name": "⚠️ 背离", "value": d, "note": "降低置信"})
    tree.append({"layer": "信号触发", "items": sig_items})

    # L4 合议层
    c = quick_council(sym)
    if "error" not in c:
        items = [{"name": "市场状态", "value": c["market_state"], "note": c.get("state_reason", "")}]
        for s in c["schools"]:
            items.append({"name": s["school"], "value": f"{s['direction']} {s['confidence']}%",
                          "note": s.get("note", "")})
        items.append({"name": "合议结果", "value": f"{c['direction']} · 一致性 {c['agreement']}%", "note": ""})
        tree.append({"layer": "八派合议", "items": items})

    # L5 结论层
    rating = rate_symbol(sym)
    plan = quick_plan(sym).get("plan")
    concl = []
    if rating:
        concl.append({"name": "综合评级", "value": f"{rating['score']} · {rating['grade']}",
                      "note": f"技术{rating['parts']['tech']} 资金{rating['parts']['fund']} 情绪{rating['parts']['senti']} 位置{rating['parts']['pos']}"})
    if plan:
        concl.append({"name": "作战计划", "value": f"{plan['direction']} 入{plan['entry']} 损{plan['stop']}",
                      "note": f"目标 {plan['target1']}/{plan['target2']} · 仓位 ≤{plan['position_pct']}%"})
    concl.append({"name": "综合方向", "value": res.get("direction", "neutral"), "note": "共振方向"})
    tree.append({"layer": "决策结论", "items": concl})

    return {"symbol": sym, "ts": int(time.time()), "tree": tree}

if __name__ == "__main__":
    import sys, json; sys.path.insert(0, ".")
    t = decision_tree("SOLUSDT")
    for layer in t.get("tree", []):
        print(f"\n== {layer['layer']} ==")
        for it in layer["items"]:
            print(f"  {it['name']}: {it['value']}  {it.get('note','')}")
