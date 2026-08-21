"""IFRS17 部署工具模块（Docker 一键部署）
- 管理 SSH 部署配置
- 打包项目代码（排除 .env / mysql 转储 / 凭据 / db / pyc / venv 等）
- 通过 SSH + SFTP 推送代码到阿里云 ECS（/www/wwwroot/ifrs17-system）
- 远程解压后执行 `docker compose up -d --build` 重建 web 镜像
- db 数据卷保留；web 容器 entrypoint 自动执行 migrate + collectstatic
"""
import os
import io
import json
import tarfile
import time
import paramiko
from django.conf import settings
from pathlib import Path

# 部署配置文件路径（不进入版本库）
DEPLOY_CONFIG_FILE = os.path.join(settings.BASE_DIR, 'deploy_config.json')

# 默认部署配置
DEFAULT_CONFIG = {
    'host': '121.41.98.55',
    'port': 22,
    'username': 'root',
    'password': '',
    'private_key_path': '',
    'remote_project_dir': '/www/wwwroot/ifrs17-system',
    'remote_temp_archive': '/tmp/ifrs17-deploy.tar.gz',
    'force_rebuild': False,
}

# 打包时排除的目录和文件模式
EXCLUDE_DIRS = {
    '__pycache__', '.pyc', 'venv', '.venv', 'env',
    'staticfiles', 'media', '.git', 'node_modules',
    'screenshots', 'mysql', 'runtime_cache',
}

EXCLUDE_FILES = {
    'db.sqlite3', 'deploy_config.json', '.gitignore',
    'baota-deploy-tutorial.html', 'baota-deploy-guide.md',
    '.env', '.wb_mysql_creds.json',
}

EXCLUDE_EXTENSIONS = {
    '.pyc', '.pyo', '.log', '.sqlite3', '.tar.gz',
    '.md', '.bat',
}


def load_deploy_config():
    """加载部署配置，如果不存在则返回默认配置"""
    if os.path.exists(DEPLOY_CONFIG_FILE):
        try:
            with open(DEPLOY_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # 合并默认值（防止缺少字段）
            merged = DEFAULT_CONFIG.copy()
            merged.update(config)
            return merged
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_CONFIG.copy()


def save_deploy_config(config):
    """保存部署配置到本地文件"""
    # 只保存已知字段
    clean = {}
    for key in DEFAULT_CONFIG:
        if key in config:
            clean[key] = config[key]
    with open(DEPLOY_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(clean, f, ensure_ascii=False, indent=2)
    return clean


def get_masked_config():
    """返回脱敏的配置（密码只显示是否已设置）"""
    config = load_deploy_config()
    has_password = bool(config.get('password'))
    has_key = bool(config.get('private_key_path'))
    return {
        'host': config['host'],
        'port': config['port'],
        'username': config['username'],
        'password_set': has_password,
        'private_key_path': config.get('private_key_path', ''),
        'private_key_set': has_key,
        'remote_project_dir': config['remote_project_dir'],
        'remote_temp_archive': config['remote_temp_archive'],
        'force_rebuild': config.get('force_rebuild', False),
    }


def _should_exclude(path_name, is_dir=False):
    """判断文件/目录是否应该被排除"""
    name = os.path.basename(path_name)

    if is_dir:
        return name in EXCLUDE_DIRS

    # 排除特定文件
    if name in EXCLUDE_FILES:
        return True

    # 排除特定扩展名
    _, ext = os.path.splitext(name)
    if ext.lower() in EXCLUDE_EXTENSIONS:
        return True

    # 排除 .tar.gz
    if name.endswith('.tar.gz'):
        return True

    return False


def create_project_archive(progress_callback=None):
    """创建项目代码的 tar.gz 归档

    Args:
        progress_callback: 可选回调函数 (current, total, filename)

    Returns:
        bytes: tar.gz 文件内容
    """
    base_dir = settings.BASE_DIR
    buf = io.BytesIO()

    # 先收集所有要打包的文件
    files_to_pack = []
    for root, dirs, files in os.walk(base_dir):
        # 过滤排除目录（原地修改 dirs 影响 walk 遍历）
        dirs[:] = [d for d in dirs if not _should_exclude(os.path.join(root, d), is_dir=True)]
        for fname in files:
            full_path = os.path.join(root, fname)
            if _should_exclude(full_path):
                continue
            # 计算相对路径（跳过跨盘符/特殊设备文件）
            try:
                rel_path = os.path.relpath(full_path, base_dir).replace('\\', '/')
            except ValueError:
                continue
            files_to_pack.append((full_path, rel_path))

    total = len(files_to_pack)

    with tarfile.open(fileobj=buf, mode='w:gz') as tar:
        for i, (full_path, rel_path) in enumerate(files_to_pack):
            tar.add(full_path, arcname=rel_path)
            if progress_callback and i % 20 == 0:
                progress_callback(i + 1, total, rel_path)

    if progress_callback:
        progress_callback(total, total, '完成')

    buf.seek(0)
    return buf.getvalue(), total


def create_ssh_client(config):
    """创建 SSH 客户端连接"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs = {
        'hostname': config['host'],
        'port': config.get('port', 22),
        'username': config['username'],
        'timeout': 30,
    }

    # 优先使用密钥认证
    key_path = config.get('private_key_path', '')
    if key_path and os.path.exists(key_path):
        connect_kwargs['key_filename'] = key_path
    elif config.get('password'):
        connect_kwargs['password'] = config['password']
    else:
        raise ValueError('未配置密码或私钥路径，无法建立 SSH 连接')

    client.connect(**connect_kwargs)
    return client


def verify_deployed_version(config):
    """部署后验证：检查服务器上的代码版本、静态文件版本、缓存头是否正确

    Returns:
        str: 验证结果描述
    """
    try:
        client = create_ssh_client(config)
        remote_dir = config['remote_project_dir']
        parts = []

        # 检查 settings.py 中的版本
        stdin, stdout, stderr = client.exec_command(
            f"grep -oP \"SYSTEM_VERSION\\s*=\\s*'\\K[^']+\" {remote_dir}/ifrs17_core/settings.py"
        )
        settings_version = stdout.read().decode('utf-8', errors='replace').strip()

        # 检查 static/js/config.js 中的版本
        stdin, stdout, stderr = client.exec_command(
            f"grep -oP \"version:\\s*'\\K[^']+\" {remote_dir}/static/js/config.js"
        )
        js_version = stdout.read().decode('utf-8', errors='replace').strip()

        # 检查 Nginx 返回的登录页是否包含该版本
        stdin, stdout, stderr = client.exec_command(
            f"curl -s http://127.0.0.1:80/login/ | grep -oP '{settings_version}' | head -1"
        )
        nginx_version = stdout.read().decode('utf-8', errors='replace').strip()

        # 检查 HTML 响应的 Cache-Control 头
        stdin, stdout, stderr = client.exec_command(
            f"curl -sI http://127.0.0.1:80/login/ | grep -i cache-control | tr -d '\\r'"
        )
        cache_header = stdout.read().decode('utf-8', errors='replace').strip()

        # 检查 Docker 容器状态（Docker 部署模式下）
        try:
            stdin, stdout, stderr = client.exec_command(
                f"cd {remote_dir} && docker compose ps 2>/dev/null"
            )
            docker_ps = stdout.read().decode('utf-8', errors='replace').strip()
            if docker_ps:
                parts.append('容器状态: ' + ' | '.join(
                    l.strip() for l in docker_ps.split('\n') if l.strip()
                ))
        except Exception:
            pass

        client.close()

        if settings_version:
            parts.append(f'代码版本: {settings_version}')
        if js_version:
            parts.append(f'静态文件版本: {js_version}')
        if nginx_version:
            parts.append('Nginx 页面已生效')
        
        if cache_header and ('no-store' in cache_header or 'no-cache' in cache_header):
            parts.append('HTML 缓存控制: 已生效 (无需手动刷新)')
        elif cache_header:
            parts.append(f'HTML 缓存控制: {cache_header}')
        else:
            parts.append('HTML 缓存控制: 未检测到 (可能需要 Ctrl+F5)')

        if settings_version and js_version and settings_version == js_version:
            return f'通过 ({", ".join(parts)})'
        else:
            return f'警告 ({", ".join(parts)})'
    except Exception as e:
        return f'验证失败: {str(e)}'


def test_ssh_connection(config):
    """测试 SSH 连接是否正常

    Returns:
        dict: {'success': bool, 'message': str, 'server_info': str}
    """
    try:
        client = create_ssh_client(config)
        stdin, stdout, stderr = client.exec_command('uname -a && whoami && df -h / | tail -1')
        output = stdout.read().decode('utf-8', errors='replace').strip()
        err = stderr.read().decode('utf-8', errors='replace').strip()
        client.close()

        if output:
            return {
                'success': True,
                'message': 'SSH 连接成功',
                'server_info': output,
            }
        else:
            return {
                'success': False,
                'message': f'SSH 连接成功但无输出: {err}',
                'server_info': '',
            }
    except paramiko.AuthenticationException:
        return {'success': False, 'message': '认证失败：用户名或密码/密钥不正确', 'server_info': ''}
    except paramiko.SSHException as e:
        return {'success': False, 'message': f'SSH 连接错误: {str(e)}', 'server_info': ''}
    except Exception as e:
        return {'success': False, 'message': f'连接失败: {str(e)}', 'server_info': ''}


def deploy_to_cloud(config=None, log_callback=None):
    """执行完整的部署流程

    Args:
        config: 部署配置，如果为 None 则从配置文件加载
        log_callback: 可选回调函数 (message: str) 用于实时输出日志

    Returns:
        dict: {'success': bool, 'log': str, 'file_count': int, 'duration': float}
    """
    if config is None:
        config = load_deploy_config()

    log_lines = []

    def log(msg):
        log_lines.append(msg)
        if log_callback:
            log_callback(msg)

    start_time = time.time()

    # ---- 步骤 1: 打包项目代码 ----
    log('=' * 50)
    log('步骤 1/4: 打包项目代码')
    log('=' * 50)

    def pack_progress(current, total, filename):
        if current % 50 == 0 or current == total:
            log(f'  打包进度: {current}/{total} 文件 ({filename})')

    try:
        archive_data, file_count = create_project_archive(pack_progress)
        archive_size_mb = len(archive_data) / (1024 * 1024)
        log(f'  打包完成: {file_count} 个文件, {archive_size_mb:.1f} MB')
    except Exception as e:
        log(f'  [错误] 打包失败: {str(e)}')
        return {'success': False, 'log': '\n'.join(log_lines), 'file_count': 0, 'duration': time.time() - start_time}

    # ---- 步骤 2: 建立 SSH 连接 ----
    log('')
    log('=' * 50)
    log('步骤 2/4: 连接云服务器')
    log('=' * 50)
    log(f'  服务器: {config["host"]}:{config.get("port", 22)}')
    log(f'  用户名: {config["username"]}')

    try:
        client = create_ssh_client(config)
        log('  SSH 连接成功')
    except Exception as e:
        log(f'  [错误] SSH 连接失败: {str(e)}')
        return {'success': False, 'log': '\n'.join(log_lines), 'file_count': file_count, 'duration': time.time() - start_time}

    # ---- 步骤 3: 上传归档文件 ----
    log('')
    log('=' * 50)
    log('步骤 3/4: 上传代码到云服务器')
    log('=' * 50)
    log(f'  上传到: {config["remote_temp_archive"]}')
    log(f'  项目目录: {config["remote_project_dir"]}')

    try:
        sftp = client.open_sftp()

        # 确保临时目录存在
        remote_tmp_dir = os.path.dirname(config['remote_temp_archive'])
        try:
            sftp.stat(remote_tmp_dir)
        except FileNotFoundError:
            pass  # /tmp 一定存在

        # 上传文件（通过 BytesIO）
        log(f'  正在上传 {archive_size_mb:.1f} MB ...')
        with sftp.file(config['remote_temp_archive'], 'wb') as remote_file:
            remote_file.write(archive_data)
        log('  上传完成')

        # 验证文件大小
        remote_stat = sftp.stat(config['remote_temp_archive'])
        remote_size_mb = remote_stat.st_size / (1024 * 1024)
        log(f'  服务器端文件大小: {remote_size_mb:.1f} MB')

        sftp.close()
    except Exception as e:
        log(f'  [错误] 上传失败: {str(e)}')
        client.close()
        return {'success': False, 'log': '\n'.join(log_lines), 'file_count': file_count, 'duration': time.time() - start_time}

    # ---- 步骤 4: 远程解压并重建 Docker 容器 ----
    log('')
    log('=' * 50)
    log('步骤 4/4: 解压代码并重建 Docker 容器')
    log('=' * 50)

    remote_dir = config['remote_project_dir']
    temp_archive = config['remote_temp_archive']

    # 构建远程执行命令（Docker 部署：解压后 docker compose up -d --build）
    # force_rebuild=True 时追加 --no-cache（依赖/系统包有变化时勾选）
    build_flags = '--no-cache' if config.get('force_rebuild') else ''

    # 解压并重建：db 数据卷保留；web 镜像用新代码；
    # web 容器 entrypoint 自动执行 migrate + collectstatic
    remote_cmd = f"""
set -e
cd {remote_dir}
echo "正在解压代码包..."
tar xzf {temp_archive} -C {remote_dir}
echo "解压完成"
echo ""
echo "重建 Docker 容器（web 镜像使用新代码，db/mysql 数据卷保留）..."
docker compose up -d --build {build_flags}
echo ""
echo "--- 容器状态 ---"
docker compose ps
echo ""
echo "等待 web 容器 entrypoint 完成迁移/静态收集..."
sleep 15
echo "清理临时文件..."
rm -f {temp_archive}
echo "Docker 部署完成"
"""

    try:
        stdin, stdout, stderr = client.exec_command(remote_cmd, timeout=300)
        # 实时读取输出
        while True:
            line = stdout.readline()
            if not line and stdout.channel.exit_status_ready():
                break
            if line:
                log(line.rstrip())

        exit_code = stdout.channel.recv_exit_status()
        err_output = stderr.read().decode('utf-8', errors='replace').strip()

        if err_output:
            log(f'\n[stderr]: {err_output}')

        client.close()

        if exit_code == 0:
            log('\n' + '=' * 50)
            log('部署成功! 系统已更新，Docker 容器已重建')
            log('=' * 50)
            duration = time.time() - start_time
            log(f'总耗时: {duration:.1f} 秒')
            log(f'云地址: http://{config["host"]}/')

            # 部署后验证：检查服务器版本是否一致
            log('\n')
            log('正在进行部署后验证...')
            verify_result = verify_deployed_version(config)
            if verify_result:
                log(f'  服务器版本验证: {verify_result}')
            else:
                log('  [警告] 无法连接到服务器进行版本验证')

            return {'success': True, 'log': '\n'.join(log_lines), 'file_count': file_count, 'duration': duration}
        else:
            log(f'\n[错误] 远程执行失败，退出码: {exit_code}')
            return {'success': False, 'log': '\n'.join(log_lines), 'file_count': file_count, 'duration': time.time() - start_time}

    except Exception as e:
        log(f'\n[错误] 远程执行异常: {str(e)}')
        client.close()
        return {'success': False, 'log': '\n'.join(log_lines), 'file_count': file_count, 'duration': time.time() - start_time}
