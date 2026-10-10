# ---------------------------------------------------------------------------
# analyst/calibration.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-33362203
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""置信度校准：预测置信 vs 实际胜率 → 校准曲线 + 校准后概率"""
import time
from collector import db

BUCKETS = [(40, 50), (50, 60), (60, 70), (70, 80), (80, 95)]

def calibration_points():
    """校准点：按预测置信分箱，统计实际胜率"""
    dbh = db.get_db()
    rows = dbh.execute("""SELECT confidence, verdict FROM predictions
        WHERE verdict IN ('hit_t1','hit_t2','hit_stop') AND confidence IS NOT NULL""").fetchall()
    dbh.close()
    if not rows:
        return {"points": [], "note": "暂无已验证预测"}
    points = []
    for lo, hi in BUCKETS:
        group = [r for r in rows if lo <= (r["confidence"] or 0) < hi]
        if not group:
            continue
        wins = sum(1 for r in group if r["verdict"] in ("hit_t1", "hit_t2"))
        actual = round(wins / len(group) * 100, 1)
        points.append({
            "bucket": f"{lo}-{hi}%", "predicted": (lo + hi) / 2,
            "actual": actual, "samples": len(group),
        })
    if not points:
        return {"points": [], "note": "暂无已验证预测"}
    # 总体偏差
    total = len(rows)
    wins = sum(1 for r in rows if r["verdict"] in ("hit_t1", "hit_t2"))
    overall = round(wins / total * 100, 1)
    note = f"共 {total} 条已验证预测，总体胜率 {overall}%"
    return {"points": points, "note": note, "total": total, "overall_rate": overall}

def calibrated_confidence(confidence, fallback=None):
    """新预测的校准后概率（冷启动向全局收缩）"""
    data = calibration_points()
    if not data.get("points"):
        return confidence if fallback is None else fallback
    points = data["points"]
    target = confidence or 50
    # 找所在箱
    for p in points:
        lo, hi = map(int, p["bucket"].replace("%", "").split("-"))
        if lo <= target < hi:
            return p["actual"]
    # 超出范围：最近箱
    best = min(points, key=lambda p: abs(p["predicted"] - target))
    return best["actual"]

if __name__ == "__main__":
    import sys; sys.path.insert(0, ".")
    print(calibration_points())
