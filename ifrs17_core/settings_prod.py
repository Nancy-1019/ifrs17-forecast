"""IFRS17 预测模型系统 — 生产环境配置（宝塔面板适配版）

宝塔面板路径约定:
  项目根目录: /www/wwwroot/ifrs17-system/
  虚拟环境:   /www/wwwroot/ifrs17-system/venv/
  静态文件:   /www/wwwroot/ifrs17-system/staticfiles/
  媒体文件:   /www/wwwroot/ifrs17-system/media/

启用法一（环境变量）:
    export DJANGO_SETTINGS_MODULE=ifrs17_core.settings_prod
    export IFRS17_SECRET_KEY="your-secret-key"

启用法二（gunicorn raw_env，已在 gunicorn_config_baota.py 中配置）:
    gunicorn -c gunicorn_config_baota.py ifrs17_core.wsgi:application
"""

import os
from .settings import *

# ===== 安全 =====
DEBUG = False
ALLOWED_HOSTS = os.environ.get('IFRS17_ALLOWED_HOSTS', '*').split(',')

# 必须修改！用环境变量或生成随机密钥
SECRET_KEY = os.environ.get('IFRS17_SECRET_KEY', SECRET_KEY)

# ===== CSRF 信任源（Django 4.0+ 必须配置，否则 POST 请求被 403 拒绝）=====
# 通过 IP 访问时浏览器发送 Origin: http://121.41.98.55
# 必须将此 origin 加入信任列表，否则登录表单 POST 会被 CSRF 中间件拒绝
_csrf_hosts = os.environ.get('IFRS17_CSRF_TRUSTED_ORIGINS', '')
if _csrf_hosts:
    CSRF_TRUSTED_ORIGINS = [h.strip() for h in _csrf_hosts.split(',') if h.strip()]
else:
    # 默认允许 HTTP 和 HTTPS 下的所有源（通过 IP 或域名访问均可）
    # 生产环境建议通过环境变量 IFRS17_CSRF_TRUSTED_ORIGINS 指定具体域名
    CSRF_TRUSTED_ORIGINS = [
        'http://*',
        'https://*',
    ]

# Cookie SameSite 策略
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SAMESITE = 'Lax'

# ===== 数据库（生产环境强制使用 MySQL）=====
# 生产部署必须连接 MySQL；不再回退 SQLite（避免出现“代码是 MySQL、运行却是 SQLite”的静默问题）。
# 实际连接参数优先取环境变量（与启动脚本 / gunicorn raw_env 一致），若缺失则使用本机 MySQL 默认值，
# 保证即使环境变量未被注入，生产进程也一定走 MySQL 而非 SQLite。
import pymysql
pymysql.install_as_MySQLdb()
DATABASES['default'] = {
    'ENGINE': 'django.db.backends.mysql',
    'NAME': os.environ.get('IFRS17_DB_NAME', 'ifrs17'),
    'USER': os.environ.get('IFRS17_DB_USER', 'ifrs17'),
    'PASSWORD': os.environ.get('IFRS17_DB_PASSWORD', 'lyikPPkMYhr5frt0PRyS'),
    'HOST': os.environ.get('IFRS17_DB_HOST', '127.0.0.1'),
    'PORT': os.environ.get('IFRS17_DB_PORT', '3306'),
    'OPTIONS': {
        'charset': 'utf8mb4',
    },
    'TEST': {
        'CHARSET': 'utf8mb4',
        'COLLATE': 'utf8mb4_unicode_ci',
    },
}

# ===== 安全头 =====
# SECURE_BROWSER_XSS_FILTER 在 Django 4.0+ 已弃用，移除
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Cookie 安全标志 — 仅在 HTTPS 下启用
# 如果 Nginx 尚未配置 SSL 证书，必须设为 False，否则浏览器不会接受
# Cookie，导致登录静默失败（页面刷新后仍处于未登录状态）
_USE_HTTPS = os.environ.get('IFRS17_USE_HTTPS', '0') == '1'
SESSION_COOKIE_SECURE = _USE_HTTPS
CSRF_COOKIE_SECURE = _USE_HTTPS

# 如果 Nginx 配置了 SSL 且通过 proxy_set_header X-Forwarded-Proto 传递，
# 启用以下配置让 Django 正确识别 HTTPS：
# SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
# SECURE_SSL_REDIRECT = True

# ===== 日志 =====
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'WARNING',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/ifrs17/django.log',
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'WARNING',
            'propagate': True,
        },
    },
}
