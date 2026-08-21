#!/usr/bin/env python
"""离线触发情景4 PAA 计算并写回 runtime_cache，使财务报表使用修复后的 YTD 累计逻辑。"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
import django
django.setup()

from data_input.views import (
    build_data_json, _serialize_row, _save_calc_cache, _CALC_CACHE,
)
from paa_engine import PAAEngine

dock_data = build_data_json('dock')
excel_data = build_data_json('excel')
print('dock sheets:', list((dock_data or {}).keys()))
print('excel sheets:', list((excel_data or {}).keys()))

engine = PAAEngine(dock_sheets=dock_data, excel_sheets=excel_data)
result = engine.run(scenario='情景4', forecast_periods_override=None)

response_data = {
    'success': result.success,
    'error': result.error,
    'selectedScenario': result.selected_scenario,
    'scenarios': result.scenarios,
    'calcLogs': result.calc_logs,
    'inputOrganized': {
        'newBusiness': [_serialize_row(r) for r in result.input_organized.get('新业务假设', [])],
        'existingBusiness': [_serialize_row(r) for r in result.input_organized.get('现有业务假设', [])],
        'rateCurve': result.input_organized.get('利率曲线', {}),
        'scenario': result.input_organized.get('选定场景', '情景0'),
        'evalDate': result.input_organized.get('评估时点', ''),
        'forecastPeriods': result.input_organized.get('预测期数', 0),
    },
    'newBusinessPredict': [_serialize_row(r) for r in result.new_business_predict],
    'existingBusinessPredict': [_serialize_row(r) for r in result.existing_business_predict],
    'combinedSummary': [_serialize_row(r) for r in result.combined_summary],
    'financialStatements': [_serialize_row(r) for r in result.financial_statements],
    'financialStatementsV2': result.financial_statements_v2,
    'summary': {
        'newBusinessRows': len(result.new_business_predict),
        'existingBusinessRows': len(result.existing_business_predict),
        'combinedSummaryRows': len(result.combined_summary),
        'financialStatementRows': len(result.financial_statements),
    },
}

_CALC_CACHE['result'] = response_data
_CALC_CACHE['scenario'] = '情景4'
from django.utils import timezone
_CALC_CACHE['timestamp'] = timezone.now().isoformat()
_save_calc_cache()

fs = response_data['financialStatementsV2']
print('FS success:', response_data['success'], 'error:', response_data['error'])
print('FS dates:', fs.get('dates'))
for r in fs.get('mtd', {}).get('income_statement', []):
    if r['item'] == '保险服务收入':
        print('MTD 保险服务收入:', r.get('values'))
        break
for r in fs.get('ytd', {}).get('income_statement', []):
    if r['item'] == '保险服务收入':
        print('YTD 保险服务收入:', r.get('values'))
        break
