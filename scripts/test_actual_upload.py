"""测试预实分析实际数据上传 + 分险类对比逻辑"""
import os, sys, django

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
django.setup()

from django.test import Client
from django.contrib.auth.models import User

# 准备测试用户
user, _ = User.objects.get_or_create(
    username='testadmin',
    defaults={'is_staff': True, 'is_superuser': True}
)
user.set_password('test123')
user.save()

c = Client()
c.login(username='testadmin', password='test123')

file_path = '验证文件/预实分析_实际数据_示例.xlsx'
with open(file_path, 'rb') as f:
    data = f.read()

resp = c.post(
    '/api/upload/actual',
    data=data,
    content_type='application/octet-stream',
    HTTP_X_FILE_NAME='%E9%A2%84%E5%AE%9E%E5%88%86%E6%9E%90_%E5%AE%9E%E9%99%85%E6%95%B0%E6%8D%AE_%E7%A4%BA%E4%BE%8B.xlsx'
)

import json
result = json.loads(resp.content)
print('HTTP status:', resp.status_code)
print('success:', result.get('success'))
print('error:', result.get('error'))
print('companySheet:', result.get('companySheet'))
print('classSheet:', result.get('classSheet'))
print('companyRows:', result.get('companyRows'))
print('classRows:', result.get('classRows'))
print('companyHeaders:', result.get('companyHeaders'))
print('classHeaders:', result.get('classHeaders'))

cc = result.get('comparison', {}).get('classComparison', {})
print('\n=== classComparison ===')
print('available:', cc.get('available'))
print('error:', cc.get('error'))
print('metrics:', cc.get('metrics'))
print('row count:', len(cc.get('rows', [])))
for r in cc.get('rows', [])[:6]:
    print('  ', r)

print('\n=== company items (overview) ===')
for it in result.get('comparison', {}).get('items', [])[:6]:
    print('  ', it)
