# ---------------------------------------------------------------------------
# analyst/llm.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-AD814D43
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""LLM 分析师（DeepSeek）：人格化输出 + 结构化分析"""
import json, urllib.request, ssl
from config import DEEPSEEK_KEY, LLM_MODEL, LLM_BASE

ctx = ssl._create_unverified_context()

SYSTEM_PROMPT = """你是{name}，一位有 15 年经验的加密货币分析师，经历过完整牛熊周期。
你的风格：
1. 专业直接，有独立观点——每次分析必须明确倾向（看多/看空/观望+置信度），不模棱两可
2. 判断要有依据：引用技术指标、K线形态、关键位，必要时提到流派视角（威科夫/缠论/斐波那契/趋势派等）
3. 敢认错——用户追问历史判断时如实复盘
4. 永远给关键位（支撑/阻力/止损）和风险提示，不鼓励无脑追高
5. 语言像真人分析师：可以说"这位置我看多，但跌破 XX 我就认错"、"别追，等回踩"
6. 每次输出格式：
   【方向】看多/看空/观望 + 置信度%
   【关键位】支撑 / 阻力 / 止损参考
   【依据】指标+形态+流派观点（引用合议结果：8派中X派看多）
   【操作建议】具体入场区/目标/仓位/风险提示
   【风险提示】明确的风险点
"""

def llm_chat(user_text, system=None, temperature=0.7):
    if not DEEPSEEK_KEY:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY")
    body = json.dumps({
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system or SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        "temperature": temperature,
    }).encode()
    req = urllib.request.Request(
        f"{LLM_BASE}/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_KEY}"})
    with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"]

def build_analyst_input(symbol, market_state, state_reason, sig_report, verdicts, direction, agreement, extra=None):
    """把数据+指标+合议结果组装成给 LLM 的输入"""
    lines = []
    lines.append(f"标的：{symbol}（Binance 现货）")
    lines.append(f"市场状态机判定：{market_state}（{state_reason}）")
    if sig_report.get("last"):
        l = sig_report["last"]
        lines.append(f"最新价：{l['close']:.2f}  24h高/低：{l['high']:.2f}/{l['low']:.2f}")
    lines.append("")
    lines.append("【指标信号】")
    for name, d, w, note in sig_report.get("signals", []):
        lines.append(f"- {name}: {note} ({d})")
    lines.append("")
    lines.append(f"【八派合议】整体倾向：{direction}（一致性 {agreement}%）")
    for v in verdicts:
        lines.append(f"- {v.school}: {v.direction} {v.confidence}% — {v.note}")
    if extra:
        lines.append("")
        lines.append(extra)
    return "\n".join(lines)

def analyze(symbol, market_state, state_reason, sig_report, verdicts, direction, agreement, extra=None):
    user_text = build_analyst_input(symbol, market_state, state_reason, sig_report, verdicts, direction, agreement, extra)
    return llm_chat(user_text)
