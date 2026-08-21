import os, django, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
django.setup()
from data_input import views as V

cr = V._resolve_calc_result(None)
summary = cr.get('combinedSummary') or []
cols = (V._PAA_DIRECT_REVENUE_COLS + V._PAA_DIRECT_EXPENSE_COLS + V._PAA_DIRECT_IFIE_COLS
        + V._PAA_CEDING_ALLOC_COLS + V._PAA_CEDING_RECOVER_COLS + V._PAA_CEDING_IFIE_COLS)

# cls=301 period 1, direct + ceded raw sums
def agg(cls, bt_filter):
    d = {c: 0.0 for c in cols}
    n = 0
    for r in summary:
        if str(r.get('精算险类')) != cls:
            continue
        if r.get('预测间隔') != 1:
            continue
        if bt_filter is not None and str(r.get('业务类型','')) == ('分出' if not bt_filter else '直保或分入' if bt_filter else ''):
            pass
        # bt_filter: True=direct, False=ceded, None=both
        is_ceded = str(r.get('业务类型','')) == '分出'
        if bt_filter is True and is_ceded:
            continue
        if bt_filter is False and not is_ceded:
            continue
        n += 1
        for c in cols:
            d[c] += V._to_float(r.get(c, 0))
    return d, n

for cls in ['301','32']:
    print(f"\n===== cls={cls} 预测间隔=1 =====")
    for bt, label in [(True,'DIRECT'),(False,'CEDED'),(None,'ALL')]:
        d, n = agg(cls, bt)
        print(f"  [{label}] rows={n}")
        for c in cols:
            if abs(d[c]) > 1e-6:
                print(f"      {c:50s} {d[c]:.2f}")
