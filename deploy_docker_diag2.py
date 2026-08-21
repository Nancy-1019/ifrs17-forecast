"""SSH 第二波诊断：确认停主机 MySQL 是否安全、宝塔面板端口、联网下载能力。"""
import paramiko

HOST = "121.41.98.55"; PORT = 22; USER = "root"; PASS = "Nancy@901019"
KW = dict(hostname=HOST, port=PORT, username=USER, password=PASS, timeout=30)

def run(client, cmd, label=None):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    code = stdout.channel.recv_exit_status()
    if label: print(f"\n=== {label} ===")
    print(out if out else "(无输出)")
    if err and code != 0: print(f"[stderr] {err}")
    return out, code

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(**KW)
print("SSH OK")

# 非系统数据库列表（判断停主机 MySQL 是否安全）
run(client,
    "mysql -uroot -p58772aba7f57276c -e \"SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT IN ('information_schema','performance_schema','mysql','sys');\" 2>/dev/null || echo QUERY_FAIL",
    "主机 MySQL 中的非系统数据库")

# 宝塔面板端口与进程
run(client, "cat /www/server/panel/data/port.pl 2>/dev/null || echo 'NO_PANEL_PORT_FILE'", "宝塔面板端口")
run(client, "ps aux | grep -i panel | grep -v grep | head -3", "宝塔面板进程")

# 主机 MySQL 是否仅被 ifrs17 使用（看连接）
run(client, "mysql -uroot -p58772aba7f57276c -e \"SELECT db, COUNT(*) c FROM information_schema.processlist WHERE db IS NOT NULL GROUP BY db;\" 2>/dev/null || echo QUERY_FAIL", "当前 MySQL 连接按库分布")

# 联网下载能力（Docker 安装源）
run(client, "curl -sI --max-time 8 https://download.docker.com 2>/dev/null | head -1 || echo 'NO_INTERNET_DOCKER_COM'", "能否访问 docker 官方源")
run(client, "curl -sI --max-time 8 https://mirrors.aliyun.com/docker-ce 2>/dev/null | head -1 || echo 'NO_ALIYUN_MIRROR'", "能否访问阿里云 Docker 镜像源")
run(client, "command -v dnf yum apt-get 2>/dev/null", "包管理器")

# 现有 gunicorn 启动方式（回滚用）
run(client, "cat /www/wwwroot/ifrs17-system/gunicorn_config_baota.py 2>/dev/null | head -20", "现有 gunicorn 配置")
run(client, "ls /www/wwwroot/ifrs17-system/start_gunicorn.sh 2>/dev/null && head -20 /www/wwwroot/ifrs17-system/start_gunicorn.sh", "现有启动脚本")

# swap 现状
run(client, "free -h | tail -1; swapon --show 2>/dev/null || echo 'NO_SWAP'", "当前 swap")

client.close()
print("\n诊断2完成。")
