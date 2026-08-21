"""验证：计算进行中"切到其他导航页"（前端停止轮询）不会中断后端计算。

证明方式：
1. 启动与 api_calc_run 完全一致的后台 worker 线程；
2. 轮询几次确认处于 running（模拟用户在计算页看进度）；
3. 停止一切轮询一段时间（模拟用户切到别的导航页，前端不再发请求）；
4. 间隔结束后再次查询，确认线程已独立推进到 done，且 /api/calc/results 可取到结果。

结论：后端线程与 HTTP 请求/前端导航完全解耦，切页不可能中断计算。
"""
import os, sys, time, json, threading
ROOT = r'D:\IFRS17预测模型'
sys.path.insert(0, os.path.join(ROOT, 'ifrs17-system'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')

import django
django.setup()

from data_input.excel_validator import validate_upload
import data_input.views as V
from django.test import RequestFactory

ATT = os.path.join(ROOT, '验证文件', 'IFRS17财务预测_改造版_开发.xlsx')
with open(ATT, 'rb') as f:
    data = f.read()
dock = validate_upload(data, 'dock')['sheetData']
excel = validate_upload(data, 'excel')['sheetData']

SC = '基础情景'
FP = 6

# 重置进度
V._CALC_PROGRESS.update({'status': 'idle', 'percent': 0, 'scenario': '', 'error': '', 'finishedAt': None})

print('=== 启动后台 worker 线程（等同 api_calc_run 内部行为）===')
t = threading.Thread(target=V._run_calc_worker, args=(dock, excel, SC, FP), daemon=True)
t.start()

# 1) 模拟用户在「计算页」看了几次进度
seen_running = False
for _ in range(30):
    p = V._snapshot_progress()
    if p['status'] == 'running':
        seen_running = True
    if p['status'] in ('done', 'error'):
        break
    time.sleep(0.1)
print('  切页前: 见过 running =', seen_running, '当前 status =', V._snapshot_progress()['status'])
assert seen_running

# 2) 模拟用户「点其他导航栏选项」——前端完全停止轮询（这里就什么都不发）
print('  模拟切到其他导航页，前端停止轮询 3 秒 ...')
time.sleep(3)

# 3) 切页回来后再次查询（等同前端 resumeCalcProgressIfRunning / 轮询恢复）
p = V._snapshot_progress()
print('  切页回来: status =', p['status'], 'percent =', p['percent'], 'scenario =', p['scenario'])
# 线程此时可能仍在跑，也可能已 done；关键是它一直在独立推进，不依赖前端
assert p['status'] in ('running', 'done'), f'切页期间线程不应被中断, 实际 {p["status"]}'

# 4) 等待线程自然结束（不再轮询，仅 join）
t.join(timeout=180)
final = V._snapshot_progress()
print('  最终: status =', final['status'], 'percent =', final['percent'], 'scenario =', final['scenario'])
assert final['status'] == 'done', f'线程应独立完成, 实际 {final["status"]}'
assert final['scenario'] == SC

# 5) 验证结果已写入缓存（前端回来即可展示，等同 /api/calc/results 返回内容）
cached = V._CALC_CACHE.get('result') or {}
print('  缓存结果: success =', cached.get('success'),
      '新业务行 =', cached.get('summary', {}).get('newBusinessRows'),
      '现有业务行 =', cached.get('summary', {}).get('existingBusinessRows'))
assert cached.get('success') is True
assert cached.get('summary', {}).get('newBusinessRows', 0) > 0

print('\nPASS — 切到其他导航页不会中断后端计算：线程独立推进至 done，结果已就绪可取。')
