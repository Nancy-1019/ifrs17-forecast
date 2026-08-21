import os, django, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
django.setup()
from data_input import views as V

# load actual cache (mutates V._ACTUAL_CACHE in place)
V._load_actual_cache()
cache = V._ACTUAL_CACHE['data']
company = cache.get('company', {})
class_data = cache.get('class', {})
print("company rows:", len(company.get('rows', [])), "class rows:", len(class_data.get('rows', [])))

comp = V._generate_actual_comparison(
    company.get('rows', []), company.get('headers', []),
    class_data.get('rows', []), class_data.get('headers', []),
)
print("\n=== Company items (10 metrics) ===")
for it in comp['items']:
    print(f"  {it['item']:16s} expected={it['expected']:>16.2f} actual={it['actual']:>16.2f} ratio={it['rate']:>7.1f} hasActual={it['hasActual']}")

cc = comp['classComparison']
print("\n=== Class comparison ===")
print("  metrics:", cc.get('metrics'))
print("  available:", cc.get('available'), "classes:", cc.get('classes'))
# show a few rows for one class
rows_by_class = {}
for r in cc.get('rows', []):
    rows_by_class.setdefault(r['classCode'], []).append(r)
for cls in list(rows_by_class)[:2]:
    print(f"  --- class {cls} ({rows_by_class[cls][0]['className']}) ---")
    for r in rows_by_class[cls]:
        print(f"      {r['metric']:14s} expected={r['expected']:>15.2f} actual={r['actual']:>15.2f} isRatio={r['isRatio']} hasActual={r['hasActual']}")
