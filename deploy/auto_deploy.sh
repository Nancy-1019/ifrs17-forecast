#!/bin/bash
# ================================================================
# IFRS17 预测模型系统 — 一键自动部署脚本（宝塔面板 11.8 + 阿里云）
#
# 使用方法：
#   1. 将整个项目上传到 /www/wwwroot/ifrs17-system/
#   2. 在宝塔终端执行: bash /www/wwwroot/ifrs17-system/deploy/auto_deploy.sh
#
# 本脚本自动完成：
#   ✅ 环境检查（Python/Nginx/Gunicorn）
#   ✅ 虚拟环境创建/修复
#   ✅ 依赖安装
#   ✅ 数据库迁移 + 初始数据加载
#   ✅ 静态文件收集
#   ✅ Gunicorn 配置（端口 8080）
#   ✅ Nginx 反向代理配置（端口 80 → 8080）
#   ✅ 防火墙放行 80/8080
#   ✅ well-known 配置修复
#   ✅ Nginx buffer 约束修复
#   ✅ 服务启动 + 验证
# ================================================================

set -e

# ===== 颜色输出 =====
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ===== 全局变量 =====
PROJECT_DIR="/www/wwwroot/ifrs17-system"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON_BIN=""
NGINX_BIN="/www/server/nginx/sbin/nginx"
NGINX_CONF_DIR="/www/server/panel/vhost/nginx"
LOG_DIR="/var/log/ifrs17"
PID_DIR="/var/run/ifrs17"
GUNICORN_PORT=8080
SERVER_IP=""

# ===== 工具函数 =====
info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; }
step()  { echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${BLUE}  STEP $1${NC}"; echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }

# ===== 获取服务器公网 IP =====
get_server_ip() {
    SERVER_IP=$(curl -s --connect-timeout 5 http://ifconfig.me 2>/dev/null || \
                curl -s --connect-timeout 5 http://ipinfo.io/ip 2>/dev/null || \
                echo "未知")
}

# ================================================================
# STEP 1: 环境检查
# ================================================================
check_environment() {
    step "1/9  环境检查"

    # 检查项目目录
    if [ ! -d "$PROJECT_DIR" ]; then
        err "项目目录不存在: $PROJECT_DIR"
        err "请先将项目代码上传到 $PROJECT_DIR"
        exit 1
    fi
    ok "项目目录存在: $PROJECT_DIR"

    # 检查 manage.py
    if [ ! -f "$PROJECT_DIR/manage.py" ]; then
        err "manage.py 不存在，项目代码不完整"
        exit 1
    fi
    ok "manage.py 存在"

    # 检查宝塔 Nginx
    if [ ! -f "$NGINX_BIN" ]; then
        err "宝塔 Nginx 未安装: $NGINX_BIN"
        err "请在宝塔面板 → 软件商店 → 安装 Nginx"
        exit 1
    fi
    ok "宝塔 Nginx 已安装: $($NGINX_BIN -v 2>&1)"

    # 检查 Python
    for py in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v $py &>/dev/null; then
            PYTHON_BIN=$(which $py)
            ok "Python: $PYTHON_BIN ($($PYTHON_BIN --version 2>&1))"
            break
        fi
    done
    if [ -z "$PYTHON_BIN" ]; then
        err "未找到 Python3，请在宝塔安装 Python 项目管理器并创建 Python 3.x 环境"
        exit 1
    fi

    # 检查是否 root
    if [ "$EUID" -ne 0 ]; then
        warn "非 root 用户，部分操作可能需要 sudo"
    fi

    get_server_ip
    ok "服务器公网 IP: $SERVER_IP"
}

# ================================================================
# STEP 2: 虚拟环境
# ================================================================
setup_venv() {
    step "2/9  虚拟环境"

    # 如果宝塔已创建虚拟环境，优先使用
    BT_VENV="/www/wwwroot/ifrs17-system/venv"
    if [ -f "$BT_VENV/bin/python" ]; then
        info "检测到已有虚拟环境: $BT_VENV"
        info "Python 版本: $($BT_VENV/bin/python --version 2>&1)"
        VENV_DIR="$BT_VENV"
    elif [ -f "$BT_VENV/bin/activate" ]; then
        info "检测到已有虚拟环境（部分）: $BT_VENV"
        VENV_DIR="$BT_VENV"
    else
        info "创建虚拟环境: $VENV_DIR"
        $PYTHON_BIN -m venv "$VENV_DIR"
        ok "虚拟环境创建完成"
    fi

    # 验证虚拟环境
    if [ ! -f "$VENV_DIR/bin/pip" ]; then
        err "虚拟环境 pip 不存在: $VENV_DIR/bin/pip"
        err "尝试重建虚拟环境..."
        rm -rf "$VENV_DIR"
        $PYTHON_BIN -m venv "$VENV_DIR"
        ok "虚拟环境重建完成"
    fi

    ok "虚拟环境路径: $VENV_DIR"
    ok "pip 版本: $($VENV_DIR/bin/pip --version 2>&1)"
}

# ================================================================
# STEP 3: 安装依赖
# ================================================================
install_deps() {
    step "3/9  安装依赖"

    cd "$PROJECT_DIR"

    info "安装 requirements.txt ..."
    "$VENV_DIR/bin/pip" install --upgrade pip -i https://mirrors.tencent.com/pypi/simple/ 2>&1 | tail -3
    "$VENV_DIR/bin/pip" install -r requirements.txt -i https://mirrors.tencent.com/pypi/simple/ 2>&1 | tail -5

    # 验证关键依赖
    for pkg in django openpyxl gunicorn; do
        if "$VENV_DIR/bin/pip" show $pkg &>/dev/null; then
            ver=$("$VENV_DIR/bin/pip" show $pkg 2>/dev/null | grep Version | awk '{print $2}')
            ok "$pkg==$ver"
        else
            err "$pkg 未安装成功"
            exit 1
        fi
    done
}

# ================================================================
# STEP 4: 数据库迁移 + 初始数据
# ================================================================
setup_database() {
    step "4/9  数据库迁移"

    cd "$PROJECT_DIR"
    export DJANGO_SETTINGS_MODULE=ifrs17_core.settings_prod

    info "执行 migrate ..."
    "$VENV_DIR/bin/python" manage.py migrate --noinput 2>&1 | tail -10
    ok "数据库迁移完成"

    info "加载初始数据 ..."
    "$VENV_DIR/bin/python" manage.py init_data 2>&1 | tail -5
    ok "初始数据加载完成"

    # 创建超级用户（如果不存在）
    "$VENV_DIR/bin/python" -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings_prod')
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', '', 'admin123')
    print('超级用户创建: admin/admin123')
else:
    print('超级用户已存在: admin')
" 2>&1
    ok "用户检查完成"
}

# ================================================================
# STEP 5: 收集静态文件
# ================================================================
collect_static() {
    step "5/9  收集静态文件"

    cd "$PROJECT_DIR"
    export DJANGO_SETTINGS_MODULE=ifrs17_core.settings_prod

    info "执行 collectstatic ..."
    "$VENV_DIR/bin/python" manage.py collectstatic --noinput 2>&1 | tail -5
    ok "静态文件收集完成: $PROJECT_DIR/staticfiles/"
}

# ================================================================
# STEP 6: 创建日志/PID 目录
# ================================================================
setup_dirs() {
    step "6/9  创建日志和 PID 目录"

    mkdir -p "$LOG_DIR" "$PID_DIR"
    
    # 获取宝塔运行用户
    BT_USER="www"
    chown -R $BT_USER:$BT_USER "$LOG_DIR" "$PID_DIR" 2>/dev/null || true
    chown -R $BT_USER:$BT_USER "$PROJECT_DIR" 2>/dev/null || true

    ok "日志目录: $LOG_DIR"
    ok "PID 目录: $PID_DIR"
    ok "项目权限: $BT_USER:$BT_USER"
}

# ================================================================
# STEP 7: 配置 Nginx
# ================================================================
setup_nginx() {
    step "7/9  配置 Nginx 反向代理"

    # 查找宝塔为 Python 项目生成的 Nginx 配置文件
    NGINX_CONF=""
    for f in \
        "$NGINX_CONF_DIR/python_ifrs17-system.conf" \
        "$NGINX_CONF_DIR/ifrs17-system.conf" \
        "$NGINX_CONF_DIR/ifrs17_backend.com.conf"; do
        if [ -f "$f" ]; then
            NGINX_CONF="$f"
            break
        fi
    done

    # 查找 rewrite 配置
    REWRITE_CONF="$NGINX_CONF_DIR/rewrite/python_ifrs17-system.conf"
    if [ -f "$REWRITE_CONF" ]; then
        info "rewrite 配置存在: $REWRITE_CONF"
    fi

    # 修复 well-known 配置（解决 "if directive is not allowed here"）
    WELL_KNOWN_CONF="$NGINX_CONF_DIR/well-known/ifrs17-system.conf"
    if [ -f "$WELL_KNOWN_CONF" ]; then
        info "修复 well-known 配置 ..."
        cat > "$WELL_KNOWN_CONF" << 'WKEOF'
location ^~ /.well-known/acme-challenge/ {
    allow all;
    root /www/wwwroot/ifrs17-system;
}
WKEOF
        ok "well-known 配置已修复: $WELL_KNOWN_CONF"
    fi

    # 修复 Nginx 主配置中的 proxy buffer 约束
    NGINX_MAIN_CONF="/www/server/nginx/conf/nginx.conf"
    if [ -f "$NGINX_MAIN_CONF" ]; then
        if grep -q "proxy_temp_file_write_size" "$NGINX_MAIN_CONF"; then
            info "检查 nginx.conf proxy buffer 设置 ..."
            BUF_SIZE=$(grep "proxy_buffer_size" "$NGINX_MAIN_CONF" | head -1 | awk '{print $2}' | tr -d ';')
            BUF_SINGLE=$(grep "proxy_buffers" "$NGINX_MAIN_CONF" | head -1 | awk '{print $3}' | tr -d ';')
            TEMP_SIZE=$(grep "proxy_temp_file_write_size" "$NGINX_MAIN_CONF" | head -1 | awk '{print $2}' | tr -d ';')
            info "  proxy_buffer_size=$BUF_SIZE, proxy_buffers单个=$BUF_SINGLE, proxy_temp_file_write_size=$TEMP_SIZE"
            
            # 计算需要的最小值
            if [ -n "$BUF_SIZE" ] && [ -n "$BUF_SINGLE" ] && [ -n "$TEMP_SIZE" ]; then
                BUF_SIZE_NUM=$(echo $BUF_SIZE | tr -dc '0-9')
                BUF_SINGLE_NUM=$(echo $BUF_SINGLE | tr -dc '0-9')
                TEMP_SIZE_NUM=$(echo $TEMP_SIZE | tr -dc '0-9')
                MAX_BUF=$((BUF_SIZE_NUM > BUF_SINGLE_NUM ? BUF_SIZE_NUM : BUF_SINGLE_NUM))
                if [ $TEMP_SIZE_NUM -lt $MAX_BUF ]; then
                    warn "proxy_temp_file_write_size ($TEMP_SIZE) < max($BUF_SIZE, $BUF_SINGLE) = ${MAX_BUF}k"
                    info "修复: proxy_temp_file_write_size ${MAX_BUF}k"
                    sed -i "s/proxy_temp_file_write_size.*/proxy_temp_file_write_size ${MAX_BUF}k;/" "$NGINX_MAIN_CONF"
                    ok "nginx.conf proxy buffer 已修复"
                else
                    ok "nginx.conf proxy buffer 约束正常"
                fi
            fi
        fi
    fi

    # 如果找到宝塔的 Nginx 配置文件，修正 proxy_pass 端口
    if [ -n "$NGINX_CONF" ]; then
        info "宝塔 Nginx 配置文件: $NGINX_CONF"
        
        # 检查当前 proxy_pass 端口
        CURRENT_PORT=$(grep "proxy_pass" "$NGINX_CONF" | grep -oP ':\K[0-9]+' | head -1)
        info "当前 proxy_pass 端口: $CURRENT_PORT"
        
        if [ "$CURRENT_PORT" != "$GUNICORN_PORT" ]; then
            warn "端口不匹配！proxy_pass=$CURRENT_PORT, Gunicorn=$GUNICORN_PORT"
            info "修正 proxy_pass 端口为 $GUNICORN_PORT ..."
            sed -i "s|proxy_pass http://127.0.0.1:[0-9]*|proxy_pass http://127.0.0.1:$GUNICORN_PORT|g" "$NGINX_CONF"
            ok "proxy_pass 已修正为 8080"
        else
            ok "proxy_pass 端口已正确 ($GUNICORN_PORT)"
        fi

        # 添加 proxy_temp_file_write_size（如果缺失）
        if ! grep -q "proxy_temp_file_write_size" "$NGINX_CONF"; then
            info "添加 proxy_temp_file_write_size 256k ..."
            sed -i '/proxy_busy_buffers_size/a\        proxy_temp_file_write_size 256k;' "$NGINX_CONF"
            ok "proxy_temp_file_write_size 已添加"
        fi

        # 确保有 client_max_body_size
        if ! grep -q "client_max_body_size" "$NGINX_CONF"; then
            info "添加 client_max_body_size 50M ..."
            sed -i '/location \/ {/i\    client_max_body_size 50M;' "$NGINX_CONF"
            ok "client_max_body_size 已添加"
        fi

    else
        warn "未找到宝塔自动生成的 Nginx 配置文件"
        warn "请手动将项目目录 deploy/nginx_baota_corrected.conf 的内容"
        warn "复制到宝塔 Python 项目管理器 → 配置文件 中"
        
        # 尝试用部署目录中的配置文件
        DEPLOY_CONF="$PROJECT_DIR/deploy/nginx_baota_corrected.conf"
        if [ -f "$DEPLOY_CONF" ]; then
            info "部署配置文件已就绪: $DEPLOY_CONF"
            info "请在宝塔面板手动应用此配置"
        fi
    fi

    # 测试 Nginx 配置
    info "测试 Nginx 配置 ..."
    if $NGINX_BIN -t 2>&1; then
        ok "Nginx 配置测试通过"
    else
        err "Nginx 配置测试失败！"
        warn "请检查上面的错误信息"
        # 不退出，继续执行
    fi

    # 重载 Nginx
    info "重载 Nginx ..."
    $NGINX_BIN -s reload 2>&1 || {
        warn "Nginx reload 失败，尝试重启 ..."
        # 通过宝塔重启
        if [ -f "/etc/init.d/nginx" ]; then
            /etc/init.d/nginx restart 2>&1
        fi
    }
    ok "Nginx 已重载"
}

# ================================================================
# STEP 8: 防火墙 + 安全组提示
# ================================================================
setup_firewall() {
    step "8/9  防火墙配置"

    # firewalld
    if command -v firewall-cmd &>/dev/null; then
        info "检测到 firewalld ..."
        for port in 80 8080 443; do
            if ! firewall-cmd --list-ports 2>/dev/null | grep -qw "$port/tcp"; then
                firewall-cmd --permanent --add-port=$port/tcp 2>&1
                ok "firewalld 放行端口: $port"
            else
                ok "firewalld 端口已放行: $port"
            fi
        done
        firewall-cmd --reload 2>&1
        ok "firewalld 已重载"
    fi

    # ufw
    if command -v ufw &>/dev/null; then
        info "检测到 ufw ..."
        for port in 80 8080 443; do
            ufw allow $port/tcp 2>&1
            ok "ufw 放行端口: $port"
        done
    fi

    # iptables (宝塔自带)
    if [ -f "/www/server/panel/data/iptables.json" ]; then
        info "检测到宝塔防火墙 ..."
        for port in 80 8080 443; do
            iptables -C INPUT -p tcp --dport $port -j ACCEPT 2>/dev/null || \
            iptables -I INPUT -p tcp --dport $port -j ACCEPT 2>&1
            ok "iptables 放行端口: $port"
        done
    fi

    # 阿里云安全组提醒
    echo ""
    echo -e "${YELLOW}┌─────────────────────────────────────────────────────────┐${NC}"
    echo -e "${YELLOW}│  ⚠️  阿里云安全组提醒                                     │${NC}"
    echo -e "${YELLOW}│  请在阿里云控制台 → ECS → 安全组 → 入方向规则中放行：     │${NC}"
    echo -e "${YELLOW}│    • 80/tcp   (HTTP)                                      │${NC}"
    echo -e "${YELLOW}│    • 443/tcp  (HTTPS, 后续SSL)                            │${NC}"
    echo -e "${YELLOW}│    • 8080/tcp (调试用，部署成功后可关闭)                   │${NC}"
    echo -e "${YELLOW}└─────────────────────────────────────────────────────────┘${NC}"
    echo ""
}

# ================================================================
# STEP 9: 启动服务 + 验证
# ================================================================
start_and_verify() {
    step "9/9  启动服务 + 验证"

    # 停止旧的 Gunicorn 进程
    info "停止旧 Gunicorn 进程 ..."
    pkill -f "gunicorn.*ifrs17" 2>/dev/null || true
    sleep 2

    # 通过宝塔启动 Gunicorn（如果宝塔 Python 项目管理器存在）
    BT_PYTHON_MGR="/www/server/panel/script/python_manager.py"
    if [ -f "$BT_PYTHON_MGR" ]; then
        info "通过宝塔启动 Python 项目 ..."
        python3 "$BT_PYTHON_MGR" start ifrs17-system 2>/dev/null || true
        sleep 3
    fi

    # 检查 Gunicorn 是否在运行
    sleep 2
    if ss -tlnp | grep -q ":$GUNICORN_PORT"; then
        ok "Gunicorn 监听端口 $GUNICORN_PORT"
    else
        warn "Gunicorn 未在 $GUNICORN_PORT 端口监听"
        info "尝试手动启动 ..."
        cd "$PROJECT_DIR"
        export DJANGO_SETTINGS_MODULE=ifrs17_core.settings_prod
        # 使用优化配置文件启动（节省内存）
        GUNICORN_CONF="$PROJECT_DIR/gunicorn_config_baota.py"
        if [ -f "$GUNICORN_CONF" ]; then
            info "使用 gunicorn_config_baota.py 启动 ..."
            nohup "$VENV_DIR/bin/gunicorn" \
                -c "$GUNICORN_CONF" \
                ifrs17_core.wsgi:application > "$LOG_DIR/gunicorn_stdout.log" 2>&1 &
        else
            info "配置文件不存在，使用命令行参数启动 ..."
            nohup "$VENV_DIR/bin/gunicorn" \
                --bind 127.0.0.1:$GUNICORN_PORT \
                --workers 2 \
                --timeout 60 \
                --preload \
                --max-requests 500 \
                --max-requests-jitter 50 \
                --chdir "$PROJECT_DIR" \
                --env DJANGO_SETTINGS_MODULE=ifrs17_core.settings_prod \
                --error-logfile "$LOG_DIR/gunicorn_error.log" \
                ifrs17_core.wsgi:application > "$LOG_DIR/gunicorn_stdout.log" 2>&1 &
        fi
        sleep 3
        if ss -tlnp | grep -q ":$GUNICORN_PORT"; then
            ok "Gunicorn 手动启动成功 (端口 $GUNICORN_PORT)"
        else
            err "Gunicorn 启动失败！"
            err "查看日志: tail -50 $LOG_DIR/gunicorn_error.log"
            exit 1
        fi
    fi

    # 本地测试 Gunicorn
    info "本地测试 Gunicorn ..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$GUNICORN_PORT/login/ 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        ok "Gunicorn 响应正常 (HTTP 200)"
    elif [ "$HTTP_CODE" = "302" ]; then
        ok "Gunicorn 响应正常 (HTTP 302 重定向)"
    else
        warn "Gunicorn 响应异常 (HTTP $HTTP_CODE)"
    fi

    # 本地测试 Nginx (80端口)
    info "本地测试 Nginx (80端口) ..."
    HTTP_CODE_80=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:80/login/ 2>/dev/null || echo "000")
    if [ "$HTTP_CODE_80" = "200" ] || [ "$HTTP_CODE_80" = "302" ]; then
        ok "Nginx 80端口响应正常 (HTTP $HTTP_CODE_80)"
    else
        warn "Nginx 80端口响应异常 (HTTP $HTTP_CODE_80)"
        warn "可能 Nginx 未启动或配置有误"
    fi

    # ===== 部署报告 =====
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}                     ✅  部署完成报告                         ${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo -e "  项目目录:   ${BLUE}$PROJECT_DIR${NC}"
    echo -e "  虚拟环境:   ${BLUE}$VENV_DIR${NC}"
    echo -e "  Gunicorn:   ${BLUE}127.0.0.1:$GUNICORN_PORT${NC}"
    echo -e "  Nginx:      ${BLUE}0.0.0.0:80 → 127.0.0.1:$GUNICORN_PORT${NC}"
    echo -e "  服务器 IP:  ${BLUE}$SERVER_IP${NC}"
    echo ""
    echo -e "  ${YELLOW}访问地址:${NC}"
    echo -e "    ${BLUE}http://$SERVER_IP/${NC}           (自动跳转登录页)"
    echo -e "    ${BLUE}http://$SERVER_IP/login/${NC}     (直接登录页)"
    echo -e "    ${BLUE}http://$SERVER_IP/admin/${NC}     (Django 管理后台)"
    echo ""
    echo -e "  ${YELLOW}登录账号:${NC}"
    echo -e "    管理员:   ${BLUE}admin / admin123${NC}"
    echo ""
    echo -e "  ${YELLOW}日志位置:${NC}"
    echo -e "    Gunicorn: ${BLUE}$LOG_DIR/gunicorn_error.log${NC}"
    echo -e "    Django:   ${BLUE}$LOG_DIR/django.log${NC}"
    echo -e "    Nginx:    ${BLUE}/www/wwwlogs/ifrs17-system.log${NC}"
    echo ""
    echo -e "  ${YELLOW}常用命令:${NC}"
    echo -e "    重启Gunicorn:  ${BLUE}pkill -f gunicorn && cd $PROJECT_DIR && $VENV_DIR/bin/gunicorn -c gunicorn_config_baota.py ifrs17_core.wsgi:application &${NC}"
    echo -e "    重载Nginx:     ${BLUE}$NGINX_BIN -s reload${NC}"
    echo -e "    查看端口:      ${BLUE}ss -tlnp | grep -E '80|8080'${NC}"
    echo ""
    echo -e "  ${RED}⚠️  安全提醒:${NC}"
    echo -e "    1. 部署成功后，在宝塔关闭 8080 外网映射"
    echo -e "    2. 确认阿里云安全组已放行 80 端口"
    echo -e "    3. 如需 HTTPS，在宝塔申请 SSL 证书后设置 IFRS17_USE_HTTPS=1"
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ================================================================
# 主流程
# ================================================================
main() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  IFRS17 预测模型系统 — 一键自动部署                        ║${NC}"
    echo -e "${GREEN}║  宝塔面板 11.8 + 阿里云 ECS                                ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"

    check_environment
    setup_venv
    install_deps
    setup_database
    collect_static
    setup_dirs
    setup_nginx
    setup_firewall
    start_and_verify
}

main "$@"
