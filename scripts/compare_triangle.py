# -*- coding: utf-8 -*-
import os, sys, django, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
sys.path.insert(0, os.path.join(ROOT, 'ifrs17-system'))
django.setup()

from paa_engine import PAAEngine
from data_input.views import build_data_json
import vba_faithful as v

PAAEngine._calculate_cashflows_existing  # ensure engine loaded
dock = build_data_json('dock')
excel = build_data_json('excel')
eng = PAAEngine(dock_sheets=dock, excel_sheets=excel)
eng._organize_inputs = None

eval_date = datetime.datetime(2026, 6, 30)
rate_curve = eng._process_interest_rate_curve(eval_date, 1, {})
existing = eng._organize_key_assumptions_existing(eval_date, {})

target = '建工险_直保或分入_现有业务'
g = [x for x in existing if str(x.get('合同组ID','')).startswith(target)][0]
# trigger cache and get system result
cf = eng._calculate_cashflows_existing(g, eval_date, 1, rate_curve, {})
sys_rows = getattr(eng, '_tmp_rows', [])
print('\nSYSTEM triangle sums:')
if sys_rows:
    s2s = lambda col: sum(r.get(col,0) for r in sys_rows)
    print('  AV (br)=', s2s('br'), 'AW (bs)=', s2s('bs'), 'AX (bt)=', s2s('bt'), 'AY (bu)=', s2s('bu'), 'AZ (bv)=', s2s('bv'))
    print('  AC (bw)=', s2s('bw'))
    print('  first 5 rows (a=1):')
    for r in sys_rows[:5]:
        print('  d=', r['d'], 'aw=', r['aw'], 'av=', r.get('av'), 'br=', r['br'], 'al=', r.get('al'))

# Use oracle build_triangle with engine inputs
original = eng._calculate_cashflows_existing.__func__
def patched(self, *args, **kwargs):
    result = original(self, *args, **kwargs)
    self._last_rows = getattr(self, '_tmp_rows', None)
    return result
# easier: rerun with debug print inside? Let's just rebuild here using engine lookups

# Use oracle build_triangle with engine inputs
fl = getattr(eng, '_fl_existing', {})
monthly = lambda s: fl.get(s, {})
PERIOD = 1
act_class = str(g.get('精算险类',''))
biz_type = str(g.get('直保或分入/分出','直保或分入'))
分出 = biz_type == '分出'
预测组 = str(g.get('现有业务预测组','') or g.get('预测组',''))
合同组ID = str(g.get('合同组ID','') or g.get('现有业务预测组ID',''))
eval_write = int(float(g.get('评估期开始业务预期写入时间（月）',0) or 0))
pred_time = eval_date.replace(month=eval_date.month+PERIOD) if eval_date.month+PERIOD<=12 else eval_date.replace(year=eval_date.year+1, month=eval_date.month+PERIOD-12)
from paa_engine.engine import _eomonth
pred_time = _eomonth(eval_date, PERIOD)

def get(d, k, default=0.0):
    if d is None: return default
    v = d.get(k)
    if v is None: return default
    try: return float(v)
    except: return default

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

print('SYSTEM INPUTS for', target)
print('  预测组:', 预测组, '合同组ID:', 合同组ID, 'act_class:', act_class)
print('  应收:', 应收, 'UPR:', UPR, 'pr:', pr, 'mr:', mr, 'int_rate:', int_rate)
print('  prem_mode[1]:', get(prem_mode.get(预测组, {}), 1), 'earn[1]:', get(earn.get(预测组, {}), 1))
print('  dev[1]:', get(dev.get(act_class, {}), 1), 'und[1]:', get(und_incur.get(act_class, {}), 1))

# Oracle inputs for same group
gid = 合同组ID
ka = v.keyassum.get(gid, {})
sp = v.groupsplice.get(gid, {})
oracle_grp = dict(
    预测组ID=gid,
    预测组=sp.get('预测组'),
    现有业务预测组=sp.get('现有业务预测组'),
    合同组名称=ka.get('合同组名称') or sp.get('合同组合名称'),
    精算险类=str(ka.get('精算险类') or sp.get('精算险类')),
    直保或分出=ka.get('直保或分入/分出') or g.get('直保或分入/分出'),
    应收保费=v.get(ka, '应收保费'),
    应付IACF=v.get(ka, '应付IACF'),
    UPR余额=v.get(v.opening.get(ka.get('合同组名称') or sp.get('合同组合名称'), {}), 'UPR余额'),
    评估期写入=v.get(ka, '评估期开始业务预期写入时间（月）'),
)
print('\nORACLE INPUTS')
print('  预测组ID:', oracle_grp['预测组ID'], '预测组:', oracle_grp['预测组'], '合同组名称:', oracle_grp['合同组名称'])
print('  应收:', oracle_grp['应收保费'], 'UPR:', oracle_grp['UPR余额'], 'eval_write:', oracle_grp['评估期写入'])
print('  oracle prem_mode[1]:', v.get(v.prem_mode.get(gid, {}), 1))
print('  oracle earn[1]:', v.get(v.earn.get(gid, {}), 1))
print('  oracle dev[1]:', v.get(v.dev.get(oracle_grp['精算险类'], {}), 1))

# Run oracle triangle
T = v.build_triangle(oracle_grp)
s2 = lambda col: sum(r[col] for r in T['rows'])
print('\nORACLE triangle sums:')
print('  AV (br)=', s2('br'), 'AW (bs)=', s2('bs'), 'AX (bt)=', s2('bt'), 'AY (bu)=', s2('bu'), 'AZ (bv)=', s2('bv'))
print('  AC (bw)=', s2('bw'))

# Print a few rows
print('\nSYSTEM vs ORACLE rows by a,d:')
for a in [1,2,3,4,5,10,20,30]:
    idx = (a-1)*60 + 0  # d=0
    if idx < len(sys_rows):
        rs = sys_rows[idx]; ro = T['rows'][idx]
        print(' a=', a, 'd=0 sys aw=', rs['aw'], 'sys br=', rs['br'], '| oracle aw=', ro['aw'], 'oracle br=', ro['br'])

print('\nprem_mode d=55..60:')
for d in range(55,61):
    print(' d=', d, 'sys prem:', get(prem_mode.get(预测组,{}), d), 'oracle prem:', v.get(v.prem_mode.get(合同组ID,{}), d))

print('\nRows a=1, d=51..59:')
for d in range(51,60):
    idx=d
    rs=sys_rows[idx]; ro=T['rows'][idx]
    print(' d=',d,'sys aw=',rs['aw'],'sys br=',rs['br'],'| oracle aw=',ro['aw'],'oracle br=',ro['br'])

print('\nCumulative AV by accident year (all d in a):')
cs=0.0; co=0.0
for a in range(1,61):
    for d in range(60):
        cs += sys_rows[(a-1)*60+d]['br']
        co += T['rows'][(a-1)*60+d]['br']
    if a in [1,2,3,4,5,10,20,30,40,50,60]:
        print(' a<=', a, 'sys=', cs, 'oracle=', co, 'diff=', co-cs)
