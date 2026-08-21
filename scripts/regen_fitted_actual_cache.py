import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
import django; django.setup()
from data_input.views import _generate_fitted_actual_cache, _save_actual_cache, _ACTUAL_CACHE, _generate_actual_comparison

# 加载计算结果
with open('data_input/runtime_cache/calc_results_map.json', 'r', encoding='utf-8') as f:
    mp = json.load(f)
calc_result = mp.get('基础情景') or mp.get('情景0')
if not calc_result:
    print('No base scenario found')
    sys.exit(1)

# 先打印当前 comparison 中的投资收益
comparison = _generate_actual_comparison([], [], [], [], period=1, scenario='情景0')
print('Comparison items count:', len(comparison.get('items', [])))
for it in comparison.get('items', []):
    if it.get('item') == '投资收益':
        print('投资收益 expected:', it.get('expected'))

# 重新生成拟合实际数（包含投资收益）
data = _generate_fitted_actual_cache(calc_result, period_idx=1, scenario='情景0')
company_rows = data.get('company', {}).get('rows', [])
for r in company_rows:
    if len(r) > 2 and '投资' in str(r[1]):
        print('Fitted company investment:', r)

# 保存缓存
_save_actual_cache()
print('Cache saved:', _ACTUAL_CACHE.get('fileName'))

# 同时导出为 Excel 上传文件（公司合计 + 精算险类两张工作表）
from openpyxl import Workbook
output_dir = os.path.join(os.path.dirname(__file__), '..', '..', '验证文件')
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, '预实分析_拟合数据.xlsx')
wb = Workbook()
# 公司合计
ws1 = wb.active
ws1.title = '公司合计实际数'
company = _ACTUAL_CACHE['data']['company']
ws1.append(company['headers'])
for r in company['rows']:
    ws1.append(r)
# 精算险类
ws2 = wb.create_sheet('精算险类实际数')
class_data = _ACTUAL_CACHE['data']['class']
ws2.append(class_data['headers'])
for r in class_data['rows']:
    ws2.append(r)
wb.save(output_path)
print('Excel saved:', output_path)
