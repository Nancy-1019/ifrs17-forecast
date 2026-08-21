#!/usr/bin/env python
import os, sys
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

for sc in ['基础情景', '情景0', '情景1', '情景2', '情景3']:
    try:
        params = engine._get_scenario_params(sc)
        print(sc, '-> months with params:', sorted(params.keys()))
        # 打印第一个有参数的月份
        for m in sorted(params.keys()):
            if params[m]:
                print('   月', m, params[m])
                break
    except Exception as e:
        print(sc, 'EXC', repr(e))
