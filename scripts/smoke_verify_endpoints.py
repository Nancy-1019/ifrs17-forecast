"""Smoke test: hit the verify endpoints against the already-loaded cache."""
import os, sys, django

sys.path.insert(0, r'D:\IFRS17预测模型\ifrs17-system')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
django.setup()

from django.test import Client

c = Client()
ok = c.login(username='admin', password='admin123')
print('login:', ok)

# 1) full
r = c.get('/api/verify/full')
print('GET /api/verify/full ->', r.status_code, '| content-type:', r.get('Content-Type'))
try:
    import json
    d = json.loads(r.content)
    sd = d.get('sheetData', {})
    cmp = d.get('comparison', {})
    print('  sheets available:', [k for k, v in sd.items() if isinstance(v, dict) and v.get('available')])
    for k in cmp:
        print('  cmp', k, '-> diffFieldCount=', cmp[k].get('diffFieldCount'), 'totalDiff=', cmp[k].get('totalDiffAmount'))
except Exception as e:
    print('  parse error:', e)

# 2) merged
for sn in ['PAA计算_新业务整理', 'PAA计算_汇总', '输出财务报表_MTD']:
    r = c.get('/api/verify/merged/' + sn)
    print('GET /api/verify/merged/%s ->' % sn, r.status_code, '| rows:', (r.json().get('rows') if r.status_code == 200 else 'ERR'))

# 3) export all
r = c.get('/api/verify/export/all')
data = b''.join(r.streaming_content) if hasattr(r, 'streaming_content') else r.content
print('GET /api/verify/export/all ->', r.status_code, '| bytes:', len(data), '| xlsx header:', data[:2] == b'PK')

# 4) export single sheet
r = c.get('/api/verify/export/sheet/PAA计算_汇总')
data2 = b''.join(r.streaming_content) if hasattr(r, 'streaming_content') else r.content
print('GET /api/verify/export/sheet/PAA计算_汇总 ->', r.status_code, '| bytes:', len(data2), '| xlsx header:', data2[:2] == b'PK')
