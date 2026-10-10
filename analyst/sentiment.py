# ---------------------------------------------------------------------------
# analyst/sentiment.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-922CB80C
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""市场情绪引擎：涨跌分布/BTC动能/活跃度 → 情绪分数与标签（驱动比格情绪）"""
import time
from collector import db

def market_sentiment():
    """从 ticker_snap 聚合市场情绪，返回 0-100 分数 + 标签 + 明细"""
    dbh = db.get_db()
    now = int(time.time())
    # 最近一次快照
    rows = dbh.execute("""SELECT t1.* FROM ticker_snap t1
        WHERE t1.ts=(SELECT MAX(ts) FROM ticker_snap t2 WHERE t2.symbol=t1.symbol)""").fetchall()
    dbh.close()
    if len(rows) < 5:
        return {"score": 50, "label": "数据不足", "detail": {}}

    # 1. 涨跌分布分（0-40）：上涨占比映射
    up = sum(1 for r in rows if r["chg24h"] > 0)
    up_ratio = up / len(rows)
    breadth = up_ratio * 40

    # 2. BTC 动能分（0-30）：BTC 24h 涨跌幅映射（±5% 封顶）
    btc = next((r for r in rows if r["symbol"] == "BTCUSDT"), None)
    btc_score = 15
    if btc:
        chg = max(-5, min(5, btc["chg24h"]))
        btc_score = 15 + chg * 3  # -5%→0, 0→15, +5%→30

    # 3. 活跃度分（0-30）：平均涨幅强度 + 成交额
    avg_chg = sum(r["chg24h"] for r in rows) / len(rows)
    avg_chg_c = max(-3, min(3, avg_chg))
    activity = 15 + avg_chg_c * 5  # -3%→0, 0→15, +3%→30

    score = int(max(0, min(100, breadth + btc_score + activity)))

    # 标签
    if score < 20: label = "恐慌"
    elif score < 35: label = "谨慎"
    elif score < 55: label = "中性"
    elif score < 75: label = "乐观"
    else: label = "贪婪"

    return {
        "score": score, "label": label,
        "detail": {
            "up_ratio": round(up_ratio * 100, 1),
            "avg_chg": round(avg_chg, 2),
            "btc_chg": round(btc["chg24h"], 2) if btc else None,
            "breadth": round(breadth, 1),
            "btc_score": round(btc_score, 1),
            "activity": round(activity, 1),
            "total": len(rows),
        },
        "ts": int(time.time() * 1000),
    }

def beagle_mood(sentiment=None):
    """市场情绪 → 比格情绪状态（驱动动画）"""
    s = sentiment or market_sentiment()
    score = s["score"]
    if score < 20: return {"mood": "panic", "emoji": "😨", "text": "市场恐慌！比格缩成一团…"}
    if score < 35: return {"mood": "cautious", "emoji": "😟", "text": "市场谨慎，比格低头慢走"}
    if score < 55: return {"mood": "calm", "emoji": "😐", "text": "市场平稳，比格悠闲散步"}
    if score < 75: return {"mood": "happy", "emoji": "😊", "text": "市场乐观，比格摇尾巴"}
    return {"mood": "excited", "emoji": "🤩", "text": "市场贪婪！比格兴奋蹦跳"}

def macro_view():
    """宏观视图：BTC.D 主导度 / 板块热度 / 波动率"""
    dbh = db.get_db()
    rows = dbh.execute("""SELECT t1.* FROM ticker_snap t1
        WHERE t1.ts=(SELECT MAX(ts) FROM ticker_snap t2 WHERE t2.symbol=t1.symbol)""").fetchall()
    dbh.close()
    if not rows:
        return {}
    btc = next((r for r in rows if r["symbol"] == "BTCUSDT"), None)
    eth = next((r for r in rows if r["symbol"] == "ETHUSDT"), None)
    total_vol = sum(r["quote_vol24h"] or 0 for r in rows)
    # BTC.D 近似：BTC 成交额 / 总成交额
    btc_d = (btc["quote_vol24h"] / total_vol * 100) if (btc and total_vol) else None
    # ETH/BTC 比
    eth_btc = (eth["price"] / btc["price"]) if (btc and eth and btc["price"]) else None
    # 波动率：24h 振幅均值
    amps = [((r["high24h"] - r["low24h"]) / r["price"] * 100) for r in rows if r["high24h"] and r["price"]]
    vol = round(sum(amps) / len(amps), 2) if amps else None
    # 领涨/领跌
    srt = sorted(rows, key=lambda r: r["chg24h"], reverse=True)
    return {
        "btc_d": round(btc_d, 2) if btc_d else None,
        "eth_btc": round(eth_btc, 5) if eth_btc else None,
        "avg_volatility": vol,
        "leaders": [{"symbol": r["symbol"], "chg": round(r["chg24h"], 2)} for r in srt[:5]],
        "laggards": [{"symbol": r["symbol"], "chg": round(r["chg24h"], 2)} for r in srt[-5:]],
        "total_vol_24h": round(total_vol / 1e9, 2),
    }
