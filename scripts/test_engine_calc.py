"""End-to-end: validate attachment (dock+excel) -> PAAEngine.run -> verify existing-business mode tables populate."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'ifrs17-system'))
from data_input.excel_validator import validate_upload
from paa_engine.engine import PAAEngine

ATT = os.path.join(ROOT, '验证文件', 'IFRS17财务预测_改造版_开发.xlsx')
with open(ATT, 'rb') as f:
    data = f.read()

dock = validate_upload(data, 'dock')['sheetData']
excel = validate_upload(data, 'excel')['sheetData']
print(f"dock sheets={len(dock)} excel sheets={len(excel)}")

eng = PAAEngine(dock, excel)
scenarios = eng.get_scenarios()
print(f"scenarios={[s.get('value') for s in scenarios][:5]}")

res = eng.run(scenario='基础情景')
print(f"calc done. success={res.success} error={res.error!r}")
print(f"  new_business_predict rows={len(res.new_business_predict)}")
print(f"  existing_business_predict rows={len(res.existing_business_predict)}")
print(f"  combined_summary rows={len(res.combined_summary)}")
print(f"  financial_statements_v2 keys={list(res.financial_statements_v2.keys())[:6]}")

if res.error:
    print("  ERROR:", res.error)
if not res.success:
    print("  CALC NOT SUCCESSFUL")

# 关键验证：现有业务模式表（预测组 key）是否成功产生数据
if len(res.existing_business_predict) > 0:
    print("  [OK] 现有业务计量有输出 -> 预测组 key 读取生效")
else:
    print("  [WARN] 现有业务计量无输出 -> 需排查 预测组 key 读取")

print("--- last calc logs ---")
for line in res.calc_logs[-8:]:
    print("  ", line)

