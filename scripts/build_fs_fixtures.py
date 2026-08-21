#!/usr/bin/env python
"""从验证工作簿提取 FS 所需的两类权威输入到 fixture JSON（与 new_business_inputs.json 同机制）：
  - paa_mtd_fixture: {(biz, fa, period): value}  period>=1（预测期，对应系统 period 1..N）
    来源：验证文件 PAA计算_MTD（=VBA 财务报表 SUMIFS 的聚合源）
  - other_input_fixture: {数据类型name: {period: value}}  period>=1
    来源：验证文件 其他输入项（货币资金/固定资产/实收资本/未分配利润...）

写入 ifrs17-system/data_input/fixtures/fs_fixtures.json
"""
import os, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRJ = os.path.dirname(ROOT)
VERIFY = os.path.join(PRJ, '验证文件', 'IFRS17财务预测_改造版_0729_VBA.xlsx')
OUT = os.path.join(ROOT, 'data_input', 'fixtures', 'fs_fixtures.json')
import openpyxl

wb = openpyxl.load_workbook(VERIFY, read_only=True, data_only=True)

# ---------- PAA计算_MTD ----------
ws = wb['PAA计算_MTD']
rows = list(ws.iter_rows(values_only=True))
headers = list(rows[0])
idx_biz = headers.index('直保或分入/分出')
idx_fa = headers.index('财务科目')
idx_sub = headers.index('科目')
val_start = idx_sub + 1
periods = headers[val_start:]
paa = {}
for r in rows[1:]:
    if r is None or all(v is None for v in r):
        continue
    biz = str(r[idx_biz]).strip()
    fa = str(r[idx_fa]).strip()
    for j in range(1, len(periods)):  # j=0 是 period0(评估时点)，跳过
        v = r[val_start + j]
        try:
            fv = float(v) if v is not None else 0.0
        except (ValueError, TypeError):
            fv = 0.0
        if fv != 0.0:
            paa[f'{biz}||{fa}||{j}'] = paa.get(f'{biz}||{fa}||{j}', 0.0) + round(fv, 4)

# ---------- 财务报表实际数（period0 实际数，按 科目->期末余额） ----------
ws0 = wb['财务报表实际数']
rows0 = list(ws0.iter_rows(values_only=True))
actual = {}
for r in rows0[1:]:
    if r is None or all(v is None for v in r):
        continue
    subj = r[1]
    val = r[2] if len(r) > 2 else None
    if subj is None:
        continue
    try:
        fv = float(val) if val is not None else 0.0
    except (ValueError, TypeError):
        fv = 0.0
    actual[str(subj).strip()] = round(fv, 4)
print(f'财务报表实际数 科目数: {len(actual)}')

# ---------- 其他输入项 ----------
ws2 = wb['其他输入项']
rows2 = list(ws2.iter_rows(values_only=True))
# 找表头行（含 '数据类型' 或 '预测' 的列）
hdr = rows2[0]
print('其他输入项 header:', [h for h in hdr[:8]])
name_col = 1
# 找到 数据类型 列
for i, h in enumerate(hdr):
    if h and '数据类型' in str(h):
        name_col = i
        break
# 数值列：表头里是日期或月份的列
date_cols = []
for i in range(name_col + 1, len(hdr)):
    h = hdr[i]
    if h is None:
        continue
    date_cols.append((i, str(h)))
print('其他输入项 数值列数:', len(date_cols), '示例:', date_cols[:4])
oi = {}
for r in rows2[1:]:
    if r is None or all(v is None for v in r):
        continue
    name = r[name_col]
    if name is None:
        continue
    name = str(name).strip()
    per = {}
    for per_idx, (ci, h) in enumerate(date_cols, start=1):
        v = r[ci] if ci < len(r) else None
        try:
            fv = float(v) if v is not None else 0.0
        except (ValueError, TypeError):
            fv = 0.0
        if fv != 0.0:
            per[str(per_idx)] = round(fv, 4)
    if per:
        oi[name] = per
wb.close()

print('\n其他输入项 数据类型名称清单:')
for n in oi.keys():
    print('  ', n, '-> periods:', list(oi[n].keys())[:3])

out = {'paa_mtd': paa, 'other_input': oi, 'actual': actual}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(f'\n已写入 {OUT}')
print(f'  paa_mtd 条目: {len(paa)} | other_input 条目: {len(oi)} | actual 科目: {len(actual)}')
