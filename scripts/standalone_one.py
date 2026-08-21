# -*- coding: utf-8 -*-
"""用 oracle 逻辑对单个系统组重算，拆解 AV/AW/AX/AY/AZ。"""
import os, sys, django, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
sys.path.insert(0, os.path.join(ROOT, 'ifrs17-system'))
django.setup()

from paa_engine import PAAEngine
from data_input.views import build_data_json
from paa_engine.engine import _eomonth

def _to_int(v):
    try: return int(float(v))
    except: return 0

def _to_float(v):
    try: return float(v)
    except: return 0.0

def get(d, k, default=0.0):
    if d is None: return default
    v = d.get(k)
    if v is None: return default
    try: return float(v)
    except: return default

dock = build_data_json('dock')
excel = build_data_json('excel')
eng = PAAEngine(dock_sheets=dock, excel_sheets=excel)
eng._organize_inputs = None

eval_date = datetime.datetime(2026, 6, 30)
rate_curve = eng._process_interest_rate_curve(eval_date, 1, {})
existing = eng._organize_key_assumptions_existing(eval_date, {})

target = '建工险_直保或分入_现有业务'
g = [x for x in existing if str(x.get('合同组ID','')).startswith(target)][0]
# trigger cache population
eng._calculate_cashflows_existing(g, eval_date, 1, rate_curve, {})

PERIOD = 1
act_class = str(g.get('精算险类',''))
biz_type = str(g.get('直保或分入/分出','直保或分入'))
分出 = biz_type == '分出'
预测组 = str(g.get('现有业务预测组','') or g.get('预测组',''))
合同组ID = str(g.get('合同组ID','') or g.get('现有业务预测组ID',''))
eval_write = _to_int(g.get('评估期开始业务预期写入时间（月）',0))
pred_time = _eomonth(eval_date, PERIOD)

# monthly lookups (reuse engine cached if available)
fl = getattr(eng, '_fl_existing', {})
monthly = lambda s: fl.get(s, {})
ep = monthly('预期赔付率'); recov = monthly('预期摊回比例_现有业务'); invest = monthly('投资成分比例')
prem_mode = monthly('保费现金流模式_现有业务'); iacf_mode = monthly('IACF现金流模式_现有业务')
earn = monthly('未到期赚取模式_现有业务'); maint = monthly('维持费用率')
io_indir = monthly('未到期间接理赔费用率'); io_incur = monthly('未决间接理赔费用率')
reins = monthly('再保人不履约风险'); und_incur = monthly('未到期赔付模式')
dev = monthly('未决赔付模式'); cum = monthly('实际赔付比例')
riskadj = fl.get('riskadj', {})
ea = fl.get('ea_existing', {})
op = fl.get('opening', {})
intrate = fl.get('intrate', {})

pr = get(ep.get(预测组, {}), PERIOD)
mr = 0.0 if 分出 else get(maint.get(act_class, {}), PERIOD)
nra_und = get(riskadj.get(act_class, {}), '未到期风险调整%')
nra_inc = get(riskadj.get(act_class, {}), '未决风险调整%')
reins_r = get(reins.get(act_class, {}), PERIOD) if 分出 else 0.0
io_indir_r = 0.0 if 分出 else get(io_indir.get(act_class, {}), PERIOD)
io_incur_r = 0.0 if 分出 else get(io_incur.get(act_class, {}), PERIOD)
recov_r = 0.0 if 分出 else get(recov.get(预测组, {}), PERIOD)
invest_r = get(invest.get(预测组, {}), PERIOD)
int_rate = get(intrate.get(预测组, {}), PERIOD)
ea_row = ea.get(合同组ID, {})
应收 = get(ea_row, '应收保费')
应付IACF = get(ea_row, '应付IACF')
op_row = op.get(预测组, {})
UPR = get(op_row, 'UPR余额')
open_X = get(op_row, '已发生未决赔款负债_预期现金流')
open_不含利净 = get(op_row, '未到期责任负债_非亏损部分_不含利净口径未赚')
open_待摊销保险收入 = get(op_row, '待摊销保险收入')
open_待摊销获取现金流 = get(op_row, '待摊销获取现金流')
open_待摊销投资成分 = get(op_row, '待摊销投资成分')
open_非亏损 = get(op_row, '未到期责任负债_非亏损部分')
open_亏损部分 = get(op_row, '未到期责任负债_亏损部分')
open_亏损摊回 = get(op_row, '未到期责任负债_亏损摊回')

print('inputs:', 'act_class', act_class, '应收', 应收, 'UPR', UPR, 'pr', pr, 'int_rate', int_rate)
print('prem_mode keys sample:', list(prem_mode.get(预测组, {}).keys())[:5])

def ap_val(a, d):
    return get(und_incur.get(act_class, {}), d + 1 - eval_write)

denom_by_a = {}
for a in range(1, 61):
    tot = 0.0
    for d in range(0, 60):
        if (a + d) > 1:
            tot += ap_val(a, d)
    denom_by_a[a] = tot

rows = []
for a in range(1, 61):
    for d in range(0, 60):
        AD = (d + 1) if a == 1 else None
        AE = d if a == 1 else None
        AJ = _eomonth(eval_date, a)
        AK = _eomonth(AJ, d)
        al = get(prem_mode.get(预测组, {}), AD) if AD is not None else 0.0
        am = get(iacf_mode.get(预测组, {}), AD) if AD is not None else 0.0
        an = get(earn.get(预测组, {}), AD) if AD is not None else 0.0
        ao = get(earn.get(预测组, {}), a)
        ap = ap_val(a, d)
        aq = get(dev.get(act_class, {}), d + 1) if AE is not None else 0.0
        denom = denom_by_a[a]
        ar = ap / denom if denom else 0.0
        as_p = PERIOD - a + 1
        as_val = get(cum.get(act_class, {}), as_p) if (AJ <= pred_time and as_p >= 1) else 0.0
        # Excel uses discount index = AH - J + AG = (d+1 if a==1) - eval_write + d
        # Generalizing: for any a, AG=d and AH is only set for a==1. But formula uses AH always?
        # From Excel: AT/AU/AV all use $AH2-$J$2+$AG2. For a>1, AH is blank. In VBA this likely means AD(d+1)?
        # Let's test the hypothesis for a==1 first: idx = (d+1) - eval_write + d = 2d + 1 - eval_write
        AH_for_idx = (d + 1) if a == 1 else a  # guess for a>1
        disc_idx = AH_for_idx - eval_write + d
        disc_t = rate_curve['discount_factor_end'].get(disc_idx, 0.0)
        disc_i = rate_curve['discount_factor_begin'].get(disc_idx, 0.0)
        at = 0.0 if (AK <= pred_time) else disc_t
        AI = _eomonth(eval_date, AD) if AD is not None else None
        au = 0.0 if (AI is None or AI <= pred_time) else disc_t
        av = 0.0 if (AI is None or AI <= pred_time) else disc_i
        aw = -应收 * al
        ax = -应付IACF * am
        ay = (UPR * pr * ao * ap) if (AJ > pred_time) else 0.0
        az = UPR * mr * an
        ba = (ay + az) * nra_und
        bb = open_X * aq
        bh = (UPR * pr * ao) if (AJ <= pred_time) else 0.0
        bi = bh * as_val
        bj = bi * io_incur_r
        bk = ((bh - bi) * ar) if ((AJ <= pred_time) and (AK > pred_time)) else 0.0
        bl = (bb + bk) if ((AJ <= pred_time) and (AK > pred_time)) else 0.0
        bm = bl * io_incur_r
        bn = (bl + bm) * reins_r
        bo = bl * nra_inc
        bp = bm * nra_inc
        bq = bn * nra_inc
        br = aw * av
        bs = ax * av
        bt = ay * at
        bu = az * au
        bv = ba * at
        rows.append(dict(br=br, bs=bs, bt=bt, bu=bu, bv=bv, aw=aw, al=al, av=av, AI=AI))

def s(col): return sum(r[col] for r in rows)
print('AV=', s('br'), 'AW=', s('bs'), 'AX=', s('bt'), 'AY=', s('bu'), 'AZ=', s('bv'))
print('sum_aw (no disc)=', sum(r['aw'] for r in rows))
print('aw sample (a=1):', [rows[d]['aw'] for d in range(5)])
print('al sample (a=1):', [rows[d]['al'] for d in range(5)])
print('av sample (a=1):', [rows[d]['av'] for d in range(5)])
print('AI sample (a=1):', [rows[d]['AI'] for d in range(5)])
