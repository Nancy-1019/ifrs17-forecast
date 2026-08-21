import os, django, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
django.setup()

from data_input import views as V

cr = V._resolve_calc_result(None)
print("scenario:", cr.get('selectedScenario'))
fs = cr.get('financialStatementsV2Merged') or cr.get('financialStatementsV2') or {}
print("FS keys:", list(fs.keys()))
ytd = fs.get('ytd') or {}
print("YTD keys:", list(ytd.keys()))
if ytd.get('income_statement'):
    print("=== FS YTD income_statement items (period_idx=1) ===")
    for r in ytd['income_statement']:
        vals = r.get('values', [])
        v = vals[1] if len(vals) > 1 else (vals[0] if vals else 0)
        print(f"  {r.get('item'):40s} {v}")

summary = cr.get('combinedSummary') or []
print("\ncombinedSummary rows:", len(summary))
if summary:
    print("combinedSummary sample keys:", sorted(summary[0].keys())[:30])
    # a few sample rows
    for r in summary[:3]:
        print("  sample:", {k: r.get(k) for k in ['精算险类','业务类型','预测间隔','输出_保险合同收入','输出_新增保费减值']})

cm = V._compute_class_metrics(cr, period_idx=1)
print("\n=== _compute_class_metrics (period_idx=1) ===")
for cls, d in sorted(cm.items()):
    print(f"  cls={cls}: {d}")

# ratio map sanity
rm = V._get_input_ratio_map()
print("\n=== ratio_map classes ===")
for k, v in rm.items():
    print(f"  {k}: {len(v)} classes -> sample {list(v.items())[:2]}")
