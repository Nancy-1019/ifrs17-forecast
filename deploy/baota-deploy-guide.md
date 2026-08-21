# IFRS17 预测模型系统 — 宝塔面板 11.8 部署指南

> 目标：将 Django 6.0 + SQLite 系统部署到阿里云 ECS，通过宝塔面板 11.8 管理
> 
> 更新：适配宝塔 11.8.0（2026-06-09 发布）— AI面板、智能依赖分析、一键性能调优

---

## 第一阶段：阿里云 ECS 准备

### 1.1 购买 ECS 实例

| 配置项 | 推荐值 |
|--------|--------|
| 地域 | 华东1（杭州）或离用户最近 |
| 实例规格 | 2 vCPU / 4 GB 内存（ecs.c7.large 或同等） |
| 操作系统 | **Ubuntu 22.04**（推荐） 或 CentOS 7.9 |
| 系统盘 | 40 GB 高效云盘 |
| 带宽 | 按量计费 5 Mbps 起步 |

### 1.2 安全组配置

阿里云 ECS 控制台 → 安全组 → 入方向 → 添加规则：

| 端口 | 协议 | 源地址 | 用途 |
|------|------|--------|------|
| 22 | TCP | 0.0.0.0/0 | SSH 远程连接 |
| 80 | TCP | 0.0.0.0/0 | HTTP 网站 |
| 443 | TCP | 0.0.0.0/0 | HTTPS（配置 SSL 证书后） |
| 8888 | TCP | 0.0.0.0/0 | 宝塔面板入口 |

> ⚠️ 部署完成后，建议将 8888 端口源地址改为你的办公 IP 白名单，或使用 SSH 隧道访问面板。

---

## 第二阶段：安装宝塔面板 11.8

### 2.1 SSH 登录 + 一键安装

```bash
ssh root@<你的公网IP>
```

**Ubuntu 22.04：（推荐）**
```bash
wget -O install.sh https://download.bt.cn/install/install-ubuntu_6.0.sh && sudo bash install.sh ed8484bec
```

**CentOS 7/8：**
```bash
yum install -y wget && wget -O install.sh https://download.bt.cn/install/install_6.0.sh && sh install.sh ed8484bec
```

安装过程约 3~5 分钟，完成后终端会显示登录信息：

```
==================================================================
外网面板地址: http://203.0.113.1:8888/abc12345
内网面板地址: http://10.0.0.1:8888/abc12345
username: abcdefgh
password: xxxxxxxxx
==================================================================
```

> 📝 **务必保存这些信息**。如果忘记了，SSH 执行 `bt default` 即可重新查看。

### 2.2 登录宝塔 11.8

浏览器打开 `http://<公网IP>:8888/安全入口`，输入用户名密码登录。

🔐 **11.8 首次登录建议：**
- 绑定宝塔账号（支持微信扫码快速登录）
- 面板设置 → 修改面板端口（非 8888）
- 面板设置 → 开启二次验证
- 面板设置 → 界面设置 → 可切换暗色主题（11.0 新增）

---

## 第三阶段：安装运行环境

### 3.1 安装推荐套件

登录后会弹出「推荐安装套件」弹窗。11.8 版本中：

| 组件 | 是否安装 | 说明 |
|------|----------|------|
| **Nginx 1.24+** | ✅ 必装 | 反向代理 + 静态文件服务。11.7 支持 HTTP/3 (QUIC) |
| Apache | ❌ 不装 | Django 用 Nginx 即可 |
| **MySQL 8.0** | ⚠️ 可选 | 如果用 SQLite 则不装；后期可切换 |
| PHP | ❌ 不装 | Django 是 Python 框架，不需要 PHP |
| phpMyAdmin | ❌ 不装 | 只有装 MySQL 时需要 |
| Redis | ❌ 不装 | 本项目暂不需要缓存 |

点击「极速安装」，等待完成（约 5~10 分钟）。

### 3.2 安装 Python 项目管理器（11.8 核心）

1. 宝塔 11.8 左侧菜单 → **软件商店**
2. 搜索框输入 **「Python项目管理器」**
3. 点击插件卡片 → **安装**

> 📌 **宝塔 11.8 中 Python 项目管理器的变化：**
> - 从 11.2 开始支持 **Python 版本云端解析安装**，无需手动编译
> - 从 11.0 开始支持 **智能依赖分析**，上传 requirements.txt 自动检测版本冲突
> - **一键性能调优**：根据 CPU 核数自动生成最优 Gunicorn 参数
> - **独立虚拟环境**：每个项目自动隔离，互不污染
> - 11.8 修复了「低权限启动用户下 Python 协同服务无法应用」的 Bug

4. 安装完插件后，进入 Python 项目管理器 → 点击顶部 **「版本管理」** 标签
5. 点击 **安装**，选择 **Python 3.13**（与开发环境一致）
6. 等待编译安装完成（约 3 分钟）

---

## 第四阶段：上传项目文件

### 4.1 本地打包项目

在 Windows 本地执行：

```powershell
# 进入项目父目录
cd D:\IFRS17预测模型

# 打包（排除缓存、数据库和开发工具）
tar -czf ifrs17-system.tar.gz `
  --exclude='__pycache__' `
  --exclude='*.sqlite3' `
  --exclude='.workbuddy' `
  --exclude='.playwright-cli' `
  ifrs17-system/
```

### 4.2 上传到服务器

**方式一：宝塔文件管理器（推荐，11.8 优化了上传速度）**

1. 宝塔 11.8 左侧 → **文件**
2. 导航到 `/www/wwwroot/`
3. 点击 **新建文件夹** → 输入 `ifrs17-system` → 确定
4. 双击进入 `ifrs17-system` 目录
5. 点击顶部 **上传** 按钮 → 选择 `ifrs17-system.tar.gz`
6. 上传完成后右键 tar.gz 文件 → **解压** → 解压到当前目录
7. 删除 tar.gz：`rm -f ifrs17-system.tar.gz`

**方式二：SCP 直传**

```bash
# 在本地终端执行
scp "D:\IFRS17预测模型\ifrs17-system.tar.gz" root@<公网IP>:/www/wwwroot/
# SSH 登录后解压
ssh root@<公网IP>
cd /www/wwwroot && mkdir -p ifrs17-system
tar -xzf ifrs17-system.tar.gz --strip-components=1 -C ifrs17-system/
rm ifrs17-system.tar.gz
```

### 4.3 确认项目结构

宝塔文件管理器进入 `/www/wwwroot/ifrs17-system/`，确认文件齐全：

```
/www/wwwroot/ifrs17-system/
├── manage.py                  ← Django 入口
├── requirements.txt           ← Python 依赖
├── gunicorn_config_baota.py   ← Gunicorn（生产模式，宝塔适配）
├── db.sqlite3                 ← SQLite 数据库（部署后创建）
├── data_fixtures/             ← 初始数据 JSON
├── data_input/                ← 核心应用
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   └── excel_validator.py
├── ifrs17_core/               ← Django 配置
│   ├── settings.py            ← 开发配置（DEBUG=True）
│   ├── settings_prod.py       ← 生产配置（DEBUG=False）
│   ├── urls.py
│   └── wsgi.py
├── static/                    ← 前端 JS/CSS
│   ├── css/styles.css
│   └── js/
├── templates/                 ← Django 模板
│   ├── base.html
│   ├── index.html
│   └── login.html
└── deploy/                    ← 部署文档（服务器上可删除）
```

---

## 第五阶段：Python 项目部署（11.8 面板操作）

### 5.1 用 Python 项目管理器创建项目

1. 宝塔 11.8 左侧 → **软件商店** → 已安装 → 找到 **Python项目管理器** → 点击 **设置**

2. 点击顶部的 **「项目管理」** 标签 → 点击 **「添加项目」**

3. 填写项目信息（11.8 界面顺序）：

   | 字段 | 填写内容 | 说明 |
   |------|----------|------|
   | **项目名称** | `ifrs17` | 自定义标识，不可含特殊字符 |
   | **项目路径** | `/www/wwwroot/ifrs17-system` | 点右侧「选择」按钮导航选择 |
   | **运行用户** | `www` | 11.8 默认，不要用 root |
   | **Python版本** | `Python 3.13` | 下拉选择已安装的版本 |
   | **框架** | `Django` | 下拉选择 |
   | **启动方式** | `gunicorn` | 下拉选择（11.8 支持 uwsgi/gunicorn/uvicorn） |
   | **启动文件/命令** | `gunicorn -c gunicorn_config_baota.py ifrs17_core.wsgi:application` | 使用宝塔适配配置 |
   | **端口** | `8000` | 监听在 127.0.0.1 |
   | **开机启动** | ✅ 勾选 | 服务器重启后自动启动 |

   > 📌 **11.8 智能性能调优提示：**
   > 如果面板弹出「是否使用自动调优参数」，选 **「自定义」** 然后直接使用我们的 `gunicorn_config_baota.py`，因为这个文件已针对本项目（Excel 大文件解析 120s 超时、4 worker 等）做了精确调优。

4. 点击 **「确定」** 保存

> ⚠️ 如果提示"模块未找到"或依赖安装失败，这是正常的——需要先手动安装依赖。

### 5.2 安装 Python 依赖

11.8 的 Python 项目管理器创建项目时会自动尝试安装 `requirements.txt`，但如果失败，按以下步骤手动安装：

1. 宝塔 11.8 左侧 → **终端**

2. 执行：

```bash
# 进入项目目录
cd /www/wwwroot/ifrs17-system

# 创建虚拟环境（如果面板没自动创建）
python3.13 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 升级 pip
pip install --upgrade pip

# 安装依赖（使用国内镜像加速）
pip install -r requirements.txt -i https://mirrors.tencent.com/pypi/simple/

# 验证
python -c "import django; print('Django', django.VERSION)"
# 应输出: Django (6, 0, 6, 'final', 0)
```

> 🔧 **如果 pip install 报错 openpyxl 或 gunicorn：**
> ```bash
> # CentOS 可能需要系统依赖
> yum install -y gcc python3-devel
> # Ubuntu
> apt install -y build-essential python3-dev
> ```

### 5.3 切换到生产环境配置

在宝塔终端中：

```bash
cd /www/wwwroot/ifrs17-system
source venv/bin/activate

# 生成随机 SECRET_KEY 并写入生产配置
python -c "
import secrets
key = secrets.token_urlsafe(50)
with open('ifrs17_core/settings_prod.py', 'r') as f:
    content = f.read()
content = content.replace('your-production-secret-key-here', key)
with open('ifrs17_core/settings_prod.py', 'w') as f:
    f.write(content)
print('SECRET_KEY 已更新')
"
```

### 5.4 初始化数据库和静态文件

```bash
cd /www/wwwroot/ifrs17-system
source venv/bin/activate

# 1. 执行数据库迁移（创建表结构）
python manage.py migrate

# 2. 收集静态文件到 staticfiles/ 目录
python manage.py collectstatic --noinput

# 3. 加载初始数据（可选，如果 data_fixtures/ 中有数据）
python manage.py init_data

# 4. 创建超级用户
python manage.py createsuperuser
# 用户名: admin
# 邮箱: 回车跳过
# 密码: admin123（生产环境务必修改！）
```

### 5.5 创建日志目录+设置权限

```bash
# 宝塔终端
mkdir -p /var/log/ifrs17
mkdir -p /var/run/ifrs17

# 设置权限（宝塔 Nginx 使用 www 用户）
chown -R www:www /www/wwwroot/ifrs17-system/
chmod -R 755 /www/wwwroot/ifrs17-system/
chmod 664 /www/wwwroot/ifrs17-system/db.sqlite3
chmod 775 /www/wwwroot/ifrs17-system/

# 日志目录权限
chown -R www:www /var/log/ifrs17 /var/run/ifrs17
chmod 755 /var/log/ifrs17 /var/run/ifrs17
```

### 5.6 启动项目

回到 **Python项目管理器** → 项目管理 → 找到 `ifrs17` → 点击 **「启动」**

状态栏应显示 🟢 **运行中**。

**如果启动失败：**
- 点击 **「日志」** 查看错误信息
- 或终端执行：`tail -50 /var/log/ifrs17/gunicorn_error.log`

---

## 第六阶段：Nginx 反向代理（11.8 网站管理）

### 6.1 创建网站

1. 宝塔 11.8 左侧 → **网站** → 点击 **「添加站点」**

2. 填写：

   | 字段 | 值 | 说明 |
   |------|-----|------|
   | **域名** | 你的公网 IP 或域名 | 11.8 支持 IP+端口创建 |
   | **根目录** | `/www/wwwroot/ifrs17-system` | 选择项目目录 |
   | FTP | 不创建 | — |
   | 数据库 | 不创建 | 使用 SQLite |
   | PHP版本 | **纯静态** | Django 用 Nginx 反代 |

3. 点击 **提交**

### 6.2 配置反向代理（11.8 界面）

1. 网站列表 → 点击刚创建的站点名称 → 进入 **站点设置**
2. 左侧菜单 → **反向代理** → 点击 **「添加反向代理」**

   | 字段 | 值 |
   |------|-----|
   | 代理名称 | `ifrs17_backend` |
   | 目标URL | `http://127.0.0.1:8000` |
   | 发送域名 | `$host` |
   | 内容替换 | 留空 |

3. 点击 **提交** → 提示「添加成功」

> 📌 **11.7/11.8 注意：** 反向代理创建后，如果使用域名创建，会自动处理 IPv6 兼容；如果使用 IP 创建，11.5+ 已原生支持。

### 6.3 优化 Nginx 配置（上传超时 + 静态文件）

> ⚠️ **重要**：宝塔自动生成的 Nginx 配置有几处需要修正，请严格按照以下内容替换。
> 完整修正版配置见 `deploy/nginx_baota_corrected.conf`。

1. 站点设置 → 左侧 **「配置文件」**

2. 在 `server` 块内部，**在反向代理 location 之前**，粘贴以下代码：

```nginx
    # ===== IFRS17 自定义配置 =====

    # 上传文件大小限制（50MB）
    client_max_body_size 50M;

    # 静态文件直连 — 用 ^~ 前缀优先于正则匹配，避免被敏感文件规则误拦
    # ⚠️ 必须先执行 python manage.py collectstatic 生成此目录
    location ^~ /static/ {
        alias /www/wwwroot/ifrs17-system/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # 媒体文件
    location ^~ /media/ {
        alias /www/wwwroot/ifrs17-system/media/;
        expires 7d;
    }

    # ===== IFRS17 配置结束 =====
```

3. 找到反向代理块（`location /` 开头），**确认端口为 8000**（与 Gunicorn bind 一致），
   并补充 `proxy_http_version` 和缓冲区设置：

```nginx
    location / {
        # ★ 端口必须与 gunicorn_config_baota.py 的 bind 一致（8000）
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # HTTP/1.1 keep-alive
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # IFRS17 大文件上传解析超时（openpyxl 需要较长时间）
        proxy_connect_timeout 60s;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;

        # 缓冲区
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }
```

4. 点击 **保存**

> **常见问题速查**：
> - **502 Bad Gateway** → 端口不匹配：检查 `proxy_pass` 端口 = Gunicorn `bind` 端口
> - **CSS/JS 404** → 未执行 `collectstatic`，或 `alias` 路径不对
> - **登录后刷新丢失登录状态** → `SESSION_COOKIE_SECURE=True` 但未配置 SSL；
>   设环境变量 `IFRS17_USE_HTTPS=0` 或在 `settings_prod.py` 中设为 `False`

### 6.4 重载 Nginx

配置文件页面顶部 → 点击 **「重载配置」** 使配置生效。

---

## 第七阶段：SSL 证书（可选，需域名）

> ⚠️ 宝塔 SSL 功能**需要域名**，纯 IP 无法申请免费证书。

如果你已绑定域名：

1. 站点设置 → 左侧 **SSL**
2. 选择 **「Let's Encrypt」** 标签（11.8 新增兼容 ARI 协议，签发成功率更高）
3. 勾选你的域名 → 点击 **「申请」**
4. 申请成功后，开启 **「强制HTTPS」**
5. 11.8 可用 **LiteSSL**（11.5 新增的免费证书品牌，也支持自动续签）

---

## 第八阶段：验证 + 故障排查

### 8.1 快速验证

| 检查项 | 操作 | 预期结果 |
|--------|------|----------|
| Gunicorn 运行 | Python项目管理器 → ifrs17 | 🟢 运行中 |
| Nginx 运行 | 软件商店 → Nginx | 🟢 运行中 |
| 登录页面 | 访问 `http://IP/login/` | 显示登录表单 |
| 用户登录 | admin / admin123 | 跳转到主页 |
| 静态文件 | 页面有样式和 JS 交互 | 无 404 报错 |
| 上传功能 | 上传 Excel 文件 | 返回校验结果 |

### 8.2 常见问题排查

| 问题 | 可能原因 | 解决方法 |
|------|----------|----------|
| **502 Bad Gateway** | Gunicorn 没启动 | Python项目管理器 → 启动项目，查看日志 |
| **静态文件 404** | 没执行 collectstatic | 终端：`python manage.py collectstatic --noinput` |
| **上传卡住/超时** | Nginx 超时太小 | 检查配置文件 `proxy_read_timeout` 是否 120s |
| **网站 403** | 文件权限问题 | `chown -R www:www /www/wwwroot/ifrs17-system/` |
| **disallowed host** | ALLOWED_HOSTS 问题 | settings_prod.py 中已设 `['*']`，确认生效 |
| **CSRF 验证失败** | HTTPS 下反向代理头丢失 | 确认 proxy_set_header 包含 X-Forwarded-Proto |
| **Python 版本不显示** | 版本管理器未安装成功 | Python项目管理器 → 版本管理 → 重新安装 |

### 8.3 日志查看

```bash
# 宝塔终端 — Gunicorn 日志
tail -100 /var/log/ifrs17/gunicorn_access.log   # 请求日志
tail -100 /var/log/ifrs17/gunicorn_error.log    # 错误日志

# 宝塔终端 — Nginx 日志
tail -100 /www/wwwlogs/ifrs17_access.log        # 访问日志
tail -100 /www/wwwlogs/ifrs17_error.log         # 错误日志

# 实时监控
tail -f /var/log/ifrs17/gunicorn_error.log
```

---

## 日常运维（11.8 面板操作）

### 重启项目
**Python项目管理器** → 找到 `ifrs17` → 点击 **「重启」**

### 更新代码后
```bash
cd /www/wwwroot/ifrs17-system
source venv/bin/activate
python manage.py migrate              # 数据库变更
python manage.py collectstatic --noinput  # 静态文件更新
```
然后回 Python项目管理器 → 重启项目。

### 数据库备份（宝塔计划任务）
1. 宝塔左侧 → **计划任务**
2. 添加任务 → Shell 脚本：
   ```bash
   cp /www/wwwroot/ifrs17-system/db.sqlite3 /www/backup/ifrs17_db_$(date +%Y%m%d_%H%M).sqlite3
   ```
3. 执行周期：每天 凌晨 3:00

### 安全加固清单
- [ ] 修改面板端口（非 8888）
- [ ] 修改 admin 密码（不要用 admin123）
- [ ] 修改 SECRET_KEY 为随机值
- [ ] 开启面板二次验证（11.8 支持 PassKey 免密码登录）
- [ ] 开启阿里云 ECS 系统盘自动快照
- [ ] 设置数据库定时备份计划任务
- [ ] （可选）11.8 安装 WAF/Nginx防火墙，AI 分析自动拦截攻击

---

## 附录：核心配置速查

### Gunicorn 关键参数（`gunicorn_config_baota.py`）

| 参数 | 值 | 说明 |
|------|-----|------|
| `bind` | `127.0.0.1:8000` | 仅本地监听，不暴露外网 |
| `workers` | CPU核数×2+1 | 自动计算 |
| `timeout` | `120` | Excel大文件解析需要 |
| `chdir` | `/www/wwwroot/ifrs17-system` | 宝塔根路径 |
| `raw_env` | `DJANGO_SETTINGS_MODULE=...` | 生产配置环境变量 |

### Django 生产配置开关（`settings_prod.py`）

| 设置 | 值 | 说明 |
|------|-----|------|
| `DEBUG` | `False` | **生产必须关闭！** |
| `ALLOWED_HOSTS` | `['*']` | 11.8 环境下允许所有 Host |
| `STATIC_ROOT` | `/www/wwwroot/.../staticfiles` | collectstatic 目标目录 |
| `SECRET_KEY` | 随机生成 | 不要用默认值 |

### 端口规划

| 端口 | 用途 | 对外暴露 |
|------|------|----------|
| 80 | Nginx HTTP | ✅ 是 |
| 443 | Nginx HTTPS | ✅ 是 |
| 8000 | Gunicorn | ❌ 否（仅本地回环） |
| 8888 | 宝塔面板 | ⚠️ 建议 IP 白名单 |
