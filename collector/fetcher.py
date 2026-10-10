# ---------------------------------------------------------------------------
# collector/fetcher.py - crypto-analyst key data logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-0BF9D712
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""定时采集器（断点续拉/重试/健康日志/补洞）"""
import time, sys
from collector.binance_client import incremental_klines, fetch_ticker24h, fetch_open_interest, fetch_funding
from collector import db
from config import SYMBOLS, INTERVALS
from analyst.monitor import check_and_store, daily_brief
from analyst.record import verify_pending
from collector.extra import run_extra_collect
from analyst.data_quality import scan_all_anomalies

IV_MS = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
# 各周期拉取起点：首次运行拉最近 N 根（够分析用）
IV_BACKFILL = {"15m": 4_000, "1h": 2_000, "4h": 1_000, "1d": 500}

def collect_klines(symbol, interval, backfill=False):
    t0 = time.time()
    try:
        last = db.max_ts(symbol, interval)
        if backfill or last == 0:
            # 首次/回填：从 now - N*interval 起拉
            start = int(time.time() * 1000) - IV_BACKFILL[interval] * IV_MS[interval]
            rows = incremental_klines(symbol, interval, start)
        else:
            rows = incremental_klines(symbol, interval, last + 1)
        db.upsert_klines(rows)
        db.log_health(f"klines_{interval}", symbol, True, (time.time()-t0)*1000)
        return len(rows)
    except Exception as e:
        db.log_health(f"klines_{interval}", symbol, False, (time.time()-t0)*1000)
        print(f"  [FAIL] {symbol} {interval}: {e}", flush=True)
        return 0

def collect_snaps():
    t0 = time.time()
    for sym in SYMBOLS:
        try:
            t = fetch_ticker24h(sym)
            db.insert_snaps("ticker_snap", [(sym, int(time.time()*1000), float(t["lastPrice"]),
                float(t["priceChangePercent"]), float(t["volume"]), float(t["quoteVolume"]),
                float(t["highPrice"]), float(t["lowPrice"]))])
        except Exception as e:
            db.log_health("snaps", sym, False, 0)
            print(f"  [FAIL] snaps {sym}: {e}", flush=True)
        time.sleep(0.1)
    db.log_health("snaps_all", "ALL", True, (time.time()-t0)*1000)

def collect_futures(symbols=None):
    """合约增强数据（OI/费率）：Binance fapi 被墙时跳过；配代理后可用
    备用源：OKX /api/v5/public/open-interest + funding-rate（需代理）"""
    for sym in (symbols or SYMBOLS):
        try:
            oi = fetch_open_interest(sym)
            db.insert_snaps("oi_snap", [(sym, int(time.time()*1000), float(oi["openInterestValue"]))])
        except Exception:
            pass  # 可选数据，失败不阻塞
        try:
            f = fetch_funding(sym, 2)
            if f:
                db.insert_snaps("funding", [(sym, f[-1]["fundingTime"], float(f[-1]["fundingRate"]), 0)])
        except Exception:
            pass
        time.sleep(0.1)

def verify_holes():
    """补洞：检查各表最新 K 线时间是否陈旧，陈旧则回补"""
    now = int(time.time() * 1000)
    for sym in SYMBOLS:
        for iv in INTERVALS:
            last = db.max_ts(sym, iv)
            if last == 0:
                collect_klines(sym, iv, backfill=True)
            elif now - last > IV_MS[iv] * 2.5:
                print(f"  [HOLE] {sym} {iv} last={last}, backfilling", flush=True)
                collect_klines(sym, iv, backfill=True)

def full_backfill():
    """全量回填（P0 初始化用）"""
    for sym in SYMBOLS:
        for iv in INTERVALS:
            collect_klines(sym, iv, backfill=True)
    collect_snaps()

def run_forever():
    db.init_db()
    print("collector starting...", flush=True)
    last_5m = last_15m = last_1h = 0
    while True:
        now = time.time()
        try:
            if now - last_5m >= 300:
                last_5m = now
                for sym in SYMBOLS:
                    collect_klines(sym, "15m")
                collect_snaps()
                try:
                    run_extra_collect()  # FGI + Gate 合约费率
                except Exception as e:
                    print(f"[extra err] {e}", flush=True)
                try:
                    anoms = scan_all_anomalies()
                    if anoms:
                        print(f"[ANOMALY] {len(anoms)} 条异常: {[(a['symbol'], a['type']) for a in anoms[:3]]}", flush=True)
                except Exception as e:
                    print(f"[anomaly err] {e}", flush=True)
                try:
                    v = verify_pending()
                    if v:
                        print(f"[VERIFY] {v} 条预测已验证", flush=True)
                except Exception as e:
                    print(f"[verify err] {e}", flush=True)
                try:
                    al = check_and_store()
                    if al:
                        print(f"[ALERT] {len(al)} 个异动: {[a['symbol'] for a in al]}", flush=True)
                except Exception as e:
                    print(f"[alert err] {e}", flush=True)
                # 每日 9:00/21:00 日报
                if time.localtime().tm_hour in (9, 21) and time.localtime().tm_min < 10:
                    try:
                        brief = daily_brief()
                        dbh = db.get_db()
                        dbh.execute("INSERT INTO analyses (ts,symbol,market_state,report,full) VALUES (?,?,?,?,?)",
                                    (int(time.time()), "BRIEF", "daily", brief, "{}"))
                        dbh.commit(); dbh.close()
                        print("[BRIEF] 日报已生成", flush=True)
                    except Exception as e:
                        print(f"[brief err] {e}", flush=True)
            if now - last_15m >= 900:
                last_15m = now
                for sym in SYMBOLS:
                    collect_klines(sym, "1h")
            if now - last_1h >= 3600:
                last_1h = now
                for sym in SYMBOLS:
                    collect_klines(sym, "4h"); collect_klines(sym, "1d")
                verify_holes()
                db.cleanup_old()
        except Exception as e:
            print(f"[loop error] {e}", flush=True)
        time.sleep(30)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        db.init_db()
        full_backfill()
        print("backfill done")
    else:
        run_forever()
