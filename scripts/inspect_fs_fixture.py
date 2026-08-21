import json
with open('data_input/fixtures/verify_targets.json', 'r', encoding='utf-8') as f:
    targets = json.load(f)

for sn in ['输出财务报表_MTD', '输出财务报表_YTD']:
    rows = targets.get(sn, [])
    if not rows:
        print(sn, 'empty')
        continue
    headers = list(rows[0].keys())
    print('\n===', sn, 'rows=', len(rows), '===')
    print('headers:', headers[:15], '...')
    date_cols = [h for h in headers if h.startswith('2026') or h.startswith('2027')]
    print('date cols:', date_cols)
    # first row sample
    if rows:
        print('first row keys:', list(rows[0].keys())[:10])
