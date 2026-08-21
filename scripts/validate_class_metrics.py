import os, django, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
django.setup()
from data_input import views as V

cr = V._resolve_calc_result(None)
fs = cr.get('financialStatementsV2Merged') or cr.get('financialStatementsV2') or {}
ytd = fs.get('ytd') or {}
def fs_val(item):
    for r in ytd.get('income_statement', []):
        if r.get('item') == item:
            v = r.get('values', [])
            return v[1] if len(v) > 1 else (v[0] if v else 0)
    return None

summary = cr.get('combinedSummary') or []
DIRECT_EXP_NOIFIE = V._PAA_DIRECT_EXPENSE_COLS
DIRECT_IFIE = V._PAA_DIRECT_IFIE_COLS

tot_ins_rev = tot_ins_exp = tot_uw = 0.0
per_class = {}
for r in summary:
    cls = str(r.get('精算险类'))
    if r.get('预测间隔') != 1:
        continue
    is_ceded = str(r.get('业务类型','')) == '分出'
    if is_ceded:
        continue  # ignore ceding (negligible in this dataset); reconcile on direct
    d = per_class.setdefault(cls, {'rev':0.0,'exp':0.0,'ifie':0.0})
    d['rev']  += V._to_float(r.get('输出_保险合同收入',0)) + V._to_float(r.get('输出_新增保费减值',0) or 0)
    for c in DIRECT_EXP_NOIFIE:
        d['exp'] += V._to_float(r.get(c,0))   # negative
    for c in DIRECT_IFIE:
        d['ifie'] += V._to_float(r.get(c,0))  # signed

# corrected metrics
agg_rev = agg_exp = agg_uw = 0.0
for cls, d in sorted(per_class.items()):
    ins_rev = d['rev']
    ins_exp = -d['exp']            # positive magnitude (excludes IFIE)
    ifie_cost = -d['ifie']         # treat IFIE as cost (positive)
    uw = ins_rev - ins_exp - ifie_cost
    agg_rev += ins_rev
    agg_exp += ins_exp
    agg_uw  += uw
    # print a few
    if cls in ('301','32','101','37'):
        print(f"  cls={cls}: 保险服务收入={ins_rev:.0f} 保险服务费用={ins_exp:.0f} 承保财务损失={ifie_cost:.0f} 承保利润={uw:.0f}")

print("\n=== SUM over classes (direct only) ===")
print(f"  保险服务收入 sum = {agg_rev:.2f}   (FS company = {fs_val('保险服务收入')})")
print(f"  保险服务费用 sum = {agg_exp:.2f}   (FS company = {fs_val('保险服务费用')})")
print(f"  承保利润   sum = {agg_uw:.2f}   (FS company = {fs_val('承保利润')})")
