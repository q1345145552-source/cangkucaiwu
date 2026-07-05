#!/bin/bash
# 一键部署脚本：本地推代码 → 服务器自动更新
set -e

SERVER_IP="187.127.124.231"
SERVER_USER="root"
SERVER_PASS="RL2XuiQVsZP/"
PROJECT_PATH="/opt/warehouse-finance"

echo "=== 1. 推送到 GitHub ==="
git add -A
git commit -m "deploy: $(date '+%Y-%m-%d %H:%M:%S')" 2>/dev/null || echo "  (无新更改，跳过 commit)"
git push origin main

echo ""
echo "=== 2. 连接服务器拉取代码并重建 ==="
python3 -c "
import paramiko
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('${SERVER_IP}', username='${SERVER_USER}', password='${SERVER_PASS}', timeout=10)

def run(cmd, timeout=120):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out)
    if err: print(err[-300:] if len(err) > 300 else err)

print('  → 拉取最新代码')
run('cd ${PROJECT_PATH} && git pull origin main')

print('  → 重建并启动容器')
run('cd ${PROJECT_PATH} && docker compose up -d --build 2>&1', 180)

print('  → 容器状态')
run('docker ps --format \"table {{.Names}}\\t{{.Status}}\\t{{.Ports}}\"')

print('  → Health Check')
run('sleep 5 && curl -s http://localhost:8000/health')

client.close()
"

echo ""
echo "============================================"
echo "  部署完成 ✅"
echo "  前端: http://${SERVER_IP}:3000"
echo "  API:  http://${SERVER_IP}:8000/docs"
echo "============================================"
