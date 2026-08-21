#!/usr/bin/env bash
# ============================================================
# IFRS17 web 容器启动入口
# 1) 等待数据库可连接（pymysql 重试）
# 2) 执行迁移
# 3) 收集静态资源
# 4) 启动 Gunicorn（workers=1，计算进度/结果缓存为进程内全局变量）
# ============================================================
set -e

echo "[entrypoint] 等待数据库就绪 (host=${IFRS17_DB_HOST:-db}:${IFRS17_DB_PORT:-3306})..."
python - <<'PY'
import pymysql, time, os, sys
host = os.environ.get('IFRS17_DB_HOST', 'db')
port = int(os.environ.get('IFRS17_DB_PORT', '3306'))
user = os.environ.get('IFRS17_DB_USER', 'ifrs17')
password = os.environ.get('IFRS17_DB_PASSWORD', '')
db = os.environ.get('IFRS17_DB_NAME', 'ifrs17')
ok = False
for i in range(60):
    try:
        conn = pymysql.connect(host=host, port=port, user=user,
                              password=password, database=db, connect_timeout=5)
        conn.close()
        ok = True
        print("[entrypoint] 数据库已就绪")
        break
    except Exception as e:
        print(f"[entrypoint] 等待数据库 ({i+1}/60): {e}")
        time.sleep(2)
if not ok:
    print("[entrypoint] 数据库等待超时，退出")
    sys.exit(1)
PY

echo "[entrypoint] 执行数据库迁移..."
python manage.py migrate --noinput

echo "[entrypoint] 收集静态资源..."
python manage.py collectstatic --noinput || true

echo "[entrypoint] 启动 Gunicorn (workers=1)..."
exec gunicorn ifrs17_core.wsgi:application \
    --bind 0.0.0.0:8080 \
    --workers 1 \
    --timeout 60 \
    --chdir /app \
    --error-logfile /var/log/ifrs17/gunicorn_error.log \
    --access-logfile -
