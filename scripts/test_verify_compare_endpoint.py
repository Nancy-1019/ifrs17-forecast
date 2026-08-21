"""端到端验证 HTTP 端点：api_verify_compare 与 api_verify_full?periods=。

流程：
1. 用附件构造验证文件 sheet_data（list-of-lists，与真实上传一致）
2. 跑引擎得到真实 calc（含 24 个月财务报表）
3. 用 RequestFactory 调用 api_verify_compare / api_verify_full，验证筛选生效
"""
import os, sys, json

ROOT = r'D:\IFRS17预测模型'
sys.path.insert(0, os.path.join(ROOT, 'ifrs17-system'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')

import django
django.setup()

from django.test import RequestFactory
from data_input import views as V
from data_input.excel_validator import validate_upload
from paa_engine.engine import PAAEngine

ATT = os.path.join(ROOT, '验证文件', 'IFRS17财务预测_改造版_开发.xlsx')
with open(ATT, 'rb') as f:
    data = f.read()
dock = validate_upload(data, 'dock')['sheetData']
excel = validate_upload(data, 'excel')['sheetData']
eng = PAAEngine(dock, excel)
res = eng.run(scenario='基础情景', forecast_periods_override=24)
assert res.success, '引擎需执行成功'
# 复刻 api_calc_run 的 response_data（dict），使 _CALC_CACHE['result'] 与真实流程一致
response_data = {
    'success': res.success,
    'error': getattr(res, 'error', '') or '',
    'selectedScenario': '基础情景',
    'newBusinessPredict': res.new_business_predict,
    'existingBusinessPredict': res.existing_business_predict,
    'combinedSummary': res.combined_summary,
    'financialStatements': res.financial_statements,
    'financialStatementsV2': res.financial_statements_v2,
    'summary': {
        'newBusinessRows': len(res.new_business_predict),
        'existingBusinessRows': len(res.existing_business_predict),
        'combinedSummaryRows': len(res.combined_summary),
        'financialStatementRows': len(res.financial_statements),
    },
}
print('引擎执行 success, 财务报表 dates=', len((response_data['financialStatementsV2'] or {}).get('dates', [])))
V._CALC_CACHE['result'] = response_data

# 构造验证文件 sheet_data（list-of-lists，与真实上传一致）
FT = os.path.join(ROOT, 'ifrs17-system', 'data_input', 'fixtures', 'verify_targets.json')
sheets = json.load(open(FT, encoding='utf-8')).get('sheets', {})
sheet_data = {}
for sn, rows in sheets.items():
    if not rows:
        continue
    headers = list(rows[0].keys())
    list_rows = [[r.get(h) for h in headers] for r in rows]
    sheet_data[sn] = {'available': True, 'headers': headers, 'rows': list_rows, 'totalRows': len(rows)}
V._VERIFY_CACHE['sheet_data'] = sheet_data

rf = RequestFactory()

# login_required 装饰器需要 request.user；用匿名可认证伪用户绕过
class _FakeUser:
    is_authenticated = True
    is_active = True
    is_anonymous = False

def auth(req):
    req.user = _FakeUser()
    return req

def period_cols(cmp):
    return [h for h in cmp.get('headers', []) if V._is_period_header(h)]

# --- 端点 1：api_verify_compare（无筛选）---
req = auth(rf.get('/api/verify/compare'))
r = V.api_verify_compare(req)
body = json.loads(r.content)
print('\n[compare] 无筛选: success=', body['success'], 'availablePeriods=', len(body['availablePeriods']))
cmp_all = body['comparison']
mtd_all_cols = period_cols(cmp_all['输出财务报表_MTD'])
print('  输出财务报表_MTD 全部时点列:', mtd_all_cols)
assert body['success']
assert body['availablePeriods']

# --- 端点 2：api_verify_compare 筛选 2026-07-31 ---
req2 = auth(rf.get('/api/verify/compare?periods=2026-07-31'))
r2 = V.api_verify_compare(req2)
body2 = json.loads(r2.content)
cmp_f1 = body2['comparison']
mtd_f1_cols = period_cols(cmp_f1['输出财务报表_MTD'])
print('\n[compare] 筛选 2026-07-31: 输出财务报表_MTD 时点列:', mtd_f1_cols)
assert mtd_f1_cols == ['2026-07-31'], f'期望仅 2026-07-31，实际 {mtd_f1_cols}'
# 行维度表（PAA计算_新业务整理）行数应减半（仅 2026-07-31）
print('  PAA计算_新业务整理 全部行=', cmp_all['PAA计算_新业务整理']['systemRows'],
      ' 筛选后行=', cmp_f1['PAA计算_新业务整理']['systemRows'])

# --- 端点 3：api_verify_full?periods= ---
req3 = auth(rf.get('/api/verify/full?periods=2026-07-31,2026-08-31'))
r3 = V.api_verify_full(req3)
body3 = json.loads(r3.content)
print('\n[full] 筛选 2 期: availablePeriods=', len(body3.get('availablePeriods', [])),
      '输出财务报表_MTD 时点列:', period_cols(body3['comparison']['输出财务报表_MTD']))
assert period_cols(body3['comparison']['输出财务报表_MTD']) == ['2026-07-31', '2026-08-31']

print('\n所有端点断言通过 ✅')
