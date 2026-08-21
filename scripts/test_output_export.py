"""Test the new /api/output/export endpoint."""
import os, sys, django
sys.path.insert(0, r'D:\IFRS17预测模型\ifrs17-system')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
django.setup()

from django.test import Client

c = Client()
print('login:', c.login(username='admin', password='admin123'))

r = c.get('/api/output/export')
data = b''.join(r.streaming_content) if hasattr(r, 'streaming_content') else r.content
print('GET /api/output/export ->', r.status_code, '| bytes:', len(data), '| xlsx header:', data[:2] == b'PK')
if r.status_code == 200:
    open(r'D:\IFRS17预测模型\验证文件\test_export\计量结果输出_系统结果.xlsx', 'wb').write(data)
