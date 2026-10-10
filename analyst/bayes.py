# ---------------------------------------------------------------------------
# analyst/bayes.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-03CB76BC
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""贝叶斯信号融合引擎：多信号作为独立证据 → 贝叶斯更新 → 后验方向概率
先验 = 历史胜率（校准后）；每个信号按历史胜率提供似然比
输出：P(bullish|evidence) 后验概率 + 证据强度 + 融合明细"""
import math
from collector import db
from indicators import ta
from analyst.resonance import tf_signal

# 信号历史胜率（来自 backtest，作为似然比的先验基础）
DEFAULT_HIT = {"bullish": 0.52, "bearish": 0.52}  # 保守默认

def _signal_likelihood(signal_name, direction, symbol, interval):
    """信号的历史胜率 → 似然比（校准过）"""
    dbh = db.get_db()
    try:
        row = dbh.execute("""SELECT win_rate, count FROM signal_stats
            WHERE signal=? AND symbol=? AND interval=?""",
            (signal_name, symbol, interval)).fetchone()
        dbh.close()
        if row and row["count"] >= 20:
            wr = row["win_rate"] / 100
            return max(0.1, min(0.9, wr))
    except Exception:
        pass
    try:
        dbh.close()
    except Exception:
        pass
    return DEFAULT_HIT[direction]

def bayes_fusion(symbol, interval="4h"):
    """贝叶斯融合：多维度证据 → P(看多) 后验"""
    raw = db.get_klines(symbol, interval, 150)
    if len(raw) < 60:
        return {"error": "数据不足"}
    klines = [{"o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"], "v": r["vol"]} for r in raw]
    closes = [k["c"] for k in klines]
    highs = [k["h"] for k in klines]
    lows = [k["l"] for k in klines]

    # 证据收集：每个证据 = (方向, 似然胜率, 权重)
    evidences = []
    # E1: 趋势排列
    e20, e50 = ta.ema(closes, 20), ta.ema(closes, 50)
    if e20 and e50:
        if closes[-1] > e20 > e50:
            evidences.append(("bullish", _signal_likelihood("ema_bull", "bullish", symbol, interval), 1.2))
        elif closes[-1] < e20 < e50:
            evidences.append(("bearish", _signal_likelihood("ema_bear", "bearish", symbol, interval), 1.2))
    # E2: RSI
    r = ta.rsi(closes)
    if r is not None:
        if r < 40:
            evidences.append(("bullish", _signal_likelihood("rsi_os", "bullish", symbol, interval), 1.0))
        elif r > 60:
            evidences.append(("bearish", _signal_likelihood("rsi_ob", "bearish", symbol, interval), 1.0))
    # E3: MACD
    macd_l, dea, hist = ta.macd(closes)
    if hist is not None:
        evidences.append(("bullish" if hist > 0 else "bearish",
                          _signal_likelihood("macd", "bullish" if hist > 0 else "bearish", symbol, interval), 0.9))
    # E4: 多周期共振
    try:
        from analyst.resonance import resonance
        res = resonance(symbol)
        if "error" not in res:
            if res["direction"] == "bullish":
                evidences.append(("bullish", min(0.85, 0.5 + res["resonance"] / 200), 1.5))
            elif res["direction"] == "bearish":
                evidences.append(("bearish", min(0.85, 0.5 + res["resonance"] / 200), 1.5))
    except Exception:
        pass
    # E5: 量价（量比+方向）
    vols = [k["v"] for k in klines]
    if len(vols) > 25:
        avg = sum(vols[-26:-1]) / 20
        vr = vols[-1] / avg if avg > 0 else 1
        if vr > 1.3:
            d = "bullish" if closes[-1] > closes[-2] else "bearish"
            evidences.append((d, 0.55, 0.8))

    if not evidences:
        return {"error": "无可用证据"}

    # 贝叶斯更新：P(up|E) ∝ P(up) × Π P(Ei|up)/P(Ei|down)
    # 简化：用胜率作为 P(E|up)，P(E|down) = 1 - P(E|up)
    prior_up = 0.5
    odds_up = prior_up / (1 - prior_up)
    log_odds = math.log(odds_up)
    detail = []
    for direction, hit_rate, weight in evidences:
        if direction == "bullish":
            lr = hit_rate / max(0.01, (1 - hit_rate))
            log_odds += math.log(lr) * weight
        else:
            lr = (1 - hit_rate) / max(0.01, hit_rate)
            log_odds += math.log(lr) * weight
        detail.append({"evidence": direction, "hit_rate": round(hit_rate, 3),
                       "weight": weight, "lr": round(lr, 3)})

    p_up = 1 / (1 + math.exp(-log_odds))
    p_up = max(0.01, min(0.99, p_up))
    direction = "bullish" if p_up >= 0.55 else ("bearish" if p_up <= 0.45 else "neutral")
    strength = abs(p_up - 0.5) * 2  # 0-1 证据强度

    return {
        "symbol": symbol, "interval": interval,
        "p_bullish": round(p_up * 100, 1),
        "direction": direction,
        "strength": round(strength * 100, 1),
        "evidences": detail,
        "prior": 0.5,
    }

def fusion_text(f):
    if not f or "error" in f:
        return ""
    emoji = "🟢" if f["direction"] == "bullish" else ("🔴" if f["direction"] == "bearish" else "⚪")
    return f"贝叶斯融合: {emoji} P(多)={f['p_bullish']}% 强度{f['strength']}% ({len(f['evidences'])}项证据)"

if __name__ == "__main__":
    import sys; sys.path.insert(0, ".")
    f = bayes_fusion("SOLUSDT")
    print(fusion_text(f))
    for e in f.get("evidences", []):
        print(" ", e)
