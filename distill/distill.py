# ---------------------------------------------------------------------------
# distill/distill.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-3CB4D2CB
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""知识蒸馏：交易大师精选书 → 各流派规则 JSON
用法: python3 distill/distill.py            # 全部
      python3 distill/distill.py wyckoff    # 单套
      python3 distill/distill.py --max-chars 20000
"""
import json, sys, os, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DEEPSEEK_KEY, LLM_MODEL, LLM_BASE

T_MASTER = Path.home() / "openclaw资产库/03-知识库-knowledge/trading/交易大师｜AI 智能体"
RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
RULES_DIR.mkdir(exist_ok=True)

# 8 套 → 核心书（相对 T_MASTER）
BOOKS = {
    "wyckoff": ["威科夫/《威科夫操盘法》.pdf"],
    "murphy": ["交易理念/28条期货交易法则 (（美）贾森艾伦扬科夫斯基,译者 顾锦生).pdf"],
    "chan": ["缠论资料/《缠论108课详解》扫地僧.pdf"],
    "fib": ["斐波那契/斐波那契交易法 (拉瑞佩萨温托).pdf"],
    "trend": ["杰西.利弗莫尔/丁圣元译《股票大作手回忆录(修订版)》.pdf", "斯坦利.克罗/期货交易策略(高清).pdf"],
    "ding": ["丁圣元/《趋势投资》金融市场技术分析指南(丁圣元30年思想集成之作蜡烛图技术与技术分析工具融汇站在趋势一边做股票投资).pdf"],
    "practical": ["傅海棠/一个农民的亿万传奇.pdf"],
    "quant": ["量化交易/征服市场的人：西蒙斯传.pdf"],
}

def extract_pdf(path, max_chars=25000):
    from pypdf import PdfReader
    r = PdfReader(str(path))
    out = []
    for p in r.pages:
        t = p.extract_text() or ""
        t = " ".join(t.split())
        if len(t) > 30:
            out.append(t)
        if sum(len(x) for x in out) > max_chars:
            break
    return "\n".join(out)[:max_chars]

def llm_rules(school, text, retries=3):
    import urllib.request, ssl
    ctx = ssl._create_unverified_context()
    prompt = f"""你是交易方法论提炼专家。以下是从《{school}》流派核心书籍提取的文本片段。
请提炼该流派完整可执行的交易方法论，输出**严格 JSON**（不要任何其他文字）：

{{
  "school": "{school}",
  "core_principles": ["核心原则3-6条"],
  "entry_rules": ["入场规则（具体可执行的判定条件）"],
  "exit_rules": ["出场/止盈/止损规则"],
  "indicators": ["使用的指标/工具及具体用法"],
  "risk_rules": ["仓位管理与风控纪律"],
  "market_conditions": ["适用/不适用的市场环境"],
  "signals": [{{"name": "信号名", "condition": "触发条件", "action": "对应操作"}}]
}}

要求：规则必须具体可执行（带数值/条件），不要空话；提炼原文精华，保留关键术语。

书籍文本（片段）：
---
{text}
---"""
    body = json.dumps({
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 4000,
    }).encode()
    req = urllib.request.Request(f"{LLM_BASE}/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_KEY}"})
    last_err = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=300, context=ctx) as r:
                data = json.loads(r.read())
            content = data["choices"][0]["message"].get("content") or ""
            if content.strip():
                return content
            last_err = "empty content"
        except Exception as e:
            last_err = e
        print(f"    [retry {i+1}] {last_err}", flush=True)
        time.sleep(8 * (i + 1))
    raise RuntimeError(f"LLM 调用失败: {last_err}")

def parse_json(text):
    """从 LLM 输出中提取 JSON"""
    import re
    m = re.search(r"\{[\s\S]*\}", text)
    if not m: raise ValueError("no json in output")
    return json.loads(m.group(0))

def distill(school, max_chars=25000):
    paths = BOOKS.get(school)
    if not paths:
        print(f"未知流派: {school}"); return
    texts = []
    for rel in paths:
        p = T_MASTER / rel
        if not p.exists():
            print(f"  跳过缺失文件: {rel}"); continue
        t = extract_pdf(p, max_chars // len(paths))
        texts.append(t)
        print(f"  [extract] {rel}: {len(t)} 字符", flush=True)
    if not texts:
        print(f"  {school}: 无可用文本"); return
    full = "\n\n---\n\n".join(texts)
    print(f"  [llm] {school} 提炼中 ({len(full)} 字符)...", flush=True)
    raw = llm_rules(school, full)
    rules = parse_json(raw)
    out = RULES_DIR / f"{school}.json"
    out.write_text(json.dumps(rules, ensure_ascii=False, indent=2))
    print(f"  ✅ {school} → {out}（{len(raw)} 字符输出）", flush=True)
    return rules

if __name__ == "__main__":
    max_chars = 25000
    only = None
    args = sys.argv[1:]
    if "--max-chars" in args:
        i = args.index("--max-chars"); max_chars = int(args[i+1])
    for a in args:
        if a in BOOKS: only = a
    targets = [only] if only else list(BOOKS)
    for s in targets:
        try:
            distill(s, max_chars)
        except Exception as e:
            print(f"  ❌ {s} 失败: {e}", flush=True)
        time.sleep(2)
    print("蒸馏完成")
