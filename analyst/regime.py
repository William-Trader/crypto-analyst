# ---------------------------------------------------------------------------
# analyst/regime.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-CBA0FF55
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""自适应市场 Regime 引擎：多指标聚类 → 市场状态 → 全局参数调节
regime 决定：信号阈值、仓位系数、止损系数、信号可信度
状态：trend(趋势) / range(震荡) / highvol(高波动) / lowvol(低波动) / crash(崩溃)"""
import time
from collector import db
from indicators import ta

# regime → 参数调节器（所有下游模块引用）
REGIME_PARAMS = {
    "trend":   {"signal_boost": 1.15, "pos_scale": 1.0, "sl_mult": 1.5, "label": "趋势市", "emoji": "📈"},
    "range":   {"signal_boost": 0.85, "pos_scale": 0.7, "sl_mult": 1.8, "label": "震荡市", "emoji": "📊"},
    "highvol": {"signal_boost": 0.90, "pos_scale": 0.6, "sl_mult": 2.2, "label": "高波动", "emoji": "🌊"},
    "lowvol":  {"signal_boost": 0.95, "pos_scale": 0.8, "sl_mult": 1.6, "label": "低波动", "emoji": "🍃"},
    "crash":   {"signal_boost": 0.70, "pos_scale": 0.4, "sl_mult": 2.5, "label": "崩溃期", "emoji": "⛈️"},
}

def detect_regime(symbol="BTCUSDT", interval="4h"):
    """多指标 regime 检测：ADX 趋势强度 + ATR 波动率百分位 + 动量 + 跌幅"""
    raw = db.get_klines(symbol, interval, 200)
    if len(raw) < 120:
        return {"regime": "range", "params": REGIME_PARAMS["range"], "score": {}, "label": "震荡市"}
    klines = [{"o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"], "v": r["vol"]} for r in raw]
    closes = [k["c"] for k in klines]
    highs = [k["h"] for k in klines]
    lows = [k["l"] for k in klines]

    # 1. 趋势强度 ADX（0-100）
    adx = ta.adx(highs, lows, closes) or 0

    # 2. 波动率百分位（ATR 在 60 日窗口中的位置）
    atrs = []
    for i in range(max(1, len(klines) - 60), len(klines)):
        k, pk = klines[i], klines[i-1]
        atrs.append(max(k["h"] - k["l"], abs(k["h"] - pk["c"]), abs(k["l"] - pk["c"])))
    cur_atr = atrs[-1]
    vol_pct = sum(1 for a in atrs if a <= cur_atr) / len(atrs) if atrs else 0.5

    # 3. 动量（20 根涨跌幅）
    mom20 = (closes[-1] / closes[-21] - 1) * 100 if len(closes) > 21 else 0

    # 4. 急跌检测（5 根跌幅）
    mom5 = (closes[-1] / closes[-6] - 1) * 100 if len(closes) > 6 else 0

    score = {"adx": round(adx, 1), "vol_pct": round(vol_pct * 100, 1),
             "mom20": round(mom20, 2), "mom5": round(mom5, 2)}

    # 决策树
    if mom5 < -8 or (mom20 < -15 and vol_pct > 0.8):
        regime = "crash"
    elif vol_pct > 0.8 and adx > 25:
        regime = "highvol"
    elif vol_pct < 0.3 and adx < 20:
        regime = "lowvol"
    elif adx >= 25:
        regime = "trend"
    else:
        regime = "range"

    # 状态转换检测（对比上次）
    prev = _last_regime(symbol)
    changed = prev != regime
    _save_regime(symbol, regime, score)

    return {
        "regime": regime, "params": REGIME_PARAMS[regime],
        "label": REGIME_PARAMS[regime]["label"], "emoji": REGIME_PARAMS[regime]["emoji"],
        "score": score, "changed": changed, "prev": prev,
    }

def _last_regime(symbol):
    dbh = db.get_db()
    try:
        row = dbh.execute("""SELECT regime FROM regime_snap WHERE symbol=?
            ORDER BY ts DESC LIMIT 1""", (symbol,)).fetchone()
        return row["regime"] if row else None
    except Exception:
        return None
    finally:
        dbh.close()

def _save_regime(symbol, regime, score):
    dbh = db.get_db()
    try:
        dbh.execute("CREATE TABLE IF NOT EXISTS regime_snap (symbol TEXT, ts INTEGER, regime TEXT, score TEXT)")
        dbh.execute("INSERT INTO regime_snap (symbol, ts, regime, score) VALUES (?,?,?,?)",
                    (symbol, int(time.time() * 1000), regime, str(score)))
        dbh.commit()
    except Exception:
        pass
    finally:
        dbh.close()

def market_regime_summary(symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT")):
    """市场级 regime 汇总：多数币状态 = 市场状态"""
    counts = {}
    for sym in symbols:
        try:
            r = detect_regime(sym)
            counts[r["regime"]] = counts.get(r["regime"], 0) + 1
        except Exception:
            continue
    if not counts:
        return None
    top = max(counts, key=counts.get)
    return {"regime": top, "params": REGIME_PARAMS[top], "distribution": counts,
            "label": REGIME_PARAMS[top]["label"], "emoji": REGIME_PARAMS[top]["emoji"]}
