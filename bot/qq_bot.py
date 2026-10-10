# ---------------------------------------------------------------------------
# bot/qq_bot.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-FDA7296F
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""QQ 机器人（botpy 官方 SDK，WS 长连接）
命令：分析X / 大盘 / 选品 / 技术面X / 战绩 / 自由提问
"""
import asyncio, re, time, json
from pathlib import Path
from config import QQ_APPID, QQ_SECRET

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GROUPS_FILE = DATA_DIR / "qq_groups.json"
PUSH_QUEUE = DATA_DIR / "push_queue.json"

def _load_json(p, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default

def record_group(group_openid):
    groups = _load_json(GROUPS_FILE, [])
    if group_openid not in groups:
        groups.append(group_openid)
        GROUPS_FILE.write_text(json.dumps(groups, ensure_ascii=False, indent=2))
        print(f"[group] 记录群 {group_openid}（共{len(groups)}个）", flush=True)

try:
    import botpy
    from botpy import Client, Intents
    from botpy.message import Message
except ImportError:
    botpy = None

from analyst.pipeline import full_analysis, get_market_snapshot
from analyst import record as rec
from collector import db
from config import SYMBOLS

SYM_MAP = {s.replace("USDT", ""): s for s in SYMBOLS}
SYM_MAP.update({s: s for s in SYMBOLS})

def resolve_symbol(txt):
    for k, v in SYM_MAP.items():
        if k.lower() in txt.lower():
            return v
    return None

def cmd_pipeline(text):
    """统一入口：返回回复文本"""
    text = text.strip()
    m = re.match(r"^(分析|技术面|看看|怎么看)?\s*([a-zA-Z]+)", text)
    if m and m.group(2).upper() in SYM_MAP:
        sym = SYM_MAP[m.group(2).upper()]
        if "技术面" in text:
            return quick_technical(sym)
        return deep_analysis(sym)
    if "大盘" in text or "市场" in text:
        return market_overview()
    if "选品" in text or "推荐" in text:
        return stock_pick()
    if "战绩" in text or "胜率" in text:
        return performance()
    if "雷达" in text or "信号" in text:
        from analyst.radar import radar_text
        return radar_text(limit=10)
    return free_chat(text)

def deep_analysis(sym):
    try:
        r = full_analysis(sym, use_llm=True)
    except Exception as e:
        return f"⚠️ 分析失败：{e}"
    if "error" in r: return r["error"]
    return (f"📊 【{sym} 深度分析】\n"
            f"市场状态：{r['market_state']}（{r['state_reason']}）\n"
            f"八派合议：{r['direction']}（一致性 {r['agreement']}%）\n\n"
            f"{r['report']}")

def quick_technical(sym):
    snap = get_market_snapshot(sym)
    if not snap: return f"{sym} 数据不足"
    from indicators import signals as se, ta
    k = snap["4h"]
    sig = se.analyze_symbol(k)
    if "error" in sig: return sig["error"]
    lines = [f"📈 【{sym} 技术面速报】"]
    for name, d, w, note in sig.get("signals", []):
        emoji = "🟢" if d == "bullish" else ("🔴" if d == "bearish" else "⚪")
        lines.append(f"{emoji} {name}: {note}")
    lines.append(f"\n综合：{sig['direction']}（得分{sig['score']}，置信{sig['confidence']}%）")
    return "\n".join(lines)

def market_overview():
    dbh = db.get_db()
    rows = dbh.execute("SELECT symbol, price, chg24h FROM ticker_snap t1 WHERE ts=(SELECT MAX(ts) FROM ticker_snap t2 WHERE t2.symbol=t1.symbol)").fetchall()
    dbh.close()
    if not rows: return "暂无行情数据（采集器启动中）"
    up = sum(1 for r in rows if r["chg24h"] > 0)
    lines = [f"🌐 【大盘速览】{len(rows)}币 {up}涨{len(rows)-up}跌"]
    for r in sorted(rows, key=lambda x: x["chg24h"], reverse=True):
        emoji = "🟢" if r["chg24h"] > 0 else "🔴"
        lines.append(f"{emoji} {r['symbol'].replace('USDT','')}: {r['price']:.2f} ({r['chg24h']:+.2f}%)")
    lines.append("\n回复「分析BTC」看单币深度分析")
    return "\n".join(lines)

def stock_pick():
    """选品：按 24h 涨跌幅 + 量能排序（后续升级为状态机筛吸筹/突破）"""
    dbh = db.get_db()
    rows = dbh.execute("SELECT symbol, price, chg24h, quote_vol24h FROM ticker_snap t1 WHERE ts=(SELECT MAX(ts) FROM ticker_snap t2 WHERE t2.symbol=t1.symbol)").fetchall()
    dbh.close()
    if not rows: return "暂无数据"
    lines = ["🎯 【选品雷达】按24h表现排序"]
    for r in sorted(rows, key=lambda x: x["quote_vol24h"] or 0, reverse=True):
        lines.append(f"- {r['symbol'].replace('USDT','')}: {r['price']:.4g} ({r['chg24h']:+.2f}%) 成交{r['quote_vol24h']/1e8:.1f}亿U")
    lines.append("\n回复「分析XXX」查看具体标的")
    return "\n".join(lines)

def performance():
    s = rec.stats()
    if s.get("total", 0) == 0: return "📋 暂无战绩记录（分析时自动记录预测）"
    return (f"📋 【分析师战绩】\n总预测 {s['total']} · 命中 {s['wins']} · 止损 {s['losses']}\n"
            f"胜率 {s['win_rate']}%（随分析量增加更准确）")

def free_chat(text):
    from analyst.llm import llm_chat
    try:
        return llm_chat(text, system=None)
    except Exception as e:
        return f"⚠️ {e}"

class AnalystBot(Client):
    async def on_ready(self):
        print(f"QQ Bot 上线: {self.robot.name if hasattr(self,'robot') else ''}", flush=True)
        asyncio.create_task(self._push_loop())

    async def _push_loop(self):
        """主动推送循环：每 20s 检查 push_queue.json，发送后移除"""
        while True:
            try:
                q = _load_json(PUSH_QUEUE, [])
                groups = _load_json(GROUPS_FILE, [])
                if q and groups:
                    item = q[0]
                    for gid in groups:
                        try:
                            await self.api.post_group_message(group_openid=gid, msg_type=0, content=str(item)[:1500])
                            print(f"[push] → {gid}: {str(item)[:50]}", flush=True)
                        except Exception as e:
                            print(f"[push err] {gid}: {e}", flush=True)
                    # 发送完成移除
                    _load_json(PUSH_QUEUE, [])  # 原子简化：清空
                    PUSH_QUEUE.write_text(json.dumps(q[1:], ensure_ascii=False))
            except Exception as e:
                print(f"[push loop err] {e}", flush=True)
            await asyncio.sleep(20)

    async def on_group_add_robot(self, message):
        """机器人被拉进群：自动记录群 ID"""
        try:
            gid = getattr(message, "group_openid", None) or getattr(message, "group_id", None)
            if gid:
                record_group(gid)
                print(f"[group] 加入群 {gid}", flush=True)
        except Exception as e:
            print(f"[group_add err] {e}", flush=True)

    async def on_group_at_message_create(self, message: Message):
        try:
            record_group(message.group_openid)
            content = re.sub(r"<@!?\d+>", "", message.content).strip()
            reply = cmd_pipeline(content)
            await self.api.post_group_message(group_openid=message.group_openid,
                msg_type=0, msg_id=message.id, content=reply[:1500])
            print(f"[group] 回复: {reply[:40]}", flush=True)
        except Exception as e:
            print(f"[group err] {e}", flush=True)

    async def on_c2c_message_create(self, message: Message):
        try:
            reply = cmd_pipeline(message.content.strip())
            await self.api.post_c2c_message(openid=message.author.user_openid,
                msg_type=0, msg_id=message.id, content=reply[:1500])
            print(f"[c2c] 回复: {reply[:40]}", flush=True)
        except Exception as e:
            print(f"[dm err] {e}", flush=True)

def run():
    if botpy is None:
        print("botpy 未安装：pip install qq-botpy")
        return
    intents = Intents(public_messages=True)
    client = AnalystBot(intents=intents)
    client.run(appid=QQ_APPID, secret=QQ_SECRET)

if __name__ == "__main__":
    run()
