# ---------------------------------------------------------------------------
# analyst/review.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-145A7BE8
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""周复盘引擎：胜率分解 + 最佳最差 + 偏差检测 + 改进措施"""
import time, json
from collector import db

def weekly_review(days=7):
    dbh = db.get_db()
    rows = dbh.execute("""SELECT * FROM predictions WHERE ts>?
        AND verdict IN ('hit_t1','hit_t2','hit_stop')""",
        (int(time.time()) - days * 86400,)).fetchall()
    dbh.close()
    total = len(rows)
    if total < 3:
        return {"period": f"{days}d", "total": total, "rate": None,
                "note": "样本不足，继续积累预测记录"}

    def is_win(r):
        return r["verdict"] in ("hit_t1", "hit_t2")

    wins = [r for r in rows if is_win(r)]
    losses = [r for r in rows if not is_win(r)]
    rate = round(len(wins) / total * 100, 1)

    # 按方向分解
    bull = [r for r in rows if r["direction"] == "bullish"]
    bear = [r for r in rows if r["direction"] == "bearish"]
    def dir_rate(rs):
        if len(rs) < 3:
            return None
        return round(sum(1 for r in rs if is_win(r)) / len(rs) * 100, 1)
    br, rr = dir_rate(bull), dir_rate(bear)

    # 最佳/最差（按盈亏幅度）
    def pnl(r):
        entry = r["entry"] or 0
        if entry <= 0:
            return 0
        if r["verdict"] == "hit_stop":
            exit_p = r["stop"] or entry
        elif r["verdict"] == "hit_t2":
            exit_p = r["target2"] or entry
        elif r["verdict"] == "hit_t1":
            exit_p = r["target1"] or entry
        else:
            exit_p = entry
        d = 1 if r["direction"] == "bullish" else -1
        return (exit_p - entry) / entry * d * 100

    ranked = sorted(rows, key=pnl, reverse=True)
    best = [{"symbol": r["symbol"].replace("USDT", ""), "ret": round(pnl(r), 2)} for r in ranked[:3]]
    worst = [{"symbol": r["symbol"].replace("USDT", ""), "ret": round(pnl(r), 2)} for r in ranked[-3:][::-1]]

    # 偏差检测
    bias = []
    if br is not None and br < 45 and len(bull) >= 3:
        bias.append(f"看多命中率仅 {br}%（{len(bull)} 次）——存在乐观偏差，追多需谨慎")
    if rr is not None and rr < 45 and len(bear) >= 3:
        bias.append(f"看空命中率仅 {rr}%（{len(bear)} 次）——存在悲观偏差，追空需谨慎")
    if br is not None and rr is not None and abs(br - rr) > 25:
        bias.append(f"多空命中率差异大（多 {br}% vs 空 {rr}%）——方向偏好明显，注意一致性风险")

    # 改进措施
    improvements = []
    for b in bias:
        if "乐观偏差" in b:
            improvements.append("震荡市下调看多信号权重，追多前要求共振 ≥60 确认")
        elif "悲观偏差" in b:
            improvements.append("强趋势市避免逆势做空，做空要求跌破关键结构")
    if not improvements:
        improvements.append("维持当前策略，继续积累样本以细化分环境统计")

    return {
        "period": f"{days}d", "total": total, "rate": rate,
        "bull_rate": br, "bear_rate": rr,
        "best": best, "worst": worst, "bias": bias, "improvements": improvements,
        "note": f"样本 {total} · 命中 {len(wins)}",
    }

if __name__ == "__main__":
    import sys; sys.path.insert(0, ".")
    print(json.dumps(weekly_review(), ensure_ascii=False, indent=1))
