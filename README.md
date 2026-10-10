# 加密货币分析师 Agent（crypto-analyst）

单分析师智能体：QQ 提问 → 数据/指标/八派合议 → LLM 分析师输出作战计划。

> **许可**：PolyForm Noncommercial License 1.0.0 —— source-available，**非 OSI 开源**，仅限非商业用途。见 [LICENSE](LICENSE)。
> **水印**：核心代码（`analyst/`、`collector/`、`indicators/`、`web/` 等）已植入**可追溯水印**（`# WM: CA-xxxxxxxx`）；水印用于**溯源**，不是防拷贝，**移除即违反许可**。见 [WATERMARK.md](WATERMARK.md)。
> **免责**：仅供研究与教育用途，不构成投资建议。

## 快速开始（本地）
```bash
python3 -m collector.fetcher backfill   # 初始化数据（Binance 免费API）
export DEEPSEEK_API_KEY=sk-xxx
python3 -m analyst.pipeline BTCUSDT     # CLI 深度分析
python3 -m web.app                      # 前端驾驶舱 :3000
```

## 部署（小馨服务器）
```bash
bash deploy/deploy.sh
```
systemd: crypto-collector（采集）/ crypto-web（前端）/ qqbot（QQ机器人，待启用）

## 模块
- `collector/` Binance 采集（断点续拉/补洞/健康日志）
- `indicators/` 20+ 指标 + K线形态 + 关键位
- `analyst/` 状态机 + 八派合议庭 + LLM 人格 + 预测记录
- `bot/` QQ 机器人（botpy）
- `web/` 驾驶舱（卡通交易员 + 大盘 + 八派仪表）
- `rules/` 知识蒸馏产物（交易大师精选 8 套 → JSON 规则）

## 命令
- `分析BTC` / `技术面SOL` / `大盘` / `选品` / `战绩` / 自由提问
