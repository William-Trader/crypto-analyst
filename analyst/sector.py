# ---------------------------------------------------------------------------
# analyst/sector.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-2C98F587
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""板块热度：按板块标签聚合币种涨幅 → 热度榜"""
import time
from collector import db

# 板块映射（base 币 → 板块），常见标的覆盖
SECTORS = {
    "L1": {"BTC", "ETH", "SOL", "BNB", "ADA", "AVAX", "DOT", "ATOM", "NEAR", "APT", "SUI", "TIA", "SEI", "INJ", "ARB", "OP", "STRK", "ZEC", "DASH", "ETC", "LTC", "BCH", "XMR", "ALGO", "HBAR", "TON", "TRX", "FIL", "ICP"},
    "DeFi": {"UNI", "AAVE", "LINK", "MKR", "COMP", "CRV", "SUSHI", "LDO", "RUNE", "SNX", "1INCH", "DYDX", "PENDLE", "JUP", "CAKE", "PancakeSwap"},
    "Meme": {"DOGE", "SHIB", "PEPE", "WIF", "BONK", "FLOKI", "MEME", "POPCAT", "MOG", "TURBO", "BRETT", "DOGS", "NOT"},
    "AI": {"FET", "RNDR", "AGIX", "TAO", "GRT", "OCEAN", "AKT", "NMR", "LTP", "AI16Z", "ARC", "VIRTUAL"},
    "RWA": {"ONDO", "POLYX", "TOKEN", "OM", "CFG", "RIO", "MPL"},
    "Game": {"GALA", "AXS", "SAND", "MANA", "ENJ", "IMX", "MAGIC", "PIXEL", "PRIME", "BIGTIME"},
    "Storage": {"FIL", "AR", "STORJ", "BLZ", "SC"},
    "Privacy": {"XMR", "ZEC", "DASH", "SCRT", "ROSE"},
    "Payments": {"XRP", "XLM", "TRX", "ALGO", "ADA"},
    "Infra": {"LINK", "GRT", "API3", "BAND", "PYTH", "POKT"},
    "CEX": {"BNB", "OKB", "GT", "KCS", "CRO"},
    "Stable": {"USDC", "FDUSD", "DAI", "TUSD", "RLUSD"},
}

def sector_heat():
    """板块热度：板块内币种 24h 涨幅均值"""
    dbh = db.get_db()
    rows = dbh.execute("""SELECT symbol, chg24h FROM ticker_snap t1
        WHERE ts=(SELECT MAX(ts) FROM ticker_snap t2 WHERE t2.symbol=t1.symbol)""").fetchall()
    dbh.close()
    if not rows:
        return {"sectors": []}
    chg = {r["symbol"].replace("USDT", ""): r["chg24h"] for r in rows}
    out = []
    for sector, bases in SECTORS.items():
        vals = [chg[b] for b in bases if b in chg]
        if len(vals) < 2:
            continue
        heat = round(sum(vals) / len(vals), 2)
        leader = max(bases, key=lambda b: chg.get(b, -999), default=None)
        out.append({"sector": sector, "heat": heat, "count": len(vals),
                    "leader": leader if leader and leader in chg else "-"})
    out.sort(key=lambda x: -x["heat"])
    return {"sectors": out[:12], "ts": int(time.time() * 1000)}

if __name__ == "__main__":
    import sys; sys.path.insert(0, ".")
    print(sector_heat())
