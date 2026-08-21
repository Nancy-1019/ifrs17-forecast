# -*- coding: utf-8 -*-
"""
生成「IFRS17 新准则预测系统 — 测试环境信息需求表」
可直发公司 IT/运维填写，填回后据此生成完整部署包。

变量名严格对齐：
  - ifrs17_core/settings_prod.py : IFRS17_ALLOWED_HOSTS / IFRS17_DB_HOST/PORT/NAME/USER/PASSWORD
  - .env.example                  : IFRS17_SECRET_KEY / IFRS17_CSRF_TRUSTED_ORIGINS / MYSQL_ROOT_PASSWORD
"""
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

OUT_XLSX = "doc_build/测试环境信息需求表.xlsx"
OUT_HTML = "doc_build/测试环境信息需求表.html"

# ---------- 样式 ----------
NAVY = "1F3864"
BLUE = "2E5496"
LIGHT = "D9E1F2"
YELLOW = "FFF2CC"
GREY = "F2F2F2"
WHITE = "FFFFFF"

H_FONT = Font(name="微软雅黑", size=11, bold=True, color=WHITE)
TITLE_FONT = Font(name="微软雅黑", size=16, bold=True, color=NAVY)
SUB_FONT = Font(name="微软雅黑", size=10, color="404040")
CELL_FONT = Font(name="微软雅黑", size=10, color="000000")
EX_FONT = Font(name="微软雅黑", size=10, italic=True, color="808080")
FILL_H = PatternFill("solid", fgColor=BLUE)
FILL_H2 = PatternFill("solid", fgColor=NAVY)
FILL_Y = PatternFill("solid", fgColor=YELLOW)
FILL_G = PatternFill("solid", fgColor=GREY)
WRAP = Alignment(wrap_text=True, vertical="top")
WRAP_C = Alignment(wrap_text=True, vertical="center", horizontal="center")
thin = Side(style="thin", color="B0B0B0")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)


def style_header(ws, row, ncols, fill=FILL_H):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = H_FONT
        cell.fill = fill
        cell.alignment = WRAP_C
        cell.border = BORDER


# ============================================================
# 数据：7 大类环境信息需求
# 元组: (需求项, 是否必填, 对应配置变量, 说明, 示例值)
# ============================================================
CATEGORIES = [
    ("一、服务器与操作系统", [
        ("服务器形态（虚机/云主机/容器）", "必填", "—",
         "虚拟机、云主机还是容器？是否允许安装依赖、开放端口", "云主机（腾讯云 CVM）"),
        ("操作系统及版本", "必填", "—",
         "推荐 Linux（CentOS 7+ / Ubuntu 22.04+ / TencentOS），需能装 Python 3.13、Gunicorn、Nginx", "Ubuntu 22.04 LTS"),
        ("CPU / 内存", "必填", "—",
         "计算引擎跑多情景，建议 ≥8G 内存", "4 核 8G"),
        ("磁盘空间", "必填", "—",
         "MySQL 数据 + 上传 Excel + runtime_cache（calc_results_map.json 等）", "100GB SSD"),
        ("操作权限", "必填", "—",
         "是否有 sudo/root 装包、开放端口、建 systemd/supervisor 服务", "提供 sudo 账号"),
        ("代码部署路径", "必填", "—",
         "项目代码放置目录（参考现生产 /www/wwwroot/ifrs17-system）", "/www/wwwroot/ifrs17-system"),
    ]),
    ("二、数据库（MySQL 8.0，pymysql 驱动）", [
        ("数据库主机 HOST", "必填", "IFRS17_DB_HOST",
         "公司 MySQL 地址；容器形态填 db service 名。系统默认 127.0.0.1", "127.0.0.1 或 mysql.corp.com"),
        ("端口 PORT", "必填", "IFRS17_DB_PORT",
         "默认 3306", "3306"),
        ("数据库名 NAME", "必填", "IFRS17_DB_NAME",
         "建议建独立测试库（避免污染生产）", "ifrs17_test"),
        ("用户名 USER", "必填", "IFRS17_DB_USER",
         "需有 DDL 权限（migrate 要建 35 张输入物理表 + 输出表 + Django 表）", "ifrs17"),
        ("密码 PASSWORD", "必填", "IFRS17_DB_PASSWORD",
         "强密码；若走容器内置 MySQL 需同步提供 MYSQL_ROOT_PASSWORD", "（公司提供）"),
        ("MySQL 版本", "必填", "—",
         "必须 ≥8.0；注意 8.0 默认 caching_sha2_password 兼容性（pymysql 已支持）", "8.0.36"),
        ("字符集", "建议", "—",
         "建议 utf8mb4", "utf8mb4"),
    ]),
    ("三、网络、域名与访问", [
        ("访问地址 / 域名", "必填", "IFRS17_ALLOWED_HOSTS",
         "逗号分隔，填公司分配的域名或 IP（对应 settings ALLOWED_HOSTS）", "test-ifrs17.corp.com,10.20.30.40"),
        ("CSRF 信任源", "必填", "IFRS17_CSRF_TRUSTED_ORIGINS",
         "与访问地址对应；HTTPS 环境必须用 https:// 前缀", "https://test-ifrs17.corp.com"),
        ("HTTPS / SSL 证书", "必填", "—",
         "公司是否提供证书？是否强制 HTTPS？我生成 Nginx HTTPS 配置模板，证书由公司 CA 提供", "公司 CA 签发 cert.pem / key.pem"),
        ("端口开放", "必填", "—",
         "80/443 是否对外；内网是否需 VPN / 白名单；防火墙/安全组审批", "开放 443"),
        ("反向代理", "必填", "—",
         "公司是否有统一网关/Nginx？还是服务器上自建 Nginx（现生产用宝塔 Nginx → proxy_pass 127.0.0.1:8080）", "自建 Nginx"),
    ]),
    ("四、运行时与进程管理", [
        ("Python 环境", "必填", "—",
         "公司提供 Python 3.13？还是要求 Docker 容器化（已有 Dockerfile，最省事）", "Docker 容器化（已有 Dockerfile）"),
        ("进程管理", "必填", "—",
         "Gunicorn 如何拉起：systemd / supervisor / 容器（现生产用 start_gunicorn.sh）", "Docker Compose"),
        ("Gunicorn workers", "必填（约束）", "—",
         "⚠️ 必须 = 1。计算进度与结果存在进程内全局变量，>1 会出现进度 0% 假象", "1"),
        ("静态文件托管", "必填", "STATIC_ROOT",
         "Nginx 托管 static/，需配置 collectstatic 收集目录", "/www/wwwroot/ifrs17-system/static"),
    ]),
    ("五、安全与账号", [
        ("SECRET_KEY", "必填", "IFRS17_SECRET_KEY",
         "测试环境必须独立生成强随机值（我可用 secrets.token_urlsafe 生成，也可你提供）", "（部署时生成）"),
        ("统一认证对接", "建议", "—",
         "当前是 Django 自带账号（admin/uploader/viewer）；如需 LDAP/OAUTH/SSO 需额外开发（非填变量能解决）", "暂用系统自带账号"),
        ("合规要求", "建议", "—",
         "财务预测数据是否需加密存储、访问审计", "无特殊要求"),
    ]),
    ("六、文件存储与缓存", [
        ("上传文件落盘", "必填", "—",
         "Excel 上传存放路径；公司是否要求对象存储（COS/S3）而非本地磁盘", "本地 /data/ifrs17/uploads"),
        ("runtime_cache 目录", "必填", "—",
         "calc_results_map.json、actual_cache.json、old_standard_cache.json 等需持久化磁盘", "项目内 runtime_cache/"),
    ]),
    ("七、运维与备份", [
        ("数据库备份", "建议", "—",
         "MySQL 定时备份策略（全量/增量、保留周期）", "每日全量，保留 7 天"),
        ("日志与监控", "建议", "—",
         "访问/错误日志轮转、是否接公司日志平台（ELK）、进程存活监控与告警", "logrotate + 进程监控"),
    ]),
]

# ============================================================
# 构建 Excel
# ============================================================
wb = openpyxl.Workbook()

# ---------- Sheet 1: 填写说明 ----------
ws = wb.active
ws.title = "填写说明"
ws.sheet_view.showGridLines = False
ws.column_dimensions["A"].width = 22
ws.column_dimensions["B"].width = 90

ws["A1"] = "IFRS17 新准则预测系统 — 测试环境部署信息需求表"
ws["A1"].font = TITLE_FONT
ws.merge_cells("A1:B1")

ws["A2"] = "版本 v5.9.92 · 部署前需向公司 IT/运维申请的环境信息清单"
ws["A2"].font = SUB_FONT
ws.merge_cells("A2:B2")

rows = [
    ("用途", "本表用于向公司 IT/运维申请测试环境资源。请按「是否必填」列标注填写对应项，填好后回传本文件即可启动部署代码生成。"),
    ("变量解耦", "系统配置已通过环境变量与代码解耦（settings_prod.py / .env）。填好下表后，我仅需把值写入 .env + 按形态适配，无需改业务代码。"),
    ("填法", "请在各明细行的「公司填写」列（黄色高亮）填入真实值；「示例值」列仅作参考（灰色）。无需改其他列。"),
    ("部署形态", "请在下方勾选测试环境预期形态（决定我铺哪条线代码）：□ Docker 容器化  □ 裸虚机(非宝塔)  □ 宝塔虚机(生产同款)"),
    ("最小必填项", "拿到以下即可部署：\n"
                   "① IFRS17_DB_HOST / PORT / NAME / USER / PASSWORD（数据库，需 DDL 权限）\n"
                   "② IFRS17_SECRET_KEY（独立强随机密钥）\n"
                   "③ IFRS17_ALLOWED_HOSTS + IFRS17_CSRF_TRUSTED_ORIGINS（域名/IP）\n"
                   "④ 服务器 OS + Python 3.13(或 Docker) + 端口/域名/HTTPS 方案\n"
                   "⑤ Gunicorn workers=1 + Nginx 反向代理 127.0.0.1:8080"),
    ("诚实边界", "以下需公司配合或额外开发，非填变量能解决：\n"
                 "• 统一认证（LDAP/OAUTH/SSO）对接公司 IAM\n"
                 "• 公司 MySQL 集群网络白名单/账号审批（我给连接串，DBA 侧授权）\n"
                 "• SSL 证书（我给 Nginx HTTPS 模板，证书由公司 CA 提供）\n"
                 "• 镜像仓库凭证（走 Docker 时推送镜像需公司 registry 账号）"),
]
r = 4
for k, v in rows:
    ws.cell(row=r, column=1, value=k).font = Font(name="微软雅黑", size=10, bold=True, color=NAVY)
    ws.cell(row=r, column=1).alignment = WRAP
    c = ws.cell(row=r, column=2, value=v)
    c.font = CELL_FONT
    c.alignment = WRAP
    ws.row_dimensions[r].height = 14 * (v.count("\n") + 2)
    r += 1

# ---------- Sheet 2: 环境信息需求明细 ----------
ws2 = wb.create_sheet("环境信息需求明细")
ws2.sheet_view.showGridLines = False
headers = ["序号", "类别", "需求项", "是否必填", "对应系统配置变量", "说明", "示例值", "公司填写（请填此列）"]
widths = [6, 26, 22, 12, 26, 40, 26, 26]
for i, w in enumerate(widths, 1):
    ws2.column_dimensions[get_column_letter(i)].width = w

ws2.cell(row=1, column=1, value="环境信息需求明细（共 %d 项，必填 %d 项）" % (
    sum(len(v) for _, v in CATEGORIES),
    sum(1 for _, v in CATEGORIES for x in v if x[1].startswith("必填"))))
ws2["A1"].font = TITLE_FONT
ws2.merge_cells("A1:H1")

for i, h in enumerate(headers, 1):
    ws2.cell(row=2, column=i, value=h)
style_header(ws2, 2, len(headers))

r = 3
idx = 0
for cat_name, items in CATEGORIES:
    # 类别分隔行
    ws2.cell(row=r, column=1, value=cat_name)
    ws2.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
    for c in range(1, 9):
        cell = ws2.cell(row=r, column=c)
        cell.font = Font(name="微软雅黑", size=10, bold=True, color=WHITE)
        cell.fill = FILL_H2
        cell.alignment = WRAP_C
        cell.border = BORDER
    r += 1
    for item in items:
        name, req, var, desc, ex = item
        idx += 1
        row_vals = [idx, cat_name, name, req, var, desc, ex, ""]
        for c, val in enumerate(row_vals, 1):
            cell = ws2.cell(row=r, column=c, value=val)
            cell.font = CELL_FONT
            cell.alignment = WRAP
            cell.border = BORDER
            if c == 7:
                cell.font = EX_FONT
            if c == 8:
                cell.fill = FILL_Y  # 公司填写列高亮
        ws2.row_dimensions[r].height = 30
        r += 1

ws2.freeze_panes = "A3"

# ---------- Sheet 3: 部署形态与约定 ----------
ws3 = wb.create_sheet("部署形态与约定")
ws3.sheet_view.showGridLines = False
ws3.column_dimensions["A"].width = 28
ws3.column_dimensions["B"].width = 80
ws3["A1"] = "部署形态与系统约定（供 IT 参考）"
ws3["A1"].font = TITLE_FONT
ws3.merge_cells("A1:B1")

notes = [
    ("已具备的部署骨架", "Dockerfile（python:3.12-slim + Gunicorn workers=1 + collectstatic + entrypoint）、docker-compose.yml、docker-entrypoint.sh、requirements.txt、.env.example、deploy/auto_deploy.sh（宝塔虚机一键部署）、Nginx 配置、logrotate、诊断脚本、部署指南。"),
    ("形态 A：Docker 容器化", "最省事。调整 docker-compose.yml（端口、卷、DB 连接、域名），提供 build+up 命令即可。需公司 registry 账号推送镜像（或用公司镜像仓库）。"),
    ("形态 B：裸虚机（非宝塔）", "auto_deploy.sh 默认写死宝塔路径，我会生成通用版：systemd service 单元 + 通用 Nginx 站点配置 + 去宝塔假设的一键部署脚本，复用 migrate/collectstatic/gunicorn 逻辑。"),
    ("形态 C：宝塔虚机", "直接复用现有 deploy/auto_deploy.sh + 宝塔 Nginx 配置，最小改动。"),
    ("强约束：workers=1", "计算进度/结果存进程内全局变量，Gunicorn workers>1 会出现进度 0% 假象，必须=1。"),
    ("静态资源", "Nginx 托管 static/，部署时执行 collectstatic 收集到 STATIC_ROOT；前端版本号经 ?v=SYSTEM_VERSION 缓存刷新。"),
    ("健康检查", "启动后 curl http://127.0.0.1:8000/ 应 302→/login/；登录 admin/admin123 验证。"),
    ("数据库迁移", "拿到公司 MySQL 后执行 migrate（data_input.0007_* 含 35 张输入物理表）；若列结构变化需重跑 schema 生成脚本。"),
]
r = 3
for k, v in notes:
    ws3.cell(row=r, column=1, value=k).font = Font(name="微软雅黑", size=10, bold=True, color=NAVY)
    ws3.cell(row=r, column=1).alignment = WRAP
    c = ws3.cell(row=r, column=2, value=v)
    c.font = CELL_FONT
    c.alignment = WRAP
    ws3.row_dimensions[r].height = 14 * (v.count("。") + 2)
    r += 1

wb.save(OUT_XLSX)
print("XLSX 已生成:", OUT_XLSX)

# ============================================================
# 构建 HTML 预览
# ============================================================
total = sum(len(v) for _, v in CATEGORIES)
req_count = sum(1 for _, v in CATEGORIES for x in v if x[1].startswith("必填"))

html = []
html.append("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IFRS17 测试环境信息需求表</title>
<style>
 body{font-family:"Microsoft YaHei",sans-serif;background:#f5f7fa;color:#222;margin:0;padding:28px}
 .wrap{max-width:1180px;margin:0 auto;background:#fff;border-radius:10px;box-shadow:0 2px 12px rgba(0,0,0,.08);padding:32px}
 h1{color:#1F3864;font-size:24px;margin:0 0 4px}
 .sub{color:#666;font-size:13px;margin-bottom:18px}
 .card{background:#f0f4fb;border-left:4px solid #2E5496;border-radius:6px;padding:14px 18px;margin:14px 0;font-size:13px;line-height:1.7}
 .card b{color:#1F3864}
 table{border-collapse:collapse;width:100%%;font-size:12.5px;margin:10px 0 26px}
 th{background:#2E5496;color:#fff;text-align:left;padding:8px 10px;position:sticky;top:0}
 td{border:1px solid #cfd8e8;padding:7px 10px;vertical-align:top}
 tr:nth-child(even) td{background:#f7f9fc}
 .cat{background:#1F3864;color:#fff;font-weight:700;padding:8px 10px;font-size:13px}
 .req{color:#c0392b;font-weight:700}
 .opt{color:#7f8c8d}
 code{background:#eef2f8;padding:1px 5px;border-radius:3px;font-family:Consolas,monospace;color:#1F3864}
 .fill{background:#fff2cc}
 .ex{color:#888;font-style:italic}
 .mini{background:#fff;border:1px solid #cfd8e8;border-radius:6px;padding:12px 16px;font-size:12.5px;line-height:1.8}
</style></head><body><div class="wrap">
<h1>IFRS17 新准则预测系统 — 测试环境部署信息需求表</h1>
<div class="sub">版本 v5.9.92 · 部署前需向公司 IT/运维申请的环境信息清单（共 %d 项，必填 %d 项）</div>

<div class="card">
<b>用途：</b>向公司 IT/运维申请测试环境资源。请按「是否必填」标注填写，填回后据此生成完整部署代码。<br>
<b>变量解耦：</b>系统配置已通过环境变量与代码解耦（settings_prod.py / .env），填好下表后仅需写入 .env + 按形态适配，无需改业务代码。<br>
<b>填法：</b>在「公司填写」列（黄底）填真实值；「示例值」列仅参考。
</div>

<div class="card"><b>最小必填项（拿到即可部署）：</b><br>
① <code>IFRS17_DB_HOST/PORT/NAME/USER/PASSWORD</code>（数据库，需 DDL 权限）<br>
② <code>IFRS17_SECRET_KEY</code>（独立强随机密钥）<br>
③ <code>IFRS17_ALLOWED_HOSTS</code> + <code>IFRS17_CSRF_TRUSTED_ORIGINS</code>（域名/IP）<br>
④ 服务器 OS + Python 3.13(或 Docker) + 端口/域名/HTTPS 方案<br>
⑤ Gunicorn workers=1 + Nginx 反向代理 127.0.0.1:8080
</div>

<div class="mini">
<b>部署形态（请勾选预期形态）：</b>　□ Docker 容器化　□ 裸虚机(非宝塔)　□ 宝塔虚机(生产同款)
</div>
""" % (total, req_count))

for cat_name, items in CATEGORIES:
    html.append('<div class="cat">%s</div>' % cat_name)
    html.append("""<table><thead><tr>
<th style="width:40px">#</th><th style="width:150px">需求项</th>
<th style="width:70px">必填</th><th style="width:190px">对应配置变量</th>
<th>说明</th><th style="width:170px">示例值</th><th style="width:170px">公司填写</th>
</tr></thead><tbody>""")
    for i, (name, req, var, desc, ex) in enumerate(items, 1):
        rc = '<span class="req">必填</span>' if req.startswith("必填") else '<span class="opt">%s</span>' % req
        html.append(
            "<tr><td>%d</td><td>%s</td><td>%s</td><td><code>%s</code></td><td>%s</td>"
            "<td class='ex'>%s</td><td class='fill'></td></tr>" % (
                i, name, rc, var or "—", desc, ex))
    html.append("</tbody></table>")

html.append("""<div class="card"><b>诚实边界（填变量无法解决，需公司配合/额外开发）：</b><br>
• 统一认证（LDAP/OAUTH/SSO）对接公司 IAM 　• 公司 MySQL 集群网络白名单/账号审批（DBA 侧）<br>
• SSL 证书（我给 Nginx HTTPS 模板，证书由公司 CA 提供） 　• 镜像仓库凭证（走 Docker 时）
</div>
<div class="card"><b>已具备部署骨架：</b>Dockerfile、docker-compose.yml、docker-entrypoint.sh、requirements.txt、.env.example、deploy/auto_deploy.sh（宝塔虚机一键部署）、Nginx 配置、logrotate、诊断脚本、部署指南。填好信息后我按形态补全缺失件即可产出端到端部署包。</div>
</div></body></html>""")

with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write("".join(html))
print("HTML 已生成:", OUT_HTML)
