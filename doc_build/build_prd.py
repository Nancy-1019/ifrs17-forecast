# -*- coding: utf-8 -*-
"""生成 IFRS17 财务预测系统 PRD 文档 (HTML 可预览 + 交付)。
内容全部基于真实代码事实：
- 前端导航：static/js/app.js pageTitles
- 后端 API：data_input/views.py
- 物理表：data_input/table_names.py (35 输入 + 6 输出)
- 情景/版本：static/js/config.js
"""
import os

OUT_DIR = os.path.join(os.path.dirname(__file__))
HTML_PATH = os.path.join(OUT_DIR, "IFRS17预测系统_PRD.html")

# ---------- 样式（EY 品牌色 + AntD 蓝，纯字符串避免 f-string 大括号冲突） ----------
CSS = """
:root{
  --ey-yellow:#FFE600; --ey-black:#1a1a1a; --ant-blue:#1677FF;
  --ink:#222; --muted:#666; --line:#e8e8e8; --bg:#f5f6f8;
  --green:#389e0d; --red:#cf1322; --chip:#eef3ff;
}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  color:var(--ink);background:var(--bg);line-height:1.7;font-size:15px}
.cover{background:linear-gradient(135deg,#1a1a1a 0%,#2b2b2b 60%,#1677ff 140%);color:#fff;padding:54px 48px 46px}
.cover .bar{width:78px;height:8px;background:var(--ey-yellow);margin-bottom:22px;border-radius:2px}
.cover h1{font-size:34px;margin:0 0 10px;font-weight:800;letter-spacing:1px}
.cover .sub{font-size:17px;opacity:.86;margin-bottom:26px}
.cover .meta{display:flex;flex-wrap:wrap;gap:10px 28px;font-size:14px;opacity:.92}
.cover .meta b{color:var(--ey-yellow)}
.wrap{max-width:1080px;margin:0 auto;padding:0 28px 70px}
.toc{background:#fff;border:1px solid var(--line);border-radius:12px;padding:22px 26px;margin:-30px 0 30px;
  box-shadow:0 6px 22px rgba(0,0,0,.06);position:relative;z-index:2}
.toc h3{margin:0 0 12px;font-size:16px;color:var(--ant-blue)}
.toc a{color:var(--ink);text-decoration:none;display:block;padding:4px 0;border-bottom:1px dashed #eee;font-size:14px}
.toc a:hover{color:var(--ant-blue)}
.toc .lv2{padding-left:18px;color:var(--muted);font-size:13px}
section{background:#fff;border:1px solid var(--line);border-radius:12px;padding:26px 30px;margin:22px 0;
  box-shadow:0 2px 10px rgba(0,0,0,.03)}
section>h2{margin:0 0 6px;font-size:22px;color:var(--ey-black);border-left:6px solid var(--ey-yellow);padding-left:12px}
section>h2 .tag{font-size:12px;color:#fff;background:var(--ant-blue);border-radius:4px;padding:2px 8px;margin-left:10px;vertical-align:middle;font-weight:600}
.lead{color:var(--muted);margin:4px 0 18px;font-size:14px}
h3{font-size:17px;color:var(--ant-blue);margin:22px 0 8px}
h4{font-size:15px;margin:16px 0 6px;color:#333}
p{margin:8px 0}
ul,ol{margin:8px 0;padding-left:22px}
li{margin:4px 0}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:13.5px}
th,td{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
th{background:#fafbff;color:var(--ant-blue);font-weight:700}
tr:nth-child(even) td{background:#fcfcfe}
.code{font-family:"SFMono-Regular",Consolas,Menlo,monospace;background:#f3f4f6;padding:2px 6px;border-radius:4px;font-size:12.5px;color:#b3261e}
.kbd{display:inline-block;background:var(--chip);border:1px solid #c9dcff;border-radius:5px;padding:1px 7px;font-size:12px;color:#0b53c2;margin:1px}
.card{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:12px 0}
.card .t{font-weight:700;color:var(--ey-black);margin-bottom:4px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:760px){.grid{grid-template-columns:1fr}}
.badge{display:inline-block;font-size:12px;padding:1px 8px;border-radius:4px;margin-right:6px}
.b-req{background:#fff1f0;color:var(--red);border:1px solid #ffccc7}
.b-opt{background:#f6ffed;color:var(--green);border:1px solid #b7eb8f}
.b-core{background:var(--chip);color:#0b53c2;border:1px solid #c9dcff}
.note{background:#fffbe6;border:1px solid #ffe58f;border-radius:8px;padding:10px 14px;margin:12px 0;font-size:13.5px}
.ok{color:var(--green);font-weight:700}
.no{color:var(--red);font-weight:700}
footer{text-align:center;color:var(--muted);font-size:13px;padding:30px 0 10px}
.pill{font-size:12px;color:#fff;background:#444;border-radius:20px;padding:2px 10px}
"""

def h2(title, tag=""):
    tag_html = f'<span class="tag">{tag}</span>' if tag else ""
    return f"<h2>{title}{tag_html}</h2>"

def derive_table(header, rows):
    """生成字段逻辑推演表：header 列名，rows 为 (字段,英文,加工逻辑,来源表/字段,说明) 元组。"""
    h = "".join(f"<th>{x}</th>" for x in header)
    body = ""
    for r in rows:
        cls = ""
        if len(r) > 2 and r[2] in ("直接取值", "查找", "加和", "计算", "归集映射"):
            cls = {"直接取值": "b-core", "查找": "b-opt", "加和": "b-req", "计算": "b-req", "归集映射": "b-opt"}.get(r[2], "")
        tds = ""
        for i, c in enumerate(r):
            if i == 2 and cls:
                tds += f'<td><span class="badge {cls}">{c}</span></td>'
            else:
                tds += f"<td>{c}</td>"
        body += f"<tr>{tds}</tr>"
    return f'<table><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>'

# ---------- 全量字段中英文映射生成 ----------
import importlib.util as _ilu, re as _re
def _load(modpath, modname):
    spec = _ilu.spec_from_file_location(modname, modpath)
    m = _ilu.module_from_spec(spec); spec.loader.exec_module(m); return m

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_fn = _load(os.path.join(_ROOT, 'paa_engine', 'field_names.py'), 'field_names')
_SCHEMA = _load(os.path.join(_ROOT, 'data_input', 'input_table_schema.py'), 'input_table_schema')
_ENG_SRC = open(os.path.join(_ROOT, 'paa_engine', 'engine.py'), encoding='utf-8').read()

def _cn(en):
    return _fn.to_cn(en)

def _extract_list(varname):
    m = _re.search(varname + r"\s*=\s*\[(.*?)\]", _ENG_SRC, _re.S)
    if not m:
        return []
    return _re.findall(r"'([a-z][a-z0-9_]*)'", m.group(1))

def _map_input_tables():
    s = _SCHEMA.INPUT_TABLE_SCHEMA
    out = []
    out.append('<p class="lead">以下为 35 张输入物理表的字段中英文映射（文本维度列 + 月度列 m01~m60 + 险类拆分列）。'
               '英文列名由系统字段注册表 <span class="code">field_names.py</span> 统一生成，与物理表一一对应；'
               '字段类型分为<b>数值</b>（含险类拆分/余额/比率/月度）与<b>文本</b>（维度列）。</p>')
    for cn, v in s.items():
        cols = v.get('columns', [])
        out.append('<details><summary style="cursor:pointer"><b>%s</b> &nbsp;<span class="code">%s</span> · %d 字段 · 来源=%s</summary>'
                   % (cn, v.get('en'), len(cols), v.get('source')))
        out.append('<table><thead><tr><th>序号</th><th>中文字段名</th><th>英文字段名</th><th>类型</th></tr></thead><tbody>')
        for i, c in enumerate(cols, 1):
            t = '数值' if c.get('type') == 'decimal' else '文本'
            out.append('<tr><td>%d</td><td>%s</td><td><span class="code">%s</span></td><td>%s</td></tr>' % (i, c.get('cn'), c.get('name'), t))
        out.append('</tbody></table></details>')
    return ''.join(out)

def _map_list_block(title, keys):
    out = ['<p><b>%s</b></p>' % title]
    out.append('<table><thead><tr><th>英文字段名</th><th>中文字段名</th></tr></thead><tbody>')
    import re as _re2
    for k in keys:
        if k in _fn.EN_TO_CN:            # 英文键 → 中文名
            en, cn = k, _fn.EN_TO_CN[k]
        elif k in _fn.CN_TO_EN:          # 中文键 → 英文名（双写保险）
            en, cn = _fn.CN_TO_EN[k], k
        elif _re2.search(r'[\u4e00-\u9fff]', k):   # 中文键但无独立英文键（如 MTD 手工科目）
            en, cn = '（中文列名，无独立英文键）', k
        else:                            # 英文键未注册（需补齐）
            en, cn = k, '—（未注册，需补齐）'
        out.append('<tr><td><span class="code">%s</span></td><td>%s</td></tr>' % (en, cn))
    out.append('</tbody></table>')
    return ''.join(out)

def _map_output_and_intermediate():
    out = []
    out.append('<h4>中间计算表（A/B/C）</h4>')
    inter = {
        '中间表 A · 新业务假设整理': ['forecast_group_id','forecast_group','expected_writing_period_months','actuarial_lob','contract_portfolio_name','business_type','保费写入时点','premium_income','acquisition_cost','advance_written_premium','再保前生效保费','分出比例','签单保费','current_recognition_ratio','iacf_amortization_ratio'],
        '中间表 B · 现有业务假设整理': ['contract_group_id','现有业务预测组ID','exist_biz_forecast_group','forecast_group_id','forecast_group','contract_group_name','actuarial_lob','direct_or_ceded','expected_writing_period_months','保费写入时点','premium_income','acquisition_cost','premium_receivable','iacf_payable','lic_risk_adj_ratio_pct','lrc_risk_adj_ratio_pct','待摊销保险收入_期初','待摊销获取现金流_期初','未到期责任负债_非亏损部分_期初','未到期责任负债_亏损部分_期初','未到期责任负债_亏损摊回_期初','已发生未决赔款负债_预期现金流_期初','间接理赔费用负债_预期现金流_期初','已发生未决赔款负债_再保人不履约_预期现金流_期初','已发生未决赔款负债_非金融风险调整_期初','间接理赔费用负债_非金融风险调整_期初','已发生未决赔款负债_再保人不履约_非金融风险调整_期初'],
        '中间表 C · 利率曲线加工': ['monthly_rate','discount_factor_end','discount_factor_begin','annual_rate_forecast','annual_rate_eval'],
    }
    for tname, keys in inter.items():
        out.append(_map_list_block(tname, keys))
    out.append('<h4>输出结果表（1~6）</h4>')
    out.append(_map_list_block('表 1 · PAA计算_新业务整理 (paa_new_business_organized)', _extract_list('NEW_BUSINESS_PREDICT_COLS')))
    out.append(_map_list_block('表 2 · PAA计算_现有业务整理 (paa_existing_business_organized)', _extract_list('EXISTING_BUSINESS_PREDICT_COLS')))
    out.append(_map_list_block('表 3 · PAA计算_汇总 (paa_summary)', _extract_list('SUMMARY_COLS')))
    # 表4 PAA计算_MTD：动态抽取引擎内 _PAA_DIRECT_* / _PAA_CEDING_* 归集列 + 其他输入/OCI/营业外键
    _mtd_direct = []
    _mtd_ceding = []
    for _v in _re.findall(r'_PAA_DIRECT_([A-Z_]+)_COLS\s*=\s*\[(.*?)\]', _ENG_SRC, _re.S):
        _mtd_direct += _re.findall(r"'([a-z][a-z0-9_]*)'", _v[1])
    for _v in _re.findall(r'_PAA_CEDING_([A-Z_]+)_COLS\s*=\s*\[(.*?)\]', _ENG_SRC, _re.S):
        _mtd_ceding += _re.findall(r"'([a-z][a-z0-9_]*)'", _v[1])
    _mtd_misc = ['OCI', 'non_operating_income', 'non_operating_expense',
                 '投资收益', '其他收益', '公允价值变动收益', '汇兑收益', '资产处置收益']
    mtd_keys = sorted(set(_mtd_direct + _mtd_ceding + _mtd_misc))
    out.append(_map_list_block('表 4 · PAA计算_MTD (paa_mtd) 归集财务科目（直保/分出列合并去重）', mtd_keys))
    # 表5/6 财务报表行项目（中文科目名，附英文标识）
    fs_items = [('一、营业总收入','total_operating_revenue'),('保险服务收入','insurance_service_revenue'),('利息收入','interest_income'),('投资收益（损失以"-"号填列）','investment_income'),('其他收益（损失以"-"号填列）','other_income'),('公允价值变动收益（损失以"-"号填列）','fair_value_income'),('汇兑收益（损失以"-"号填列）','fx_income'),('其他业务收入','other_business_income'),('资产处置收益（损失以"-"号填列）','asset_disposal_income'),('二、营业总支出','total_operating_expense'),('保险服务费用','insurance_service_expense'),('分出保费的分摊','ceded_premium_allocation'),('减：摊回保险服务费用','less_recoverable_service_expense'),('承保财务损失','underwriting_financial_loss'),('减：分出再保险财务收益','less_ceded_reinsurance_finance_income'),('提取保费准备金','premium_reserve_extraction'),('利息支出','interest_expense'),('税金及附加','tax_and_surcharge'),('手续费及佣金支出','commission_expense'),('业务及管理费','admin_expense'),('信用减值损失','credit_impairment_loss'),('其他资产减值损失','other_asset_impairment_loss'),('其他业务成本','other_business_cost'),('三、营业利润（亏损以"-"号填列）','operating_profit'),('加：营业外收入','plus_non_operating_income'),('减：营业外支出','less_non_operating_expense'),('四、利润总额（亏损总额以"-"号填列）','total_profit'),('减：所得税费用','less_income_tax'),('五、净利润（净亏损以"-"号填列）','net_profit'),('六、其他综合收益的税后净额','oci_net_of_tax'),('七、综合收益总额','total_comprehensive_income'),('承保利润','underwriting_profit'),('资产','assets'),('分出再保险合同资产','reinsurance_contract_asset'),('其他资产','other_assets'),('资产总计','total_assets'),('负债','liabilities'),('保险合同负债','insurance_contract_liability'),('其他负债','other_liabilities'),('负债合计','total_liabilities'),('负债及所有者权益总计','total_liabilities_and_equity')]
    out.append('<p><b>表 5 · 财务报表_MTD (financial_statement_mtd) / 表 6 · 财务报表_YTD (financial_statement_ytd) 行项目</b></p>')
    out.append('<table><thead><tr><th>中文字段名（行项目）</th><th>英文标识</th></tr></thead><tbody>')
    for cn, en in fs_items:
        out.append('<tr><td>%s</td><td><span class="code">%s</span></td></tr>' % (cn, en))
    out.append('</tbody></table>')
    return ''.join(out)

# ---------- 内容 ----------
body = []
A = body.append

A('<div class="cover"><div class="bar"></div>')
A('<h1>IFRS17 财务预测系统</h1>')
A('<div class="sub">产品需求文档（PRD）— PAA 保费分配法财务预测与验证平台</div>')
A('<div class="meta">')
A('<span>文档版本：<b>v1.0</b></span>')
A('<span>系统版本：<b>v5.9.92</b></span>')
A('<span>编制日期：<b>2026-08-20</b></span>')
A('<span>密级：<b>内部</b></span>')
A('<span>适用机构：<b>中华财险 · 创新研发中心</b></span>')
A('</div></div>')

A('<div class="wrap">')

# 目录
A('<div class="toc"><h3>目录</h3>')
toc = [
    ("1. 修订记录", ""),
    ("2. 产品概述", ""),
    ("2.1 项目背景", "lv2"), ("2.2 产品定位", "lv2"), ("2.3 目标用户", "lv2"),
    ("2.4 核心价值与目标", "lv2"),
    ("3. 用户角色与权限", ""),
    ("4. 功能需求", ""),
    ("4.1 数据输入管理", "lv2"), ("4.2 计算引擎", "lv2"), ("4.3 结果展示面板", "lv2"),
    ("4.4 计量结果输出", "lv2"), ("4.5 验证差异比对", "lv2"),
    ("4.6 数据及逻辑归集", "lv2"), ("4.7 系统管理", "lv2"),
    ("5. 数据架构", ""),
    ("5.1 总体数据模型", "lv2"), ("5.2 输入数据（35 张物理表）", "lv2"),
    ("5.3 输出数据（6 张物理表）", "lv2"), ("5.4 计算版本存储", "lv2"), ("5.5 全量字段中英文映射", "lv2"),
    ("6. 技术架构", ""),
    ("7. 非功能性需求", ""),
    ("8. 验收标准", ""),
    ("9. 版本管理与部署", ""),
    ("附录 A. 前端导航清单", "lv2"), ("附录 B. 后端 API 清单", "lv2"),
    ("附录 C. 术语表", "lv2"),
]
for txt, cls in toc:
    A(f'<a class="{cls}" href="#{txt.split(" ",1)[0]}">{txt}</a>')
A('</div>')

# 1 修订记录
A('<section id="1"><h2>1. 修订记录</h2>')
A('<table><thead><tr><th>版本</th><th>日期</th><th>说明</th><th>作者</th></tr></thead><tbody>')
rev = [
    ("v1.0", "2026-08-20", "首版 PRD：汇总系统功能、数据架构、技术架构、非功能需求与部署方案（基于 v5.9.92 代码基线）", "AI 辅助编撰"),
    ("v5.9.92", "2026-08-19", "35 张输入表拆为各自带真实列的物理表（1,743 字段）；上传双写 + 存量回填", "研发"),
    ("v5.9.82", "2026-08-17", "系统运行日志、SQL 查询、计算版本入库（CalculationVersion/Snapshot）", "研发"),
    ("v5.9.78", "2026-08-11", "基础情景验证/计量改走引擎实时输出（B 方案），fixture 仅作黄金基准占位", "研发"),
    ("v5.9.74", "2026-08-04", "字段中英文中心化注册表（field_names.py）英文化重构", "研发"),
]
for r in rev:
    A(f"<tr><td><b>{r[0]}</b></td><td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td></tr>")
A('</tbody></table></section>')

# 2 产品概述
A('<section id="2"><h2>2. 产品概述</h2>')
A('<h3>2.1 项目背景</h3>')
A('<p>《国际财务报告准则第 17 号（IFRS17）》自 2023-01-01 起生效，要求保险公司以统一计量模型（BBA / PAA / VFA）'
  '列报保险合同资产负债与损益。财险（非寿险）业务普遍适用 <b>PAA 保费分配法</b>，其计量高度依赖'
  '对未来保费、赔付、费用现金流的分月预测与利率折现。</p>')
A('<p>本系统原为<b>安永（EY）资产负债管理模型</b>的 AI 改造版，落地为中华财险自研的 IFRS17 财务预测工具，'
  '覆盖「输入数据标准化 → 自动计量 → 六表零差异验证 → 财务报表与预测分析」的完整闭环，'
  '支撑偿付能力、预算管理与经营分析的精算财务工作。</p>')
A('<h3>2.2 产品定位</h3>')
A('<p>面向财险精算与财务团队的 <b>IFRS17 PAA 法财务预测与验证平台</b>：'
  '以 Excel/系统对接方式采集预测假设，由 Python 计量引擎完成分月 PAA 计量，'
  '输出标准财务报表并可对压力情景做多情景比对、预实分析与新旧准则桥接，'
  '内置黄金基准校验（六表零差异）保障计量正确性。</p>')
A('<h3>2.3 目标用户</h3>')
A('<ul>'
  '<li><b>精算 / 财务分析师</b>：维护预测假设、执行计算、查看财务报表与情景分析；</li>'
  '<li><b>数据录入 / 对接人员</b>：上传手工 Excel 与系统对接数据；</li>'
  '<li><b>系统管理员</b>：用户权限、部署推送、运行日志、SQL 查询、数据字典维护。</li></ul>')
A('<h3>2.4 核心价值与目标</h3>')
A('<div class="grid">')
A('<div class="card"><div class="t">标准化输入</div>35 张输入表物理化，含 1,743 个真实字段（月度 m01~m60、险类拆分），中英文列名一致可审计。</div>')
A('<div class="card"><div class="t">自动化计量</div>PAA 引擎分月计量新/现有业务，支持基础 + 4 套压力情景异步计算与进度可视化。</div>')
A('<div class="card"><div class="t">可信验证</div>六表零差异比对 + 情景黄金基准 fixture + 预测时点筛选，差异可下钻到单元格。</div>')
A('<div class="card"><div class="t">决策分析</div>财务报表（MTD/YTD）、分险种利润表、多情景比对、预实分析、新旧准则桥接。</div>')
A('</div></section>')

# 3 角色权限
A('<section id="3"><h2>3. 用户角色与权限</h2>')
A('<p class="lead">系统采用 Django 自带账号体系，按角色控制功能可见性与操作权限（权限位：<span class="code">can_upload</span> 等）。</p>')
A('<table><thead><tr><th>角色</th><th>示例账号</th><th>权限范围</th><th>典型操作</th></tr></thead><tbody>')
roles = [
    ("管理员 Admin", "admin / admin123", "全部权限（含系统管理、SQL 查询、部署、日志）", "用户管理、部署推送、运行日志审计、SQL 只读查询、数据表字典维护"),
    ("上传员 Uploader", "uploader / upload123", "数据输入权限（<span class='code'>can_upload</span>）", "Excel 上传、系统对接上传、预实/旧准则数据上传、数据预览与下载"),
    ("只读 Viewer", "viewer / viewer123", "只读（不可上传/计算/导出/管理）", "查看计算结果、财务报表、验证比对、数据字典"),
]
for r in roles:
    A(f"<tr><td><b>{r[0]}</b></td><td><span class='code'>{r[1]}</span></td><td>{r[2]}</td><td>{r[3]}</td></tr>")
A('</tbody></table>')
A('<div class="note">若公司要求对接统一身份认证（LDAP / OAUTH / SSO），需额外开发，不属于当前内置能力。</div>')
A('</section>')

# 4 功能需求
A('<section id="4"><h2>4. 功能需求</h2>')
A('<p class="lead">以下功能模块与前端导航（<span class="code">app.js pageTitles</span>）、后端 API（<span class="code">views.py</span>）一一对应。</p>')

# 4.1 数据输入
A('<h3>4.1 数据输入管理</h3>')
A('<div class="card"><div class="t">4.1.1 Excel 上传接口（excel-upload）</div>'
  '25 张手工输入表的 Excel 上传、结构校验、落库与历史记录；支持单表数据预览与下载（<span class="code">api_upload / api_upload_history / api_download_sheet</span>）。</div>')
A('<div class="card"><div class="t">4.1.2 系统对接接口（system-dock-upload）</div>'
  '10 张系统对接表（核心系统 / 数仓对接，如系统期初余额表、初始确认利率曲线、即期利率曲线等）上传与校验（<span class="code">api_upload</span> 同通道，来源标记 dock）。</div>')
A('<div class="card"><div class="t">4.1.3 预实分析上传（actual-upload）</div>'
  '实际数与旧准则数据上传，支撑预实分析与新旧准则桥接（<span class="code">api_upload_actual / api_upload_old_standard</span>）。</div>')
A('<div class="card"><div class="t">4.1.4 输入数据物理化</div>'
  '35 张输入表在 MySQL 中各对应一张独立物理表，含真实列结构（文本维度列 + 月度列 m01~m60 + 险类拆分列）；'
  '上传时双写（旧 active 行置否、新行置真），<span class="code">get_input_tables()</span> 返回真实字段，数据字典展示字段结构。</div>')
A('<p>输入表分组（部分列举）：新业务保费收入、新业务应收保费减值、预期赔付率/维持费用率/获取费用率、'
  '保费现金流模式（新/现有）、IACF 现金流模式、未到期/未决赔付模式、合同组关键假设（现有业务）、'
  '基本信息、对应关系配置表、压力情景配置表、财务报表实际数、初始确认/即期利率曲线等。</p>')

# 4.2 计算引擎（展开：中间计算表 + 输出结果表字段逻辑推演）
A('<h3>4.2 计算引擎</h3>')
A('<p class="lead">计算引擎（<span class="code">paa_engine/engine.py</span>）以 PAA 保费分配法为核心，'
  '由 <span class="code">run()</span> 主流程按 6 步管线执行：<b>基本信息 → 情景参数 → 利率曲线加工 → 输入整理 → '
  '新/现有业务计量（60×60 现金流预测三角/开发三角 + 折现）→ 汇总与财务报表</b>。下面分别对「中间计算表」与「6 张输出结果表」做字段逻辑推演 '
  '（加工逻辑类型：<span class="badge b-core">直接取值</span> 取输入原值 / '
  '<span class="badge b-opt">查找</span> 按键值查表 / <span class="badge b-req">加和</span> 跨行累加 / '
  '<span class="badge b-req">计算</span> 按 PAA 公式推导 / <span class="badge b-opt">归集映射</span> 由输出列映射到财务科目）。</p>')

A('<h4>4.2.0 计算总流程（run 管线）</h4>')
A(derive_table(
  ['步骤', '处理', '主要输入（来源表）', '产出'],
  [ ('1 基本信息', '读取评估时点与预测期数', '基本信息表', 'eval_date / forecast_periods'),
    ('2 情景参数', '加载基础 + 压力情景月度参数', '压力情景配置表 + 基础参数', 'scenario_params（按年取赔付率/费用率/利率压力）'),
    ('3 利率曲线加工', '加工月度折现因子与远期利率', '初始确认利率曲线 / 即期利率曲线', '月度折现因子_期末 / 月度远期利率'),
    ('4 输入整理', '组织新/现有业务关键假设', '预期赔付率/维持费用率/获取费用率/现金流模式/系统期初余额/合同组关键假设', 'input_organized（新/现有业务假设 + 利率曲线）'),
    ('5 业务计量', '构建 60×60 现金流预测三角（开发三角）并 PAA 聚合', 'input_organized + 利率曲线', '新/现有业务现金流预测三角 + PAA 聚合（输出_* 列）'),
    ('6 汇总与报表', '合并新/现有 + 生成财务报表', 'combined_summary', '汇总表 + PAA_MTD + 财务报表 MTD/YTD') ]))

A('<h4>4.2.1 中间计算表（输入整理与计量）</h4>')
A('<p>中间结果存于内存（<span class="code">result.input_organized / new_business_predict / existing_business_predict</span>），'
  '并经 <span class="code">translate_out_deep</span> 转回中文列名，供「输入整理 / 新业务计量 / 现有业务计量」页展示。</p>')

A('<p><b>中间表 A · 新业务假设整理</b>（<span class="code">_organize_key_assumptions_new</span>，行维度：预测组 × 险类 × 业务类型，经情景压力缩放）</p>')
A(derive_table(['字段(中文)', '英文', '加工逻辑', '来源表/字段（中文）', '计算逻辑', '说明'],
  [ ('预测组ID', 'forecast_group_id', '直接取值', '合同组拼接.新业务预测组ID', '直接取合同组拼接表中该新业务预测组对应的预测组ID原值，无加工', '业务分组键'),
    ('预测组', 'forecast_group', '直接取值', '合同组关键假设(新业务).预测组 / 合同组拼接', '直接取合同组关键假设(新业务)的预测组原值（回退合同组拼接）', '业务分组名'),
    ('评估期开始业务预期写入时间（月）', 'expected_writing_period_months', '直接取值', '合同组关键假设(新业务).E / 合同组拼接', '直接取合同组关键假设(新业务)的评估期开始业务预期写入时间（月）原值（回退合同组拼接写入月数）', '写入时点月数'),
    ('精算险类', 'actuarial_lob', '直接取值', '合同组关键假设(新业务).精算险类 / 对应关系配置表', '直接取合同组关键假设(新业务)的精算险类原值（回退对应关系配置表精算险类列）', '险种归类'),
    ('合同组合名称', 'contract_portfolio_name', '直接取值', '对应关系配置表.合同组合名称', '直接取对应关系配置表.合同组合名称原值', '组合名'),
    ('业务类型', 'business_type', '直接取值', '合同组关键假设(新业务).业务类型 / 对应关系配置表 / 默认"直保或分入"', '直接取合同组关键假设(新业务)的业务类型原值（回退对应关系配置表，缺省"直保或分入"）', '直保或分入 / 分出'),
    ('保费写入时点', '保费写入时点', '计算', 'EOMONTH(评估日, 评估期开始业务预期写入时间（月）)', '计算 = EOMONTH(评估日, 评估期开始业务预期写入时间（月）)，取评估日加N个月后的月末日期', '月末写入时点'),
    ('保费收入', 'premium_income', '计算', '合同组关键假设(新业务).保费收入 × (1 + 原保险保费增长压力)', '计算 = 合同组关键假设(新业务).保费收入 × (1 + 原保险保费增长压力[按写入时点所在年取])，情景压力缩放后保费', '情景缩放后保费'),
    ('获取费用', 'acquisition_cost', '计算', '合同组关键假设(新业务).获取费用 × (1 + 原保险保费增长压力)', '计算 = 合同组关键假设(新业务).获取费用 × (1 + 原保险保费增长压力[按写入时点所在年取])；分出组取IACF', '分出组取 IACF'),
    ('再保前生效保费', '再保前生效保费', '计算', '生效保费_新业务.第N个月（N=评估期开始业务预期写入时间（月））, 预测组=本表预测组', '查找「生效保费_新业务」表，按 预测组=本表预测组、第N个月（N=评估期开始业务预期写入时间（月））取数值，再 × (1+原保险保费增长压力)', '新业务生效保费'),
    ('分出比例', '分出比例', '计算', '预期摊回比例_新业务.第N个月（N=评估期开始业务预期写入时间（月））, 精算险类=本表精算险类', '查找「预期摊回比例_新业务」表，按 精算险类=本表精算险类、第N个月（N=评估期开始业务预期写入时间（月））取数值（比例不缩放）', '再保分出比例'),
    ('签单保费', '签单保费', '计算', '签单保费_新业务.第N个月（N=评估期开始业务预期写入时间（月））, 预测组=本表预测组', '查找「签单保费_新业务」表，按 预测组=本表预测组、第N个月（N=评估期开始业务预期写入时间（月））取数值，再 × (1+原保险保费增长压力)', '新业务签单保费'),
    ('当期确认比例', 'current_recognition_ratio', '计算', '占位常量 1.0（由现金流 confirm_ratio 覆盖）', '占位常量 1.0；实际由新业务现金流计算 confirm_ratio = 未到期赚取模式[1] 覆盖', '收入确认进度'),
    ('获取现金流摊销比例', 'iacf_amortization_ratio', '计算', '占位常量 1.0（由现金流 amortization_ratio 覆盖）', '占位常量 1.0；实际由新业务现金流计算 amortization_ratio 覆盖', 'IACF 摊销'),
    ('当期提前初始确认签单保费', 'advance_written_premium', '计算', '合同组关键假设(新业务).当期提前初始确认签单保费 × (1 + 原保险保费增长压力)', '计算 = 合同组关键假设(新业务).当期提前初始确认签单保费 × (1 + 原保险保费增长压力[按写入时点所在年取])', '投资成分基数') ]))

A('<p><b>中间表 B · 现有业务假设整理</b>（<span class="code">_organize_key_assumptions_existing</span>，含期初余额，行维度：合同组 × 预测组）</p>')
A(derive_table(['字段(中文)', '英文', '加工逻辑', '来源表/字段（中文）', '计算逻辑', '说明'],
  [ ('合同组ID', 'contract_group_id', '直接取值', '合同组拼接.合同组ID', '直接取合同组拼接表中该现有业务组对应的合同组ID原值', '合同组键'),
    ('现有业务预测组ID', '现有业务预测组ID', '直接取值', '合同组拼接.现有业务预测组ID', '直接取合同组拼接表.现有业务预测组ID原值', '现有业务分组键'),
    ('现有业务预测组', 'exist_biz_forecast_group', '直接取值', '合同组拼接.现有业务预测组', '直接取合同组拼接表.现有业务预测组原值', '现有业务分组名'),
    ('预测组ID', 'forecast_group_id', '直接取值', '合同组拼接.预测组ID', '直接取合同组拼接表.预测组ID原值', '预测组键'),
    ('预测组', 'forecast_group', '直接取值', '合同组拼接.预测组', '直接取合同组拼接表.预测组原值', '预测组名'),
    ('合同组名称', 'contract_group_name', '直接取值', '合同组拼接.合同组名称', '直接取合同组拼接表中该现有业务组对应的合同组名称原值', '合同组名'),
    ('精算险类', 'actuarial_lob', '直接取值', '合同组拼接.精算险类', '直接取合同组拼接表.精算险类原值', '险种归类'),
    ('直保或分入/分出', 'direct_or_ceded', '直接取值', '合同组拼接.业务类型', '直接取合同组拼接表.业务类型原值（直保或分入 / 分出）', '业务类型'),
    ('评估期开始业务预期写入时间（月）', 'expected_writing_period_months', '直接取值', '合同组拼接.评估期开始业务预期写入时间（月）', '直接取合同组拼接表.评估期开始业务预期写入时间（月）原值', '写入时点月数'),
    ('保费写入时点', '保费写入时点', '计算', 'EOMONTH(评估日, 评估期开始业务预期写入时间（月）)', '计算 = EOMONTH(评估日, 评估期开始业务预期写入时间（月）)，取评估日加N个月后的月末日期', '月末写入时点'),
    ('保费收入', 'premium_income', '直接取值', '合同组关键假设_现有业务.应收保费', '直接取合同组关键假设_现有业务.应收保费原值（期初应收保费）', '期初应收保费'),
    ('获取费用', 'acquisition_cost', '直接取值', '合同组关键假设_现有业务.应付IACF', '直接取合同组关键假设_现有业务.应付IACF原值（期初应付IACF）', '期初应付 IACF'),
    ('应收保费', 'premium_receivable', '直接取值', '合同组关键假设_现有业务.应收保费', '直接取合同组关键假设_现有业务.应收保费原值', '期初应收'),
    ('应付IACF', 'iacf_payable', '直接取值', '合同组关键假设_现有业务.应付IACF', '直接取合同组关键假设_现有业务.应付IACF原值', '期初应付 IACF'),
    ('未决风险调整%', 'lic_risk_adj_ratio_pct', '查找', '风险调整比例.lic_risk_adj_ratio_pct', '查找「风险调整比例」表，按 精算险类=本表精算险类 匹配取该列值', '已发生风险调整比例'),
    ('未到期风险调整%', 'lrc_risk_adj_ratio_pct', '查找', '风险调整比例.lrc_risk_adj_ratio_pct', '查找「风险调整比例」表，按 精算险类=本表精算险类 匹配取该列值', '未到期风险调整比例'),
    ('待摊销保险收入_期初', '待摊销保险收入_期初', '直接取值', '系统期初余额表.待摊销保险收入', '直接取系统期初余额表.待摊销保险收入原值（按预测维度+业务类型+精算险类匹配）', '期初待摊收入'),
    ('待摊销获取现金流_期初', '待摊销获取现金流_期初', '直接取值', '系统期初余额表.待摊销获取现金流', '直接取系统期初余额表.待摊销获取现金流原值', '期初待摊 IACF'),
    ('未到期责任负债_非亏损部分_期初', '未到期责任负债_非亏损部分_期初', '直接取值', '系统期初余额表.未到期责任负债_非亏损部分(不含利净)', '直接取系统期初余额表.未到期责任负债_非亏损部分(不含利净)原值', '期初 LRC 非亏损'),
    ('未到期责任负债_亏损部分_期初', '未到期责任负债_亏损部分_期初', '直接取值', '系统期初余额表.未到期责任负债_亏损部分', '直接取系统期初余额表.未到期责任负债_亏损部分原值', '期初 LRC 亏损'),
    ('未到期责任负债_亏损摊回_期初', '未到期责任负债_亏损摊回_期初', '直接取值', '系统期初余额表.未到期责任负债_亏损摊回', '直接取系统期初余额表.未到期责任负债_亏损摊回原值', '期初 LRC 亏损摊回'),
    ('已发生未决赔款负债_预期现金流_期初', '已发生未决赔款负债_预期现金流_期初', '直接取值', '系统期初余额表.已发生未决赔款负债_预期现金流', '直接取系统期初余额表.已发生未决赔款负债_预期现金流原值', '期初 LIC 预期现金流'),
    ('间接理赔费用负债_预期现金流_期初', '间接理赔费用负债_预期现金流_期初', '直接取值', '系统期初余额表.间接理赔费用负债_预期现金流', '直接取系统期初余额表.间接理赔费用负债_预期现金流原值', '期初 LAE 预期现金流'),
    ('已发生未决赔款负债_再保人不履约_预期现金流_期初', '已发生未决赔款负债_再保人不履约_预期现金流_期初', '直接取值', '系统期初余额表.已发生未决赔款负债_再保人不履约_预期现金流', '直接取系统期初余额表.已发生未决赔款负债_再保人不履约_预期现金流原值', '期初 LIC 不履约预期现金流'),
    ('已发生未决赔款负债_非金融风险调整_期初', '已发生未决赔款负债_非金融风险调整_期初', '直接取值', '系统期初余额表.已发生未决赔款负债_非金融风险调整', '直接取系统期初余额表.已发生未决赔款负债_非金融风险调整原值', '期初 LIC 风险调整'),
    ('间接理赔费用负债_非金融风险调整_期初', '间接理赔费用负债_非金融风险调整_期初', '直接取值', '系统期初余额表.间接理赔费用负债_非金融风险调整', '直接取系统期初余额表.间接理赔费用负债_非金融风险调整原值', '期初 LAE 风险调整'),
    ('已发生未决赔款负债_再保人不履约_非金融风险调整_期初', '已发生未决赔款负债_再保人不履约_非金融风险调整_期初', '直接取值', '系统期初余额表.已发生未决赔款负债_再保人不履约_非金融风险调整', '直接取系统期初余额表.已发生未决赔款负债_再保人不履约_非金融风险调整原值', '期初 LIC 不履约风险调整') ]))

A('<p><b>中间表 C · 利率曲线加工</b>（<span class="code">_process_interest_rate_curve</span>，月度为索引，预测期×12 与 120 取大者为深度上限）</p>')
A(derive_table(['字段(中文)', '英文', '加工逻辑', '来源表/字段（中文）', '计算逻辑', '说明'],
  [ ('月度折现远期利率', 'monthly_rate', '计算', '月>1：月度折现因子_期末[月] ÷ 月度折现因子_期末[月-1] - 1；否则 年化利率_预测期 ÷ 12', '计算 = 若月>1，月度折现因子_期末(月) ÷ 月度折现因子_期末(月-1) - 1；若月=1，年化利率_预测期 ÷ 12。推导出当期计息月利率', '当期计息利率'),
    ('月度折现因子_期末', 'discount_factor_end', '计算', '(1 + 年化利率_预测期 ÷ 12) ^ (-月)', '计算 = (1 + 年化利率_预测期 ÷ 12) ^ (-月)，将第月月末现金流折到第0月', '期末时点折现'),
    ('月度折现因子_期初', 'discount_factor_begin', '计算', '(1 + 年化利率_预测期 ÷ 12) ^ (-月 + 1)', '计算 = (1 + 年化利率_预测期 ÷ 12) ^ (-月 + 1)，将第月月初现金流折到第0月', '期初时点折现'),
    ('年化利率_预测期', 'annual_rate_forecast', '计算', '即期利率曲线.年利率 × (1 + 情景即期利率调整)[按所属年取压力]', '计算 = 即期利率曲线.年利率 × (1 + 情景即期利率调整[按所属年取压力值])，含情景压力的预测期年利率', '含情景压力的年利率'),
    ('年化利率_评估日', 'annual_rate_eval', '直接取值', '即期利率曲线.年利率（不施加情景压力）', '直接取即期利率曲线.年利率原值（不施加情景压力）', '基础年利率') ]))

A('<h4>4.2.2 输出结果表（6 张物理表）字段逻辑推演</h4>')

A('<p><b>表 1 · PAA计算_新业务整理</b>（<span class="code">paa_new_business_organized</span>，行维度 = 中间表 A × 预测间隔；PAA 计量列来自引擎内部构建的 <b>60×60 现金流预测三角（开发三角）</b>，该三角由保费/IACF/赚取模式、预期赔付率、维持费用率、投资成分比例、预期摊回比例、风险调整比例等输入表按月展开并折现后聚合而成）</p>')
A(derive_table(['字段(中文)', '英文', '加工逻辑', '来源表/字段（中文）', '计算逻辑', '说明'],
  [ ('子合同组合名称', 'sub_contract_portfolio_name', '直接取值', '中间表A.精算险类', '直接取中间表A.精算险类原值（按 预测组ID&预测间隔 关联）', '行维度'),
    ('评估期开始业务预期写入时间（月）', 'expected_writing_period_months', '直接取值', '中间表A', '直接取中间表A.评估期开始业务预期写入时间（月）原值', '行维度'),
    ('预测组', 'forecast_group', '直接取值', '中间表A', '直接取中间表A.预测组原值', '行维度'),
    ('预测组ID', 'forecast_group_id', '直接取值', '中间表A', '直接取中间表A.预测组ID原值', '行维度'),
    ('直保或分入/分出', 'direct_or_ceded', '直接取值', '中间表A.业务类型', '直接取中间表A.业务类型原值', '行维度'),
    ('精算险类', 'actuarial_lob', '直接取值', '中间表A', '直接取中间表A.精算险类原值', '行维度'),
    ('评估日', 'valuation_date', '直接取值', '基本信息.评估日', '直接取基本信息.评估日原值', '行维度'),
    ('预测时点', 'forecast_point', '计算', 'EOMONTH(评估日, 预测间隔)', '计算 = EOMONTH(评估日, 预测间隔)，取评估日加N个预测间隔月后的月末日期', '月末时点'),
    ('预测时点年初', 'forecast_point_year_start', '计算', 'DATE(预测时点年-1, 12, 31)', '计算 = DATE(预测时点年份-1, 12, 31)，取上年末作为年初基准', '年初基准'),
    ('预测间隔', 'forecast_interval', '直接取值', 'period (1..N)', '直接取现金流三角的 period 序号 (1..N)', '行维度'),
    ('数据来源表', 'source_table', '直接取值', '"新业务预期现金流_{预测间隔}"', '直接拼接字符串"新业务预期现金流_{预测间隔}"作为溯源标记', '溯源标记'),
    ('当期确认比例', 'current_recognition_ratio', '计算', '现金流.confirm_ratio = 未到期赚取模式[1]', '计算 = 新业务现金流三角 confirm_ratio = 未到期赚取模式[1]（收入确认进度）', '收入确认进度'),
    ('获取现金流摊销比例', 'iacf_amortization_ratio', '计算', '现金流.amortization_ratio', '计算 = 新业务现金流三角 amortization_ratio（IACF 摊销进度）', 'IACF 摊销进度'),
    ('投资成分比例%', 'investment_component_ratio_pct', '计算', '现金流.investment_ratio', '计算 = 新业务现金流三角 investment_ratio（投资成分占比）', '投资成分比例'),
    ('预期摊回比例%', 'expected_recovery_ratio_pct', '计算', '现金流.ceding_recover_ratio', '计算 = 新业务现金流三角 ceding_recover_ratio（再保摊回占比）', '再保摊回比例'),
    ('当月计息利率', 'current_accrual_rate', '查找', '中间表C.月度折现远期利率[预测间隔]', '查找中间表C.月度折现远期利率，按下标=预测间隔月份取数作为当期计息利率', '当期计息'),
    ('保费收入', 'premium_income', '计算', '直保 = 中间表A.保费收入；分出 = 输出_现金流_收到的保费', '计算 = 直保取 中间表A.保费收入；分出取 输出_现金流_收到的保费', '行维度'),
    ('获取费用', 'acquisition_cost', '计算', '直保 = 中间表A.获取费用；分出 = 输出_现金流_支付的IACF', '计算 = 直保取 中间表A.获取费用；分出取 输出_现金流_支付的IACF', '行维度'),
    ('输出_保险合同收入', 'out_insurance_contract_revenue', '计算', '-(保险收入)；保险收入 = 待摊销保险收入×当期确认比例 + 分解投资成分（现金流预测三角聚合）', '计算 = -(保险收入)；保险收入 = 待摊销保险收入×当期确认比例 + 分解投资成分（来自 60×60 现金流预测三角聚合）', 'PAA 收入'),
    ('输出_新增保费减值', 'out_premium_impairment_addition', '计算', '常量 0（引擎预留列，当前未产出）', '常量 0，引擎预留列，当前版本未产出', '预留'),
    ('输出_未到期责任负债_非亏损部分', 'out_lrc_non_onerous', '计算', '收到保费 + 支出IACF(负) + 未到期计息 + 保险收入 + 摊销获取费用 + 分解投资成分（新业务期初为0）', '计算 = 收到保费 + 支出IACF(负) + 未到期计息 + 保险收入 + 摊销获取费用 + 分解投资成分（新业务期初为0）', 'LRC 非亏损'),
    ('输出_未到期责任负债_亏损部分', 'out_lrc_onerous', '计算', 'MAX(预期未来现金流合计 - 期末非亏损未到期负债, 0)', '计算 = MAX(预期未来现金流合计 - 期末非亏损未到期负债, 0)', 'LRC 亏损'),
    ('输出_未到期责任负债_亏损摊回', 'out_lrc_onerous_recoverable', '计算', '-亏损部分 × 预期摊回比例', '计算 = -亏损部分 × 预期摊回比例', 'LRC 亏损摊回'),
    ('输出_已发生未决赔款负债_预期现金流', 'out_lic_expected_cf', '计算', '新业务现金流预测三角 · 已发生未决赔款负债_预期现金流（赔付现金流 × 折现因子_期末）', '计算 = Σ 新业务现金流预测三角中「已发生未决赔款负债_预期现金流」列，即各事故月/发展月组合的赔付现金流 × 折现因子_期末 后聚合', 'LIC 预期现金流'),
    ('输出_间接理赔费用负债_预期现金流', 'out_lae_liability_expected_cf', '计算', '新业务现金流预测三角 · 间接理赔费用负债_预期现金流（间接理赔现金流 × 折现因子_期末）', '计算 = Σ 新业务现金流预测三角中「间接理赔费用负债_预期现金流」列', 'LAE 预期现金流'),
    ('输出_已发生未决赔款负债_再保人不履约_预期现金流', 'out_lic_rnpr_expected_cf', '计算', '新业务现金流预测三角 · 再保人不履约_预期现金流', '计算 = Σ 新业务现金流预测三角中「再保人不履约_预期现金流」列', 'LIC 不履约预期现金流'),
    ('输出_已发生未决赔款负债_非金融风险调整', 'out_lic_risk_adj', '计算', '新业务现金流预测三角 · 已发生未决赔款负债_非金融风险调整', '计算 = Σ 新业务现金流预测三角中「已发生未决赔款负债_非金融风险调整」列', 'LIC 风险调整'),
    ('输出_间接理赔费用负债_非金融风险调整', 'out_lae_liability_risk_adj', '计算', '新业务现金流预测三角 · 间接理赔费用负债_非金融风险调整', '计算 = Σ 新业务现金流预测三角中「间接理赔费用负债_非金融风险调整」列', 'LAE 风险调整'),
    ('输出_已发生未决赔款负债_再保人不履约_非金融风险调整', 'out_lic_rnpr_risk_adj', '计算', '新业务现金流预测三角 · 再保人不履约_非金融风险调整', '计算 = Σ 新业务现金流预测三角中「再保人不履约_非金融风险调整」列', 'LIC 不履约风险调整'),
    ('输出_保险服务收入', 'out_insurance_contract_revenue', '计算', '= -保险收入（同保险合同收入口径，取负填列）', '计算 = -保险收入（同保险合同收入口径取负填列）', '保险服务收入'),
    ('输出_赔付与费用_分解的投资成分', 'out_claims_expense_investment_component_released', '计算', '-分解投资成分', '计算 = -分解投资成分', '投资成分释放'),
    ('输出_赔付与费用_摊销的保险获取现金流', 'out_claims_expense_iacf_amortized', '计算', '-摊销获取费用', '计算 = -摊销获取费用', 'IACF 摊销'),
    ('输出_亏损合同损益', 'out_onerous_contract_result', '计算', '-(亏损部分 - 期初亏损(0))', '计算 = -(亏损部分 - 期初亏损(0))', '亏损合同'),
    ('输出_亏损摊回损益', 'out_onerous_recoverable_result', '计算', '-(亏损摊回 - 期初亏损摊回(0))', '计算 = -(亏损摊回 - 期初亏损摊回(0))', '亏损摊回'),
    ('输出_赔付与费用_已发生未决赔款负债提转差_预期现金流', 'out_claims_expense_lic_movement_expected_cf', '计算', '-(期末预期现金流 - 期初(0) + 支付赔付)', '计算 = -(期末预期现金流 - 期初(0) + 支付赔付)', 'LIC 提转差'),
    ('输出_赔付与费用_已发生未决赔款负债提转差_非金融风险调整', 'out_claims_expense_lic_movement_risk_adj', '计算', '-(期末NRA - 期初(0))', '计算 = -(期末NRA - 期初(0))', 'LIC 风险调整提转差'),
    ('输出_赔付与费用_间接理赔费用提转差_预期现金流', 'out_claims_expense_lae_movement_expected_cf', '计算', '-(期末间接 - 期初(0) + 支付理赔费用)', '计算 = -(期末间接 - 期初(0) + 支付理赔费用)', 'LAE 提转差'),
    ('输出_赔付与费用_间接理赔费用提转差_非金融风险调整', 'out_claims_expense_lae_movement_risk_adj', '计算', '-(期末间接NRA - 期初(0))', '计算 = -(期末间接NRA - 期初(0))', 'LAE 风险调整提转差'),
    ('输出_赔付与费用_再保人不履约风险提转差_预期现金流', 'out_claims_expense_rnpr_movement_expected_cf', '计算', '-期末再保', '计算 = -期末再保', '不履约提转差'),
    ('输出_赔付与费用_再保人不履约风险提转差_非金融风险调整', 'out_claims_expense_rnpr_movement_risk_adj', '计算', '-期末再保NRA', '计算 = -期末再保NRA', '不履约风险调整提转差'),
    ('输出_IFIE_未到期_未到期计息', 'out_ifie_lrc_accretion', '计算', '-未到期计息', '计算 = -未到期计息', 'IFIE 未到期计息'),
    ('输出_IFIE_已发生未决_已发生未决赔款负债计息_预期现金流', 'out_ifie_lic_accretion_expected_cf', '计算', '0（新业务无期初现值）', '计算 = 0（新业务无期初现值）', 'IFIE LIC 计息'),
    ('输出_IFIE_已发生未决_已发生未决赔款负债计息_非金融风险调整', 'out_ifie_lic_accretion_risk_adj', '计算', '0', '计算 = 0', 'IFIE LIC 风险调整计息'),
    ('输出_IFIE_已发生未决_间接理赔费用计息_预期现金流', 'out_ifie_lae_accretion_expected_cf', '计算', '0', '计算 = 0', 'IFIE LAE 计息'),
    ('输出_IFIE_已发生未决_间接理赔费用计息_非金融风险调整', 'out_ifie_lae_accretion_risk_adj', '计算', '0', '计算 = 0', 'IFIE LAE 风险调整计息'),
    ('输出_现金流_支付的赔付与理赔费用', 'out_cf_claims_and_lae_paid', '计算', '支付赔付 + 支付理赔费用', '计算 = 新业务现金流三角第N月 支付赔付 + 支付理赔费用', '实际赔付流出'),
    ('输出_现金流_支付的维持费用', 'out_cf_maintenance_paid', '计算', '支付维持', '计算 = 新业务现金流三角第N月 支付维持', '实际维持流出'),
    ('输出_现金流_收到的保费', 'out_cf_premium_received', '计算', '当期收到保费', '计算 = 新业务现金流三角第N月 当期收到保费', '实际保费流入'),
    ('输出_现金流_支付的IACF', 'out_cf_iacf_paid', '计算', '当期支出IACF', '计算 = 新业务现金流三角第N月 当期支出IACF', '实际 IACF 流出'),
    ('输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流', 'out_oci_lic_accretion_rate_change_expected_cf', '计算', '-(期末预期现金流 - 期初(0) + 提转差预期现金流 + IFIE预期现金流)', '计算 = -(期末预期现金流 - 期初(0) + 提转差预期现金流 + IFIE预期现金流)', 'OCI LIC 利率变化'),
    ('输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整', 'out_oci_lic_accretion_rate_change_risk_adj', '计算', '-(期末NRA - 期初(0) + 提转差NRA + IFIE_NRA)', '计算 = -(期末NRA - 期初(0) + 提转差NRA + IFIE_NRA)', 'OCI LIC 风险调整'),
    ('输出_OCI_已发生未决_间接理赔费用计息与利率变化_预期现金流', 'out_oci_lae_accretion_rate_change_expected_cf', '计算', '-(期末间接 - 期初(0) + 提转差间接 + IFIE间接)', '计算 = -(期末间接 - 期初(0) + 提转差间接 + IFIE间接)', 'OCI LAE 利率变化'),
    ('输出_OCI_已发生未决_间接理赔费用计息与利率变化_非金融风险调整', 'out_oci_lae_accretion_rate_change_risk_adj', '计算', '-(期末间接NRA - 期初(0) + 提转差间接NRA + IFIE间接NRA)', '计算 = -(期末间接NRA - 期初(0) + 提转差间接NRA + IFIE间接NRA)', 'OCI LAE 风险调整') ]))

A('<p><b>表 2 · PAA计算_现有业务整理</b>（<span class="code">paa_existing_business_organized</span>，行维度 = 中间表 B × 预测间隔；PAA 计量列来自引擎内部构建的 <b>60×60 现金流预测三角（开发三角）</b> + 折现 + 期初余额滚动；开发三角由保费/IACF/赚取模式、预期赔付率、维持费用率、风险调整比例、期初余额等输入表按月展开而成）</p>')
A(derive_table(['字段(中文)', '英文', '加工逻辑', '来源表/字段（中文）', '计算逻辑', '说明'],
  [ ('精算险类', 'actuarial_lob', '直接取值', '中间表B', '直接取中间表B.精算险类原值（按 合同组ID&预测间隔 关联）', '行维度'),
    ('评估期开始业务预期写入时间（月）', 'expected_writing_period_months', '直接取值', '中间表B', '直接取中间表B.评估期开始业务预期写入时间（月）原值', '行维度'),
    ('合同组名称', 'contract_group_name', '直接取值', '中间表B', '直接取中间表B.合同组名称原值', '行维度'),
    ('合同组ID', 'contract_group_id', '直接取值', '中间表B', '直接取中间表B.合同组ID原值', '行维度'),
    ('现有业务预测组ID', '现有业务预测组ID', '直接取值', '中间表B', '直接取中间表B.现有业务预测组ID原值', '行维度'),
    ('预测组', 'forecast_group', '直接取值', '中间表B', '直接取中间表B.预测组原值', '行维度'),
    ('直保或分入/分出', 'direct_or_ceded', '直接取值', '中间表B', '直接取中间表B.业务类型原值', '行维度'),
    ('评估日 / 预测时点 / 预测时点年初 / 预测间隔 / 数据来源表', 'valuation_date/forecast_point/forecast_point_year_start/forecast_interval/source_table', '直接取值/计算', '同表1 行维度逻辑', '评估日直接取基本信息；预测时点=EOMONTH(评估日,预测间隔)；预测时点年初=DATE(年-1,12,31)；预测间隔取 period；数据来源表拼接字符串', '行维度'),
    ('当期确认比例 / 获取现金流摊销比例 / 当月计息利率', 'current_recognition_ratio/iacf_amortization_ratio/current_accrual_rate', '计算/查找', '现金流.confirm_ratio / amortization_ratio / 中间表C.月度折现远期利率[预测间隔]', '确认比例=现金流三角confirm_ratio；摊销比例=amortization_ratio；当月计息利率=查找中间表C按下标=预测间隔取数', '比例类'),
    ('待摊销保险收入', 'unamortized_insurance_revenue', '计算', '(期初待摊销保险收入 + 期初UPR - 期初不含利净) × (1 + 当期计息利率)', '计算 = (系统期初余额表.待摊销保险收入 + UPR余额 - 未到期责任负债_非亏损部分_不含利净) × (1 + 当月计息利率)', '期初滚动'),
    ('待摊销获取现金流', 'unamortized_iacf', '计算', '期初待摊销获取现金流 × (1 + 当期计息利率)', '计算 = 系统期初余额表.待摊销获取现金流 × (1 + 当月计息利率)', '期初滚动'),
    ('待摊销投资成分', 'unamortized_investment_component', '计算', '期初待摊销投资成分 × (1 + 当期计息利率)', '计算 = 系统期初余额表.待摊销投资成分 × (1 + 当月计息利率)', '期初滚动'),
    ('未到期责任负债_亏损部分_期初', 'lrc_onerous_opening', '直接取值', '中间表B.未到期责任负债_亏损部分_期初', '直接取系统期初余额表.未到期责任负债_亏损部分原值', '期初存量'),
    ('未到期责任负债_亏损摊回_期初', 'lrc_onerous_recoverable_opening', '直接取值', '中间表B.未到期责任负债_亏损摊回_期初', '直接取系统期初余额表.未到期责任负债_亏损摊回原值', '期初存量'),
    ('未到期责任负债_非亏损部分_期初', 'lrc_non_onerous_opening', '直接取值', '中间表B.未到期责任负债_非亏损部分_期初', '直接取系统期初余额表.未到期责任负债_非亏损部分原值', '期初存量'),
    ('当期收到保费', 'premium_received_current', '计算', '现有业务现金流预测三角 · 当期收到保费（应收保费 × 赚取模式 × 折现因子_期初，AI≤预测时点）', '计算 = -Σ 现有业务现金流预测三角中「当期收到保费」列（应收保费 × 保费现金流模式_现有业务 × 折现因子_期初），仅累计 AI（实际流入月）≤预测时点的行', '实际保费流入'),
    ('当期支出IACF', 'iacf_paid_current', '计算', '现有业务现金流预测三角 · 当期支出IACF（应付IACF × IACF模式 × (1+费用率上升) × 折现因子_期初，AI≤预测时点）', '计算 = -Σ 现有业务现金流预测三角中「当期支出IACF」列（应付IACF × IACF现金流模式_现有业务 × (1+费用率上升) × 折现因子_期初），仅累计 AI≤预测时点的行', '实际 IACF 流出'),
    ('未到期责任负债计息', 'lrc_accretion', '计算', '当期计息利率 × (期初非亏损 + 当期收到保费 + 当期支出IACF)', '计算 = 当月计息利率 × (期初非亏损 + 当期收到保费 + 当期支出IACF)', 'IFIE 未到期计息'),
    ('保险收入', 'insurance_revenue_recognized', '计算', '-待摊销保险收入×确认比例 - 分解投资成分', '计算 = -待摊销保险收入×当期确认比例 - 分解投资成分', 'PAA 收入'),
    ('摊销获取费用', 'acquisition_cost_amortized', '计算', '-待摊销获取现金流×摊销比例', '计算 = -待摊销获取现金流×获取现金流摊销比例', 'IACF 摊销'),
    ('分解投资成分', 'investment_component_released', '计算', '-待摊销投资成分×确认比例', '计算 = -待摊销投资成分×当期确认比例', '投资成分释放'),
    ('未到期责任负债_非亏损部分', 'lrc_non_onerous_closing', '计算', '期初非亏损 + 当期收到保费 + 当期支出IACF + 未到期计息 + 保险收入 + 摊销获取费用 + 分解投资成分', '计算 = 期初非亏损 + 当期收到保费 + 当期支出IACF + 未到期计息 + 保险收入 + 摊销获取费用 + 分解投资成分', 'LRC 非亏损期末'),
    ('预期未来保费现金流入', 'expected_future_premium_inflow', '计算', '现有业务现金流预测三角 · 预期未来保费现金流入（当期收到保费 × 折现因子_期初，AK>预测时点）', '计算 = Σ 现有业务现金流预测三角中「预期未来保费现金流入」列（当期收到保费 × 折现因子_期初），仅累计 AK（现金流发生月）>预测时点的行', '未来保费'),
    ('预期未来保险获取现金流出', 'expected_future_iacf_outflow', '计算', '现有业务现金流预测三角 · 预期未来保险获取现金流出（当期支出IACF × 折现因子_期初，AK>预测时点）', '计算 = Σ 现有业务现金流预测三角中「预期未来保险获取现金流出」列（当期支出IACF × 折现因子_期初），仅累计 AK>预测时点的行', '未来 IACF'),
    ('预期未来赔付现金流出（含间接理赔费用）', 'expected_future_claims_outflow_incl_lae', '计算', '现有业务现金流预测三角 · 预期未来赔付现金流出（已发生赔付现金流 × 折现因子_期末，AK>预测时点）', '计算 = Σ 现有业务现金流预测三角中「预期未来赔付现金流出」列（已发生赔付现金流 × 折现因子_期末），仅累计 AK>预测时点的行', '未来赔付'),
    ('预期未来维持费用现金流出', 'expected_future_maintenance_outflow', '计算', '现有业务现金流预测三角 · 预期未来维持费用现金流出（支付维持 × 折现因子_期末，AK>预测时点）', '计算 = Σ 现有业务现金流预测三角中「预期未来维持费用现金流出」列（支付维持 × 折现因子_期末），仅累计 AK>预测时点的行', '未来维持'),
    ('非金融风险调整', 'risk_adjustment', '计算', '现有业务现金流预测三角 · 非金融风险调整（(预期未来赔付+预期未来维持) × 风险调整比例 × 折现因子_期末，AK>预测时点）', '计算 = Σ 现有业务现金流预测三角中「非金融风险调整」列（(预期未来赔付 + 预期未来维持) × 风险调整比例 × 折现因子_期末），仅累计 AK>预测时点的行', '未来 RA'),
    ('预期未来现金流合计', 'expected_future_cf_total', '计算', '预期未来保费 + 预期未来IACF + 预期未来赔付 + 预期未来维持 + 非金融风险调整', '计算 = 预期未来保费 + 预期未来IACF + 预期未来赔付 + 预期未来维持 + 非金融风险调整', '未来合计'),
    ('未到期责任负债_亏损部分', 'lrc_onerous', '计算', 'MAX(预期未来现金流合计 - 期末非亏损未到期负债, 0)', '计算 = MAX(预期未来现金流合计 - 期末非亏损未到期负债, 0)', 'LRC 亏损'),
    ('未到期责任负债_亏损摊回', 'lrc_onerous_recoverable', '计算', '-亏损部分 × 预期摊回比例', '计算 = -亏损部分 × 预期摊回比例', 'LRC 亏损摊回'),
    ('支付赔付累计', 'cf_claims_paid_cumulative', '计算', '现有业务现金流预测三角 · 支付赔付（d=预测间隔）', '计算 = -Σ 现有业务现金流预测三角中「支付赔付」列，按 发展月 d = 预测间隔 累加', '实际赔付累计'),
    ('支付间接理赔费用累计', 'cf_indirect_lae_paid_cumulative', '计算', '现有业务现金流预测三角 · 支付间接理赔费用（d=预测间隔）', '计算 = -Σ 现有业务现金流预测三角中「支付间接理赔费用」列，按 发展月 d = 预测间隔 累加', '实际 LAE 累计'),
    ('支付维持费用', 'cf_maintenance_paid', '计算', '现有业务现金流预测三角 · 支付维持费用（AI≤预测时点）', '计算 = -Σ 现有业务现金流预测三角中「支付维持费用」列（UPR × 维持费用率 × 赚取模式），仅累计 AI≤预测时点的行', '实际维持流出'),
    ('支付赔付', 'cf_claims_paid', '计算', '支付赔付累计', '计算 = 支付赔付累计', '实际赔付'),
    ('支付间接理赔费用', 'cf_lae_paid', '计算', '支付间接理赔费用累计', '计算 = 支付间接理赔费用累计', '实际 LAE'),
    ('输出_保险合同收入', 'out_insurance_contract_revenue', '计算', '= -保险收入', '计算 = -保险收入', 'PAA 收入'),
    ('输出_未到期责任负债_非亏损部分', 'out_lrc_non_onerous', '计算', '= 未到期责任负债_非亏损部分（期末）', '计算 = 未到期责任负债_非亏损部分（期末）', 'LRC 非亏损'),
    ('输出_未到期责任负债_亏损部分', 'out_lrc_onerous', '计算', '= 未到期责任负债_亏损部分', '计算 = 未到期责任负债_亏损部分', 'LRC 亏损'),
    ('输出_未到期责任负债_亏损摊回', 'out_lrc_onerous_recoverable', '计算', '= 未到期责任负债_亏损摊回', '计算 = 未到期责任负债_亏损摊回', 'LRC 亏损摊回'),
    ('输出_已发生未决赔款负债_预期现金流', 'out_lic_expected_cf', '计算', '现有业务现金流预测三角 · 期末已发生未决赔款负债_预期现金流（支付赔付 × 折现因子_期末，AK>预测时点）', '计算 = Σ 现有业务现金流预测三角中「期末已发生未决赔款负债_预期现金流」列（支付赔付 × 折现因子_期末），仅累计 AK>预测时点的行', 'LIC 预期现金流'),
    ('输出_间接理赔费用负债_预期现金流', 'out_lae_liability_expected_cf', '计算', '现有业务现金流预测三角 · 期末间接理赔费用负债_预期现金流（支付间接理赔费用 × 折现因子_期末，AK>预测时点）', '计算 = Σ 现有业务现金流预测三角中「期末间接理赔费用负债_预期现金流」列（支付间接理赔费用 × 折现因子_期末），仅累计 AK>预测时点的行', 'LAE 预期现金流'),
    ('输出_已发生未决赔款负债_再保人不履约_预期现金流', 'out_lic_rnpr_expected_cf', '计算', '现有业务现金流预测三角 · 期末再保人不履约_预期现金流（支付赔付 × 再保人不履约比例 × 折现因子_期末，AK>预测时点）', '计算 = Σ 现有业务现金流预测三角中「期末再保人不履约_预期现金流」列（支付赔付 × 再保人不履约比例 × 折现因子_期末），仅累计 AK>预测时点的行', 'LIC 不履约预期现金流'),
    ('输出_已发生未决赔款负债_非金融风险调整', 'out_lic_risk_adj', '计算', '现有业务现金流预测三角 · 期末已发生未决赔款负债_非金融风险调整（支付赔付 × 风险调整比例 × 折现因子_期末，AK>预测时点）', '计算 = Σ 现有业务现金流预测三角中「期末已发生未决赔款负债_非金融风险调整」列（支付赔付 × 风险调整比例 × 折现因子_期末），仅累计 AK>预测时点的行', 'LIC 风险调整'),
    ('输出_间接理赔费用负债_非金融风险调整', 'out_lae_liability_risk_adj', '计算', '现有业务现金流预测三角 · 期末间接理赔费用负债_非金融风险调整（支付间接理赔费用 × 风险调整比例 × 折现因子_期末，AK>预测时点）', '计算 = Σ 现有业务现金流预测三角中「期末间接理赔费用负债_非金融风险调整」列（支付间接理赔费用 × 风险调整比例 × 折现因子_期末），仅累计 AK>预测时点的行', 'LAE 风险调整'),
    ('输出_已发生未决赔款负债_再保人不履约_非金融风险调整', 'out_lic_rnpr_risk_adj', '计算', '现有业务现金流预测三角 · 期末再保人不履约_非金融风险调整（支付赔付 × 再保人不履约比例 × 风险调整比例 × 折现因子_期末，AK>预测时点）', '计算 = Σ 现有业务现金流预测三角中「期末再保人不履约_非金融风险调整」列（支付赔付 × 再保人不履约比例 × 风险调整比例 × 折现因子_期末），仅累计 AK>预测时点的行', 'LIC 不履约风险调整'),
    ('输出_保险服务收入', 'out_insurance_contract_revenue', '计算', '= -保险收入', '计算 = -保险收入', '保险服务收入'),
    ('输出_赔付与费用_分解的投资成分', 'out_claims_expense_investment_component_released', '计算', '= -分解投资成分', '计算 = -分解投资成分', '投资成分释放'),
    ('输出_赔付与费用_摊销的保险获取现金流', 'out_claims_expense_iacf_amortized', '计算', '= -摊销获取费用', '计算 = -摊销获取费用', 'IACF 摊销'),
    ('输出_亏损合同损益', 'out_onerous_contract_result', '计算', '-(亏损部分 - 期初亏损)', '计算 = -(亏损部分 - 期初亏损)', '亏损合同'),
    ('输出_亏损摊回损益', 'out_onerous_recoverable_result', '计算', '-(亏损摊回 - 期初亏损摊回)', '计算 = -(亏损摊回 - 期初亏损摊回)', '亏损摊回'),
    ('输出_赔付与费用_已发生未决赔款负债提转差_预期现金流', 'out_claims_expense_lic_movement_expected_cf', '计算', '-(期末预期现金流 - 期初预期现金流现值 + 支付赔付)', '计算 = -(期末预期现金流 - 期初预期现金流现值 + 支付赔付)', 'LIC 提转差'),
    ('输出_赔付与费用_已发生未决赔款负债提转差_非金融风险调整', 'out_claims_expense_lic_movement_risk_adj', '计算', '-(期末NRA - 期初NRA)', '计算 = -(期末NRA - 期初NRA)', 'LIC 风险调整提转差'),
    ('输出_赔付与费用_间接理赔费用提转差_预期现金流', 'out_claims_expense_lae_movement_expected_cf', '计算', '-(期末间接 - 期初间接 + 支付理赔费用)', '计算 = -(期末间接 - 期初间接 + 支付理赔费用)', 'LAE 提转差'),
    ('输出_赔付与费用_间接理赔费用提转差_非金融风险调整', 'out_claims_expense_lae_movement_risk_adj', '计算', '-(期末间接NRA - 期初间接NRA)', '计算 = -(期末间接NRA - 期初间接NRA)', 'LAE 风险调整提转差'),
    ('输出_赔付与费用_再保人不履约风险提转差_预期现金流', 'out_claims_expense_rnpr_movement_expected_cf', '计算', '-期末再保', '计算 = -期末再保', '不履约提转差'),
    ('输出_赔付与费用_再保人不履约风险提转差_非金融风险调整', 'out_claims_expense_rnpr_movement_risk_adj', '计算', '-期末再保NRA', '计算 = -期末再保NRA', '不履约风险调整提转差'),
    ('输出_IFIE_未到期_未到期计息', 'out_ifie_lrc_accretion', '计算', '=-未到期责任负债计息', '计算 = -未到期责任负债计息', 'IFIE 未到期计息'),
    ('输出_IFIE_已发生未决_已发生未决赔款负债计息_预期现金流', 'out_ifie_lic_accretion_expected_cf', '计算', '=-期初预期现金流现值 × 当期计息利率', '计算 = -期初预期现金流现值 × 当月计息利率', 'IFIE LIC 计息'),
    ('输出_IFIE_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整', 'out_ifie_lic_accretion_rate_change_risk_adj', '计算', '=-期初NRA现值 × 当期计息利率', '计算 = -期初NRA现值 × 当月计息利率', 'IFIE LIC 风险调整利率变化'),
    ('输出_IFIE_已发生未决_间接理赔费用计息与利率变化_预期现金流', 'out_ifie_lae_accretion_rate_change_expected_cf', '计算', '=-期初间接现值 × 当期计息利率', '计算 = -期初间接现值 × 当月计息利率', 'IFIE LAE 利率变化'),
    ('输出_IFIE_已发生未决_间接理赔费用计息与利率变化_非金融风险调整', 'out_ifie_lae_accretion_rate_change_risk_adj', '计算', '=-期初间接NRA现值 × 当期计息利率', '计算 = -期初间接NRA现值 × 当月计息利率', 'IFIE LAE 风险调整利率变化'),
    ('输出_现金流_支付的赔付与理赔费用', 'out_cf_claims_and_lae_paid', '计算', '支付赔付 + 支付理赔费用', '计算 = 支付赔付 + 支付理赔费用', '实际赔付流出'),
    ('输出_现金流_支付的维持费用', 'out_cf_maintenance_paid', '计算', '= 支付维持费用', '计算 = 支付维持费用', '实际维持流出'),
    ('输出_现金流_收到的保费', 'out_cf_premium_received', '计算', '= 当期收到保费', '计算 = 当期收到保费', '实际保费流入'),
    ('输出_现金流_支付的IACF', 'out_cf_iacf_paid', '计算', '= 当期支出IACF', '计算 = 当期支出IACF', '实际 IACF 流出'),
    ('输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流', 'out_oci_lic_accretion_rate_change_expected_cf', '计算', '=-(期末预期现金流 - 期初预期现金流现值 + 提转差预期现金流 + IFIE预期现金流)', '计算 = -(期末预期现金流 - 期初预期现金流现值 + 提转差预期现金流 + IFIE预期现金流)', 'OCI LIC 利率变化'),
    ('输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整', 'out_oci_lic_accretion_rate_change_risk_adj', '计算', '=-(期末NRA - 期初NRA + 提转差NRA + IFIE_NRA)', '计算 = -(期末NRA - 期初NRA + 提转差NRA + IFIE_NRA)', 'OCI LIC 风险调整'),
    ('输出_OCI_已发生未决_间接理赔费用计息与利率变化_预期现金流', 'out_oci_lae_accretion_rate_change_expected_cf', '计算', '-(期末间接 - 期初间接 + 提转差间接 + IFIE间接)', '计算 = -(期末间接 - 期初间接 + 提转差间接 + IFIE间接)', 'OCI LAE 利率变化'),
    ('输出_OCI_已发生未决_间接理赔费用计息与利率变化_非金融风险调整', 'out_oci_lae_accretion_rate_change_risk_adj', '计算', '-(期末间接NRA - 期初间接NRA + 提转差间接NRA + IFIE间接NRA)', '计算 = -(期末间接NRA - 期初间接NRA + 提转差间接NRA + IFIE间接NRA)', 'OCI LAE 风险调整') ]))

A('<p><b>表 3 · PAA计算_汇总</b>（<span class="code">paa_summary</span>，新、现有业务同「预测组ID & 预测间隔」合并；共 51 列）</p>')
A(derive_table(['字段(中文)', '英文', '加工逻辑', '来源表/字段（中文）', '计算逻辑', '说明'],
  [ ('合同组ID名称', 'contract_group_id_name', '直接取值', '新业务整理.预测组ID', '直接取表1（新业务整理）.预测组ID原值', '组合键'),
    ('预测间隔', 'forecast_interval', '直接取值', 'period', '直接取现金流三角 period 序号', '组合键'),
    ('排列组合项', 'arrangement_combination', '计算', '"{预测组ID}&{预测间隔}"', '计算 = 拼接字符串"{预测组ID}&{预测间隔}"', '组合键'),
    ('合同组名称', 'contract_group_name', '直接取值', '新/现有业务整理.预测组', '直接取表1/表2.预测组原值', '维度'),
    ('评估期开始业务预期写入时间（月）', 'expected_writing_period_months', '直接取值', '新/现有业务整理', '直接取表1/表2.评估期开始业务预期写入时间（月）原值', '维度'),
    ('预测间隔_排列', 'forecast_interval_arrangement', '直接取值', 'period', '直接取 period 序号', '维度'),
    ('合同组ID', 'contract_group_id', '直接取值', '预测组ID', '直接取表1/表2.预测组ID原值', '维度'),
    ('子合同组合名称', 'sub_contract_portfolio_name', '直接取值', '精算险类', '直接取表1/表2.精算险类原值', '维度'),
    ('合同组合名称', 'contract_portfolio_name', '直接取值', '预测组', '直接取表1/表2.预测组原值（合同组合名称）', '维度'),
    ('业务类型', 'business_type', '直接取值', '直保或分入/分出', '直接取表1/表2.业务类型原值', '维度'),
    ('精算险类', 'actuarial_lob', '直接取值', '精算险类', '直接取表1/表2.精算险类原值', '维度'),
    ('评估日', 'valuation_date', '直接取值', '基本信息.评估日', '直接取基本信息.评估日原值', '维度'),
    ('预测时点', 'forecast_point', '直接取值', '新业务整理.预测时点', '直接取表1.预测时点原值（现有业务按同预测间隔推导）', '维度'),
    ('38 个输出_* 计量列', 'out_*（同表1/表2）', '加和', '新业务整理[out_*] + 现有业务整理[out_*]（同预测组ID & 预测间隔）', '计算 = 按 预测组ID&预测间隔 对齐，新业务整理[out_*] + 现有业务整理[out_*] 逐项相加（仅现有业务组则取现有业务原值）', '两业务合并；仅现有业务组则取现有业务原值') ]))

A('<p><b>表 4 · PAA计算_MTD</b>（<span class="code">paa_mtd</span>，将汇总表输出_* 按财务科目归集；直保/分出映射列不同，并并入费用输入项/其他输入项手工科目）</p>')
A(derive_table(['字段(中文)', '英文', '加工逻辑', '来源表/字段（中文）', '计算逻辑', '说明'],
  [ ('保险服务收入', 'insurance_service_revenue', '归集映射', '直保：输出_保险合同收入 + 输出_新增保费减值；分出：无', '计算 = 直保取 汇总表(表3).输出_保险合同收入 + 输出_新增保费减值；分出组该科目为0（收入计入分出保费的分摊）', '收入侧（MTD 内为正）'),
    ('保险服务费用', 'insurance_service_expense', '归集映射', '直保：9 列（输出_赔付与费用_分解投资成分 / 摊销IACF / 亏损合同 / 4 个提转差 / 支付赔付与理赔费用 / 支付维持）；分出：无', '计算 = 直保取 表3 中9列取负之和（输出_赔付与费用_分解投资成分 / 摊销IACF / 亏损合同 / 4个提转差 / 支付赔付与理赔费用 / 支付维持）', '费用侧（MTD 内为负）'),
    ('减：摊回保险服务费用', 'less_recoverable_service_expense', '归集映射', '分出：11 列（复效保费 / 调整手续费 / 亏损摊回 / 支付赔付与理赔费用 / 分解投资成分 / 2 个不履约提转差 / 4 个提转差）；另 + 摊回分保费用(手工)', '计算 = 分出取 表3 中11列之和（复效保费 / 调整手续费 / 亏损摊回 / 支付赔付与理赔费用 / 分解投资成分 / 2个不履约提转差 / 4个提转差）+ 费用输入项.摊回分保费用(手工)', '再保摊回'),
    ('分出保费的分摊', 'ceded_premium_allocation', '归集映射', '分出：输出_保险合同收入', '计算 = 分出取 表3.输出_保险合同收入', '分出收入'),
    ('承保财务损失（IFIE）', 'underwriting_financial_loss', '归集映射', '直保/分出：5 列（输出_IFIE_未到期计息 + 4 个已发生计息）', '计算 = 取 表3 中5列之和（输出_IFIE_未到期计息 + 4个已发生计息）', '计息损失'),
    ('减：分出再保险财务收益', 'less_ceded_reinsurance_finance_income', '归集映射', '分出：5 列（同 IFIE 映射）', '计算 = 分出取 表3 中 IFIE 映射5列之和', '再保财务收益'),
    ('OCI（其他综合收益）', 'OCI', '归集映射', '直保/分出：4 列（输出_OCI_已发生未决 4 项）', '计算 = 取 表3 中4列之和（输出_OCI_已发生未决 4 项）', '利率变化'),
    ('业务及管理费', 'admin_expense', '归集映射+手工', '费用输入项.业务及管理费（当月发生数）', '计算 = 费用输入项.业务及管理费（当月发生数）取负填入', '手工科目（MTD 内为负）'),
    ('税金及附加', 'tax_and_surcharge', '归集映射+手工', '费用输入项.税金及附加（当月发生数）', '计算 = 费用输入项.税金及附加（当月发生数）取负填入', '手工科目'),
    ('手续费及佣金支出', 'commission_expense', '归集映射+手工', '费用输入项.手续费及佣金支出', '计算 = 费用输入项.手续费及佣金支出取负填入', '手工科目'),
    ('复效保费', 'insurance_service_revenue(加)', '归集映射+手工', '费用输入项.复效保费（增加利润记正）', '计算 = 费用输入项.复效保费（增加利润记正）取正填入', '手工科目'),
    ('调整手续费', 'other_business_income/other_business_cost', '归集映射+手工', '费用输入项.调整手续费（正→其他业务收入；负→其他业务成本）', '计算 = 费用输入项.调整手续费（正→其他业务收入；负→其他业务成本）', '手工科目'),
    ('投资收益', '投资收益', '归集映射+手工', '其他输入项.投资收益', '计算 = 其他输入项.投资收益原值', '手工科目'),
    ('利息收入', 'interest_income', '归集映射+手工', '其他输入项.利息收入', '计算 = 其他输入项.利息收入原值', '手工科目'),
    ('其他收益/公允价值变动收益/汇兑收益/其他业务收入/资产处置收益', 'other_income/fair_value_income/fx_income/other_business_income/asset_disposal_income', '归集映射+手工', '其他输入项对应科目', '计算 = 其他输入项对应科目原值（收入类取正）', '手工科目'),
    ('提取保费准备金', 'premium_reserve_extraction', '归集映射+手工', '其他输入项.提取保费准备金（取负）', '计算 = 其他输入项.提取保费准备金取负填入', '手工科目'),
    ('利息支出', 'interest_expense', '归集映射+手工', '其他输入项.利息支持（取负）', '计算 = 其他输入项.利息支持取负填入', '手工科目'),
    ('信用减值损失/其他资产减值损失/其他业务成本/营业外收入/营业外支出', 'credit_impairment_loss/other_asset_impairment_loss/other_business_cost/non_operating_income/non_operating_expense', '归集映射+手工', '其他输入项对应科目（损失/支出取负）', '计算 = 其他输入项对应科目原值（损失/支出类取负填入）', '手工科目') ]))

A('<p><b>表 5 · 财务报表_MTD</b>（<span class="code">financial_statement_mtd</span>，由 PAA_MTD 各科目取正/取负 + Period 0 取「财务报表实际数」；含利润表 26 行 + 资产负债表 8 行）</p>')
A(derive_table(['字段(中文)', '英文', '加工逻辑', '来源表/字段（中文）', '计算逻辑', '说明'],
  [ ('一、营业总收入', 'total_operating_revenue', '计算', '各收入项加总（见下）；Period 0 取实际数', '计算 = Period 0 取「财务报表实际数」营业总收入；其余 = 各收入项加总（保险服务收入+利息收入+投资收益+其他收益类等）', '利润表合计'),
    ('保险服务收入', 'insurance_service_revenue', '计算', 'MTD.保险服务收入（取正）', '计算 = MTD.保险服务收入（取正）', '利润表项'),
    ('利息收入', 'interest_income', '计算', 'MTD.利息收入', '计算 = MTD.利息收入', '利润表项'),
    ('投资收益（损失以"-"号填列）', 'investment_income', '计算', 'MTD.投资收益', '计算 = MTD.投资收益', '利润表项'),
    ('其他收益/公允价值变动收益/汇兑收益/其他业务收入/资产处置收益', 'other_income/fair_value_income/fx_income/other_business_income/asset_disposal_income', '计算', 'MTD 对应科目', '计算 = MTD 对应科目原值', '利润表项'),
    ('二、营业总支出', 'total_operating_expense', '计算', '各费用项加总 - 摊回 - 再保财务收益；Period 0 取实际数', '计算 = Period 0 取实际数；其余 = 各费用项加总（保险服务费用+分出保费分摊+承保财务损失+提取保费准备金+利息支出等） - 摊回保险服务费用 - 分出再保险财务收益', '利润表合计'),
    ('保险服务费用', 'insurance_service_expense', '计算', '-MTD.保险服务费用（取正填列）', '计算 = -MTD.保险服务费用（取正填列）', '利润表项'),
    ('分出保费的分摊', 'ceded_premium_allocation', '计算', '-MTD.分出保费的分摊', '计算 = -MTD.分出保费的分摊', '利润表项'),
    ('减：摊回保险服务费用', 'less_recoverable_service_expense', '计算', 'MTD.减：摊回保险服务费用（取正）', '计算 = MTD.减：摊回保险服务费用（取正）', '利润表项'),
    ('承保财务损失', 'underwriting_financial_loss', '计算', '-MTD.承保财务损失（取正）', '计算 = -MTD.承保财务损失（取正）', '利润表项'),
    ('减：分出再保险财务收益', 'less_ceded_reinsurance_finance_income', '计算', 'MTD.减：分出再保险财务收益（取正）', '计算 = MTD.减：分出再保险财务收益（取正）', '利润表项'),
    ('提取保费准备金', 'premium_reserve_extraction', '计算', '-MTD.提取保费准备金', '计算 = -MTD.提取保费准备金', '利润表项'),
    ('利息支出/税金及附加/手续费及佣金支出/业务及管理费/信用减值损失/其他资产减值损失/其他业务成本', 'interest_expense/tax_and_surcharge/commission_expense/admin_expense/credit_impairment_loss/other_asset_impairment_loss/other_business_cost', '计算', '-MTD 对应科目', '计算 = -MTD 对应科目', '利润表项'),
    ('三、营业利润（亏损以"-"号填列）', 'operating_profit', '计算', '营业总收入 - 营业总支出；Period 0 取实际数', '计算 = 营业总收入 - 营业总支出；Period 0 取实际数', '利润表合计'),
    ('加：营业外收入', 'plus_non_operating_income', '计算', 'MTD.营业外收入', '计算 = MTD.营业外收入', '利润表项'),
    ('减：营业外支出', 'less_non_operating_expense', '计算', '-MTD.营业外支出', '计算 = -MTD.营业外支出', '利润表项'),
    ('四、利润总额（亏损总额以"-"号填列）', 'total_profit', '计算', '营业利润 + 营业外收入 - 营业外支出；Period 0 取实际数', '计算 = 营业利润 + 营业外收入 - 营业外支出；Period 0 取实际数', '利润表合计'),
    ('减：所得税费用', 'less_income_tax', '计算', '利润总额 × 25%；Period 0 取实际数', '计算 = 利润总额 × 25%；Period 0 取实际数', '利润表项'),
    ('五、净利润（净亏损以"-"号填列）', 'net_profit', '计算', '利润总额 - 所得税费用', '计算 = 利润总额 - 所得税费用', '利润表合计'),
    ('六、其他综合收益的税后净额', 'oci_net_of_tax', '计算', 'MTD.OCI', '计算 = MTD.OCI', '利润表项'),
    ('七、综合收益总额', 'total_comprehensive_income', '计算', '净利润 + 其他综合收益', '计算 = 净利润 + 其他综合收益', '利润表合计'),
    ('承保利润', 'underwriting_profit', '计算', '保险服务收入 - 保险服务费用 - 分出保费的分摊 + 摊回保险服务费用 - 承保财务损失 + 分出再保险财务收益 - 提取保费准备金', '计算 = 保险服务收入 - 保险服务费用 - 分出保费的分摊 + 摊回保险服务费用 - 承保财务损失 + 分出再保险财务收益 - 提取保费准备金', '核心指标'),
    ('资产 / 负债 / 所有者权益（表头）', 'assets/liabilities/equity', '直接取值', 'CAS25 资产负债表表头', '直接取 CAS25 资产负债表表头原值', '资产负债表表头'),
    ('分出再保险合同资产', 'reinsurance_contract_asset', '计算', '-Σ(分出业务 保险合同负债列)（取负）', '计算 = -Σ(分出业务 保险合同负债列)（取负）', '资产负债表项'),
    ('其他资产', 'other_assets', '常量', '0（当前未建模）', '常量 0（当前版本未建模）', '资产负债表项'),
    ('保险合同负债', 'insurance_contract_liability', '加和', 'Σ(直保或分入 6 列：LRC非亏损/LRC亏损/已发生预期现金流/间接理赔预期现金流/已发生风险调整/间接理赔风险调整)（按预测间隔归集）', '计算 = Σ(直保或分入 6 列：LRC非亏损/LRC亏损/已发生预期现金流/间接理赔预期现金流/已发生风险调整/间接理赔风险调整)（按预测间隔归集）', '资产负债表项'),
    ('其他负债', 'other_liabilities', '常量', '0（当前未建模）', '常量 0（当前版本未建模）', '资产负债表项'),
    ('资产总计', 'total_assets', '计算', '分出再保险合同资产', '计算 = 分出再保险合同资产', '资产负债表合计'),
    ('负债合计', 'total_liabilities', '计算', '保险合同负债', '计算 = 保险合同负债', '资产负债表合计'),
    ('负债及所有者权益总计', 'total_liabilities_and_equity', '计算', '保险合同负债 + 分出再保险合同资产', '计算 = 保险合同负债 + 分出再保险合同资产', '资产负债表合计') ]))

A('<p><b>表 6 · 财务报表_YTD</b>（<span class="code">financial_statement_ytd</span>，年初至今累计；YTD = 实际数(Period 0) + MTD 累计，1 月重置）</p>')
A(derive_table(['字段(中文)', '英文', '加工逻辑', '来源表/字段（中文）', '计算逻辑', '说明'],
  [ ('各利润表科目（26 行）', '同表5 利润表科目', '计算', 'YTD = IF(月=1, 0, 上期YTD) + 当期MTD；所得税 = 上期所得税 + (当期利润总额 - 上期利润总额) × 25%', '计算 = 各利润表科目 YTD = IF(月=1, 0, 上期YTD) + 当期MTD；所得税 = 上期所得税 + (当期利润总额 - 上期利润总额) × 25%（年初重置）', '累计'),
    ('净利润', 'net_profit', '计算', '利润总额 - 所得税费用（累计重算）', '计算 = 累计利润总额 - 累计所得税费用', '累计合计'),
    ('综合收益总额', 'total_comprehensive_income', '计算', '净利润 + 其他综合收益（累计重算）', '计算 = 累计净利润 + 累计其他综合收益', '累计合计'),
    ('各资产负债表科目（8 行）', '同表5 资产负债表科目', '直接取值', '资产负债表为存量，直接取当期 MTD 值（无累计）', '直接取当期 MTD 资产负债表值（存量科目无需累计，Period 0 取财务报表实际数）', '存量') ]))

A('<div class="note">加工口径说明：① 所有数值经 <span class="code">translate_out_deep</span> 在返回边界回写为中文列名，'
  '六表零差异不受影响；② 压力情景（情景1~4）通过对 保费收入/获取费用/预期赔付率/费用率/利率按年施加压力参数缩放；'
  '③ MTD 利润表 Period 0（评估时点）直接取「财务报表实际数」系统对接数据，其余期间由 PAA_MTD 推导。</div>')
A('<div class="note">压力情景参数（中文化，<span class="code">SCENARIO_PARAM_CN</span>）：原保险保费增长、预期赔付率上升、预期费用率上升、即期利率变动。</div>')

# 4.3 结果展示
A('<h3>4.3 结果展示面板</h3>')
res = [
    ("结果总览（dashboard）", "首页指标卡与关键结论汇总。"),
    ("输出财务报表（financial-statements）", "PAA 法下利润表等财务报表，含 MTD / YTD 口径。"),
    ("分险种利润表（sub-class-profit）", "按险类拆分利润表，支持指标 / 利润双 Tab。"),
    ("多情景比对（scenario-compare）", "基础情景 vs 压力情景 1~4 的横向比对。"),
    ("新旧预测比对（old-new-bridge）", "新旧准则预测结果桥接对照（新旧准则桥接）。"),
    ("预实分析（actual-vs-expected）", "预测 vs 实际对比，概览（公司合计）+ 分险种，4 率单位统一为百分比。"),
]
A('<table><thead><tr><th>模块</th><th>说明</th></tr></thead><tbody>')
for r in res:
    A(f"<tr><td><b>{r[0]}</b></td><td>{r[1]}</td></tr>")
A('</tbody></table>')

# 4.4 计量输出
A('<h3>4.4 计量结果输出（paa-summary）</h3>')
A('<p>六张核心结果表（物理表名 / 中文名）统一经 <span class="code">financialStatementsV2Merged</span> 作为三面板唯一数据源：</p>')
A('<table><thead><tr><th>物理表名</th><th>中文名</th><th>说明</th></tr></thead><tbody>')
out = [
    ("paa_new_business_organized", "PAA计算_新业务整理", "新业务分月 PAA 计量整理"),
    ("paa_existing_business_organized", "PAA计算_现有业务整理", "现有业务分月 PAA 计量整理（含险类拆分）"),
    ("paa_summary", "PAA计算_汇总", "新/现有业务汇总"),
    ("paa_mtd", "PAA计算_MTD", "月初至今口径（引擎不产出对应粒度，验证恒取 fixture）"),
    ("financial_statement_mtd", "财务报表_MTD", "财务报表月初至今"),
    ("financial_statement_ytd", "财务报表_YTD", "财务报表年初至今"),
]
for r in out:
    A(f"<tr><td><span class='code'>{r[0]}</span></td><td>{r[1]}</td><td>{r[2]}</td></tr>")
A('</tbody></table>')
A('<p>支持结果导出 Excel（<span class="code">api_output_export / api_export_table_xlsx</span>）。</p>')

# 4.5 验证
A('<h3>4.5 验证差异比对</h3>')
A('<div class="card"><div class="t">4.5.1 验证文件上传（verify-upload）</div>权威 VBA 验证工作簿上传，按情景分文件存储黄金基准（<span class="code">api_upload_verify</span>）。</div>')
A('<div class="card"><div class="t">4.5.2 验证核对结果（verify-check）</div>系统输出 vs 验证文件逐表核对，预测时点筛选联动数据预览（<span class="code">api_verify_data</span>）。</div>')
A('<div class="card"><div class="t">4.5.3 差异比对结果（verify-results）</div>六表零差异比对，支持完整比对明细下钻、导出（<span class="code">api_verify_compare / api_verify_merged / api_verify_export_all</span>）。</div>')
A('<div class="note">关键规则：① 基础情景（情景0）已计算时走<b>引擎实时输出</b>，改假设重算即真实反映；未计算时回退 fixture 黄金基准。'
  '② 压力情景（1~4）恒回显各自情景 fixture。③ 预测时点筛选若选中时点在验证文件无覆盖，强制判定 <span class="code">data_gap</span>（校验不通过），避免误判「完全一致」。</div>')

# 4.6 数据逻辑归集
A('<h3>4.6 数据及逻辑归集（data-logic-collection）</h3>')
A('<p>集中归集展示数据来源与加工逻辑（<span class="code">api_logic_outline</span>），便于审计与交接，对应「合理性分析工具」的数据/逻辑透明化诉求。</p>')

# 4.7 系统管理
A('<h3>4.7 系统管理</h3>')
A('<table><thead><tr><th>模块</th><th>能力</th><th>API</th></tr></thead><tbody>')
adm = [
    ("部署管理（deploy-manage）", "配置 / 测试 / 一键推送至生产（阿里云），含部署状态", "api_deploy_config / api_deploy_test / api_deploy_push"),
    ("系统运行日志（system-log）", "全链路埋点（登录/上传/计算/导出/部署/SQL），分页过滤 + 自动刷新", "api_system_log"),
    ("SQL 查询（sql-query）", "管理员只读查询，白名单 SELECT/WITH/SHOW/EXPLAIN/DESCRIBE，禁止写/DDL/多语句", "api_system_sql_query"),
    ("数据表字典（table-dict）", "35 输入表 + 6 输出表真实字段结构、查询模板", "api_system_table_dict"),
]
for r in adm:
    A(f"<tr><td><b>{r[0]}</b></td><td>{r[1]}</td><td><span class='code'>{r[2]}</span></td></tr>")
A('</tbody></table>')
A('</section>')

# 5 数据架构
A('<section id="5"><h2>5. 数据架构</h2>')
A('<h3>5.1 总体数据模型</h3>')
A('<p>系统数据分三层：<b>输入层</b>（35 张物理表，中文化采集）、<b>计算层</b>（PAA 引擎内存计算 + 计算版本快照）、'
  '<b>输出层</b>（6 张结果物理表 + 财务报表）。全链路字段经中心化注册表 <span class="code">paa_engine/field_names.py</span>'
  '（CN_TO_EN / EN_TO_CN）做中英文转换，对外展示保持中文，六表零差异不受影响。</p>')
A('<h3>5.2 输入数据（35 张物理表）</h3>')
A('<ul>'
  '<li><b>规模</b>：25 张手工 Excel + 10 张系统对接，共 <b>1,743</b> 个真实字段；</li>'
  '<li><b>列类型</b>：文本维度列（CharField）、数值列（DecimalField，含月度 m01~m60、险类直保/分出拆分、余额/比率）；</li>'
  '<li><b>险类拆分</b>：21 个业务线（交强险、商业三者险、企业财产险…）× 直保或分入 / 分出，映射为 <span class="code">{lob}_direct / {lob}_ceded</span>；</li>'
  '<li><b>示例</b>：<span class="code">system_opening_balance</span>（系统期初余额表，含险类拆分）、<span class="code">initial_recognition_rate_curve</span>（初始确认利率曲线，41 个险类利率列）。</li></ul>')
A('<h3>5.3 输出数据（6 张物理表）</h3>')
A('<p>见 4.4 节六张结果表。对外 Excel / 前端 / 验证比对均使用中文列名，由注册表在返回边界 <span class="code">translate_out_deep</span> 回写。</p>')
A('<h3>5.4 计算版本存储</h3>')
A('<p>计算版本 <span class="code">CalculationVersion</span> 与快照 <span class="code">CalculationSnapshot</span> 持久化到 MySQL，'
  '支撑版本回溯、跨页进度保留与已入库版本列表管理。</p>')
A('<h3>5.5 全量字段中英文映射</h3>')
A('<p>本节给出系统<b>全部表</b>的中英文字段映射：35 张输入物理表、3 张中间计算表（A/B/C）、'
  '6 张输出结果表。中英文双向转换由中心化注册表 <span class="code">field_names.py</span> 统一维护，'
  '本表由该注册表 + 输入表静态 schema（<span class="code">input_table_schema.py</span>）+ 引擎列常量（<span class="code">engine.py</span>）'
  '自动抽取生成，保证与代码基线一致，避免文档与实现漂移。</p>')
A('<h4>5.5.1 输入表全量字段映射（35 张物理表）</h4>')
A(_map_input_tables())
A('<h4>5.5.2 中间计算表与输出结果表字段映射</h4>')
A(_map_output_and_intermediate())
A('</section>')

# 6 技术架构
A('<section id="6"><h2>6. 技术架构</h2>')
A('<div class="grid">')
A('<div class="card"><div class="t">前端</div>HTML / CSS / JavaScript / Chart.js 单页应用（SPA），AntD5 蓝 #1677FF 配色。</div>')
A('<div class="card"><div class="t">后端</div>Django（Python），MySQL 8.0（pymysql 驱动），openpyxl 处理 Excel。</div>')
A('<div class="card"><div class="t">计量引擎</div>paa_engine：PAA 保费分配法 Python 引擎，分月计量新/现有业务。</div>')
A('<div class="card"><div class="t">部署</div>Docker / 宝塔 Nginx + Gunicorn（<b>workers=1</b>，计算进度存进程内全局变量）；本地开发 + 阿里云生产。</div>')
A('<div class="card"><div class="t">版本控制</div>GitHub 中央库 + 本地 / 阿里云双位置同步（main / develop / feature / hotfix）。</div>')
A('<div class="card"><div class="t">版本号管理</div>SYSTEM_VERSION 在 settings.py 与 config.js 双处同步，经 <span class="code">?v=</span> 缓存刷新。</div>')
A('</div>')
A('<div class="note">生产部署硬约束：Gunicorn <b>workers 必须为 1</b>。多 worker 会导致计算进度 / 结果（进程内全局变量）互相不可见，表现为进度 0% 假象。</div>')
A('</section>')

# 7 非功能
A('<section id="7"><h2>7. 非功能性需求</h2>')
A('<table><thead><tr><th>类别</th><th>需求</th></tr></thead><tbody>')
nfr = [
    ("性能", "计算异步化 + 进度轮询；结果缓存落盘（calc_results_map.json 等）；上传解析与落库分离。"),
    ("安全", "角色权限控制；SQL 查询白名单 + 危险语句拦截并记日志；SECRET_KEY 测试/生产独立；敏感信息（.env / 密码 / db.sqlite3 / runtime_cache / 上传财务数据）已纳入 .gitignore。"),
    ("兼容性", "跨平台行尾（.gitattributes）保障本地 Windows / 阿里云 Linux 一致；主流浏览器；静态资源 cache buster。"),
    ("可维护性", "版本号双处同步机制；全链路运行日志；数据表字典自描述真实字段；字段中英文注册表集中管理。"),
    ("数据质量", "上传结构校验；六表零差异验证 + 缺失时点检测（data_gap）；预测时点筛选一致性。"),
    ("可部署性", "Docker 容器化 + 宝塔/通用 Nginx + systemd 双路线；部署脚本 auto_deploy.sh / update_deploy.sh。"),
]
for r in nfr:
    A(f"<tr><td><b>{r[0]}</b></td><td>{r[1]}</td></tr>")
A('</tbody></table></section>')

# 8 验收
A('<section id="8"><h2>8. 验收标准</h2>')
A('<table><thead><tr><th>模块</th><th>验收要点</th></tr></thead><tbody>')
acc = [
    ("数据输入", "35 张表可上传并落为独立物理表；字段名与数据字典一致；双写后旧 active 行正确置否。"),
    ("计算引擎", "基础 + 4 压力情景可触发异步计算；进度实时可见；计算版本可入库并回溯。"),
    ("结果展示", "财务报表 MTD/YTD、分险种利润表、多情景比对、预实分析、新旧桥接数据正确渲染。"),
    ("计量输出", "6 张结果表数值与引擎一致；Excel 导出成功。"),
    ("验证比对", "六表零差异达成；改基础假设重算后验证实时反映；缺失时点正确判定 data_gap。"),
    ("系统管理", "SQL 查询仅放行白名单；危险语句被拦截；日志完整；字典展示真实字段。"),
    ("安全权限", "viewer 无上传/计算/导出权限；uploader 无管理权限。"),
]
for r in acc:
    A(f"<tr><td><b>{r[0]}</b></td><td>{r[1]}</td></tr>")
A('</tbody></table></section>')

# 9 版本部署
A('<section id="9"><h2>9. 版本管理与部署</h2>')
A('<h3>9.1 分支模型</h3>')
A('<ul>'
  '<li><span class="badge b-core">main</span>生产稳定分支，仅接受来自 develop / hotfix 的合并；</li>'
  '<li><span class="badge b-core">develop</span>集成分支，功能合并于此；</li>'
  '<li><span class="badge b-req">feature/*</span>需求 / 功能开发分支，完成后合回 develop；</li>'
  '<li><span class="badge b-opt">hotfix/*</span>生产紧急修复分支，完成后合回 main 与 develop。</li></ul>')
A('<h3>9.2 双位置同步（本地 ↔ 阿里云）</h3>')
A('<p>GitHub 作为中央版本库枢纽：本地开发机与阿里云生产机均 <span class="code">clone</span> 同一仓库，'
  '本地提交经 <span class="code">push</span> 入中央库，阿里云侧 <span class="code">pull</span> 后执行 migrate / collectstatic / 重启 Gunicorn 完成发布。'
  '提交遵循 Conventional Commits（feat / fix / chore / docs …）。详见已生成的《代码迭代管理方案》。</p>')
A('<h3>9.3 测试环境部署</h3>')
A('<p>已生成《测试环境信息需求表》（doc_build/），向公司 IT 获取数据库 / 域名 / SECRET_KEY / 部署形态等信息后，'
  '按 Docker 或通用 Nginx + systemd 路线生成可执行部署包（含真实 .env、workers=1 约束）。</p>')
A('</section>')

# 附录
A('<section id="附录"><h2>附录</h2>')
A('<h3 id="附录A">附录 A. 前端导航清单（pageTitles）</h3>')
A('<p>数据输入（Excel 上传 / 系统对接 / 预实上传 + 35 张表页）、计算（计算流程 / 输入整理 / 新业务计量 / 现有业务计量）、'
  '结果展示（结果总览 / 输出财务报表 / 分险种利润表 / 多情景比对 / 新旧预测比对 / 预实分析）、'
  '计量结果输出（六张结果表）、验证（验证文件上传 / 验证核对结果 / 差异比对结果）、'
  '数据及逻辑归集、系统管理（部署管理 / 系统运行日志 / SQL 查询 / 数据表字典）。</p>')
A('<h3 id="附录B">附录 B. 后端 API 清单（views.py，节选）</h3>')
apis = [
    "登录鉴权：login_view / logout_view / index / api_version",
    "数据输入：api_upload / api_upload_history / api_download_sheet / api_download_all / api_upload_verify / api_upload_actual / api_upload_old_standard",
    "验证比对：api_verify_full / api_verify_compare / api_verify_merged / api_verify_data / api_verify_export_sheet / api_verify_export_all",
    "结果导出：api_output_export / api_export_table_xlsx",
    "计算引擎：api_calc_scenarios / api_calc_run / api_calc_progress / api_calc_results / api_calc_results_all / api_calc_input_org / api_calc_verify_output",
    "预实 / 桥接：api_actual_compare / api_bridge_comparison",
    "部署：api_deploy_config / api_deploy_test / api_deploy_push",
    "逻辑 / 日志 / 版本：api_logic_outline / api_system_log / api_calc_versions / api_calc_push_version / api_calc_push_version_status",
    "系统：api_system_sql_query / api_system_table_dict / api_dashboard_snapshot",
]
for a in apis:
    A(f"<p><span class='code'>{a}</span></p>")
A('<h3 id="附录C">附录 C. 术语表</h3>')
A('<table><thead><tr><th>术语</th><th>含义</th></tr></thead><tbody>')
terms = [
    ("IFRS17", "国际财务报告准则第 17 号（保险合同），2023-01-01 生效。"),
    ("PAA", "Premium Allocation Approach 保费分配法，财险适用的简化计量模型。"),
    ("BBA", "Building Block Approach 模块法，通用计量模型。"),
    ("六表零差异", "系统计量输出与权威 VBA 验证工作簿在六张结果表上完全一致。"),
    ("压力情景", "基础情景外的 4 套加压假设（保费增长 / 赔付率上升 / 费用率上升 / 利率变动）。"),
    ("MTD / YTD", "Month-to-Date 月初至今 / Year-to-Date 年初至今口径。"),
    ("计算版本", "将某次完整计算结果快照持久化，支持回溯与对比。"),
]
for t in terms:
    A(f"<tr><td><b>{t[0]}</b></td><td>{t[1]}</td></tr>")
A('</tbody></table>')
A('</section>')

A('<footer>IFRS17 财务预测系统 PRD v1.0 · 基于系统 v5.9.92 代码基线自动编撰 · 内部资料</footer>')
A('</div>')  # wrap

html = f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>\
<meta name='viewport' content='width=device-width,initial-scale=1'>\
<title>IFRS17 财务预测系统 PRD</title><style>{CSS}</style></head>\
<body>{''.join(body)}</body></html>"

with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)
print("生成完成:", HTML_PATH, "大小:", len(html), "字节")
