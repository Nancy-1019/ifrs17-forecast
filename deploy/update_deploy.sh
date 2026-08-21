#!/bin/bash
# ================================================================
# IFRS17 预测模型系统 — Docker 一键部署脚本（容器模式）
#
# 使用场景：本地打包最新代码上传到服务器后，执行此脚本完成发布
# 操作方式：解压代码到项目目录，然后 docker compose up -d --build
#
# 说明：
#   - 重建 web 镜像（使用新代码），db 数据卷（db_data）保留，数据不丢
#   - web 容器 entrypoint 会自动执行 migrate + collectstatic
#   - 不再操作主机 Gunicorn / 宝塔 Nginx（已由容器接管 :80 / :8080）
#
# 用法：
#   bash /www/wwwroot/ifrs17-system/deploy/update_deploy.sh
#   bash /www/wwwroot/ifrs17-system/deploy/update_deploy.sh --no-cache
# ================================================================
set -e

# ---- 颜色输出 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
echo_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
echo_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ---- 配置 ----
PROJECT_DIR="/www/wwwroot/ifrs17-system"
BUILD_FLAGS=""

# ---- 解析参数 ----
for arg in "$@"; do
    case $arg in
        --no-cache)  BUILD_FLAGS="--no-cache" ;;
        --help|-h)
            echo "用法: bash update_deploy.sh [--no-cache]"
            echo ""
            echo "选项:"
            echo "  --no-cache   强制重建镜像（依赖/系统包有变化时使用）"
            exit 0
            ;;
    esac
done

echo ""
echo "=========================================="
echo "  IFRS17 系统 Docker 部署"
echo "=========================================="
echo ""

# ---- 1. 环境检查 ----
echo_info "步骤 1/4: 环境检查"
if [ ! -d "$PROJECT_DIR" ]; then
    echo_error "项目目录不存在: $PROJECT_DIR"
    exit 1
fi
cd "$PROJECT_DIR"

if ! command -v docker >/dev/null 2>&1; then
    echo_error "未检测到 docker，请确认 Docker 已安装"
    exit 1
fi
if ! command -v docker compose >/dev/null 2>&1 && ! docker compose version >/dev/null 2>&1; then
    echo_error "未检测到 docker compose 插件"
    exit 1
fi
echo_info "  项目目录: $PROJECT_DIR"
echo ""

# ---- 2. 确认数据卷与 .env ----
echo_info "步骤 2/4: 检查 .env 与数据卷"
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo_warn "  .env 不存在，docker compose 可能因缺少变量失败，请先 cp .env.example .env 并填写"
else
    echo_info "  .env 存在"
fi
echo_info "  数据卷 db_data（MySQL 数据）将保留，不会随重建丢失"
echo ""

# ---- 3. 重建容器 ----
echo_info "步骤 3/4: 重建 Docker 容器（web 镜像使用新代码）"
docker compose up -d --build $BUILD_FLAGS
echo ""

# ---- 4. 状态与验证 ----
echo_info "步骤 4/4: 容器状态与验证"
docker compose ps
echo ""

echo_info "等待 web 容器 entrypoint 完成迁移/静态收集..."
sleep 15

# 检查 Nginx 80 端口（容器）
if command -v curl >/dev/null 2>&1; then
    LOGIN_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:80/login/ 2>/dev/null || echo "000")
    if [ "$LOGIN_CODE" = "200" ] || [ "$LOGIN_CODE" = "302" ]; then
        echo_info "  Nginx(:80) /login/ 返回: $LOGIN_CODE (正常)"
    else
        echo_error "  Nginx(:80) /login/ 返回: $LOGIN_CODE (异常，请检查容器日志)"
    fi
fi

echo ""
echo "=========================================="
echo "  Docker 部署完成"
echo "  访问地址: http://$(curl -s ifconfig.me 2>/dev/null || echo '服务器IP')/login/"
echo "  登录账号: admin / admin123"
echo "=========================================="
echo ""
echo "如遇问题，请检查:"
echo "  1. web 容器日志: docker compose logs web"
echo "  2. 数据库日志:   docker compose logs db"
echo "  3. 容器状态:     docker compose ps"
echo ""
