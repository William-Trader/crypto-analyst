# ---------------------------------------------------------------------------
# analyst/verdict.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-D5E3089F
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""每日 Verdict：综合 FGI + 市场情绪 + 状态机 + 八派 → 市场级判断（W1 级决策）"""
import time, json
from collector import db
from analyst.sentiment import market_sentiment
from analyst.council_quick import quick_council
from analyst.state_machine import classify
from indicators import ta

def market_verdict(symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT")):
    """市场级判断：多币状态聚合 + FGI + 情绪 → verdict"""
    # 各币状态机
    states = {}
    directions = []
    for sym in symbols:
        try:
            c = quick_council(sym)
            if "error" not in c:
                states[sym] = {"state": c["market_state"], "direction": c["direction"],
                               "agreement": c["agreement"]}
                directions.append(c["direction"])
        except Exception:
            continue

    senti = market_sentiment()
    fgi = None
    dbh = db.get_db()
    try:
        row = dbh.execute("SELECT * FROM fgi_snap ORDER BY ts DESC LIMIT 1").fetchone()
        if row:
            fgi = {"value": row["value"], "label": row["label"]}
    except Exception:
        pass
    dbh.close()

    # 方向投票
    bull = sum(1 for d in directions if d == "bullish")
    bear = sum(1 for d in directions if d == "bearish")
    total = len(directions) or 1
    # 得分体系（0-100，>55 看多，<45 看空）
    score = 50
    score += (bull - bear) / total * 30           # 方向投票 ±30
    score += (senti["score"] - 50) * 0.3          # 情绪 ±15
    if fgi:
        score += (fgi["value"] - 50) * 0.15       # FGI ±7.5
    score = max(0, min(100, score))

    if score >= 58:
        verdict, vcolor = "看多", "green"
    elif score <= 42:
        verdict, vcolor = "看空", "red"
    else:
        verdict, vcolor = "观望", "yellow"

    reasons = []
    if fgi:
        reasons.append(f"FGI {fgi['value']}（{fgi['label']}）")
    reasons.append(f"市场情绪 {senti['score']}（{senti['label']}，涨跌比 {senti['detail'].get('up_ratio', 0)}%）")
    for sym, st in states.items():
        reasons.append(f"{sym.replace('USDT','')}: {st['state']}/{st['direction']}")
    if bull > bear:
        reasons.append(f"多币合议偏多（{bull}多{bear}空）")
    elif bear > bull:
        reasons.append(f"多币合议偏空（{bull}多{bear}空）")

    return {
        "ts": int(time.time()), "date": time.strftime("%Y-%m-%d"),
        "verdict": verdict, "color": vcolor, "score": round(score, 1),
        "bull": bull, "bear": bear, "states": states,
        "fgi": fgi, "sentiment": senti["score"],
        "reasons": reasons,
        "history": _verdict_history(),
    }

def _verdict_history():
    """历史 verdict 准确率（对照 BTC 次日涨跌）+ 最新验证"""
    dbh = db.get_db()
    try:
        rows = dbh.execute("SELECT date, verdict_json FROM verdict_daily ORDER BY date DESC LIMIT 14").fetchall()
    except Exception:
        rows = []
    dbh.close()
    out = []
    for r in rows:
        try:
            v = json.loads(r["verdict_json"])
            item = {"date": v.get("date"), "verdict": v.get("verdict"), "score": v.get("score")}
            # 验证：BTC 收盘对比（用 1d K 线）
            try:
                k1 = db.get_klines("BTCUSDT", "1d", 20)
                for i in range(len(k1) - 1):
                    if time.strftime("%Y-%m-%d", time.gmtime(k1[i]["ts"] / 1000)) == item["date"]:
                        chg = (k1[i+1]["close"] - k1[i]["close"]) / k1[i]["close"] * 100
                        item["next_chg"] = round(chg, 2)
                        if v.get("verdict") == "看多":
                            item["correct"] = chg > 0.5
                        elif v.get("verdict") == "看空":
                            item["correct"] = chg < -0.5
                        else:
                            item["correct"] = abs(chg) <= 0.5
                        break
            except Exception:
                pass
            out.append(item)
        except Exception:
            continue
    return out

def verdict_track_record(history=None):
    """Verdict 历史准确率统计（比格认错/邀功依据）"""
    hist = history if history is not None else _verdict_history()
    verified = [h for h in hist if h.get("correct") is not None]
    if not verified:
        return {"verified": 0, "rate": None, "note": "暂无已验证记录"}
    correct = sum(1 for h in verified if h["correct"])
    return {"verified": len(verified), "rate": round(correct / len(verified) * 100, 1),
            "note": f"近{len(verified)}次判断正确{correct}次"}

def verdict_with_opinion():
    """Verdict + 比格观点（LLM 口吻，权威化）"""
    v = get_latest_verdict() or market_verdict()
    opinion = None
    try:
        from analyst.llm import llm_chat
        lines = [f"日期 {v['date']}，系统判定 {v['verdict']}（{v['score']}分）"]
        lines += ["- " + r for r in v.get("reasons", [])[:6]]
        opinion = llm_chat(
            "你是资深加密分析师。基于以下市场判断数据，用一段 80 字以内、像真人分析师晨会发言的话总结你的观点："
            "要有明确立场、给一个可执行建议（仓位/操作）、口吻自信专业。\n\n" + "\n".join(lines),
            temperature=0.6)
    except Exception:
        pass
    v["opinion"] = opinion
    return v

def save_verdict(v):
    dbh = db.get_db()
    try:
        dbh.execute("CREATE TABLE IF NOT EXISTS verdict_daily (date TEXT PRIMARY KEY, ts INTEGER, verdict_json TEXT)")
        dbh.execute("INSERT OR REPLACE INTO verdict_daily (date, ts, verdict_json) VALUES (?,?,?)",
                    (v["date"], v["ts"], json.dumps(v, ensure_ascii=False)))
        dbh.commit()
    finally:
        dbh.close()

def get_latest_verdict():
    dbh = db.get_db()
    try:
        row = dbh.execute("SELECT * FROM verdict_daily ORDER BY date DESC LIMIT 1").fetchone()
        if row:
            return json.loads(row["verdict_json"])
    except Exception:
        pass
    finally:
        dbh.close()
    return None

if __name__ == "__main__":
    import sys; sys.path.insert(0, ".")
    v = market_verdict()
    save_verdict(v)
    print(json.dumps(v, ensure_ascii=False, indent=1)[:800])
