"""
生成带示例数据的预实分析测试文件
"""
import os
import shutil
from openpyxl import load_workbook

TEMPLATE = os.path.join(os.path.dirname(__file__), '..', '验证文件', '预实分析_实际数据上传模板.xlsx')
OUT_FILE = os.path.join(os.path.dirname(__file__), '..', '验证文件', '预实分析_实际数据_示例.xlsx')

shutil.copy(TEMPLATE, OUT_FILE)
wb = load_workbook(OUT_FILE)

# 填充公司合计实际数
ws_company = wb['公司合计实际数']
example_values = {
    '保险服务收入': 465279.13,
    '保险服务费用': 459911.77,
    '分出再保险净损益': 328.12,
    '承保财务损益净额': 2629.92,
    '投资收益': 16821.31,
    '其他损益': 12642.97,
    '净利润': 11695.75,
}
for row in ws_company.iter_rows(min_row=2, max_row=ws_company.max_row):
    item = row[1].value
    if item in example_values:
        row[2].value = example_values[item]

# 填充精算险类实际数
ws_class = wb['精算险类实际数']
# 列索引：A=评估时点, B=代码, C=名称, D=保险服务收入, E=保险服务费用, F=分出再保险净损益, G=承保财务损益净额,
# H=投资收益, I=其他损益, J=营业利润, K=净利润, L=净资产, M=综合成本率, N=综合赔付率, O=综合费用率
for row in ws_class.iter_rows(min_row=2, max_row=ws_class.max_row):
    code = row[1].value
    if code in ['32', '37', '38', '101', '104', '301', '302', '602']:
        row[3].value = 100000 + hash(code) % 50000  # 保险服务收入
        row[4].value = 80000 + hash(code) % 30000   # 保险服务费用
        row[5].value = 1000 + hash(code) % 2000     # 分出再保险净损益
        row[6].value = 500 + hash(code) % 1000      # 承保财务损益净额
        row[7].value = 2000 + hash(code) % 3000     # 投资收益
        row[8].value = 1000 + hash(code) % 2000     # 其他损益
        row[9].value = row[3].value - row[4].value - row[5].value - row[6].value + row[7].value + row[8].value  # 营业利润
        row[10].value = row[9].value * 0.75          # 净利润
        row[11].value = 500000 + hash(code) % 100000 # 净资产
        row[12].value = 95 + hash(code) % 10         # 综合成本率
        row[13].value = 60 + hash(code) % 15         # 综合赔付率
        row[14].value = 30 + hash(code) % 10         # 综合费用率

wb.save(OUT_FILE)
print(f'已生成示例数据文件: {OUT_FILE}')
