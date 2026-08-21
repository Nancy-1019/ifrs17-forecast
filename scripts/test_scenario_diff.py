#!/usr/bin/env python
"""对比不同情景的输出差异，并校验基础情景与改动前缓存一致。"""
import os, sys, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
import django
django.setup()

from data_input.views import build_data_json
from paa_engine import PAAEngine

dock_data = build_data_json('dock')
excel_data = build_data_json('excel')

engine = PAAEngine(dock_sheets=dock_data, excel_sheets=excel_data)
# 列出可用情景
try:
    sc_list = engine.get_scenario_list()
    print('可用情景:', [s.get('value') for s in sc_list])
except Exception as e:
    print('get_scenario_list err', e)
    sc_list = [{'value': '基础情景'}]

def fs_agg(fs):
    mtd = fs.get('mtd', {})
    inc = {r['item']: r['values'] for r in mtd.get('income_statement', [])}
    def total(item):
        v = inc.get(item, [])
        return sum(v) if v else 0.0
    return {
        '保险服务收入': total('保险服务收入'),
        '承保利润': total('承保利润'),
        '净利润': total('五、净利润（净亏损以"-"号填列）'),
        '保险服务费用': total('保险服务费用'),
    }

results = {}
for sc in ['情景1', '情景2']:
    try:
        r = engine.run(scenario=sc, forecast_periods_override=None)
        if not r.success:
            print(sc, 'FAIL', r.error)
            continue
        fs = r.financial_statements_v2
        results[sc] = fs_agg(fs)
        print(sc, results[sc])
    except Exception as e:
        print(sc, 'EXC', repr(e))

# 基础情景与改动前缓存对比
cache_path = os.path.join(ROOT, 'data_input', 'runtime_cache', 'calc_result_cache.json')
if os.path.exists(cache_path):
    with open(cache_path, encoding='utf-8') as f:
        cached = json.load(f)
    cfs = cached.get('financialStatementsV2', {})
    cagg = fs_agg(cfs)
    print('--- 基础情景 vs 改动前缓存 ---')
    base = results.get('基础情景')
    if base:
        for k in base:
            diff = base[k] - cagg.get(k, 0.0)
            print(f'  {k}: 新={base[k]:.2f} 旧={cagg.get(k,0.0):.2f} 差={diff:.4f}')

# 情景差异
print('--- 情景间差异（相对基础情景）---')
base = results.get('基础情景')
if base:
    for sc, agg in results.items():
        if sc == '基础情景':
            continue
        print(sc, {k: (agg[k]-base[k]) for k in base})
