#!/usr/bin/env bash
# ============================================================
# IFRS17 系统 — 服务器部署脚本（Docker 方式）
# 在服务器上、项目根目录（含 docker-compose.yml / .env）执行：
#   bash deploy-docker.sh
#
# 前置（一次性）：
#   1) 安装 Docker 与 docker compose 插件
#   2) cp .env.example .env 并填写
#   3) 把生产库导出放到 ./mysql/init/ifrs17_dump.sql
#   4) 停用宝塔 Nginx（见下方）
# ============================================================
set -e
cd "$(dirname "$0")"

# 0) 检查 .env
if [ ! -f .env ]; then
  echo "错误：未找到 .env，请先 cp .env.example .env 并填写。"
  exit 1
fi

# 1) 停用宝塔 Nginx，避免与容器 nginx 抢占 :80
echo ">> 停用宝塔 Nginx（如未使用宝塔可忽略报错）..."
/etc/init.d/nginx stop 2>/dev/null || systemctl stop nginx 2>/dev/null || true

# 2) 构建并拉起全部服务
echo ">> 构建并启动容器（db / web / nginx）..."
docker compose --env-file .env up -d --build

# 3) 健康检查
echo ">> 等待 web 服务就绪..."
for i in $(seq 1 30); do
  if docker compose exec -T web python manage.py check >/dev/null 2>&1; then
    echo ">> web 健康检查通过"
    break
  fi
  sleep 2
done

echo ""
echo "部署完成。访问 http://<服务器IP>"
echo "查看日志：docker compose logs -f web"
echo "回滚宝塔：/etc/init.d/nginx start"
