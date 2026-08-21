#!/usr/bin/env python
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
import django
django.setup()
from data_input.views import build_data_json
from paa_engine import PAAEngine

dock = build_data_json('dock'); excel = build_data_json('excel')
engine = PAAEngine(dock_sheets=dock, excel_sheets=excel)

def nb_prem_sum(org):
    return sum((r.get('保费收入', 0) or 0) for r in org['新业务假设'])

def nb_cc_sum(org):
    return sum((r.get('当期提前初始确认签单保费', 0) or 0) for r in org['新业务假设'])

def ex_iacf_sum(org):
    return sum((r.get('应付IACF', 0) or 0) for r in org['现有业务假设'])

for sc in ['基础情景', '情景1', '情景2', '情景3']:
    org = engine.organize_inputs(sc)
    print(f"{sc}: 新业务保费和={nb_prem_sum(org):,.0f} CC和={nb_cc_sum(org):,.0f} 现有业务应付IACF和={ex_iacf_sum(org):,.0f}")
    # 利率曲线首月
    rc = org['利率曲线']['月度远期利率']
    print(f"   月度远期利率[1..3]={[round(rc.get(m,0),6) for m in (1,2,3)]}")
