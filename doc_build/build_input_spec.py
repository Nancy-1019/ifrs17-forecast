# -*- coding: utf-8 -*-
"""
生成 IFRS17 预测模型「输入数据规格」文档。
数据源：data_input/input_table_schema.py（由真实活跃上传数据生成的静态快照）
产出：
  doc_build/输入数据规格.html  （可浏览器预览）
  doc_build/输入数据规格.xlsx  （可交付 / 打印）
字段说明规则：
  - 月度列 m01~m60 -> 第 N 月度量列（月度现金流/金额）
  - 文本列        -> 文本维度列
  - 数值列含 _direct/_ceded -> 险类拆分数值列（直保/分出）
  - 其余数值列    -> 数值列
常见维度字段（updated_date / valuation_point / data_type / forecast_group /
actuarial_lob / scenario / remark 等）给出中文语义说明。
"""
import importlib.util
import os
import re
import html
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
SPEC_PATH = os.path.join(PROJECT, "data_input", "input_table_schema.py")

spec = importlib.util.spec_from_file_location("its", SPEC_PATH)
its = importlib.util.module_from_spec(spec)
spec.loader.exec_module(its)
SCHEMA = its.INPUT_TABLE_SCHEMA

MON = re.compile(r"^m\d+$")

# 常见维度字段的中文语义说明（按英文字段名匹配）
FIELD_DESC = {
    "updated_date": "数据更新日期",
    "valuation_point": "评估时点（预测基准日）",
    "data_type": "数据类型标识",
    "forecast_group": "预测组（现有业务分组维度）",
    "actuarial_lob": "精算险类代码",
    "scenario": "情景标识",
    "remark": "备注说明",
    "source": "数据来源标识",
    "period": "期间",
    "currency": "币种",
    "version": "版本号",
}

SRC_CN = {"excel": "手工输入", "dock": "系统对接"}

VERSION = "v5.9.92"
BUILD_DATE = "2026-08-19"
GEN_TIME = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def field_desc(c):
    name = c["name"]
    cn = c.get("cn", "")
    t = c["type"]
    if MON.match(name):
        n = int(name[1:])
        return "第%d月度量列（月度现金流/金额）" % n
    if name in FIELD_DESC:
        return FIELD_DESC[name]
    if t == "text":
        return "文本维度列"
    # decimal 非月度
    if name.endswith("_direct"):
        return "险类拆分数值列（直保）"
    if name.endswith("_ceded"):
        return "险类拆分数值列（分出）"
    if "_" in name and any(name.startswith(p) for p in (
        "compulsory_auto", "additional", "commercial_tp", "vehicle_damage",
        "enterprise_property", "cargo", "liability", "guarantee", "credit",
        "special_risk", "home_property", "construction", "other_line",
        "marine_hull", "crop", "livestock", "accident", "commercial_health",
        "critical_illness", "other_policy_health", "other")):
        return "险类拆分数值列"
    return "数值列"


def type_tag(t, name):
    if MON.match(name):
        return "月度"
    return "文本" if t == "text" else "数值"


# ---- 统计 ----
total_tables = len(SCHEMA)
total_cols = sum(len(v["columns"]) for v in SCHEMA.values())
src_stat = {}
cat_stat = {}
for cn, v in SCHEMA.items():
    src_stat[v.get("source")] = src_stat.get(v.get("source"), 0) + 1
    cat_stat[v.get("category")] = cat_stat.get(v.get("category"), 0) + 1

# 按分类分组（保持出现顺序）
cats = []
groups = {}
for cn, v in SCHEMA.items():
    cat = v.get("category", "未分类")
    if cat not in groups:
        groups[cat] = []
        cats.append(cat)
    groups[cat].append((cn, v))


# =================== HTML ===================
def build_html():
    cards = []
    cards.append(("<div class='card-stat'><div class='num'>%d</div>"
                  "<div class='lbl'>输入表总数</div></div>") % total_tables)
    for s, n in src_stat.items():
        cards.append(("<div class='card-stat'><div class='num'>%d</div>"
                      "<div class='lbl'>%s</div></div>") % (n, SRC_CN.get(s, s)))
    cards.append(("<div class='card-stat'><div class='num'>%d</div>"
                  "<div class='lbl'>业务分类</div></div>") % len(cat_stat))
    cards.append(("<div class='card-stat'><div class='num'>%d</div>"
                  "<div class='lbl'>字段总数</div></div>") % total_cols)

    # 总览表
    ov_rows = []
    for i, (cn, v) in enumerate(SCHEMA.items(), 1):
        months = sum(1 for c in v["columns"] if MON.match(c["name"]))
        ov_rows.append(
            "<tr><td>%d</td><td>%s</td><td><code>%s</code></td>"
            "<td><span class='badge %s'>%s</span></td>"
            "<td><span class='badge cat'>%s</span></td>"
            "<td>%d</td><td>%d</td></tr>" % (
                i, html.escape(cn), html.escape(v["en"]),
                v.get("source"), SRC_CN.get(v.get("source"), v.get("source")),
                html.escape(v.get("category", "")),
                len(v["columns"]), months))
    ov_table = ("<table class='ov'><thead><tr><th>序号</th><th>中文表名</th>"
                "<th>英文物理表名</th><th>来源</th><th>分类</th>"
                "<th>字段数</th><th>月度列</th></tr></thead><tbody>%s</tbody></table>"
                ) % "".join(ov_rows)

    # 分类展开
    detail = []
    for cat in cats:
        detail.append("<h2 class='cat'>%s <span class='cat-count'>(%d 张表)</span></h2>"
                      % (html.escape(cat), len(groups[cat])))
        for cn, v in groups[cat]:
            months = sum(1 for c in v["columns"] if MON.match(c["name"]))
            rows = []
            for j, c in enumerate(v["columns"], 1):
                tag = type_tag(c["type"], c["name"])
                cls = {"月度": "t-month", "文本": "t-text", "数值": "t-num"}[tag]
                rows.append(
                    "<tr><td>%d</td><td>%s</td><td><code>%s</code></td>"
                    "<td><span class='t %s'>%s</span></td><td>%s</td></tr>" % (
                        j, html.escape(c.get("cn", "")), html.escape(c["name"]),
                        cls, tag, html.escape(field_desc(c))))
            tbl = ("<table class='field'><thead><tr><th>序号</th><th>中文字段名</th>"
                   "<th>英文字段名</th><th>类型</th><th>说明</th></tr></thead>"
                   "<tbody>%s</tbody></table>") % "".join(rows)
            detail.append(
                "<div class='table-card'>"
                "<div class='th'><div><span class='cn'>%s</span>"
                "<span class='badge %s'>%s</span>"
                "<span class='badge cat'>%s</span></div>"
                "<div class='meta'>英文表名 <code>%s</code> · 字段 %d · 月度列 %d</div>"
                "</div>%s</div>" % (
                    html.escape(cn), v.get("source"),
                    SRC_CN.get(v.get("source"), v.get("source")),
                    html.escape(v.get("category", "")),
                    html.escape(v["en"]), len(v["columns"]), months, tbl))

    legend = ("<div class='legend'>"
              "<span class='t t-month'>月度</span> 第 N 月度量列（m01~m60）&nbsp;&nbsp;"
              "<span class='t t-text'>文本</span> 文本维度列&nbsp;&nbsp;"
              "<span class='t t-num'>数值</span> 数值列（含险类拆分/余额/比率等）"
              "</div>")

    doc = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IFRS17 预测模型 · 输入数据规格 (%s)</title>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,"Microsoft YaHei",sans-serif;color:#1f1f1f;margin:0;background:#f5f7fa}
  header{background:#1677ff;color:#fff;padding:26px 40px}
  header h1{margin:0;font-size:23px;font-weight:700}
  header .meta{margin-top:8px;opacity:.92;font-size:13px;line-height:1.7}
  .cards{display:flex;gap:16px;padding:24px 40px;flex-wrap:wrap}
  .card-stat{background:#fff;border-radius:10px;padding:16px 22px;min-width:118px;box-shadow:0 1px 4px rgba(0,0,0,.08);border-left:4px solid #1677ff}
  .card-stat .num{font-size:25px;font-weight:700;color:#1677ff}
  .card-stat .lbl{font-size:13px;color:#666;margin-top:4px}
  .wrap{padding:0 40px 40px}
  h2.cat{margin:34px 0 12px;color:#1677ff;font-size:18px;border-bottom:2px solid #1677ff;padding-bottom:6px}
  .cat-count{color:#999;font-size:13px;font-weight:400}
  .ov{margin-top:18px}
  table{border-collapse:collapse;width:100%%;font-size:13px}
  th,td{border:1px solid #e8e8e8;padding:7px 10px;text-align:left;vertical-align:top}
  th{background:#fafafa;font-weight:600}
  .ov tbody tr:nth-child(even){background:#fafcff}
  code{font-family:"SFMono-Regular",Consolas,monospace;font-size:12px;color:#0958d9;background:#f0f5ff;padding:1px 5px;border-radius:4px}
  .table-card{background:#fff;border-radius:10px;padding:16px 18px;margin:14px 0;box-shadow:0 1px 4px rgba(0,0,0,.06)}
  .table-card .th{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:6px}
  .table-card .th .cn{font-size:16px;font-weight:600;margin-right:6px}
  .table-card .meta{font-size:12px;color:#888}
  .field tbody tr:nth-child(even){background:#fafcff}
  .badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:12px}
  .badge.excel{background:#e6f4ff;color:#1677ff}
  .badge.dock{background:#f6ffed;color:#389e0d}
  .badge.cat{background:#fff7e6;color:#d46b08}
  .t{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:600}
  .t-month{background:#fff1f0;color:#cf1322}
  .t-text{background:#f0f0f0;color:#595959}
  .t-num{background:#e6f4ff;color:#1677ff}
  .legend{margin:10px 0 4px;font-size:13px;color:#555}
  footer{color:#999;font-size:12px;padding:20px 40px;border-top:1px solid #e8e8e8}
</style>
</head>
<body>
<header>
  <h1>IFRS17 预测模型 · 输入数据规格</h1>
  <div class="meta">系统版本：%s　|　规格生成日期：%s　|　数据来源：真实活跃上传数据静态快照（data_input/input_table_schema.py）<br>
  说明：35 张输入数据表已各自落为独立物理表，表名与数据字典英文表名一一对应；以下列出每张表的真实字段结构。</div>
</header>
<div class="cards">%s</div>
<div class="wrap">
  <h2 class="cat">一、输入表总览</h2>
  %s
  <h2 class="cat">二、字段类型说明</h2>
  %s
  <h2 class="cat">三、按分类展开 · 各表字段明细</h2>
  %s
</div>
<footer>本规格文档由输入数据自动生成，生成时间 %s 。字段类型：text=文本维度列 / decimal=数值列（均允许为空）。</footer>
</body>
</html>""" % (
        VERSION, VERSION, BUILD_DATE, "".join(cards), ov_table, legend,
        "".join(detail), GEN_TIME)
    return doc


# =================== XLSX ===================
def build_xlsx(path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    hdr_fill = PatternFill("solid", fgColor="1677FF")
    hdr_font = Font(color="FFFFFF", bold=True, size=11)
    title_font = Font(bold=True, size=14, color="1677FF")
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap = Alignment(vertical="top", wrap_text=True)

    # --- Sheet1 总览 ---
    ws = wb.active
    ws.title = "总览"
    ws.append(["序号", "中文表名", "英文物理表名", "来源", "分类", "字段数", "月度列数"])
    for c in range(1, 8):
        cell = ws.cell(row=1, column=c)
        cell.fill = hdr_fill; cell.font = hdr_font; cell.border = border
    for i, (cn, v) in enumerate(SCHEMA.items(), 1):
        months = sum(1 for c in v["columns"] if MON.match(c["name"]))
        ws.append([i, cn, v["en"], SRC_CN.get(v.get("source"), v.get("source")),
                   v.get("category", ""), len(v["columns"]), months])
        for c in range(1, 8):
            ws.cell(row=i + 1, column=c).border = border
    widths = [6, 26, 38, 12, 16, 8, 10]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"

    # --- Sheet2 字段明细 ---
    ws2 = wb.create_sheet("字段明细")
    ws2.append(["表序号", "中文表名", "英文表名", "来源", "分类",
                "字段序号", "中文字段名", "英文字段名", "类型", "说明"])
    for c in range(1, 11):
        cell = ws2.cell(row=1, column=c)
        cell.fill = hdr_fill; cell.font = hdr_font; cell.border = border
    r = 2
    for i, (cn, v) in enumerate(SCHEMA.items(), 1):
        for j, c in enumerate(v["columns"], 1):
            ws2.append([i, cn, v["en"], SRC_CN.get(v.get("source"), v.get("source")),
                        v.get("category", ""), j, c.get("cn", ""), c["name"],
                        type_tag(c["type"], c["name"]), field_desc(c)])
            for cidx in range(1, 11):
                cell = ws2.cell(row=r, column=cidx)
                cell.border = border; cell.alignment = wrap
            r += 1
    widths2 = [8, 24, 34, 10, 14, 8, 22, 30, 8, 34]
    for i, w in enumerate(widths2, 1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    ws2.freeze_panes = "A2"

    # --- Sheet3 分类汇总 ---
    ws3 = wb.create_sheet("分类汇总")
    ws3.append(["分类", "表数量", "字段数量"])
    for c in range(1, 4):
        cell = ws3.cell(row=1, column=c)
        cell.fill = hdr_fill; cell.font = hdr_font; cell.border = border
    rr = 2
    for cat in cats:
        tbls = groups[cat]
        ncols = sum(len(v["columns"]) for _, v in tbls)
        ws3.append([cat, len(tbls), ncols])
        for c in range(1, 4):
            ws3.cell(row=rr, column=c).border = border
        rr += 1
    ws3.append(["合计", total_tables, total_cols])
    for c in range(1, 4):
        cell = ws3.cell(row=rr, column=c)
        cell.font = Font(bold=True); cell.border = border
    for i, w in enumerate([20, 12, 14], 1):
        ws3.column_dimensions[get_column_letter(i)].width = w
    ws3.freeze_panes = "A2"

    wb.save(path)


def main():
    html_path = os.path.join(HERE, "输入数据规格.html")
    xlsx_path = os.path.join(HERE, "输入数据规格.xlsx")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html())
    build_xlsx(xlsx_path)
    print("生成完成：")
    print("  HTML:", html_path)
    print("  XLSX:", xlsx_path)
    print("  总表数=%d  总字段数=%d  来源=%s  分类数=%d"
          % (total_tables, total_cols, src_stat, len(cat_stat)))


if __name__ == "__main__":
    main()
