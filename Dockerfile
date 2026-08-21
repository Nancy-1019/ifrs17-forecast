# ============================================================
# IFRS17 新准则预测模型系统 — 生产镜像
# Django + Gunicorn（workers=1，关键：计算进度/结果缓存为进程内全局变量）
# 基础镜像使用 python:3.12-slim；如服务器 venv 用其他 Python 版本，请同步调整。
# ============================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=ifrs17_core.settings_prod \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 注意：不执行 apt-get update（Debian 官方源国内极慢），procps 非运行必需
# settings_prod 的 RotatingFileHandler 与 gunicorn 错误日志依赖此目录
RUN mkdir -p /var/log/ifrs17

# 运行时计算缓存目录（runtime_cache 不进镜像，需显式建目录供应用写缓存）
RUN mkdir -p /app/data_input/runtime_cache

# 先装依赖（利用镜像层缓存，代码变动不必重装）
# 使用阿里云 PyPI 镜像，避免 pypi.org 国内超时
COPY requirements.txt .
RUN pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple \
    && pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple

# 复制项目代码（已通过 .dockerignore 排除 venv/验证文件/doc_build 等大目录）
COPY . .

# 静态资源收集到 STATIC_ROOT=/app/staticfiles，由 nginx 容器直接服务
RUN python manage.py collectstatic --noinput || true

EXPOSE 8080

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
