# crypto-analyst 部署脚本（小馨服务器 YOUR_SERVER_IP）
# 用法: bash deploy/deploy.sh
set -euo pipefail

HOST="ubuntu@YOUR_SERVER_IP"
KEY="$HOME/.ssh/your-key.pem"
REMOTE="/home/ubuntu/crypto-analyst"
LOCAL="$(cd "$(dirname "$0")/.." && pwd)"

echo "== 1. 同步代码 =="
rsync -az --exclude data --exclude __pycache__ -e "ssh -i $KEY -o IdentitiesOnly=yes" "$LOCAL/" "$HOST:$REMOTE/"

echo "== 2. 服务器端环境 =="
ssh -i "$KEY" -o IdentitiesOnly=yes "$HOST" bash -s <<'EOF'
set -e
cd /home/ubuntu/crypto-analyst
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -U pip
  .venv/bin/pip install -q -r requirements.txt
fi
# DeepSeek key（本地 .zshrc 传入）
if [ ! -f .env ]; then
  touch .env
fi
grep -q DEEPSEEK_API_KEY .env || echo "DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY" >> .env
echo "env: $(grep -c DEEPSEEK .env) DEEPSEEK key"
EOF

echo "== 3. 安装 systemd 服务 =="
ssh -i "$KEY" -o IdentitiesOnly=yes "$HOST" bash -s <<'EOF'
set -e
cd /home/ubuntu/crypto-analyst
cat > /tmp/crypto-collector.service <<UNIT
[Unit]
Description=Crypto Analyst Collector
After=network.target
[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/crypto-analyst
EnvironmentFile=/home/ubuntu/crypto-analyst/.env
ExecStart=/home/ubuntu/crypto-analyst/.venv/bin/python -m collector.fetcher
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
UNIT
cat > /tmp/crypto-web.service <<UNIT
[Unit]
Description=Crypto Analyst Web
After=network.target
[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/crypto-analyst
EnvironmentFile=/home/ubuntu/crypto-analyst/.env
ExecStart=/home/ubuntu/crypto-analyst/.venv/bin/python -m web.app
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
UNIT
sudo cp /tmp/crypto-collector.service /etc/systemd/system/
sudo cp /tmp/crypto-web.service /etc/systemd/system/
sudo systemctl daemon-reload
echo "services installed"
EOF

echo "== 4. 初始化数据 + 启动 =="
ssh -i "$KEY" -o IdentitiesOnly=yes "$HOST" bash -s <<'EOF'
set -e
cd /home/ubuntu/crypto-analyst
export $(grep DEEPSEEK .env | xargs)
.venv/bin/python -m collector.fetcher backfill 2>&1 | tail -3 || true
sudo systemctl enable --now crypto-collector crypto-web
sleep 3
systemctl is-active crypto-collector crypto-web
EOF

echo "== 完成 =="
echo "Web: http://YOUR_SERVER_IP:3000"
