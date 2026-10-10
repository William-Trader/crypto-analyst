# ---------------------------------------------------------------------------
# scripts/report_image.py - crypto-analyst key automation logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-76D2BFB6
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""图片报告：Pillow 绘制 K线图+关键位 → PNG（QQ 图片推送/网页展示）"""
import io, os, sys
from datetime import datetime

def draw_kline_chart(symbol, interval="4h", n=60):
    """绘制 K 线 + EMA20/50 + 关键位标注 → PNG bytes"""
    from PIL import Image, ImageDraw, ImageFont
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from collector import db
    from indicators import ta
    from analyst.council_quick import quick_plan

    raw = db.get_klines(symbol, interval, n)
    if len(raw) < 30:
        return None
    klines = [{"ts": r["ts"], "o": r["open"], "h": r["high"], "l": r["low"], "c": r["close"]} for r in raw]

    W, H = 900, 480
    MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 70, 20, 50, 40
    img = Image.new("RGB", (W, H), (11, 14, 26))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
        font_b = ImageFont.truetype("/System/Library/Fonts/Helvetica-Bold.ttf", 16)
    except Exception:
        font = font_b = ImageFont.load_default()

    # 标题
    last = klines[-1]
    chg = (last["c"] - klines[-2]["c"]) / klines[-2]["c"] * 100
    d.text((MARGIN_L, 12), f"{symbol} {interval}  K线图", fill=(255, 255, 255), font=font_b)
    d.text((W - MARGIN_R - 160, 14), f"最新 {last['c']:.2f}  {chg:+.2f}%",
           fill=(110, 245, 122) if chg >= 0 else (255, 108, 108), font=font_b)

    # 价格范围（含均线和关键位）
    closes = [k["c"] for k in klines]
    e20s = []
    e50s = []
    for i in range(len(closes)):
        seg = closes[:i+1]
        if len(seg) >= 20:
            e20s.append((klines[i]["ts"], ta.ema(seg, 20)))
        if len(seg) >= 50:
            e50s.append((klines[i]["ts"], ta.ema(seg, 50)))

    plan = quick_plan(symbol).get("plan")
    all_vals = [k["h"] for k in klines] + [k["l"] for k in klines]
    all_vals += [v for _, v in e20s] + [v for _, v in e50s]
    if plan:
        all_vals += [plan["stop"], plan["target1"], plan["target2"], plan["entry"]]
    lo, hi = min(all_vals), max(all_vals)
    span = (hi - lo) or 1
    pad = span * 0.06
    lo -= pad; hi += pad

    def X(ts):
        i = next((idx for idx, k in enumerate(klines) if k["ts"] >= ts), len(klines) - 1)
        return MARGIN_L + i / (len(klines) - 1) * (W - MARGIN_L - MARGIN_R)
    def Y(v):
        return MARGIN_T + (hi - v) / (hi - lo) * (H - MARGIN_T - MARGIN_B)

    # 网格
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        y = Y(v)
        d.line([(MARGIN_L, y), (W - MARGIN_R, y)], fill=(26, 31, 61))
        d.text((8, y - 7), f"{v:.4g}", fill=(107, 118, 168), font=font)
    # 时间刻度
    for idx in range(0, len(klines), max(1, len(klines) // 6)):
        k = klines[idx]
        d.text((X(k["ts"]) - 20, H - MARGIN_B + 8),
               datetime.utcfromtimestamp(k["ts"] / 1000).strftime("%m-%d"), fill=(107, 118, 168), font=font)

    # 蜡烛
    bw = (W - MARGIN_L - MARGIN_R) / len(klines)
    for i, k in enumerate(klines):
        x = MARGIN_L + i * bw + bw / 2
        up = k["c"] >= k["o"]
        col = (110, 245, 122) if up else (255, 108, 108)
        d.line([(x, Y(k["h"])), (x, Y(k["l"]))], fill=col)
        y1, y2 = Y(max(k["o"], k["c"])), Y(min(k["o"], k["c"]))
        d.rectangle([x - bw * 0.32, y1, x + bw * 0.32, y2], fill=col)

    # 均线
    def draw_line(points, color):
        pts = [(X(ts), Y(v)) for ts, v in points if MARGIN_L <= X(ts) <= W - MARGIN_R]
        if len(pts) > 1:
            d.line(pts, fill=color, width=2)
    draw_line(e20s, (255, 215, 94))
    draw_line(e50s, (88, 166, 255))

    # 关键位标注
    if plan:
        marks = [("止损", plan["stop"], (255, 108, 108)), ("入场", plan["entry"], (34, 211, 238)),
                 ("目标1", plan["target1"], (110, 245, 122)), ("目标2", plan["target2"], (124, 108, 255))]
        for name, v, col in marks:
            y = Y(v)
            d.line([(MARGIN_L, y), (W - MARGIN_R, y)], fill=col, width=1)
            d.text((W - MARGIN_R - 90, y - 9), f"{name} {v:.4g}", fill=col, font=font)

    # 脚注
    d.text((MARGIN_L, H - 14), "比格 · 加密投研 · 数据源 Binance/Gate · 仅供参考",
           fill=(90, 94, 126), font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    data = draw_kline_chart(sym)
    if data:
        out = f"/tmp/{sym}_chart.png"
        open(out, "wb").write(data)
        print(f"已生成 {out} ({len(data)} bytes)")
    else:
        print("数据不足")
