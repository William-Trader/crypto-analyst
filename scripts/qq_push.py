#!/usr/bin/env python3
# ---------------------------------------------------------------------------
# scripts/qq_push.py - crypto-analyst key automation logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-5BC5EAC8
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""主动推送消息到 QQ 群（写入 push_queue.json，bot 进程自动发送）
用法: python3 scripts/qq_push.py "消息内容"
"""
import json, sys
from pathlib import Path

QUEUE = Path(__file__).resolve().parent.parent / "data" / "push_queue.json"

def main():
    msg = " ".join(sys.argv[1:]) or "🐕 比格来报到！"
    try:
        q = json.loads(QUEUE.read_text())
    except Exception:
        q = []
    q.append(msg)
    QUEUE.write_text(json.dumps(q, ensure_ascii=False))
    print(f"已入队（队列 {len(q)} 条）：{msg[:60]}")

if __name__ == "__main__":
    main()
