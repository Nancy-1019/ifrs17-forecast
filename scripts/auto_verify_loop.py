#!/usr/bin/env python
"""
IFRS17 自动验证循环脚本（与系统后端比对逻辑保持一致）

- 读取验证文件(IFRS17财务预测_改造版_0729_VBA.xlsx)中的 6 张输出表
- 复用 data_input.views 的解析器(_parse_verify_sheet / _parse_financial_report_sheet)
  与对齐主键(VERIFY_KEY_COLS)，保证与系统 UI 的差异比对完全一致
- 复用 _build_system_verify_rows 取得系统输出，并用 _generate_comparison 作权威校验
- 额外做单元格级差异抓取（仅在数值列、主键对齐后），便于定位引擎偏差

用法:
  python scripts/auto_verify_loop.py [all]    # 默认 all，覆盖 6 张表
"""
import os
import sys
import json
import csv
import datetime
import argparse
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRJ_ROOT = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
import django
django.setup()

import openpyxl
from data_input.views import (
    _parse_verify_sheet,
    _parse_financial_report_sheet,
    VERIFY_OUTPUT_SHEETS,
    FINANCIAL_REPORT_SHEETS,
    VERIFY_KEY_COLS,
    _build_system_verify_rows,
    _generate_comparison,
    _CALC_CACHE,
)

VERIFY_FILE = os.path.join(PRJ_ROOT, '验证文件', 'IFRS17财务预测_改造版_0729_VBA.xlsx')
REPORT_DIR = os.path.join(PRJ_ROOT, '验证文件', 'auto_verify_reports')
os.makedirs(REPORT_DIR, exist_ok=True)

TOLERANCE = 0.01


def _serialize(v):
    if v is None:
        return None
    if isinstance(v, datetime.datetime):
        return v.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(v, datetime.date):
        return v.strftime('%Y-%m-%d')
    return v


def _to_float(v):
    """严格数值转换：None/空/非数字返回 None（区别于模块级 _to_float 的 0.0 兜底）。"""
    if v is None or v == '':
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _normalize_header(h):
    if h is None:
        return ''
    return str(h).strip().replace(' ', '').replace('\u3000', '')


def _cell_value(row, idx, header):
    if isinstance(row, dict):
        return row.get(header)
    return row[idx] if idx < len(row) else None


def _is_real_number(v):
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return True
    try:
        import numbers
        return isinstance(v, numbers.Real)
    except Exception:
        return False


def _is_numeric_side(rows, idx, header):
    cnt = num = 0
    for r in rows[:15]:
        v = _cell_value(r, idx, header)
        if v is not None:
            cnt += 1
            if _is_real_number(v):
                num += 1
    return cnt > 0 and num >= max(1, int(cnt * 0.6))


def _is_numeric_col(v_rows, s_rows, idx, header):
    # 仅当 verify 与 system 两侧均为数值列时才纳入数值比对，
    # 避免单侧为空占位整数（如 verify 子合同组合名称=0）误判为数值列。
    if not _is_numeric_side(v_rows, idx, header):
        return False
    if s_rows and not _is_numeric_side(s_rows, idx, header):
        return False
    return True


def _build_key(row_dict, headers, keys):
    return '||'.join('' if row_dict.get(k) is None else str(row_dict.get(k)) for k in keys)


def load_system_cache():
    cache_path = os.path.join(ROOT, 'data_input', 'runtime_cache', 'calc_result_cache.json')
    if not os.path.exists(cache_path):
        return None
    return json.load(open(cache_path, encoding='utf-8')).get('result')


def compare_faithful(v_headers, v_rows, s_rows, key_cols, tolerance=TOLERANCE):
    """单元格级差异比对（数值列、主键对齐后），返回 (report, cell_diffs)"""
    v_numeric = [i for i in range(len(v_headers)) if _is_numeric_col(v_rows, s_rows, i, v_headers[i])]

    v_by_key = {}
    for r in v_rows:
        rd = {h: (r[i] if i < len(r) else None) for i, h in enumerate(v_headers)}
        v_by_key[_build_key(rd, v_headers, key_cols)] = rd

    s_by_key = {}
    if s_rows:
        for r in s_rows:
            s_by_key[_build_key(r, list(r.keys()), key_cols)] = r

    common_keys = set(v_by_key) & set(s_by_key)
    total_diff = 0.0
    field_diffs = []
    cell_diffs = []

    for ci in v_numeric:
        col_name = v_headers[ci]
        v_sum = s_sum = 0.0
        diff_cells = 0
        for key in sorted(common_keys):
            vv = v_by_key[key].get(col_name)
            sv = s_by_key[key].get(col_name)
            vf = _to_float(vv)
            sf = _to_float(sv)
            if vf is not None:
                v_sum += vf
            if sf is not None:
                s_sum += sf
            if vf is not None and sf is not None:
                d = vf - sf
                if abs(d) > tolerance:
                    total_diff += abs(d)
                    diff_cells += 1
                    # 仅保留前若干单元格明细，避免超大 CSV
                    if len(cell_diffs) < 5000:
                        cell_diffs.append({
                            'key': key, 'field': col_name,
                            'verify': round(vf, 4), 'system': round(sf, 4),
                            'diff': round(d, 4),
                        })
        field_diffs.append({
            'field': col_name,
            'verifySum': round(v_sum, 2),
            'systemSum': round(s_sum, 2),
            'diff': round(v_sum - s_sum, 2),
            'diffCells': diff_cells,
        })
    field_diffs.sort(key=lambda x: abs(x['diff']), reverse=True)
    diff_field_count = sum(1 for f in field_diffs if f['diffCells'] > 0)
    report = {
        'status': 'compared' if s_rows else 'verify_only',
        'verifyRows': len(v_rows),
        'systemRows': len(s_rows) if s_rows else 0,
        'commonKeys': len(common_keys),
        'numericFields': len(field_diffs),
        'diffFieldCount': diff_field_count,
        'fieldDiffs': field_diffs,
        'totalDiffAmount': round(total_diff, 2),
    }
    return report, cell_diffs


def save_csv_cells(sheet_name, cells, ts):
    if not cells:
        return None
    path = os.path.join(REPORT_DIR, f'cells_{sheet_name}_{ts}.csv')
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['key', 'field', 'verify', 'system', 'diff'])
        w.writeheader()
        for c in cells:
            w.writerow(c)
    return path


def main():
    parser = argparse.ArgumentParser(description='IFRS17 自动验证循环')
    parser.add_argument('target', nargs='?', default='all',
                        choices=['all'], help='比对目标（当前仅支持 all，覆盖 6 张表）')
    parser.add_argument('--scenario', default='基础情景', help='场景名称')
    parser.add_argument('--tolerance', type=float, default=0.01, help='数值容差')
    args = parser.parse_args()
    global TOLERANCE
    TOLERANCE = args.tolerance

    print('=' * 70)
    print(f'IFRS17 自动验证循环 | 目标={args.target} | 场景={args.scenario}')
    print(f'验证文件: {VERIFY_FILE}')
    print(f'时间: {datetime.datetime.now().isoformat()}')
    print('=' * 70)

    # 1. 读取验证文件并解析（复用后端解析器）
    print('\n[1/4] 读取并解析验证文件输出表...')
    wb = openpyxl.load_workbook(VERIFY_FILE, read_only=True, data_only=True)
    verify_data = {}
    verify_raw = {}
    for sheet_name in VERIFY_OUTPUT_SHEETS:
        if sheet_name not in wb.sheetnames:
            verify_data[sheet_name] = {'available': False, 'headers': [], 'rows': []}
            verify_raw[sheet_name] = ([], [])
            print(f"  {sheet_name}: 缺失")
            continue
        ws = wb[sheet_name]
        if sheet_name in FINANCIAL_REPORT_SHEETS:
            headers, rows = _parse_financial_report_sheet(ws)
        else:
            headers, rows = _parse_verify_sheet(ws)
        rows_serialized = [[_serialize(v) for v in row] for row in rows]
        verify_data[sheet_name] = {
            'available': True,
            'headers': [_serialize(h) for h in headers],
            'rows': rows_serialized,
        }
        verify_raw[sheet_name] = (headers, rows_serialized)
        print(f"  {sheet_name}: 可用 | 行数={len(rows_serialized)} | 列数={len(headers)}")
    wb.close()

    # 2. 读取系统计算结果
    print('\n[2/4] 读取系统计算结果...')
    calc_result = load_system_cache()
    if calc_result and calc_result.get('success'):
        print('  已加载持久化的计算结果')
    else:
        print('  缓存不可用，无法比对（请先运行系统计算）')
        sys.exit(1)
    system_rows_map = _build_system_verify_rows(calc_result)

    # 3. 逐表比对
    print('\n[3/4] 逐表比对（单元格级，数值列）...')
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    summary = {}
    for sheet_name in VERIFY_OUTPUT_SHEETS:
        info = verify_data[sheet_name]
        if not info.get('available'):
            summary[sheet_name] = {'status': 'missing', 'message': '验证文件中缺少该表'}
            print(f"\n  [{sheet_name}] 缺失")
            continue
        v_headers, v_rows = verify_raw[sheet_name]
        key_cols = VERIFY_KEY_COLS.get(sheet_name, ['合同组ID'])
        s_rows = system_rows_map.get(sheet_name)

        report, cells = compare_faithful(v_headers, v_rows, s_rows, key_cols, tolerance=args.tolerance)
        # 与后端权威比对交叉校验
        _CALC_CACHE['result'] = calc_result
        backend_cmp = _generate_comparison({sheet_name: info}).get(sheet_name, {})
        backend_diff_fields = backend_cmp.get('diffFieldCount', 0)

        csv_path = save_csv_cells(sheet_name, cells, ts)
        summary[sheet_name] = report
        print(f"\n  [{sheet_name}]")
        print(f"    验证行数={report['verifyRows']} | 系统行数={report['systemRows']} | 共同键={report['commonKeys']}")
        print(f"    数值列差异字段数={report['diffFieldCount']} | 差异总额={report['totalDiffAmount']}")
        print(f"    后端权威 diffFieldCount={backend_diff_fields} (交叉校验)")
        if report['diffFieldCount'] > 0:
            top = [f"{f['field']}(单元={f['diffCells']},Δ={f['diff']})" for f in report['fieldDiffs'][:8] if f['diffCells'] > 0]
            print(f"    差异字段: {top}")
            if csv_path:
                print(f"    单元格明细CSV: {csv_path}")

    # 4. 保存报告
    print('\n[4/4] 保存差异报告...')
    json_path = os.path.join(REPORT_DIR, f'report_{args.target}_{ts}.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'target': args.target,
            'scenario': args.scenario,
            'verify_overview': {k: {'rows': len(v[1]), 'cols': len(v[0])} for k, v in verify_raw.items()},
            'comparison': summary,
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f'  JSON摘要: {json_path}')
    print('\n完成。')


if __name__ == '__main__':
    main()
