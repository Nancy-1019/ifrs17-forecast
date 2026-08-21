"""SSH 只读诊断：采集阿里云 ECS 当前状态。需先在本地运行，确认部署前置条件。"""
import paramiko
import sys

HOST = "121.41.98.55"
PORT = 22
USER = "root"
PASS = "Nancy@901019"

SSH_KWARGS = dict(hostname=HOST, port=PORT, username=USER, password=PASS, timeout=30)

def run(client, cmd, label=None):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
    out = stdout.read().decode("utf-8", "replace").strip()
    err = stderr.read().decode("utf-8", "replace").strip()
    code = stdout.channel.recv_exit_status()
    if label:
        print(f"\n=== {label} ===")
    print(out if out else "(无输出)")
    if err and code != 0:
        print(f"[stderr] {err}")
    return out, code

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"连接 {HOST}:{PORT} ...")
    client.connect(**SSH_KWARGS)
    print("SSH 连接成功\n")

    run(client, "uname -a", "系统信息")
    run(client, "cat /etc/os-release | head -3", "OS 发行版")

    # Docker 状态
    run(client, "command -v docker && docker --version || echo 'DOCKER_NOT_INSTALLED'", "Docker 是否已安装")
    run(client, "docker compose version 2>/dev/null || docker-compose --version 2>/dev/null || echo 'COMPOSE_NOT_INSTALLED'", "Docker Compose")

    # 磁盘与内存
    run(client, "df -h / | tail -2", "根分区磁盘")
    run(client, "free -h | head -2", "内存")

    # 宝塔 / 系统 Nginx
    run(client, "/etc/init.d/nginx status 2>/dev/null | head -3 || true", "宝塔 Nginx 状态")
    run(client, "ps aux | grep -E 'nginx|gunicorn' | grep -v grep | head -10", "运行中的 nginx/gunicorn 进程")

    # 现有 MySQL (宿主机)
    run(client, "ps aux | grep -E 'mysqld|mysql' | grep -v grep | head -3", "宿主机 MySQL 进程")
    run(client, "ls -la /www/server/mysql/ 2>/dev/null | head -2 || echo 'no bt mysql'", "宝塔 MySQL 目录")

    # 当前代码版本
    run(client, "grep -oP \"SYSTEM_VERSION\\s*=\\s*'\\K[^']+\" /www/wwwroot/ifrs17-system/ifrs17_core/settings.py 2>/dev/null || echo 'NO_SETTINGS'", "当前代码版本")
    run(client, "ls -la /www/wwwroot/ifrs17-system/docker-compose.yml 2>/dev/null || echo 'NO_DOCKER_FILES'", "服务器是否已有 Docker 文件")
    run(client, "ls -la /www/wwwroot/ifrs17-system/media 2>/dev/null | head -3; du -sh /www/wwwroot/ifrs17-system/media 2>/dev/null", "media 目录体积")

    # 数据库体积 (现有 ifrs17 库)
    run(client, "mysql -uroot -p58772aba7f57276c -e \"SELECT table_schema, ROUND(SUM(data_length+index_length)/1024/1024,2) AS mb FROM information_schema.tables WHERE table_schema='ifrs17' GROUP BY table_schema;\" 2>/dev/null || echo 'MYSQL_QUERY_FAILED'", "ifrs17 库体积(MB)")

    client.close()
    print("\n诊断完成。")

if __name__ == "__main__":
    main()
