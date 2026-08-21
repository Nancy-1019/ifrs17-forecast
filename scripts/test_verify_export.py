#!/usr/bin/env python
"""验证验证核对展示/导出接口：上传验证文件 -> 测试 full/merged/export 接口。
同时把验证缓存写回 runtime_cache/verify_cache.json，供重启后的服务器直接展示。"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
import django
django.setup()

from django.test import Client

VERIFY_PATH = sys.argv[1] if len(sys.argv) > 1 else r'D:\IFRS17预测模型\验证文件\IFRS17财务预测_改造版_0729_VBA.xlsx'
OUT_DIR = r'D:\IFRS17预测模型\验证文件\test_export'
os.makedirs(OUT_DIR, exist_ok=True)

c = Client()
print('login:', c.login(username='admin', password='admin123'))

with open(VERIFY_PATH, 'rb') as f:
    body = f.read()
resp = c.post('/api/upload/verify', data=body,
             HTTP_X_FILE_NAME=os.path.basename(VERIFY_PATH),
             content_type='application/octet-stream')
j = resp.json()
print('upload:', resp.status_code, 'success=', j.get('success'),
      'sheets=', list((j.get('sheetData') or {}).keys()))

resp = c.get('/api/verify/full')
fj = resp.json()
print('full:', resp.status_code, 'loaded=', fj.get('loaded'), 'fileName=', fj.get('fileName'))

sheets = ['PAA计算_新业务整理', 'PAA计算_现有业务整理', 'PAA计算_汇总', 'PAA计算_MTD', '输出财务报表_MTD', '输出财务报表_YTD']
for sn in sheets:
    r = c.get('/api/verify/merged/' + sn)
    if r.status_code == 200:
        d = r.json()
        sysn = sum(1 for row in d.get('rows', []) if any(row.get(f + '__系统') is not None for f in d.get('numeric_headers', [])))
        print('merged %s: rows=%d numeric=%d systemRows=%d' % (sn, len(d.get('rows', [])), len(d.get('numeric_headers', [])), sysn))
    else:
        print('merged %s: ERR' % sn, r.status_code, r.json())

# 导出全部
r = c.get('/api/verify/export/all')
all_bytes = b''.join(r.streaming_content)
print('export/all:', r.status_code, r.get('Content-Type'), 'bytes=', len(all_bytes))
open(os.path.join(OUT_DIR, '验证核对完整结果.xlsx'), 'wb').write(all_bytes)

# 导出单表
for sn in ['PAA计算_汇总', 'PAA计算_MTD', '输出财务报表_MTD', 'PAA计算_新业务整理']:
    r = c.get('/api/verify/export/sheet/' + sn)
    b = b''.join(r.streaming_content)
    print('export/sheet %s:' % sn, r.status_code, 'bytes=', len(b))
    open(os.path.join(OUT_DIR, '验证核对_%s.xlsx' % sn), 'wb').write(b)

print('DONE. 验证缓存已写回 runtime_cache/verify_cache.json')
