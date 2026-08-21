"""端到端验证「预测时点筛选」比对逻辑。

不依赖 Web 请求，直接调用 views 模块函数：
- _collect_available_periods：时点并集
- _apply_period_filter：行维度滤行 / 列维度滤列
- _generate_comparison(filter_periods=...)：差异比对随筛选变化
"""
import os, sys, json

ROOT = r'D:\IFRS17预测模型'
sys.path.insert(0, os.path.join(ROOT, 'ifrs17-system'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')

import django
django.setup()

from data_input import views as V

FT = os.path.join(ROOT, 'ifrs17-system', 'data_input', 'fixtures', 'verify_targets.json')
sheets = json.load(open(FT, encoding='utf-8')).get('sheets', {})

# 构造 sheet_data（与上传解析结构一致）：headers=列名, rows=dict 行列表
sheet_data = {}
for sn, rows in sheets.items():
    if not rows:
        continue
    headers = list(rows[0].keys())
    sheet_data[sn] = {'available': True, 'headers': headers, 'rows': rows, 'totalRows': len(rows)}

print('=== 1) 可用预测时点 (availablePeriods) ===')
periods = V._collect_available_periods(sheet_data)
print(periods)
assert periods, 'availablePeriods 不能为空'

# 构造系统输出 = fixture 本身（零差异基线），仅用于验证“过滤后行/列正确、差异仍为零”
system_rows_map = {sn: rows for sn, rows in sheets.items() if rows}

print('\n=== 2) 无筛选（全部）比对 ===')
cmp_all = V._generate_comparison(sheet_data, None, system_rows_map)
for sn in V.VERIFY_OUTPUT_SHEETS:
    c = cmp_all.get(sn, {})
    print(f'  {sn}: verifyRows={c.get("verifyRows")} systemRows={c.get("systemRows")} '
          f'status={c.get("status")} totalDiff={c.get("totalDiffAmount")} headers={len(c.get("headers", []))}')

print('\n=== 3) 仅筛选 2026-07-31 ===')
f1 = ['2026-07-31']
cmp_f1 = V._generate_comparison(sheet_data, f1, system_rows_map)
for sn in V.VERIFY_OUTPUT_SHEETS:
    c = cmp_f1.get(sn, {})
    hdrs = c.get('headers', [])
    # 列维度表：表头应只剩 非日期列 + 选中日期列
    period_cols = [h for h in hdrs if V._is_period_header(h)]
    print(f'  {sn}: verifyRows={c.get("verifyRows")} systemRows={c.get("systemRows")} '
          f'periodCols={period_cols} totalDiff={c.get("totalDiffAmount")}')

print('\n=== 4) 仅筛选 2026-06-30,2026-07-31,2026-08-31 ===')
f3 = ['2026-06-30', '2026-07-31', '2026-08-31']
cmp_f3 = V._generate_comparison(sheet_data, f3, system_rows_map)
for sn in V.VERIFY_OUTPUT_SHEETS:
    c = cmp_f3.get(sn, {})
    hdrs = c.get('headers', [])
    period_cols = [h for h in hdrs if V._is_period_header(h)]
    print(f'  {sn}: verifyRows={c.get("verifyRows")} systemRows={c.get("systemRows")} '
          f'periodCols={period_cols} totalDiff={c.get("totalDiffAmount")}')

print('\n=== 5) 断言：列维度表时点列数随筛选收窄 ===')
# 输出财务报表_MTD 全部时点
hdrs_all = cmp_all['输出财务报表_MTD']['headers']
n_all = len([h for h in hdrs_all if V._is_period_header(h)])
hdrs_f3 = cmp_f3['输出财务报表_MTD']['headers']
n_f3 = len([h for h in hdrs_f3 if V._is_period_header(h)])
print(f'  输出财务报表_MTD 全部时点列数={n_all}, 筛选3期列数={n_f3}')
assert n_f3 == 3, f'期望 3 个时点列，实际 {n_f3}'
assert n_all >= n_f3, '筛选后时点列数应 <= 全部'

print('\n=== 6) 断言：行维度表行数随筛选收窄（PAA计算_新业务整理）===')
n_all_nb = cmp_all['PAA计算_新业务整理']['verifyRows']
n_f3_nb = cmp_f3['PAA计算_新业务整理']['verifyRows']
print(f'  PAA计算_新业务整理 全部行={n_all_nb}, 筛选3期行={n_f3_nb}')
assert n_f3_nb <= n_all_nb, '筛选后行数应 <= 全部'

print('\n=== 7) 断言：零差异基线在筛选后仍为零 ===')
for sn in V.VERIFY_OUTPUT_SHEETS:
    assert cmp_f3[sn].get('totalDiffAmount', 0) == 0, f'{sn} 筛选后差异非0'
print('  OK：所有表筛选后差异总额均为 0（与基线一致）')

print('\n全部断言通过 ✅')
