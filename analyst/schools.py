# ---------------------------------------------------------------------------
# analyst/schools.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-AEC319D9
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""八大流派合议庭：每派基于同一数据独立判断（确定性规则，零 LLM 成本）

蒸馏出的 rules/*.json 会增强各派规则；当前内置各派核心规则的可执行版本。
"""
import json
from pathlib import Path
from indicators import ta

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"

class SchoolVerdict:
    def __init__(self, school, direction, confidence, note):
        self.school = school
        self.direction = direction      # bullish / bearish / neutral
        self.confidence = confidence    # 0-100
        self.note = note

    def to_dict(self):
        return {"school": self.school, "direction": self.direction,
                "confidence": self.confidence, "note": self.note}

# ---------- 各派规则（内置版，蒸馏后增强） ----------

def school_wyckoff(sig, klines):
    """威科夫：量价关系 → 吸筹/派发阶段"""
    closes = [k["c"] for k in klines]
    vols = [k["v"] for k in klines]
    n = len(klines)
    if n < 60: return SchoolVerdict("wyckoff", "neutral", 40, "数据不足")
    hi = max(k["h"] for k in klines[-60:]); lo = min(k["l"] for k in klines[-60:])
    pos = (closes[-1] - lo) / (hi - lo) if hi > lo else 0.5
    vol_trend = sum(vols[-10:]) / sum(vols[-30:]) if sum(vols[-30:]) else 1
    price_trend = closes[-1] - closes[-30]

    if pos < 0.35 and vol_trend < 0.9 and price_trend > 0:
        return SchoolVerdict("wyckoff", "bullish", 70, "低位缩量+价格企稳（吸筹C阶段候选）")
    if pos < 0.35 and vol_trend > 1.3 and price_trend < 0:
        return SchoolVerdict("wyckoff", "bearish", 65, "低位放量下跌（下探/派发延续）")
    if pos > 0.65 and vol_trend < 0.9 and price_trend < 0:
        return SchoolVerdict("wyckoff", "bearish", 70, "高位缩量滞涨（派发候选）")
    if pos > 0.65 and vol_trend > 1.3 and price_trend > 0:
        return SchoolVerdict("wyckoff", "bullish", 60, "高位放量突破（需求跟进）")
    return SchoolVerdict("wyckoff", "neutral", 45, f"位置{pos:.0%}量能{vol_trend:.1f}x")

def school_fib(sig, klines):
    """斐波那契：回撤位支撑/阻力"""
    closes = [k["c"] for k in klines]
    n = len(klines)
    if n < 30: return SchoolVerdict("fib", "neutral", 40, "")
    swing_hi = max(k["h"] for k in klines[-60:])
    swing_lo = min(k["l"] for k in klines[-60:])
    levels = ta.fib_levels(swing_lo, swing_hi)
    last = closes[-1]
    # 最近回撤方向：取 swing_hi 为顶时看 0.382/0.5/0.618
    for lv in (0.618, 0.5, 0.382):
        price = levels[f"fib_{lv}"]
        dist = abs(last - price) / price
        if dist < 0.005:
            above = last > price
            d = "bullish" if above else "bearish"
            return SchoolVerdict("fib", d, 62, f"回撤{lv}位({price:.0f})附近")
    return SchoolVerdict("fib", "neutral", 45, f"远离关键回撤位")

def school_chan(sig, klines):
    """缠论简化：最近中枢 + 背驰粗判"""
    closes = [k["c"] for k in klines]
    n = len(klines)
    if n < 60: return SchoolVerdict("chan", "neutral", 40, "")
    seg = closes[-60:]
    # 简化：三根摆动高低点成中枢
    hi1 = max(seg[10:20]); lo1 = min(seg[10:20])
    hi2 = max(seg[30:40]); lo2 = min(seg[30:40])
    center_hi = min(hi1, hi2); center_lo = max(lo1, lo2)
    if center_hi <= center_lo: return SchoolVerdict("chan", "neutral", 40, "中枢未成型")
    last = closes[-1]
    # 跌破中枢后拉回 = 中枢支撑；站上中枢 = 突破
    if last > center_hi:
        # 简单背驰：价格新高但 RSI 更低
        rsi_now = ta.rsi(closes[-40:])
        rsi_prev = ta.rsi(closes[-80:-40])
        if rsi_now is not None and rsi_prev is not None and rsi_now < rsi_prev - 5:
            return SchoolVerdict("chan", "bearish", 60, f"新高+RSI背驰(中枢{center_lo:.0f}-{center_hi:.0f})")
        return SchoolVerdict("chan", "bullish", 58, f"突破中枢上沿({center_hi:.0f})")
    if last < center_lo:
        return SchoolVerdict("chan", "bearish", 58, f"跌破中枢下沿({center_lo:.0f})")
    return SchoolVerdict("chan", "neutral", 50, f"中枢内震荡({center_lo:.0f}-{center_hi:.0f})")

def school_trend(sig, klines):
    """利弗莫尔/克罗：趋势跟踪——顺势而为"""
    closes = [k["c"] for k in klines]
    ema20 = ta.ema(closes, 20); ema50 = ta.ema(closes, 50)
    if ema20 is None or ema50 is None: return SchoolVerdict("trend", "neutral", 40, "")
    last = closes[-1]
    if last > ema20 > ema50:
        return SchoolVerdict("trend", "bullish", 72, "多头排列，顺势看多")
    if last < ema20 < ema50:
        return SchoolVerdict("trend", "bearish", 72, "空头排列，顺势看空")
    if last > ema50 and ema20 < ema50:
        return SchoolVerdict("trend", "neutral", 50, "回踩50日线（观察企稳）")
    return SchoolVerdict("trend", "neutral", 45, "均线纠缠（趋势派观望）")

def school_murphy(sig, klines):
    """约翰·墨菲：综合技术分析——趋势线+形态+量价确认"""
    closes = [k["c"] for k in klines]
    n = len(klines)
    if n < 40: return SchoolVerdict("murphy", "neutral", 40, "")
    sig_dir = sig.get("direction", "neutral")
    conf = sig.get("confidence", 0)
    # 墨菲强调"确认"：方向信号 + 量能确认
    vol_ratio = ta.volume_ratio([k["v"] for k in klines])
    if sig_dir == "bullish" and vol_ratio and vol_ratio > 1.2:
        return SchoolVerdict("murphy", "bullish", 65, f"多头信号+放量确认({vol_ratio:.1f}x)")
    if sig_dir == "bearish" and vol_ratio and vol_ratio > 1.2:
        return SchoolVerdict("murphy", "bearish", 65, f"空头信号+放量确认({vol_ratio:.1f}x)")
    if sig_dir == "bullish":
        return SchoolVerdict("murphy", "bullish", 45, "多头信号但缺量能确认")
    if sig_dir == "bearish":
        return SchoolVerdict("murphy", "bearish", 45, "空头信号但缺量能确认")
    return SchoolVerdict("murphy", "neutral", 40, "等待信号确认")

def school_ding(sig, klines):
    """丁圣元：趋势交易理念——大方向 + 顺势"""
    closes = [k["c"] for k in klines]
    n = len(closes)
    if n < 100: return SchoolVerdict("ding", "neutral", 40, "")
    ema100 = ta.ema(closes, 100)
    if ema100 is None: return SchoolVerdict("ding", "neutral", 40, "")
    last = closes[-1]
    d = "bullish" if last > ema100 else "bearish"
    return SchoolVerdict("ding", d, 55, f"{'站上' if d=='bullish' else '跌破'}100日线（大势{'多头' if d=='bullish' else '空头'}）")

def school_practical(sig, klines):
    """实战派（傅海棠等）：位置+盈亏比思维"""
    closes = [k["c"] for k in klines]
    n = len(klines)
    if n < 60: return SchoolVerdict("practical", "neutral", 40, "")
    hi = max(k["h"] for k in klines[-60:]); lo = min(k["l"] for k in klines[-60:])
    pos = (closes[-1] - lo) / (hi - lo) if hi > lo else 0.5
    if pos < 0.25:
        return SchoolVerdict("practical", "bullish", 60, "区间低位（盈亏比占优）")
    if pos > 0.75:
        return SchoolVerdict("practical", "bearish", 55, "区间高位（追高盈亏比差）")
    return SchoolVerdict("practical", "neutral", 45, "中部位置（等待）")

def school_quant(sig, klines):
    """量化派：多因子信号加权"""
    return SchoolVerdict("quant", sig.get("direction", "neutral"),
                         min(80, sig.get("confidence", 0)), f"多因子得分{sig.get('score', 0)}")

SCHOOLS = {
    "wyckoff": school_wyckoff, "fib": school_fib, "chan": school_chan,
    "trend": school_trend, "murphy": school_murphy, "ding": school_ding,
    "practical": school_practical, "quant": school_quant,
}

def load_extra_rules():
    """加载蒸馏出的增强规则（rules/*.json），存在则覆盖内置"""
    if not RULES_DIR.exists(): return {}
    out = {}
    for f in RULES_DIR.glob("*.json"):
        try:
            out[f.stem] = json.loads(f.read_text())
        except Exception:
            pass
    return out

def convene(sig, klines, market_state):
    """合议：全部流派独立判断 → 汇总"""
    verdicts = [fn(sig, klines) for fn in SCHOOLS.values()]
    # 状态机调整：震荡市里趋势派/丁派权重降低（蓝本：合议结果展示所有派，汇总时加权）
    weights = {s: 1.0 for s in SCHOOLS}
    if market_state in ("range", "accumulation", "distribution"):
        weights["trend"] = 0.5; weights["ding"] = 0.5
    bull = sum(w * v.confidence for v, w in zip(verdicts, weights.values()) if v.direction == "bullish")
    bear = sum(w * v.confidence for v, w in zip(verdicts, weights.values()) if v.direction == "bearish")
    total = bull + bear
    if total == 0: return verdicts, "neutral", 0, 0
    score = (bull - bear) / total
    direction = "bullish" if score > 0.15 else ("bearish" if score < -0.15 else "neutral")
    agreement = max(bull, bear) / total * 100  # 一致性
    return verdicts, direction, round(score, 2), int(agreement)
