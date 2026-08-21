"""验证财务报表输出月份数与预测期数一致（24个月）。"""
import os
import sys
import django

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IFRS = os.path.join(ROOT, 'ifrs17-system')
sys.path.insert(0, IFRS)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
django.setup()

from data_input.excel_validator import validate_upload
from paa_engine.engine import PAAEngine
from data_input.views import _build_system_verify_rows

ATT = os.path.join(ROOT, '验证文件', 'IFRS17财务预测_改造版_开发.xlsx')
with open(ATT, 'rb') as f:
    data = f.read()

dock = validate_upload(data, 'dock')['sheetData']
excel = validate_upload(data, 'excel')['sheetData']
print(f'dock sheets={len(dock)} excel sheets={len(excel)}')

eng = PAAEngine(dock, excel)
res = eng.run(scenario='基础情景', forecast_periods_override=24)
print(f'calc success={res.success} error={res.error!r}')

fs = res.financial_statements_v2
print(f'engine dates count={len(fs.get("dates", []))}')
print(f'engine dates first 5={fs.get("dates", [])[:5]}')
print(f'engine dates last 3={fs.get("dates", [])[-3:]}')

# 模拟 API 缓存结构
calc = {
    'success': res.success,
    'newBusinessPredict': res.new_business_predict,
    'existingBusinessPredict': res.existing_business_predict,
    'combinedSummary': res.combined_summary,
    'financialStatementsV2': res.financial_statements_v2,
}
sys_rows = _build_system_verify_rows(calc)
for sn in ['输出财务报表_MTD', '输出财务报表_YTD']:
    rows = sys_rows.get(sn) or []
    if not rows:
        print(f'{sn}: EMPTY')
        continue
    headers = list(rows[0].keys())
    date_cols = [h for h in headers if h != '科目']
    print(f'{sn}: rows={len(rows)} date cols={len(date_cols)} first 5={date_cols[:5]} last 3={date_cols[-3:]}')

# 检查是否包含24个预测月末（含评估时点共25列）
for sn in ['输出财务报表_MTD', '输出财务报表_YTD']:
    rows = sys_rows.get(sn) or []
    date_cols = [h for h in list(rows[0].keys()) if h != '科目'] if rows else []
    assert len(date_cols) == 25, f'{sn} expected 25 date cols, got {len(date_cols)}'
    print(f'[PASS] {sn} has 25 date columns')
