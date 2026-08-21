import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
import django
django.setup()

cache_path = 'data_input/runtime_cache/verify_cache.json'
with open(cache_path, 'r', encoding='utf-8') as f:
    cache = json.load(f)

print('Keys:', list(cache.keys()))
comparison = cache.get('comparison', {})
print('Sheets:', list(comparison.keys()))
for sheet, cmp in comparison.items():
    print('\n===', sheet, '===')
    print('summary:', cmp.get('summary', {}))
    print('diffFieldCount:', cmp.get('diffFieldCount'))
    print('totalDiffAmount:', cmp.get('totalDiffAmount'))
    print('fieldDiffs count:', len(cmp.get('fieldDiffs', [])))
    # print first few field diffs
    for fd in (cmp.get('fieldDiffs') or [])[:5]:
        print('  ', fd)
