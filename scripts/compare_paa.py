# -*- coding: utf-8 -*-
"""比对系统 period1 预测输出 与 验证文件 *整理表 的 输出_* 列。
目标：定位 PAA 计算逻辑差异，驱动自动修复循环。
"""
import os, sys, json, django
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
sys.path.insert(0, os.path.join(ROOT, 'ifrs17-system'))
django.setup()

import openpyxl
from collections import Counter, defaultdict

CACHE = os.path.join(ROOT, 'ifrs17-system', 'data_input', 'runtime_cache', 'calc_result_cache.json')
result = json.load(open(CACHE, encoding='utf-8'))['result']

def period1(rows):
    return [r for r in rows if r.get('预测间隔') == 1]

sys_exist = period1(result['existingBusinessPredict'])
sys_new = period1(result['newBusinessPredict'])

VP = os.path.join(ROOT, '验证文件', 'IFRS17财务预测_改造版_0729_VBA.xlsx')
wb = openpyxl.load_workbook(VP, data_only=True)

def load_verify(sheet):
    ws = wb[sheet]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hdr = rows[0]
    data = [dict(zip(hdr, r)) for r in rows[1:] if any(v is not None for v in r)]
    return data

ver_exist = load_verify('PAA计算_现有业务整理')
ver_new = load_verify('PAA计算_新业务整理')

def keyof(r, src):
    if src == 'sys_exist':
        return (str(r.get('合同组ID','')), str(r.get('直保或分入/分出','')))
    if src == 'sys_new':
        return (str(r.get('预测组ID','')), str(r.get('直保或分入/分出','')))
    if src == 'ver_exist':
        return (str(r.get('合同组ID','')), str(r.get('直保或分入/分出','')))
    if src == 'ver_new':
        return (str(r.get('合同组ID','')), str(r.get('直保或分入/分出','')))
    return ()

# 组覆盖分析
def groups(rows, src):
    return Counter(keyof(r, src) for r in rows)
print("=== 组覆盖 ===")
ge = groups(sys_exist,'sys_exist'); gve = groups(ver_exist,'ver_exist')
gn = groups(sys_new,'sys_new'); gvn = groups(ver_new,'ver_new')
print(f"现有: 系统 {len(ge)} 组, 验证 {len(gve)} 组")
print(f"  系统独有: {set(ge)-set(gve)}")
print(f"  验证独有: {set(gve)-set(ge)}")
print(f"新业务: 系统 {len(gn)} 组, 验证 {len(gvn)} 组")
print(f"  系统独有: {set(gn)-set(gvn)}")
print(f"  验证独有: {set(gvn)-set(gn)}")

# 输出_* 列比对
def output_cols(rows):
    if not rows: return []
    return [c for c in rows[0].keys() if c.startswith('输出_')]

def compare_pair(sys_rows, ver_rows, src_sys, src_ver, label):
    scols = output_cols(sys_rows); vcols = output_cols(ver_rows)
    common = [c for c in vcols if c in scols]
    print(f"\n=== {label} === 输出列 系统{len(scols)} 验证{len(vcols)} 共同{len(common)}")
    sys_map = {keyof(r,src_sys): r for r in sys_rows}
    ver_map = {keyof(r,src_ver): r for r in ver_rows}
    matched = set(sys_map) & set(ver_map)
    print(f"可对齐组: {len(matched)} / 系统{len(sys_map)} 验证{len(ver_map)}")
    col_stats = {}
    samples = []
    for col in common:
        diffs = 0; tot = 0.0; mx = 0.0; mxkey=None
        for k in matched:
            sv = sys_map[k].get(col); vv = ver_map[k].get(col)
            a = float(sv) if isinstance(sv,(int,float)) else 0.0
            b = float(vv) if isinstance(vv,(int,float)) else 0.0
            d = abs(a-b)
            if d > 0.01:
                diffs += 1; tot += d
                if d > mx: mx = d; mxkey=k
                if len(samples) < 200:
                    samples.append((col, k, round(a,2), round(b,2), round(d,2)))
        col_stats[col] = (diffs, round(tot,2), round(mx,2), mxkey)
    # 按 diff 数排序
    ranked = sorted(col_stats.items(), key=lambda x:(-x[1][0], -x[1][1]))
    print("top 差异列 (列, 差异单元格数, 总abs差, 最大abs差):")
    for col,(d,t,m,mk) in ranked[:25]:
        print(f"  {col}: n={d} tot={t} max={m} @{mk}")
    # 保存明细
    outdir = os.path.join(ROOT,'验证文件','auto_verify_reports')
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, f'diffs_{label}.csv'),'w',encoding='utf-8') as f:
        f.write('col,key,sys_val,ver_val,absdiff\n')
        for s in samples:
            f.write(','.join(str(x) for x in s)+'\n')
    return col_stats, matched

compare_pair(sys_exist, ver_exist, 'sys_exist', 'ver_exist', '现有业务')
compare_pair(sys_new, ver_new, 'sys_new', 'ver_new', '新业务')
wb.close()
print('\nDONE')
