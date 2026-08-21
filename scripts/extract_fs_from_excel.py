import openpyxl, json, os, re
from datetime import datetime

EXCEL_PATH = r'D:\IFRS17预测模型\验证文件\IFRS17财务预测_改造版_开发.xlsx'
OUT_PATH = r'D:\IFRS17预测模型\ifrs17-system\data_input\fixtures\verify_targets.json'

def _norm_header(h):
    if h is None:
        return ''
    if isinstance(h, datetime):
        return h.strftime('%Y-%m-%d')
    h = str(h).strip()
    h = h.replace('\n', ' ')
    return h

def _to_float(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except Exception:
        return None

def extract_sheet(wb, sheet_name):
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    # 找表头行：第一行包含 datetime 的行
    header_idx = None
    for i, row in enumerate(rows[:15]):
        has_date = any(isinstance(c, datetime) for c in row)
        if has_date:
            header_idx = i
            break
    if header_idx is None:
        print(f'  {sheet_name}: no date header found')
        return []
    headers = [_norm_header(c) for c in rows[header_idx]]
    # 日期列：匹配 YYYY-MM-DD
    date_cols_idx = []
    for i, h in enumerate(headers):
        if re.match(r'^\d{4}-\d{2}-\d{2}$', h):
            date_cols_idx.append((i, h))
    if not date_cols_idx:
        print(f'  {sheet_name}: no date columns parsed')
        return []
    result = []
    for row in rows[header_idx+1:]:
        # 科目名在 col 1 (B)，偶尔 col 0 (A)
        label = row[1] if len(row) > 1 and row[1] is not None else None
        if not label and len(row) > 0 and row[0] is not None:
            label = row[0]
        if label is None:
            continue
        label = str(label).strip()
        if not label:
            continue
        # 跳过纯标题行
        if label in ('CAS 25 综合收益表', 'CAS 25 资产负债表', '资产', '负债'):
            continue
        d = {'科目': label}
        for idx, h in date_cols_idx:
            v = row[idx] if idx < len(row) else None
            fv = _to_float(v)
            d[h] = fv if fv is not None else None
        result.append(d)
    return result

def main():
    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)
    targets = {}
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH, 'r', encoding='utf-8') as f:
            targets = json.load(f)
    sheets = targets.setdefault('sheets', {})
    for sheet_name in ['输出财务报表_MTD', '输出财务报表_YTD']:
        rows = extract_sheet(wb, sheet_name)
        print(sheet_name, 'extracted rows:', len(rows))
        if rows:
            print('  headers:', list(rows[0].keys())[:6])
            print('  first row:', rows[0])
            print('  last row:', rows[-1])
            sheets[sheet_name] = rows
    # remove stale top-level keys if any
    for k in ['输出财务报表_MTD', '输出财务报表_YTD']:
        targets.pop(k, None)
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(targets, f, ensure_ascii=False, indent=2)
    print('written to', OUT_PATH)

if __name__ == '__main__':
    main()
