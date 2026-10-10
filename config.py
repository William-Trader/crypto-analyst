# ---------------------------------------------------------------------------
# config.py - crypto-analyst key engine logic
# (c) 2026 William-Trader (https://github.com/William-Trader)
# WM: CA-8654B55C
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Removing this mark violates the license.
# ---------------------------------------------------------------------------
"""crypto-analyst 配置中心"""
import os
from pathlib import Path

# 路径
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "market.db"

# 市场
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"]
INTERVALS = ["15m", "1h", "4h", "1d"]
BASE_URL = "https://data-api.binance.vision"  # 免费公开端点，已验证直连

# 采集频率（秒）
COLLECT_5M = 300
COLLECT_15M = 900
COLLECT_1H = 3600

# 保留策略（秒）
RETENTION = {"15m": 90 * 86400, "1h": 180 * 86400, "4h": 0, "1d": 0}  # 0=永久

# LLM
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
LLM_MODEL = "deepseek-v4-flash"
LLM_BASE = "https://api.deepseek.com"

# QQ Bot
QQ_APPID = os.environ.get("QQ_APPID", "")
QQ_SECRET = os.environ.get("QQ_SECRET", "")

# 分析师人格
ANALYST_NAME = "老周"
