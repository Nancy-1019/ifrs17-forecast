#!/bin/bash
# ============================================================
# IFRS17 系统登录问题诊断 + 修复脚本
# 在宝塔终端执行: bash /www/wwwroot/ifrs17-system/deploy/diagnose_login.sh
# ============================================================

PROJECT_DIR="/www/wwwroot/ifrs17-system"
NGINX_SBIN="/www/server/nginx/sbin/nginx"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "========================================"
echo "  IFRS17 登录问题诊断"
echo "========================================"
echo ""

# ---------- 1. 检查 Gunicorn ----------
echo -e "${YELLOW}[1/8] 检查 Gunicorn 运行状态${NC}"
if ss -tlnp | grep -q ":8080"; then
    echo -e "${GREEN}✓ Gunicorn 正在监听 8080 端口${NC}"
    ss -tlnp | grep ":8080"
else
    echo -e "${RED}✗ Gunicorn 未在 8080 端口运行${NC}"
    echo "  请在宝塔 Python 项目管理器中启动项目"
fi
echo ""

# ---------- 2. 测试 Gunicorn 本地响应 ----------
echo -e "${YELLOW}[2/8] 测试 Gunicorn 本地响应${NC}"
LOGIN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/login/)
echo "  /login/ 状态码: $LOGIN_STATUS"
if [ "$LOGIN_STATUS" = "200" ]; then
    echo -e "${GREEN}✓ Gunicorn 响应正常${NC}"
else
    echo -e "${RED}✗ Gunicorn 响应异常 (期望 200)${NC}"
fi

# 测试根路径重定向
ROOT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/)
echo "  / 状态码: $ROOT_STATUS (期望 302 重定向到 /login/)"
echo ""

# ---------- 3. 测试登录 POST ----------
echo -e "${YELLOW}[3/8] 测试登录 POST 请求${NC}"
# 先获取 CSRF token
CSRF_RESPONSE=$(curl -s -c /tmp/ifrs17_cookies.txt http://127.0.0.1:8080/login/)
CSRF_TOKEN=$(echo "$CSRF_RESPONSE" | grep -oP 'csrfmiddlewaretoken" value="\K[^"]+')

if [ -z "$CSRF_TOKEN" ]; then
    echo -e "${RED}✗ 无法获取 CSRF token，登录页面可能异常${NC}"
else
    echo "  CSRF token 获取成功: ${CSRF_TOKEN:0:20}..."

    # 提交登录
    LOGIN_RESULT=$(curl -s -o /dev/null -w "%{http_code}" \
        -b /tmp/ifrs17_cookies.txt \
        -c /tmp/ifrs17_cookies.txt \
        -X POST http://127.0.0.1:8080/login/ \
        -H "Referer: http://127.0.0.1:8080/login/" \
        -d "csrfmiddlewaretoken=${CSRF_TOKEN}&username=admin&password=admin123&next=")

    echo "  登录 POST 状态码: $LOGIN_RESULT"

    if [ "$LOGIN_RESULT" = "302" ]; then
        echo -e "${GREEN}✓ 登录成功！重定向到首页${NC}"
    elif [ "$LOGIN_RESULT" = "403" ]; then
        echo -e "${RED}✗ CSRF 验证失败 (403)${NC}"
        echo "  原因: Django CSRF_TRUSTED_ORIGINS 未配置"
        echo "  修复: 确认 settings.py 中有 CSRF_TRUSTED_ORIGINS = ['http://*', 'https://*']"
    elif [ "$LOGIN_RESULT" = "200" ]; then
        echo -e "${YELLOW}⚠ 登录返回 200（可能是用户名密码错误，页面重新渲染）${NC}"
        echo "  请检查数据库中是否存在 admin 用户"
    elif [ "$LOGIN_RESULT" = "500" ]; then
        echo -e "${RED}✗ 服务器内部错误 (500)${NC}"
        echo "  请查看 Django 日志: tail -50 /var/log/ifrs17/django.log"
    else
        echo -e "${YELLOW}⚠ 登录返回 $LOGIN_RESULT${NC}"
    fi
fi
echo ""

# ---------- 4. 检查 Django 设置模块 ----------
echo -e "${YELLOW}[4/8] 检查 Django 设置模块${NC}"
# 查找虚拟环境
VENV_PATH=""
for p in "$PROJECT_DIR/venv" "$PROJECT_DIR/.venv" "/www/server/pyproject_evn/ifrs17-system"; do
    if [ -f "$p/bin/python" ]; then
        VENV_PATH="$p"
        break
    fi
done

if [ -z "$VENV_PATH" ]; then
    echo -e "${YELLOW}  未找到虚拟环境，尝试系统 Python${NC}"
    # 查找 Gunicorn 进程使用的 Python
    GUNICORN_PYTHON=$(ps aux | grep gunicorn | grep -oP 'bin/python[0-9.]*' | head -1)
    if [ -n "$GUNICORN_PYTHON" ]; then
        echo "  Gunicorn 使用 Python: $GUNICORN_PYTHON"
    fi
else
    echo "  虚拟环境: $VENV_PATH"
    # 检查当前使用的 settings 模块
    cd "$PROJECT_DIR"
    SETTINGS_MODULE=$($VENV_PATH/bin/python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
# 模拟 Gunicorn 环境
import importlib
# 检查 gunicorn 配置
try:
    with open('gunicorn_config_baota.py') as f:
        content = f.read()
        if 'settings_prod' in content:
            print('settings_prod (gunicorn_config_baota.py 中配置)')
        else:
            print('settings (默认)')
except:
    print('settings (默认)')
" 2>/dev/null)
    echo "  预期配置模块: $SETTINGS_MODULE"
fi

# 检查宝塔是否使用了 gunicorn_config_baota.py
BT_GUNICORN_CONF=$(find /www/server/panel -name "*.conf" -path "*python*" 2>/dev/null | head -5)
if [ -n "$BT_GUNICORN_CONF" ]; then
    echo "  宝塔 Python 配置文件:"
    echo "$BT_GUNICORN_CONF" | while read f; do
        echo "    $f"
    done
fi
echo ""

# ---------- 5. 检查数据库用户 ----------
echo -e "${YELLOW}[5/8] 检查数据库用户${NC}"
cd "$PROJECT_DIR"
if [ -n "$VENV_PATH" ]; then
    PYTHON_BIN="$VENV_PATH/bin/python"
else
    PYTHON_BIN="python3"
fi

DB_CHECK=$($PYTHON_BIN -c "
import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
import django
django.setup()
from django.contrib.auth.models import User
users = User.objects.all()
if users.exists():
    for u in users:
        print(f'  用户: {u.username} | 超级用户: {u.is_superuser} | 活跃: {u.is_active} | 密码是否可用: {u.has_usable_password()}')
else:
    print('  数据库中没有用户！')
" 2>&1)

echo "$DB_CHECK"
echo ""

# ---------- 6. 检查 Nginx ----------
echo -e "${YELLOW}[6/8] 检查 Nginx 状态${NC}"
# 检查哪个 Nginx 在监听 80
NGINX_80=$(ss -tlnp | grep ":80 ")
if echo "$NGINX_80" | grep -q "nginx"; then
    echo -e "${GREEN}✓ Nginx 正在监听 80 端口${NC}"
    echo "  $NGINX_80"
else
    echo -e "${RED}✗ 80 端口无 Nginx 监听${NC}"
    echo "  请启动宝塔 Nginx: /etc/init.d/nginx start"
fi

# 检查是否有系统 Nginx 干扰
if systemctl is-active nginx 2>/dev/null | grep -q "active"; then
    echo -e "${RED}  ⚠ 系统 Nginx 也在运行，可能冲突！${NC}"
    echo "  停止系统 Nginx: systemctl stop nginx && systemctl disable nginx"
fi
echo ""

# ---------- 7. 检查 Nginx 站点配置 ----------
echo -e "${YELLOW}[7/8] 检查 Nginx 站点配置${NC}"
# 查找 ifrs17 站点配置
SITE_CONF=$(find /www/server/panel/vhost/nginx/ -name "*ifrs17*" -type f 2>/dev/null)
if [ -z "$SITE_CONF" ]; then
    echo -e "${RED}✗ 未找到 ifrs17 站点配置文件${NC}"
else
    for conf in $SITE_CONF; do
        echo "  配置文件: $conf"
        # 检查 proxy_pass 端口
        PROXY_PASS=$(grep "proxy_pass" "$conf" 2>/dev/null)
        echo "  $PROXY_PASS"

        # 检查 server_name
        SERVER_NAME=$(grep "server_name" "$conf" 2>/dev/null)
        echo "  $SERVER_NAME"

        # 检查是否有 static location
        if grep -q "/static/" "$conf" 2>/dev/null; then
            echo -e "  ${GREEN}✓ 有 /static/ 配置${NC}"
        else
            echo -e "  ${YELLOW}⚠ 缺少 /static/ 配置，CSS/JS 将 404${NC}"
        fi
        echo ""
    done
fi

# ---------- 8. 测试通过 Nginx 访问 ----------
echo -e "${YELLOW}[8/8] 测试通过 Nginx (80端口) 访问${NC}"
NGINX_LOGIN=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:80/login/)
echo "  Nginx /login/ 状态码: $NGINX_LOGIN"

if [ "$NGINX_LOGIN" = "200" ]; then
    echo -e "${GREEN}✓ Nginx 反向代理正常${NC}"
elif [ "$NGINX_LOGIN" = "404" ]; then
    echo -e "${RED}✗ 404 — server_name 未匹配 IP 访问${NC}"
    echo "  修复: 在站点配置中添加 server_name _; 或 default_server"
elif [ "$NGINX_LOGIN" = "502" ]; then
    echo -e "${RED}✗ 502 — proxy_pass 端口与 Gunicorn 不一致${NC}"
    echo "  检查: proxy_pass 应为 http://127.0.0.1:8080"
elif [ "$NGINX_LOGIN" = "000" ]; then
    echo -e "${RED}✗ Nginx 无响应${NC}"
else
    echo -e "${YELLOW}⚠ 状态码: $NGINX_LOGIN${NC}"
fi
echo ""

# ---------- 总结 ----------
echo "========================================"
echo "  诊断完成"
echo "========================================"
echo ""
echo "如果登录 POST 返回 403:"
echo "  → 已修复: settings.py 添加了 CSRF_TRUSTED_ORIGINS"
echo "  → 需要重启 Gunicorn 使配置生效"
echo ""
echo "如果登录 POST 返回 200 (用户名密码错误):"
echo "  → 执行以下命令创建 admin 用户:"
echo "    cd $PROJECT_DIR"
echo "    source venv/bin/activate"
echo "    python manage.py shell -c \""
echo "from django.contrib.auth.models import User"
echo "User.objects.filter(username='admin').delete()"
echo "User.objects.create_superuser('admin', '', 'admin123')"
echo "print('admin 用户已创建')"
echo "\""
echo ""
echo "如果登录 POST 返回 500:"
echo "  → 查看错误日志: tail -50 /var/log/ifrs17/django.log"
echo "  → 或切换到 DEBUG 模式测试: 修改 wsgi.py 使用 settings 而非 settings_prod"
echo ""
echo "修复后重启命令:"
echo "  1. 重启 Gunicorn (宝塔面板 Python项目管理器 → 重启)"
echo "  2. 重载 Nginx: $NGINX_SBIN -t && $NGINX_SBIN -s reload"
