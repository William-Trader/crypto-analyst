# ---------------------------------------------------------------------------
# analyst/risk_engine.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-3D8C9C04
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""智能风控引擎：regime 自适应仓位 + 动态止损 + Chandelier 追踪止损 + 敞口仪表"""
from indicators import ta
from analyst.regime import detect_regime, REGIME_PARAMS

def smart_risk(symbol="BTCUSDT", direction="neutral", confidence=50, pos_pct=None):
    """输出：建议仓位（regime 自适应）+ 止损（ATR×regime系数）+ 追踪止损 + 风险敞口"""
    raw_klines = None
    from collector import db
    raw = db.get_klines(symbol, "4h", 200)
    if len(raw) < 60:
        return {"error": "数据不足"}
    klines = [{"o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"], "v": r["vol"]} for r in raw]
    closes = [k["c"] for k in klines]
    highs = [k["h"] for k in klines]
    lows = [k["l"] for k in klines]
    last = closes[-1]

    # 1. regime 检测（BTC 市场级）
    rg = detect_regime(symbol)
    rp = rg.get("params", REGIME_PARAMS["range"])

    # 2. ATR（动态）
    atr = ta.atr(highs, lows, closes, 14) or last * 0.02

    # 3. 动态止损：ATR × regime 系数
    sl_dist = atr * rp["sl_mult"]
    if direction == "bullish":
        stop = last - sl_dist
        stop_pct = sl_dist / last * 100
    elif direction == "bearish":
        stop = last + sl_dist
        stop_pct = sl_dist / last * 100
    else:
        stop, stop_pct = None, None

    # 4. Chandelier 追踪止损（20 根最高/最低 - ATR×3）
    lookback = 22
    if direction == "bullish":
        hh = max(k["h"] for k in klines[-lookback:])
        chandelier = hh - atr * 3
        chandelier_pct = (last - chandelier) / last * 100
    elif direction == "bearish":
        ll = min(k["l"] for k in klines[-lookback:])
        chandelier = ll + atr * 3
        chandelier_pct = (chandelier - last) / last * 100
    else:
        chandelier, chandelier_pct = None, None

    # 5. 动态仓位：基础(由调用方给或默认20%) × regime 缩放 × 置信度修正
    base = pos_pct or 20.0
    pos = base * rp["pos_scale"] * (0.7 + confidence / 200)
    pos = max(1.0, min(40.0, pos))

    # 6. 风险敞口仪表
    exposure = {
        "stop_pct": round(stop_pct, 2) if stop_pct else 0,
        "risk_per_trade": round(pos * (stop_pct or 0) / 100, 2),  # 单笔风险占资金%
        "position": round(pos, 1),
        "regime_scale": rp["pos_scale"],
    }

    return {
        "symbol": symbol, "direction": direction, "confidence": confidence,
        "regime": rg["regime"], "regime_label": rg["label"],
        "atr": round(atr, 4), "atr_pct": round(atr / last * 100, 2),
        "stop": round(stop, 4) if stop else None, "stop_pct": round(stop_pct, 2) if stop_pct else None,
        "chandelier": round(chandelier, 4) if chandelier else None,
        "chandelier_pct": round(chandelier_pct, 2) if chandelier_pct else None,
        "position_pct": round(pos, 1),
        "exposure": exposure,
        "note": f"{rg['emoji']} {rg['label']}：止损系数 {rp['sl_mult']}×ATR，仓位缩放 {rp['pos_scale']}",
    }

if __name__ == "__main__":
    import sys; sys.path.insert(0, ".")
    r = smart_risk("BTCUSDT", "bullish", 65)
    print(f"Regime: {r['regime_label']} | 止损 {r['stop']} ({r['stop_pct']}%) | 追踪 {r['chandelier']} | 仓位 {r['position_pct']}%")
    print(r["note"])
