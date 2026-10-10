# ---------------------------------------------------------------------------
# analyst/backtest_engine.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-5061D9FD
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""完整回测引擎（freqtrade 同口径：成本/复利/equity 曲线/Sharpe/Sortino/Calmar/MaxDD）
策略：信号入场 → ATR×1.5 止损 / T1=T+2ATR / T2=T+3.5ATR / 超时 N 根了结"""
import math
from collector import db
from indicators import ta

FEE_BPS = 8  # 双边成本 bps

def _annualized(mean_daily, stdev, days_scale=365):
    if stdev == 0:
        return 0.0
    return mean_daily / stdev * math.sqrt(days_scale)

def run_backtest(symbol, interval, entry_signal="rsi_os", capital=10000.0,
                 pos_pct=0.3, timeout_bars=24, t1_mult=2.0, t2_mult=3.5, sl_mult=1.5):
    """
    entry_signal: rsi_os | rsi_ob | boll_up | boll_dn | cross_up | cross_dn
    返回: {metrics, trades[], equity[]}
    """
    raw = db.get_klines(symbol, interval, 5000)
    klines = [{"ts": r["ts"], "o": r["open"], "h": r["high"], "l": r["low"],
               "c": r["close"], "v": r["vol"]} for r in raw]
    if len(klines) < 120:
        return {"error": "数据不足"}

    # 预计算信号序列
    closes = [k["c"] for k in klines]
    signal_at = [False] * len(klines)
    for i in range(60, len(klines)):
        sig = False
        if entry_signal == "rsi_os":
            r = ta.rsi(closes[max(0, i-30):i+1], 14)
            sig = r is not None and r < 30
        elif entry_signal == "rsi_ob":
            r = ta.rsi(closes[max(0, i-30):i+1], 14)
            sig = r is not None and r > 70
        elif entry_signal == "boll_up":
            up, mid, dn = ta.bollinger(closes[max(0, i-60):i+1], 20)
            sig = up is not None and klines[i]["c"] >= up
        elif entry_signal == "boll_dn":
            up, mid, dn = ta.bollinger(closes[max(0, i-60):i+1], 20)
            sig = dn is not None and klines[i]["c"] <= dn
        elif entry_signal in ("cross_up", "cross_dn"):
            e20a, e50a = ta.ema(closes[max(0,i-60):i], 20), ta.ema(closes[max(0,i-60):i], 50)
            e20b, e50b = ta.ema(closes[max(0,i-60):i+1], 20), ta.ema(closes[max(0,i-60):i+1], 50)
            if None not in (e20a, e50a, e20b, e50b):
                if entry_signal == "cross_up":
                    sig = e20a <= e50a and e20b > e50b
                else:
                    sig = e20a >= e50a and e20b < e50b
        signal_at[i] = sig

    # 模拟交易
    balance = capital
    trades, equity = [], []
    i = 0
    n = len(klines)
    while i < n - 1:
        equity.append({"ts": klines[i]["ts"], "balance": round(balance, 2)})
        if signal_at[i] and balance > 10:
            entry = klines[i]["c"]
            # 计算 ATR
            atr = ta.atr([k["h"] for k in klines[max(0,i-20):i+1]],
                         [k["l"] for k in klines[max(0,i-20):i+1]],
                         [k["c"] for k in klines[max(0,i-20):i+1]], 14)
            if not atr: atr = entry * 0.02
            long = entry_signal in ("rsi_os", "boll_dn", "cross_up")
            sl = entry - atr * sl_mult if long else entry + atr * sl_mult
            t1 = entry + atr * t1_mult if long else entry - atr * t1_mult
            t2 = entry + atr * t2_mult if long else entry - atr * t2_mult
            # 持仓扫描
            exit_i, exit_price, reason = None, entry, "timeout"
            for j in range(i + 1, min(i + timeout_bars + 1, n)):
                k = klines[j]
                if long:
                    if k["l"] <= sl: exit_i, exit_price, reason = j, sl, "stop"
                    elif k["h"] >= t2: exit_i, exit_price, reason = j, t2, "t2"
                    elif k["h"] >= t1: exit_i, exit_price, reason = j, t1, "t1"
                else:
                    if k["h"] >= sl: exit_i, exit_price, reason = j, sl, "stop"
                    elif k["l"] <= t2: exit_i, exit_price, reason = j, t2, "t2"
                    elif k["l"] <= t1: exit_i, exit_price, reason = j, t1, "t1"
                if exit_i is not None: break
            if exit_i is None:
                exit_i, exit_price, reason = min(i + timeout_bars, n - 1), klines[min(i + timeout_bars, n-1)]["c"], "timeout"
            # 结算（含成本 8bps 双边）
            gross = (exit_price - entry) / entry if long else (entry - exit_price) / entry
            net = gross - FEE_BPS / 10000 * 2
            notional = balance * pos_pct
            pnl = notional * net
            balance += pnl
            trades.append({
                "entry_ts": klines[i]["ts"], "exit_ts": klines[exit_i]["ts"],
                "entry": round(entry, 4), "exit": round(exit_price, 4),
                "ret_pct": round(net * 100, 3), "pnl": round(pnl, 2),
                "reason": reason, "bars": exit_i - i,
            })
            i = exit_i + 1
        else:
            i += 1
    equity.append({"ts": klines[-1]["ts"], "balance": round(balance, 2)})

    if not trades:
        return {"error": "无交易产生（信号太少或数据不足）", "metrics": {"trades": 0}}

    # ===== 机构级指标（freqtrade 口径） =====
    total_profit = balance - capital
    days = max(1, (klines[-1]["ts"] - klines[0]["ts"]) / 86400000)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t["pnl"] for t in losses)) / len(losses) if losses else 0
    profit_factor = (sum(t["pnl"] for t in wins) / abs(sum(t["pnl"] for t in losses))) if losses and sum(t["pnl"] for t in losses) else float('inf')
    expectancy = (win_rate / 100 * avg_win) - ((100 - win_rate) / 100 * avg_loss)

    # equity 序列 → 日收益 → Sharpe/Sortino
    daily = {}
    for e in equity:
        d = e["ts"] // 86400000
        daily[d] = e["balance"]
    ds = sorted(daily)
    daily_returns = []
    for a, b in zip(ds, ds[1:]):
        if daily[a] > 0:
            daily_returns.append(daily[b] / daily[a] - 1)
    mean_d = sum(daily_returns) / len(daily_returns) if daily_returns else 0
    stdev_d = (sum((r - mean_d) ** 2 for r in daily_returns) / len(daily_returns)) ** 0.5 if daily_returns else 0
    down = [r for r in daily_returns if r < 0]
    down_stdev = (sum(r ** 2 for r in down) / len(down)) ** 0.5 if down else 0
    sharpe = _annualized(mean_d, stdev_d) if stdev_d else 0
    sortino = _annualized(mean_d, down_stdev) if down_stdev else 0

    # Max Drawdown（balance 序列 peak-to-trough）
    peak, max_dd, dd_pct = equity[0]["balance"], 0.0, 0.0
    for e in equity:
        peak = max(peak, e["balance"])
        dd = peak - e["balance"]
        if dd > max_dd:
            max_dd = dd
            dd_pct = dd / peak * 100 if peak else 0

    cagr = ((balance / capital) ** (365 / days) - 1) * 100 if balance > 0 else 0
    calmar = cagr / dd_pct if dd_pct > 0 else 0

    return {
        "symbol": symbol, "interval": interval, "signal": entry_signal,
        "capital": capital, "pos_pct": pos_pct, "fee_bps": FEE_BPS,
        "metrics": {
            "trades": len(trades), "win_rate": round(win_rate, 1),
            "total_profit": round(total_profit, 2),
            "total_return_pct": round(total_profit / capital * 100, 2),
            "cagr_pct": round(cagr, 2), "sharpe": round(sharpe, 3),
            "sortino": round(sortino, 3), "calmar": round(calmar, 2),
            "max_drawdown": round(max_dd, 2), "max_drawdown_pct": round(dd_pct, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else None,
            "expectancy": round(expectancy, 2),
            "avg_win": round(avg_win, 2), "avg_loss": round(avg_loss, 2),
            "avg_bars": round(sum(t["bars"] for t in trades) / len(trades), 1),
            "days": round(days, 1),
        },
        "trades": trades[-50:],
        "equity": equity[::max(1, len(equity) // 200)],
    }
