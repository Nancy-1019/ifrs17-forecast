"""以 admin 身份在运行中的服务上跑一次计算并上传预实示例，落盘缓存，供 viewer 查看 demo 数据。"""
import os, sys, json, urllib.request, urllib.parse, http.cookiejar

BASE = 'http://localhost:8000'

# 1) 生成预实示例文件（若不存在）
gen = os.path.join(os.path.dirname(__file__), 'generate_actual_test_data.py')
if not os.path.exists('验证文件/预实分析_实际数据_示例.xlsx'):
    import runpy
    runpy.run_path(gen, run_name='__main__')

# 2) 登录 admin
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def get(url):
    return opener.open(url).read().decode('utf-8', 'ignore')

login_html = get(BASE + '/login/')
import re
m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', login_html)
csrf = m.group(1) if m else ''

data = urllib.parse.urlencode({
    'csrfmiddlewaretoken': csrf,
    'username': 'admin',
    'password': 'admin123',
    'next': '/',
}).encode()
req = urllib.request.Request(BASE + '/login/', data=data, method='POST')
opener.open(req)

# 3) 触发计算
calc_body = json.dumps({'scenario': '情景0', 'forecast_periods': 12}).encode()
req = urllib.request.Request(BASE + '/api/calc/run', data=calc_body, method='POST',
                             headers={'Content-Type': 'application/json'})
try:
    resp = opener.open(req).read().decode('utf-8', 'ignore')
    rj = json.loads(resp)
    print('CALC success:', rj.get('success'), '| selectedScenario:', rj.get('selectedScenario'),
          '| fsV2 dates:', bool(rj.get('financialStatementsV2', {}).get('dates')) if rj.get('success') else None)
except Exception as e:
    print('CALC ERROR:', e)

# 4) 上传预实示例
actual_path = '验证文件/预实分析_实际数据_示例.xlsx'
with open(actual_path, 'rb') as f:
    raw = f.read()
req = urllib.request.Request(BASE + '/api/upload/actual', data=raw, method='POST',
                             headers={'Content-Type': 'application/octet-stream',
                                      'X-File-Name': urllib.parse.quote('预实分析_实际数据_示例.xlsx')})
try:
    resp = opener.open(req).read().decode('utf-8', 'ignore')
    rj = json.loads(resp)
    print('ACTUAL success:', rj.get('success'), '| fileName:', rj.get('fileName'),
          '| classComp available:', (rj.get('comparison', {}).get('classComparison', {}).get('available') if rj.get('success') else None))
except Exception as e:
    print('ACTUAL ERROR:', e)
