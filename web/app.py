# ---------------------------------------------------------------------------
# web/app.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-A3C98908
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""FastAPI 前端工作台：驾驶舱 API + SSE 动作流 + 静态页面"""
import json, time, sqlite3, asyncio
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from collector import db
from config import SYMBOLS, DB_PATH
from analyst.pipeline import full_analysis
from collector.sources import source_status
from collector.universe import universe_stats
from analyst.radar import scan_radar
from analyst.calc import all_calcs
from analyst import record
from analyst.council_quick import quick_council, quick_plan
from analyst.verdict import market_verdict, get_latest_verdict, save_verdict
from analyst.sentiment import market_sentiment, beagle_mood, macro_view
from analyst.composite import rate_top
from analyst.correlation import correlation_matrix
from analyst.backtest_engine import run_backtest
from indicators.backtest import signal_backtest, make_rsi_signal, make_boll_signal

app = FastAPI(title="Crypto Analyst Cockpit")
STATIC = Path(__file__).resolve().parent / "static"

# ---------- API ----------
@app.get("/api/overview")
def overview():
    dbh = db.get_db()
    rows = dbh.execute("""SELECT t1.symbol, t1.price, t1.chg24h, t1.quote_vol24h,
        (SELECT oi_usd FROM oi_snap o WHERE o.symbol=t1.symbol ORDER BY ts DESC LIMIT 1) oi
        FROM ticker_snap t1 WHERE ts=(SELECT MAX(ts) FROM ticker_snap t2 WHERE t2.symbol=t1.symbol)""").fetchall()
    health = dbh.execute("SELECT task, ok FROM collect_health ORDER BY id DESC LIMIT 10").fetchall()
    dbh.close()
    return {"tickers": [dict(r) for r in rows], "health": [dict(h) for h in health]}

@app.get("/api/analyze/{symbol}")
def analyze(symbol: str):
    sym = symbol.upper()
    if not sym.endswith("USDT"): sym += "USDT"
    try:
        r = full_analysis(sym, use_llm=True)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return r

@app.get("/api/history/{symbol}")
def history(symbol: str):
    dbh = db.get_db()
    rows = dbh.execute("""SELECT ts, market_state, report FROM analyses WHERE symbol=?
        ORDER BY ts DESC LIMIT 20""", (symbol.upper(),)).fetchall()
    dbh.close()
    return [dict(r) for r in rows]

@app.get("/api/alerts")
def alerts(after: int = 0):
    dbh = db.get_db()
    try:
        dbh.execute("CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, symbol TEXT, price REAL, chg_5m REAL, reasons TEXT, cause TEXT)")
        dbh.commit()
        rows = dbh.execute("SELECT * FROM alerts WHERE ts>? ORDER BY ts ASC LIMIT 10", (after,)).fetchall()
    except Exception:
        rows = []
    dbh.close()
    return [dict(r) for r in rows]

@app.get("/api/kline/{symbol}")
def kline(symbol: str, interval: str = "4h", limit: int = 120):
    """K线（完整 OHLCV，供蜡烛图）"""
    iv = interval if interval in ("15m", "1h", "4h", "1d") else "4h"
    rows = db.get_klines(symbol.upper(), iv, limit)
    return [{"ts": r["ts"], "o": r["open"], "h": r["high"], "l": r["low"],
             "c": r["close"], "v": r["vol"], "qv": r["quote_vol"]} for r in rows]

@app.get("/api/universe")
def universe():
    dbh = db.get_db()
    rows = dbh.execute("SELECT symbol, source, quote_vol, rank FROM universe ORDER BY rank LIMIT 500").fetchall()
    dbh.close()
    return {"universe": [dict(r) for r in rows], "stats": universe_stats(),
            "sources": source_status()}

@app.get("/api/tickers")
def tickers(top: int = 30):
    dbh = db.get_db()
    rows = dbh.execute("""SELECT t1.symbol, t1.price, t1.chg24h, t1.quote_vol24h, t1.ts,
        u.source FROM ticker_snap t1 JOIN universe u ON u.symbol=t1.symbol
        WHERE t1.ts=(SELECT MAX(ts) FROM ticker_snap t2 WHERE t2.symbol=t1.symbol)
        ORDER BY t1.quote_vol24h DESC LIMIT ?""", (top,)).fetchall()
    dbh.close()
    return [dict(r) for r in rows]

@app.get("/api/calc/{symbol}")
def calc(symbol: str):
    """指标计算过程（点击看计算）"""
    sym = symbol.upper()
    if not sym.endswith("USDT"): sym += "USDT"
    rows = db.get_klines(sym, "4h", 120)
    if not rows:
        return {"error": f"{sym} 暂无数据"}
    klines = [{"ts": r["ts"], "o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"], "v": r["vol"]} for r in rows]
    return {"symbol": sym, "interval": "4h", "calcs": all_calcs(klines)}

@app.get("/api/radar")
def radar(limit: int = 15):
    try:
        return {"signals": scan_radar(limit=limit)}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/sources")
def sources():
    return {"sources": source_status(), "stats": universe_stats()}

@app.get("/api/macro")
def macro():
    """市场情绪 + 宏观（驱动比格情绪）"""
    s = market_sentiment()
    return {"sentiment": s, "beagle": beagle_mood(s), "macro": macro_view()}

@app.get("/api/backtest/run")
def backtest_run(symbol: str = "BTCUSDT", interval: str = "4h", signal: str = "rsi_os"):
    """回测实验室：指定币/周期/信号 → 历史统计"""
    sym = symbol.upper()
    if not sym.endswith("USDT"): sym += "USDT"
    iv = interval if interval in ("15m", "1h", "4h", "1d") else "4h"
    tests = {
        "rsi_os": ("RSI超卖(<30)", make_rsi_signal(14, 30, True)),
        "rsi_ob": ("RSI超买(>70)", make_rsi_signal(14, 70, False)),
        "boll_up": ("突破布林上轨", make_boll_signal(20, False)),
        "boll_dn": ("跌破布林下轨", make_boll_signal(20, True)),
    }
    if signal not in tests:
        return {"error": f"未知信号 {signal}，可选: {list(tests)}"}
    name, fn = tests[signal]
    try:
        r = signal_backtest(sym, iv, name, fn)
        if not r:
            return {"error": f"{sym} {iv} 数据不足"}
        return r
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/rating")
def rating(limit: int = 20):
    """多因子综合评级（技术+资金+情绪+位置）"""
    try:
        return {"ratings": rate_top(limit)}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/backtest/strategy")
def backtest_strategy(symbol: str = "BTCUSDT", interval: str = "4h", signal: str = "rsi_os",
                      capital: float = 10000, pos_pct: float = 0.3):
    """完整策略回测（成本/复利/equity曲线/机构指标）"""
    sym = symbol.upper()
    if not sym.endswith("USDT"): sym += "USDT"
    iv = interval if interval in ("15m", "1h", "4h", "1d") else "4h"
    try:
        r = run_backtest(sym, iv, signal, capital, pos_pct)
        return r
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/correlation")
def correlation(top: int = 12):
    """币种相关性矩阵 + BTC 联动度"""
    try:
        return correlation_matrix(top=top)
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/opportunity")
def opportunity(limit: int = 10):
    """智能机会榜（评级+共振+AI观点）"""
    from analyst.opportunity import opportunity_board
    try:
        return {"board": opportunity_board(limit)}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/resonance/{symbol}")
def resonance_api(symbol: str):
    """多周期共振"""
    from analyst.resonance import resonance
    sym = symbol.upper()
    if not sym.endswith("USDT"): sym += "USDT"
    return resonance(sym)

@app.get("/api/regime")
def regime(symbol: str = "BTCUSDT"):
    from analyst.regime import detect_regime, market_regime_summary
    return {"single": detect_regime(symbol), "market": market_regime_summary()}

@app.get("/api/bayes/{symbol}")
def bayes_api(symbol: str):
    """贝叶斯信号融合"""
    from analyst.bayes import bayes_fusion
    sym = symbol.upper()
    if not sym.endswith("USDT"): sym += "USDT"
    return bayes_fusion(sym)

@app.get("/api/risk")
def risk_api(symbol: str = "BTCUSDT", direction: str = "bullish", confidence: int = 65):
    """智能风控（regime 自适应）"""
    from analyst.risk_engine import smart_risk
    sym = symbol.upper()
    if not sym.endswith("USDT"): sym += "USDT"
    return smart_risk(sym, direction, confidence)

@app.get("/api/anomalies")
def anomalies(interval: str = "15m"):
    from analyst.data_quality import scan_all_anomalies
    return {"anomalies": scan_all_anomalies(interval=interval)}

@app.get("/api/calibration")
def calibration():
    from analyst.calibration import calibration_points
    return calibration_points()

@app.get("/api/shadow")
def shadow():
    from analyst.shadow import shadow_account
    return shadow_account()

@app.get("/api/review/weekly")
def review_weekly(days: int = 7):
    from analyst.review import weekly_review
    return weekly_review(days)

@app.get("/api/decision-tree")
def decision_tree(symbol: str = "BTCUSDT"):
    from analyst.decision_tree import decision_tree as dt
    return dt(symbol)

@app.get("/api/sector-heat")
def sector_heat():
    from analyst.sector import sector_heat as sh
    return sh()

@app.get("/api/reports")
def reports(limit: int = 15):
    dbh = db.get_db()
    rows = dbh.execute("SELECT ts, symbol, market_state, report FROM analyses ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    dbh.close()
    return {"reports": [{"ts": r["ts"], "symbol": r["symbol"], "type": "standard",
                         "title": f"{r['symbol']} · {r['market_state']}",
                         "summary": (r["report"] or "")[:150]} for r in rows]}

@app.get("/api/report-image/{symbol}")
def report_image(symbol: str):
    """K线图图片（Pillow 绘制）"""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.report_image import draw_kline_chart
    sym = symbol.upper()
    if not sym.endswith("USDT"): sym += "USDT"
    data = draw_kline_chart(sym)
    if not data:
        return JSONResponse({"error": "数据不足"}, status_code=404)
    from fastapi.responses import Response
    return Response(content=data, media_type="image/png",
                    headers={"Cache-Control": "max-age=60"})

@app.get("/api/fgi")
def fgi():
    from collector import db as cdb
    dbh = cdb.get_db()
    try:
        row = dbh.execute("SELECT * FROM fgi_snap ORDER BY ts DESC LIMIT 1").fetchone()
    except Exception:
        row = None
    dbh.close()
    if not row:
        return {"error": "暂无 FGI 数据"}
    return {"value": row["value"], "label": row["label"], "ts": row["ts"]}

@app.get("/api/verdict")
def verdict(refresh: int = 0):
    if refresh:
        try:
            v = market_verdict()
            save_verdict(v)
            return v
        except Exception as e:
            return {"error": str(e)}
    v = get_latest_verdict()
    if not v:
        try:
            v = market_verdict()
            save_verdict(v)
        except Exception as e:
            return {"error": str(e)}
    return v

@app.get("/api/futures")
def futures():
    """合约资金费率排行（Gate 免费源）"""
    from collector import db as cdb
    dbh = cdb.get_db()
    try:
        rows = dbh.execute("""SELECT f1.symbol, f1.rate, f1.ts FROM funding f1
            WHERE f1.ts=(SELECT MAX(ts) FROM funding f2 WHERE f2.symbol=f1.symbol)
            ORDER BY ABS(f1.rate) DESC LIMIT 15""").fetchall()
    except Exception:
        rows = []
    dbh.close()
    return [dict(r) for r in rows]

@app.get("/api/council")
def council(symbol: str = "BTCUSDT"):
    """八派合议（轻量，无 LLM，秒开）"""
    sym = symbol.upper()
    if not sym.endswith("USDT"): sym += "USDT"
    from collector import db as cdb
    from indicators import signals as se, ta
    from analyst import state_machine, schools
    raw = cdb.get_klines(sym, "4h", 150)
    if len(raw) < 80:
        return {"error": "数据不足"}
    k4h = [{"ts": r["ts"], "o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"], "v": r["vol"]} for r in raw]
    sig = se.analyze_symbol(k4h)
    closes = [k["c"] for k in k4h]
    highs = [k["h"] for k in k4h]
    lows = [k["l"] for k in k4h]
    state, reason, _ = state_machine.classify(k4h, ta.rsi(closes), ta.adx(highs, lows, closes), ta.atr(highs, lows, closes))
    verdicts, direction, score, agreement = schools.convene(sig, k4h, state)
    return {"symbol": sym, "market_state": state, "state_reason": reason,
            "direction": direction, "agreement": agreement,
            "schools": [v.to_dict() for v in verdicts]}

@app.get("/api/plan")
def plan(symbol: str = "BTCUSDT"):
    """作战计划（轻量，无 LLM）"""
    sym = symbol.upper()
    if not sym.endswith("USDT"): sym += "USDT"
    from collector import db as cdb
    from indicators import signals as se
    from analyst import risk
    raw = cdb.get_klines(sym, "4h", 150)
    if len(raw) < 80:
        return {"error": "数据不足"}
    k4h = [{"ts": r["ts"], "o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"], "v": r["vol"]} for r in raw]
    sig = se.analyze_symbol(k4h)
    plan = risk.build_plan(sym, k4h, sig.get("direction", "neutral"), sig.get("confidence", 50))
    return {"symbol": sym, "direction": sig.get("direction"), "confidence": sig.get("confidence"),
            "signal_count": len(sig.get("signals", [])), "plan": plan}

@app.get("/api/facilities")
def facilities():
    """全部建筑缩略数据（一次请求，供建筑外部面板轮询）"""
    from collector import db as cdb
    out = {}
    try:
        dbh = cdb.get_db()
        btc = dbh.execute("SELECT * FROM ticker_snap WHERE symbol='BTCUSDT' ORDER BY ts DESC LIMIT 1").fetchone()
        dbh.close()
        if btc:
            out["data"] = {"price": btc["price"], "chg": btc["chg24h"],
                            "high": btc["high24h"], "low": btc["low24h"]}
    except Exception:
        pass
    try:
        from analyst.sentiment import market_sentiment
        s = market_sentiment()
        out["obs"] = {"score": s["score"], "label": s["label"]}
    except Exception:
        pass
    try:
        from analyst.council_quick import quick_council, quick_plan
        c = quick_council("BTCUSDT")
        out["council"] = {"direction": c["direction"], "agreement": c["agreement"]}
        p = quick_plan("BTCUSDT")
        out["war"] = {"direction": p.get("direction"), "confidence": p.get("confidence")}
    except Exception:
        pass
    try:
        from analyst.radar import scan_radar
        out["radar"] = {"count": len(scan_radar(limit=10))}
    except Exception:
        pass
    try:
        from analyst.record import stats
        out["hq"] = stats()
    except Exception:
        pass
    return out

@app.get("/api/analyses")
def analyses(limit: int = 10):
    dbh = db.get_db()
    rows = dbh.execute("SELECT ts, symbol, market_state, report FROM analyses ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    dbh.close()
    return [dict(r) for r in rows]

@app.get("/api/stats")
def stats():
    return rec_stats()

def rec_stats():
    dbh = db.get_db()
    rows = dbh.execute("SELECT * FROM predictions").fetchall()
    dbh.close()
    if not rows: return {"total": 0}
    wins = sum(1 for r in rows if r["verdict"] in ("hit_t1", "hit_t2"))
    losses = sum(1 for r in rows if r["verdict"] == "hit_stop")
    return {"total": len(rows), "wins": wins, "losses": losses,
            "win_rate": round(wins/len(rows)*100, 1) if rows else 0}

@app.websocket("/ws/stream")
async def stream(ws: WebSocket):
    """实时动作流（SSE 替代：WebSocket 推送采集/分析事件）"""
    await ws.accept()
    last_id = 0
    while True:
        dbh = db.get_db()
        rows = dbh.execute("SELECT id, task, symbol, ts, ok FROM collect_health WHERE id>? ORDER BY id DESC LIMIT 20", (last_id,)).fetchall()
        dbh.close()
        for r in reversed(rows):
            await ws.send_text(json.dumps({"type": "health", **dict(r)}, default=str))
            last_id = max(last_id, r["id"])
        await asyncio.sleep(5)

@app.get("/")
def index():
    resp = FileResponse(STATIC / "index.html")
    resp.headers["Cache-Control"] = "no-store"
    return resp

app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
