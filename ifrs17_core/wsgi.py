"""WSGI config for ifrs17_core project."""
import os
from django.core.wsgi import get_wsgi_application

# 生产环境经 Gunicorn 启动时一律使用 settings_prod（强制 MySQL）。
# 注：本环境 gunicorn 的 raw_env 未被正确注入，故此处直接默认 settings_prod，
# 保证生产进程必然走 MySQL，而不会静默回退到基础 settings 的 SQLite。
# 本地开发使用 manage.py runserver，其 DJANGO_SETTINGS_MODULE 由 manage.py 显式设为
# ifrs17_core.settings（SQLite），不受此默认值影响。
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings_prod')
application = get_wsgi_application()
