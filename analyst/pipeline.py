# ---------------------------------------------------------------------------
# analyst/pipeline.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-42735010
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""分析流水线 v2：多时间框架 + 形态注入 + 历史背书 + 作战计划 + 预测入库"""
import time
import json
from pathlib import Path
from collector import db
from indicators import signals as sig_engine, ta
from indicators.patterns import detect_patterns, recent_swings
from indicators.backtest import backtest_all
from analyst import state_machine, schools, llm, risk, record
from analyst.regime import detect_regime
from analyst.bayes import bayes_fusion, fusion_text

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"

def load_distilled_rules():
    out = {}
    if not RULES_DIR.exists(): return out
    for f in RULES_DIR.glob("*.json"):
        try:
            out[f.stem] = json.loads(f.read_text())
        except Exception:
            pass
    return out

def rules_reference(rules):
    if not rules: return ""
    parts = ["【交易大师蒸馏规则参考】"]
    for school, r in rules.items():
        pr = r.get("core_principles", [])[:2]
        sigs = r.get("signals", [])[:2]
        lines = [f"- {school}: " + "; ".join(pr)]
        if sigs:
            lines.append(f"  ·信号: " + "; ".join(f"{s.get('name')}({s.get('condition','')[:36]}→{s.get('action','')[:18]})" for s in sigs))
        parts.append("\n".join(lines))
    return "\n".join(parts)[:3200]

def get_market_snapshot(symbol):
    k15 = db.get_klines(symbol, "15m", 200)
    k1h = db.get_klines(symbol, "1h", 200)
    k4h = db.get_klines(symbol, "4h", 150)
    if not k15 or not k1h or not k4h:
        return None
    def fmt(rows):
        return [{"ts": r["ts"], "o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"], "v": r["vol"]} for r in rows]
    snap = {"15m": fmt(k15), "1h": fmt(k1h), "4h": fmt(k4h)}
    dbh = db.get_db()
    t = dbh.execute("SELECT * FROM ticker_snap WHERE symbol=? ORDER BY ts DESC LIMIT 1", (symbol,)).fetchone()
    if t: snap["ticker"] = dict(t)
    dbh.close()
    return snap

def timeframe_view(snap):
    """多时间框架：4h 趋势 / 1h 结构 / 15m 时机"""
    out = {}
    for iv in ("4h", "1h", "15m"):
        k = snap[iv]
        closes = [x["c"] for x in k]
        e20, e50 = ta.ema(closes, 20), ta.ema(closes, 50)
        r = ta.rsi(closes, 14)
        trend = "多头排列" if (e20 and e50 and closes[-1] > e20 > e50) else \
                ("空头排列" if (e20 and e50 and closes[-1] < e20 < e50) else "纠缠")
        out[iv] = {
            "trend": trend, "rsi": round(r, 1) if r else None,
            "ema20": round(e20, 2) if e20 else None, "ema50": round(e50, 2) if e50 else None,
            "last": closes[-1],
        }
    return out

def full_analysis(symbol, use_llm=True):
    snap = get_market_snapshot(symbol)
    if not snap:
        return {"error": f"{symbol} 数据不足，请先运行采集器"}

    k4h, k1h, k15 = snap["4h"], snap["1h"], snap["15m"]
    closes = [k["c"] for k in k4h]
    highs = [k["h"] for k in k4h]
    lows = [k["l"] for k in k4h]
    vols = [k["v"] for k in k4h]

    # 指标 + 形态 + 摆动点
    sig = sig_engine.analyze_symbol(k4h)
    if "error" in sig: return sig
    sig["patterns"] = detect_patterns(k4h)
    sig["swings"] = recent_swings(k4h)
    sig["vpvr"] = ta.vpvr(closes, vols)
    sig["tf"] = timeframe_view(snap)

    # 状态机（4h）
    rsi_v = ta.rsi(closes)
    adx_v = ta.adx(highs, lows, closes)
    atr_v = ta.atr(highs, lows, closes)
    atr_pct = (atr_v / closes[-1] * 100) if atr_v else None
    state, reason, params = state_machine.classify(k4h, rsi_v, adx_v, atr_pct)

    # 史诗级升级：regime 自适应 + 贝叶斯融合
    rg = None
    fusion = None
    try:
        rg = detect_regime(symbol)
    except Exception:
        pass
    try:
        fusion = bayes_fusion(symbol)
    except Exception:
        pass
    if rg:
        extra_rg = f"【市场Regime】{rg['emoji']} {rg['label']}（ADX {rg['score'].get('adx')} · 波动率{rg['score'].get('vol_pct')}%）"
        if rg.get("changed"):
            extra_rg += f" ⚠️ 状态转换: {rg.get('prev', '?')} → {rg['regime']}"
    else:
        extra_rg = None
    if fusion and "error" not in fusion:
        extra_fs = fusion_text(fusion) + "（" + "; ".join(f"{e['evidence']}:{e['hit_rate']}" for e in fusion.get("evidences", [])[:4]) + "）"
    else:
        extra_fs = None

    # 八派合议
    verdicts, direction, score, agreement = schools.convene(sig, k4h, state)

    # 历史胜率背书（4h 常用信号）
    backtests = backtest_all(symbol, "4h")
    bt_text = ""
    if backtests:
        lines = ["【信号历史胜率背书】（过去1年 4h 级别，未来5根）"]
        for b in backtests[:5]:
            lines.append(f"- {b['signal']}: 出现{b['count']}次, 触达+2%概率{b['win_rate']}%, "
                         f"触达-2%概率{b['loss_rate']}%, 平均最高涨{b['avg_max_up']}%")
        bt_text = "\n".join(lines)

    # 周复盘纠偏
    review = record.weekly_review()
    review_text = ""
    if review:
        review_text = "【本周复盘】" + "；".join(review["issues"])

    # 蒸馏规则
    distilled = load_distilled_rules()
    ref_text = rules_reference(distilled)

    # 形态文本
    pat_text = ""
    if sig.get("patterns"):
        pat_text = "【K线形态】" + "、".join(f"{p[0]}({p[1]})" for p in sig["patterns"][:4])
    # 关键位
    sw = sig.get("swings", {})
    lvl_text = f"【关键位】区间高 {sw.get('high', 0):.2f} / 低 {sw.get('low', 0):.2f}"
    vp = sig.get("vpvr", {})
    if vp.get("poc"):
        lvl_text += f" / 筹码峰 {vp['poc']:.2f}"

    # 组装 extra
    extra_parts = [extra_rg if extra_rg else None, extra_fs if extra_fs else None,
                   bt_text, review_text, pat_text, lvl_text, ref_text]
    extra = "\n\n".join(x for x in extra_parts if x)

    # 作战计划（确定性规则）
    plan = risk.build_plan(symbol, k4h, direction, sig.get("confidence", 50))
    plan_text = risk.plan_to_text(plan) if plan else ""
    if plan_text:
        extra = (extra + "\n\n" if extra else "") + plan_text

    result = {
        "symbol": symbol, "ts": int(time.time()), "market_state": state, "state_reason": reason,
        "signal": {k: sig[k] for k in ("last", "signals", "direction", "score", "confidence", "bull", "bear")},
        "direction": direction, "agreement": agreement, "schools": [v.to_dict() for v in verdicts],
        "tf": sig["tf"], "plan": plan, "backtests": backtests[:5] if backtests else [],
        "regime": rg, "fusion": fusion,
        "extra": extra,
    }

    if use_llm:
        try:
            result["report"] = llm.analyze(symbol, state, reason, sig, verdicts, direction, agreement, extra)
        except Exception as e:
            result["report"] = f"[LLM 调用失败: {e}]\n\n（纯技术面）方向: {direction} 一致性: {agreement}%\n{plan_text}"
    else:
        result["report"] = f"（非 LLM 模式）方向: {direction} 一致性: {agreement}%\n{plan_text}"

    # 预测入库（自动记录，用于战绩/复盘）
    try:
        record.save_from_plan(plan, notes=f"state={state}, agreement={agreement}%")
    except Exception:
        pass

    dbh = db.get_db()
    dbh.execute("INSERT INTO analyses (ts,symbol,market_state,report,full) VALUES (?,?,?,?,?)",
                (result["ts"], symbol, state, result["report"], json.dumps(result, ensure_ascii=False, default=str)))
    dbh.commit(); dbh.close()
    return result

if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    llm_on = "--no-llm" not in sys.argv
    r = full_analysis(sym, use_llm=llm_on)
    if "error" in r:
        print(r["error"])
    else:
        print(f"\n=== {sym} | 状态: {r['market_state']} ({r['state_reason']}) ===")
        print(f"TF: {r.get('tf')}")
        print(f"合议: {r['direction']} 一致性{r['agreement']}%")
        for s in r["schools"]:
            print(f"  {s['school']}: {s['direction']} {s['confidence']}% - {s['note']}")
        if r.get("plan"):
            print("\n" + risk.plan_to_text(r["plan"]))
        if r.get("backtests"):
            print("\n背书:")
            for b in r["backtests"]:
                print(f"  {b['signal']}: {b['count']}次 胜{b['win_rate']}% 败{b['loss_rate']}%")
        print("\n" + r["report"][:1500])
