# crypto-analyst · 项目归档说明（2026-09-02）

## 状态：已归档（服务器部署已清理，本地代码保留为资产）

- 服务器（YOUR_SERVER_IP）上的 crypto-analyst 部署已于 2026-09-02 13:00 清理：
  crypto-collector/crypto-web/crypto-qqbot 服务已删、/home/ubuntu/crypto-analyst 已删、晨报 crontab 已清
- 保留：OpenClaw（龙虾，18789）+ QQ 通道（appId YOUR_APP_ID，比格机器人由 OpenClaw 代理）
- 本地代码保留在本目录，可作为资产复用

## 资产清单

| 资产 | 位置 | 价值 |
|---|---|---|
| 万字蓝图 | BLUEPRINT-V2.md（52KB，24章） | 系统设计宪法，可复用 |
| 分析引擎代码 | analyst/（regime/bayes/risk_engine/calibration/shadow/review/verdict/opportunity/resonance/composite/backtest_engine/decision_tree/sentiment/sector/data_quality/schools/pipeline） | 直接可移植的模块化 Python 引擎 |
| 数据层 | collector/（多源 Binance/Gate/KuCoin/FGI + 断点续拉/补洞/健康） | 免费数据管道 |
| 指标库 | indicators/（20+ 指标 + 形态 + VPVR + 信号回测） | 纯 Python 无依赖 |
| 蒸馏规则 | rules/*.json（7 套交易大师流派） | LLM 蒸馏产物 |
| 前端 | web/static/index.html（像素世界+比格） | 单文件可复用 |
| 技能 | workspace/skills/local-knowledge-base + knowledge-archive | 已注册 |

## 复用方式
- 如需重启：rsync 到任意服务器 → pip install -r requirements.txt → systemd 三服务
- 数据源全免费（Binance data-api / Gate / alternative.me），无需代理
