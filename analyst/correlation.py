# ---------------------------------------------------------------------------
# analyst/correlation.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-5F27DACE
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""相关性分析：深研池币种收益率相关性矩阵 + 板块联动"""
from collector import db
from collector.universe import deep_pool

def _returns(symbol, interval="4h", n=120):
    rows = db.get_klines(symbol, interval, n)
    if len(rows) < 60:
        return None
    closes = [r["close"] for r in rows]
    return [closes[i] / closes[i-1] - 1 for i in range(1, len(closes))]

def pearson(a, b):
    if len(a) != len(b) or len(a) < 20:
        return 0.0
    ma, mb = sum(a)/len(a), sum(b)/len(b)
    num = sum((x-ma)*(y-mb) for x, y in zip(a, b))
    da = sum((x-ma)**2 for x in a) ** 0.5
    db_ = sum((y-mb)**2 for y in b) ** 0.5
    return num / (da * db_) if da and db_ else 0.0

def correlation_matrix(symbols=None, interval="4h", top=12):
    pool = (symbols or deep_pool())[:top]
    rets = {}
    for s in pool:
        r = _returns(s, interval)
        if r: rets[s] = r
    syms = list(rets.keys())
    matrix = []
    for a in syms:
        row = {"symbol": a}
        for b in syms:
            row[b] = round(pearson(rets[a], rets[b]), 2)
        matrix.append(row)
    # 平均联动度（与大盘 BTC 的相关系数）
    if "BTCUSDT" in syms:
        bt = rets["BTCUSDT"]
        avg = {}
        for s in syms:
            avg[s] = round(pearson(rets[s], bt), 2)
    else:
        avg = {}
    return {"symbols": syms, "matrix": matrix, "btc_corr": avg}

if __name__ == "__main__":
    import sys; sys.path.insert(0, ".")
    r = correlation_matrix()
    print("symbols:", r["symbols"][:6])
    for row in r["matrix"][:4]:
        print(row["symbol"], {k: v for k, v in row.items() if k != "symbol" and k in r["symbols"][:5]})
    print("BTC corr:", r["btc_corr"])
