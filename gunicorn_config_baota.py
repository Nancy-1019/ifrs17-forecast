"""Gunicorn 生产配置 — IFRS17 预测模型系统（宝塔面板适配）

优化要点（节省服务器资源）:
  - workers 固定为 1（关键：计算进度 _CALC_PROGRESS 与结果缓存 _CALC_CACHE /
    _CALC_RESULTS_MAP 都是进程内全局变量；若 workers>1，前端轮询进度 / 取结果的
    请求可能被分配到不同 worker，导致进度永远显示 0%、结果取不到。单 worker 保证
    状态共享，彻底消除"计算卡在 0%"的假象）
  - preload_app = True（预加载应用，worker 共享内存，节省 30-50% RAM）
  - max_requests = 500（定期回收 worker，防止内存泄漏）
  - accesslog = None（关闭访问日志，低流量站点不需要，省 I/O）
  - timeout = 60（缩短超时，避免 worker 长时间被占用；计算在后台线程跑，不受此限）

宝塔面板路径约定:
  - 项目根目录: /www/wwwroot/ifrs17-system/
  - 日志目录:   /var/log/ifrs17/
  - PID 目录:   /var/run/ifrs17/
"""
import os

# 绑定地址（宝塔 Nginx 反向代理到此处）
bind = "127.0.0.1:8080"

# Worker 进程数：固定为 1
# 原因见文件头说明——计算进度/结果缓存是进程内全局变量，多 worker 会导致前端轮询
# 进度/取结果时命中不同进程而看不到状态（表现为"计算卡在 0%"）。单 worker 保证状态
# 一致。小规格 ECS 下 1 个 worker 足够承载本内部工具；若日后需要多 worker 并发，
# 应先将 _CALC_PROGRESS/_CALC_CACHE/_CALC_RESULTS_MAP 改为文件/Redis 共享存储。
workers = 1

# Worker 类型
worker_class = "sync"

# 每个 worker 最大请求数（防止内存泄漏，定期回收重启 worker）
max_requests = 500
max_requests_jitter = 50

# 超时设置（文件上传 openpyxl 解析可能较慢，60 秒足够）
timeout = 60
graceful_timeout = 20

# 日志 — 仅保留 error 日志，关闭 access 日志（低流量站点无需记录每个请求）
accesslog = None
errorlog = "/var/log/ifrs17/gunicorn_error.log"
loglevel = "warning"

# 进程命名
proc_name = "ifrs17-system"

# 守护进程模式
daemon = True

# 预加载应用（worker 共享代码内存，节省 30-50% RAM）
preload_app = True

# PID 文件
pidfile = "/tmp/gunicorn-ifrs17.pid"

# 设置工作目录
chdir = "/www/wwwroot/ifrs17-system"

# 环境变量（生产模式）
raw_env = [
    "DJANGO_SETTINGS_MODULE=ifrs17_core.settings_prod",
    # 生产数据库（MySQL 5.7，宝塔安装）
    "IFRS17_DB_HOST=127.0.0.1",
    "IFRS17_DB_NAME=ifrs17",
    "IFRS17_DB_USER=ifrs17",
    "IFRS17_DB_PASSWORD=lyikPPkMYhr5frt0PRyS",
    "IFRS17_DB_PORT=3306",
]
