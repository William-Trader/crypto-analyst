#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# scripts/morning_brief.py - crypto-analyst key automation logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-D1636E19
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""比格晨报生成器：Verdict + 情绪 + FGI + 费率榜 + 信号榜 + 比格观点
供 QQ 主动推送 / 网页展示使用。用法: python3 scripts/morning_brief.py [--save]"""
import sys, time
sys.path.insert(0, ".")

def build_brief():
    from analyst.verdict import verdict_with_opinion, save_verdict
    from analyst.sentiment import market_sentiment, macro_view
    from analyst.radar import scan_radar
    from collector import db

    v = verdict_with_opinion()
    save_verdict(v)
    s = market_sentiment()
    m = macro_view()

    lines = [f"📰 【比格晨报 {time.strftime('%Y-%m-%d %H:%M')}】"]
    emoji = {"看多": "🟢", "看空": "🔴", "观望": "⚪"}.get(v["verdict"], "")
    lines.append(f"⚖️ 今日 Verdict: {emoji} {v['verdict']}（{v['score']}分）")
    if v.get("opinion"):
        lines.append(f"🐕 比格说: {v['opinion']}")
    if v.get("fgi"):
        f = v["fgi"]
        lines.append(f"😱 FGI: {f['value']} {f['label']}")
    lines.append(f"🌡️ 情绪: {s['score']}（{s['label']}，涨跌比 {s['detail'].get('up_ratio', 0)}%）")
    if m.get("btc_d") is not None:
        lines.append(f"📊 BTC.D {m['btc_d']}% · 总成交 {m.get('total_vol_24h', 0)}B")
    # 费率榜
    dbh = db.get_db()
    try:
        rows = dbh.execute("""SELECT f1.symbol, f1.rate FROM funding f1
            WHERE f1.ts=(SELECT MAX(ts) FROM funding f2 WHERE f2.symbol=f1.symbol)
            ORDER BY ABS(f1.rate) DESC LIMIT 4""").fetchall()
        if rows:
            lines.append("💰 费率异动: " + " | ".join(
                f"{r['symbol'].replace('USDT','')} {r['rate']*100:+.4f}%" for r in rows))
    except Exception:
        pass
    dbh.close()
    # 信号榜
    try:
        sigs = scan_radar(limit=5)
        if sigs:
            lines.append("📡 雷达信号: " + " | ".join(
                f"{s['symbol'].replace('USDT','')} {s['name']}" for s in sigs))
    except Exception:
        pass
    # 关键位
    try:
        from analyst.council_quick import quick_plan
        p = quick_plan("BTCUSDT").get("plan")
        if p:
            lines.append(f"🎯 BTC 作战: {p['direction']} 入场{p['entry']} 止损{p['stop']} 目标{p['target1']}")
    except Exception:
        pass
    lines.append("—— 数据源: Binance/Gate/alternative.me · 仅供参考，不构成投资建议")
    return "\n".join(lines)

if __name__ == "__main__":
    brief = build_brief()
    print(brief)
    if "--save" in sys.argv:
        from collector import db
        dbh = db.get_db()
        try:
            dbh.execute("CREATE TABLE IF NOT EXISTS briefs (ts INTEGER PRIMARY KEY, content TEXT)")
            dbh.execute("INSERT OR REPLACE INTO briefs (ts, content) VALUES (?,?)", (int(time.time()), brief))
            dbh.commit()
        finally:
            dbh.close()
        print("\n[已存档 briefs 表]", file=sys.stderr)
