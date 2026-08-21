"""本地开发配置 — 使用 MySQL 8.0（与云端数据库引擎/字符集一致）

与 settings.py(SQLite) 并存，不改动后者，便于回退。
用法：
    set DJANGO_SETTINGS_MODULE=ifrs17_core.settings_local_mysql
    python manage.py runserver 127.0.0.1:8000
"""
import os
from .settings import *  # noqa: F401,F403

import pymysql
pymysql.install_as_MySQLdb()

# 本地 MySQL 8.0（utf8mb4），连接参数与云端 settings_prod 同构，
# 默认指向本机 127.0.0.1，可用环境变量覆盖。
DATABASES = {
    'default': {
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
}
