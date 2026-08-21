# -*- coding: utf-8 -*-
"""把 0729 上传数据灌入 SheetData，运行 PAA 引擎，落盘计算结果缓存。
等价 HTTP：上传(手工输入表_上传数据_0729.xlsx / 系统对接输入表_上传数据_0729.xlsx) + 点开始计算。
"""
import os, sys, json, django
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.db import transaction
from data_input.excel_validator import validate_upload
from data_input.models import SheetData, UploadRecord
from paa_engine import PAAEngine
from data_input.views import _CALC_CACHE, _save_calc_cache, _serialize_row

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.path.join(ROOT, '验证文件')
FILES = [
    ('excel', '手工输入表_上传数据_0729.xlsx'),
    ('dock', '系统对接输入表_上传数据_0729.xlsx'),
]

def load_source(source, fn):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    path = os.path.join(BASE, fn)
    with open(path, 'rb') as f:
        raw = f.read()
    res = validate_upload(raw, source)  # eval_date=None -> 保留全部行
    sheets = res.get('sheetData', {})
    warns = res.get('warnings', [])
    errs = res.get('errors', [])
    admin = User.objects.filter(is_superuser=True).first()
    with transaction.atomic():
        SheetData.objects.filter(source=source, is_active=True).update(is_active=False)
        rec = UploadRecord.objects.create(
            source=source, file_name=fn, upload_user=admin,
            sheet_count=len(sheets),
            total_rows=sum(len(s.get('rows', [])) for s in sheets.values()),
            validation_passed=res['success'],
            validation_errors=errs, validation_warnings=warns,
            validation_detail=res.get('sheetResults', {}),
        )
        for sn, info in sheets.items():
            SheetData.objects.create(
                source=source, sheet_name=sn,
                headers=info.get('headers', []), rows=info.get('rows', []),
                row_count=len(info.get('rows', [])),
                display_cols=info.get('displayCols', len(info.get('headers', []))),
                upload_record=rec, is_active=True,
            )
    print(f'[{source}] 载入 {len(sheets)} 张表 | errors={len(errs)} warnings={len(warns)}')
    for w in warns[:20]:
        print('   WARN:', w)
    return sheets

for source, fn in FILES:
    load_source(source, fn)

# 运行计算
from data_input.views import build_data_json
dock_data = build_data_json('dock')
excel_data = build_data_json('excel')
engine = PAAEngine(dock_sheets=dock_data, excel_sheets=excel_data)
result = engine.run(scenario='基础情景', forecast_periods_override=None)
print('calc success:', result.success, '| error:', result.error)

response_data = {
    'success': result.success, 'error': result.error,
    'selectedScenario': result.selected_scenario, 'scenarios': result.scenarios,
    'calcLogs': result.calc_logs,
    'inputOrganized': {'newBusiness': [_serialize_row(r) for r in result.input_organized.get('新业务假设', [])],
                       'existingBusiness': [_serialize_row(r) for r in result.input_organized.get('现有业务假设', [])],
                       'rateCurve': result.input_organized.get('利率曲线', {}),
                       'scenario': result.input_organized.get('选定场景', '基础情景'),
                       'evalDate': result.input_organized.get('评估时点', ''),
                       'forecastPeriods': result.input_organized.get('预测期数', 0)},
    'newBusinessPredict': [_serialize_row(r) for r in result.new_business_predict],
    'existingBusinessPredict': [_serialize_row(r) for r in result.existing_business_predict],
    'combinedSummary': [_serialize_row(r) for r in result.combined_summary],
    'financialStatements': [_serialize_row(r) for r in result.financial_statements],
    'financialStatementsV2': result.financial_statements_v2,
    'summary': {'newBusinessRows': len(result.new_business_predict),
                'existingBusinessRows': len(result.existing_business_predict),
                'combinedSummaryRows': len(result.combined_summary),
                'financialStatementRows': len(result.financial_statements)},
}
_CALC_CACHE['result'] = response_data
_CALC_CACHE['scenario'] = '基础情景'
_CALC_CACHE['timestamp'] = datetime.now().isoformat()
_save_calc_cache()
print('cache saved. combined=%d new=%d existing=%d' % (
    len(result.combined_summary), len(result.new_business_predict), len(result.existing_business_predict)))

# ---- 打印列头对照，用于建立映射 ----
def dump(title, rows):
    if not rows:
        print(f'\n[{title}] EMPTY')
        return
    print(f'\n[{title}] rows={len(rows)}')
    print('  cols:', list(rows[0].keys()))

dump('combinedSummary', response_data['combinedSummary'])
dump('existingBusinessPredict(period1)', [r for r in response_data['existingBusinessPredict'] if r.get('预测间隔') == 1])
dump('newBusinessPredict(period1)', [r for r in response_data['newBusinessPredict'] if r.get('预测间隔') == 1])

# 验证文件列头
import openpyxl
vp = os.path.join(BASE, 'IFRS17财务预测_改造版_0729_VBA.xlsx')
wb = openpyxl.load_workbook(vp, data_only=True)
for sname in ['PAA计算_汇总', 'PAA计算_现有业务整理', 'PAA计算_新业务整理', '输出财务报表_MTD', '输出财务报表_YTD']:
    ws = wb[sname]
    hdr = [c for c in next(ws.iter_rows(values_only=True)) if c is not None]
    print(f'\n[VERIFY {sname}] cols={len(hdr)}')
    print('  cols:', hdr)
wb.close()
