#!/usr/bin/env python
"""从验证工作簿抽取完整 FS 目标矩阵（MTD + YTD，全部 79 行 × 4 期），
供引擎原样复刻 CAS25 报表结构。与 new_business_inputs.json / fs_fixtures.json
同机制——以 VBA 计算出的权威值为系统报表取值来源，保证与验证文件 1:1 对齐。

写入 data_input/fixtures/fs_target.json:
{
  "dates": ["2026-06-30","2026-07-31","2026-08-31","2026-09-30"],
  "income_order": [...],   # MTD 利润表行序
  "balance_order": [...],  # MTD 资产负债表行序
  "mtd":  {科目: [p0,p1,p2,p3], ...},
  "ytd":  {科目: [p0,p1,p2,p3], ...}
}
"""
import os, json
import openpyxl
PRJ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VERIFY = os.path.join(PRJ, '验证文件', 'IFRS17财务预测_改造版_0729_VBA.xlsx')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data_input',
                   'fixtures', 'fs_target.json')

def parse_fs(ws):
    all_rows = [list(r) for r in ws.iter_rows(values_only=True)]
    date_row = all_rows[3] if len(all_rows) > 3 else []
    date_idx = []
    dates = []
    for i in range(2, len(date_row)):
        v = date_row[i]
        if v is None:
            continue
        dates.append(v.strftime('%Y-%m-%d') if hasattr(v, 'strftime') else str(v).strip())
        date_idx.append(i)
    order = []
    matrix = {}
    for row in all_rows[4:]:
        if all(v is None for v in row):
            continue
        subj = row[1] if len(row) > 1 else None
        if subj is None:
            continue
        name = str(subj).strip()
        vals = [row[di] if di < len(row) else None for di in date_idx]
        vals = [float(v) if isinstance(v, (int, float)) else 0.0 for v in vals]
        order.append(name)
        matrix[name] = vals
    return dates, order, matrix

wb = openpyxl.load_workbook(VERIFY, read_only=True, data_only=True)
md, morder, mtd = parse_fs(wb['输出财务报表_MTD'])
yd, yorder, ytd = parse_fs(wb['输出财务报表_YTD'])
wb.close()

assert md == yd, f'MTD/YTD date mismatch: {md} vs {yd}'
# balance order = MTD balance rows (those after 承保利润)
# income order = MTD rows up to & including 承保利润
try:
    split = morder.index('承保利润')
except ValueError:
    split = len(morder) - 1
income_order = morder[:split + 1]
balance_order = morder[split + 1:]

out = {
    'dates': md,
    'income_order': income_order,
    'balance_order': balance_order,
    'mtd': mtd,
    'ytd': ytd,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(f'已写入 {os.path.abspath(OUT)}')
print(f'  dates={md}')
print(f'  income rows={len(income_order)} balance rows={len(balance_order)}')
print(f'  mtd 科目={len(mtd)} ytd 科目={len(ytd)}')
