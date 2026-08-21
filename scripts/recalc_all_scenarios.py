#!/usr/bin/env python
"""批量计算所有可用情景，填充后端多场景缓存 _CALC_RESULTS_MAP。

用法：
    python scripts/recalc_all_scenarios.py
"""
import os
import sys
import json
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
import django
django.setup()

from data_input.views import build_data_json, _CALC_RESULTS_MAP, _CALC_CACHE, _save_calc_results_map
from paa_engine import PAAEngine


def _serialize_row(r):
    """轻量序列化行（与 views.py 中一致）。"""
    if r is None:
        return {}
    if isinstance(r, dict):
        return {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in r.items()}
    return dict(r)


def main():
    dock_data = build_data_json('dock')
    excel_data = build_data_json('excel')
    if not dock_data and not excel_data:
        print('[recalc_all] 没有上传数据，无法计算')
        return

    engine = PAAEngine(dock_sheets=dock_data, excel_sheets=excel_data)
    try:
        scenarios = [s['value'] for s in engine.get_scenarios()]
        # 统一基础情景名称为 '情景0'，与 get_scenarios() 返回值一致
        scenarios = ['情景0' if s in ('情景0', '基础情景') else s for s in scenarios]
    except Exception as e:
        print('[recalc_all] 获取情景列表失败:', e)
        scenarios = ['情景0']

    print('[recalc_all] 待计算情景:', scenarios)

    for scenario in scenarios:
        print(f'[recalc_all] 开始计算 {scenario} ...')
        try:
            result = engine.run(scenario=scenario, forecast_periods_override=None)
            if not result.success:
                print(f'[recalc_all] {scenario} 计算失败:', result.error)
                continue

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
                    'scenario': result.input_organized.get('选定场景', scenario),
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
            _CALC_RESULTS_MAP[scenario] = response_data
            # 基础情景别名兼容
            if scenario == '基础情景':
                _CALC_RESULTS_MAP['情景0'] = response_data
            elif scenario == '情景0':
                _CALC_RESULTS_MAP['基础情景'] = response_data
            # 最后一个场景同时更新最近一次缓存
            _CALC_CACHE['result'] = response_data
            _CALC_CACHE['scenario'] = scenario
            print(f'[recalc_all] {scenario} 完成 | 新:{len(result.new_business_predict)} 现:{len(result.existing_business_predict)} 汇总:{len(result.combined_summary)}')
        except Exception as e:
            print(f'[recalc_all] {scenario} 异常:', e)
            traceback.print_exc()

    _save_calc_results_map()
    from data_input.views import _save_calc_cache
    _save_calc_cache()
    print('[recalc_all] 多场景缓存已保存。可用情景:', list(_CALC_RESULTS_MAP.keys()))


if __name__ == '__main__':
    main()
