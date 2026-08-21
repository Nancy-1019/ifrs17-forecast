# -*- coding: utf-8 -*-
"""Faithful new-business PAA oracle: reconstruct 3600-row triangle from verification inputs
(identical grid structure to existing-business oracle, but claim base = premium*earn[a]+advance,
 no opening balances), aggregate per PAA计算_新业务预测 formulas, compare to PAA计算_新业务整理 输出_*.
Goal: reach 0 diff across all 41 new-business groups."""
import os, sys, datetime, calendar
from openpyxl import load_workbook

ROOT = "D:/IFRS17预测模型"
VBX = os.path.join(ROOT, "验证文件", "IFRS17财务预测_改造版_0729_VBA.xlsx")
wb = load_workbook(VBX, data_only=True)

def ci(c):
    n = 0
    for ch in c:
        n = n*26 + (ord(ch)-64)
    return n-1

def norm_key(v):
    if isinstance(v, datetime.datetime):
        return str(v.toordinal() - datetime.date(1899,12,30).toordinal())
    return str(v)

def _norm_header(h):
    if h is None: return None
    return "".join(str(h).split())  # drop all whitespace incl. newlines

def table_keyed(sheet, key_col, header_row=1):
    ws = wb[sheet]; rows = list(ws.iter_rows(values_only=True)); hdr = rows[header_row-1]
    hdr = [_norm_header(h) for h in hdr]
    ki = key_col-1 if isinstance(key_col, int) else ci(key_col)
    out = {}
    for r in rows[header_row:]:
        if ki >= len(r) or r[ki] is None: continue
        key = norm_key(r[ki]); d = {}
        for j, v in enumerate(r):
            h = hdr[j]
            if h is not None and j != ki: d[h] = v
        out[key] = d
    return out

def table_keyed_monthcols(sheet, key_col, header_row=1):
    ws = wb[sheet]; rows = list(ws.iter_rows(values_only=True)); hdr = rows[header_row-1]
    hdr = [_norm_header(h) for h in hdr]
    ki = key_col-1 if isinstance(key_col, int) else ci(key_col)
    out = {}
    for r in rows[header_row:]:
        if ki >= len(r) or r[ki] is None: continue
        key = norm_key(r[ki]); d = {}
        for j, v in enumerate(r):
            if j == ki: continue
            h = hdr[j]
            if h is None: continue
            try: m = int(float(h))
            except: continue
            d[m] = v
        out[key] = d
    return out

def get(d, k, default=0.0):
    v = d.get(k)
    if v is None: return default
    try: return float(v)
    except: return default

def gv(v, default=0.0):
    if v is None: return default
    try: return float(v)
    except: return default

# ---------- inputs ----------
keynew = table_keyed("输入整理-合同组关键假设_新业务", key_col=4)   # key=预测组ID
ep_new = table_keyed_monthcols("输入整理-预期赔付率", key_col=5)       # key=预测组
maint_new = table_keyed_monthcols("输入整理-维持费用率", key_col=5)    # key=预测组 (or 险类)
und_incur = table_keyed_monthcols("输入整理-未到期赔付模式", key_col=4) # key=险类
cum = table_keyed_monthcols("输入整理-实际赔付比例_累计", key_col=4)    # key=险类
prem_mode = table_keyed_monthcols("输入整理-保费现金流模式", key_col=4) # key=预测组ID
iacf_mode = table_keyed_monthcols("输入整理-IACF现金流模式", key_col=4)# key=预测组ID
earn = table_keyed_monthcols("输入整理-未到期赚取模式", key_col=4)      # key=预测组ID
riskadj = table_keyed("风险调整比例", key_col=3)                        # key=险类
reins = table_keyed_monthcols("再保人不履约风险", key_col=3)            # key=险类
invest = table_keyed_monthcols("投资成分比例", key_col=3)               # key=预测组
recov_new = table_keyed_monthcols("预期摊回比例_新业务", key_col=3)      # key=险类
io_indir = table_keyed_monthcols("未决间接理赔费用率", key_col=3)        # key=险类

# discount curve
wsr = wb["输入整理-即期利率曲线加工"]; rowsr = list(wsr.iter_rows(values_only=True)); hdr_r = rowsr[0]
ie = hdr_r.index("进展月份") if "进展月份" in hdr_r else ci("E")
ih = hdr_r.index("月度折现因子（期末折现）_预测时点")
ii = hdr_r.index("月度折现因子（期初折现）_预测时点")
disc = {}
for r in rowsr[1:]:
    if r[ie] is None: continue
    try: k = int(float(r[ie]))
    except: continue
    disc[k] = (gv(r[ih]), gv(r[ii]))
# extend discount curve beyond max key by compounding last monthly factor
maxk = max(disc.keys()) if disc else 0
if maxk > 0:
    r_end = disc[maxk][0]/disc[maxk-1][0] if maxk > 1 and disc[maxk-1][0] != 0 else 1.0
    r_begin = disc[maxk][1]/disc[maxk-1][1] if maxk > 1 and disc[maxk-1][1] != 0 else 1.0
    for k in range(maxk+1, 125):
        disc[k] = (disc[k-1][0]*r_end, disc[k-1][1]*r_begin)

EVAL_DATE = wb["基本信息"]["C2"].value
G2 = EVAL_DATE                                   # 评估日
PERIOD = 1                                        # J2 = 预测间隔
PRED_TIME = datetime.datetime(2026,7,31)          # H2 = EOMONTH(EVAL_DATE, PERIOD) ; hardcode matches workbook
H2 = PRED_TIME

def eomonth(dt, months):
    y = dt.year + (dt.month-1+months)//12
    m = (dt.month-1+months)%12 + 1
    return datetime.datetime(y, m, calendar.monthrange(y,m)[1])

# ---------- triangle reconstruction ----------
def build_triangle(grp):
    gid = grp["预测组ID"]; biz = grp["直保或分入/分出"]
    险类 = grp["精算险类"]
    分出 = (biz == "分出")
    premium_income = grp["premium_income"]
    acquisition_cost = grp["acquisition_cost"]
    advance_written_premium = grp["advance_written_premium"]
    expected_writing_period_months = grp["expected_writing_period_months"]
    # For 分出 (ceded) groups, premium_income=0 and the ceded premium sits in acquisition_cost;
    # treat acquisition_cost as the effective premium for both cashflow and claim base, IACF=0.
    effective_premium_income = acquisition_cost if 分出 else premium_income
    pr = get(ep_new.get(grp["预测组"], {}), PERIOD)
    mr = 0.0 if 分出 else get(maint_new.get(grp["预测组"], {}), PERIOD)
    if mr == 0.0 and not 分出:
        mr = get(maint_new.get(险类, {}), PERIOD)   # fallback: key by 险类
    nra_und = get(riskadj.get(险类, {}), "未到期风险调整%")
    nra_inc = get(riskadj.get(险类, {}), "未决风险调整%")
    reins_r = 0.0 if not 分出 else get(reins.get(险类, {}), PERIOD)
    io_indir_r = 0.0 if 分出 else get(io_indir.get(险类, {}), PERIOD)
    recov_r = 0.0 if 分出 else get(recov_new.get(险类, {}), PERIOD)
    invest_r = get(invest.get(grp["预测组"], {}), PERIOD)
    # discount / int rate for the period
    P = get(_intrate, PERIOD) if '_intrate' in globals() else 0.0

    # precompute denom_adv = sum of AG (维持 earn) over rows where AB>H2 (block1, W>=2)
    denom_adv = 0.0
    for a in range(1, 61):
        for d in range(0, 60):
            W = d+1 if a == 1 else None
            AB = eomonth(G2, W) if W is not None else None
            if AB is not None and AB > H2:
                denom_adv += get(earn.get(gid, {}), W)
    # precompute denom_AK per accident block (only block1 has AC<=H2)
    # denom_AK = sum of AI over block1 rows where AD>H2
    denom_AK = 0.0
    for d in range(0, 60):
        AC1 = eomonth(H2, 0)  # a=1
        AD1 = eomonth(H2, d)
        if AD1 > H2:
            denom_AK += get(und_incur.get(险类, {}), d+1) if (d+1) in und_incur.get(险类, {}) else 0.0

    rows = []
    for a in range(1, 61):
        for d in range(0, 60):
            W = d+1 if a == 1 else None
            Z = a
            AA = d
            AC = eomonth(H2, a-1)
            AD = eomonth(AC, d)
            AB = eomonth(G2, W) if W is not None else None
            AH = get(earn.get(gid, {}), a)            # 保费赚取比例_赔付
            AG = get(earn.get(gid, {}), W) if W is not None else 0.0  # 保费赚取比例_维持
            AE_mode = get(prem_mode.get(gid, {}), W) if W is not None else 0.0
            AF_mode = get(iacf_mode.get(gid, {}), W) if W is not None else 0.0
            # Two distinct pattern references in VBA:
            #  * expected-future-claims chain (AR, drives 亏损部分) reads 未到期赔付模式 at index d
            #  * IBNR block (AK = AI/SUMIFS) renormalizes 未到期赔付模式 at index d+1 (matches actual triangle)
            # They never coexist on one row (AR only when AC>H2/a>=2; IBNR only when AC<=H2/a=1).
            ai_idx = d
            AI = get(und_incur.get(险类, {}), ai_idx) if ai_idx in und_incur.get(险类, {}) else 0.0
            ai_ibnr = d+1
            AI_ibnr = get(und_incur.get(险类, {}), ai_ibnr) if ai_ibnr in und_incur.get(险类, {}) else 0.0
            # claim base
            adv = (advance_written_premium*AH/denom_adv) if (PERIOD == 1 and AC > H2 and denom_adv != 0) else 0.0
            CA = effective_premium_income*AH + adv
            # expected claims / maintenance  (CA = earn[a]*(premium_income + advance_written_premium/denom_adv) > 0, so AR/AS/AT positive, matching VBA)
            AR = pr*CA*AI if AC > H2 else 0.0
            CB = premium_income*AG + ((advance_written_premium*AG/denom_adv) if (PERIOD == 1 and AB is not None and AB > H2 and denom_adv != 0) else 0.0)
            AS = CB*mr
            AT = (AR+AS)*nra_und
            # ultimate / paid
            AU = pr*CA if AC <= H2 else 0.0
            al_cum = get(cum.get(险类, {}), PERIOD - a + 1) if (PERIOD - a + 1) >= 1 else 0.0
            AV = AU*al_cum
            AW = AV*io_indir_r
            # IBNR chain
            ak_mode = (AI_ibnr/denom_AK) if (AC <= H2 and AD > H2 and denom_AK != 0) else 0.0
            AX = (AU-AV)*ak_mode if (AC <= H2 and AD > H2) else 0.0
            AY = AX*io_indir_r
            AZ = (AX+AY)*reins_r
            BA = AX*nra_inc
            BB = AY*nra_inc
            BC = AZ*nra_inc
            # discount — three distinct indices (empirically verified):
            #  * future-claims/NRA PV (BF, BH): index d+a-2   (matches 商业三者险 预期未来赔付=1168086198.77 exact)
            #  * IBNR chain PV (BI,BJ,BK,BL,BM,BN): index d-1+a (matches 种植业 已发生未决)
            #  * maint/IACF PV (AN, AO, AB-based): index d-1+a
            midx_claims = d + a - 2
            midx_ibnr = d - 1 + a
            dt_c, di_c = disc.get(midx_claims, (0.0, 0.0))
            dt_i, di_i = disc.get(midx_ibnr, (0.0, 0.0))
            AM_claims = dt_c if AD > H2 else 0.0
            AM_ibnr = dt_i if AD > H2 else 0.0
            AN = dt_i if (AB is not None and AB > H2) else 0.0
            AO = di_i if (AB is not None and AB > H2) else 0.0
            # nominal cashflows & PV
            AP = -effective_premium_income*AE_mode
            AQ = 0.0 if 分出 else -acquisition_cost*AF_mode
            BD = AP*AO
            BE = AQ*AO
            BF = AR*AM_claims
            BG = AS*AN
            # NRA PV must discount claims portion at AM_claims and maintenance
            # portion at AN (they use different indices), so split AT.
            BH = AR*nra_und*AM_claims + AS*nra_und*AN
            BI = AX*AM_ibnr
            BJ = AY*AM_ibnr
            BK = -AZ*AM_ibnr
            BL = BA*AM_ibnr
            BM = BB*AM_ibnr
            BN = -BC*AM_ibnr
            advance_written_premium_val = grp["advance_written_premium"] if (a == 1 and d == 0) else 0.0  # 当期提前初始确认签单保费 (advance written premium), inception cell
            rows.append(dict(a=a, d=d, AC=AC, AD=AD, AB=AB, AH=AH, AG=AG,
                             AI=AI, CA=CA, AR=AR, CB=CB, AS=AS, AT=AT,
                             AU=AU, AV=AV, AW=AW, AK=ak_mode, AX=AX, AY=AY,
                             AZ=AZ, BA=BA, BB=BB, BC=BC,
                             AN=AN, AO=AO, AP=AP, AQ=AQ,
                             BD=BD, BE=BE, BF=BF, BG=BG, BH=BH, BI=BI, BJ=BJ,
                             BK=BK, BL=BL, BM=BM, BN=BN, advance_written_premium=advance_written_premium_val))
    return dict(rows=rows, grp=grp, ctx=dict(pr=pr, mr=mr, nra_und=nra_und, nra_inc=nra_inc,
        reins_r=reins_r, io_indir_r=io_indir_r, recov_r=recov_r, invest_r=invest_r,
        premium_income=premium_income, acquisition_cost=acquisition_cost, advance_written_premium=advance_written_premium))

def aggregate(T):
    rows = T["rows"]; ctx = T["ctx"]
    def s(col): return sum(r[col] for r in rows)
    def siff(col, cond): return sum(r[col] for r in rows if cond(r))
    L = ctx.get("当期确认比例", 1.0/PERIOD)  # placeholder; set below
    # discount/int from period
    P = T["ctx"].get("_P", 0.0009347725)
    biz = T["grp"]["直保或分入/分出"]
    分出 = (biz == "分出")
    # 当期收到保费 / 当期支出IACF : triangle AP/AQ where AB==H2
    AK = -siff("AP", lambda r: r["AB"] is not None and r["AB"] == H2)
    AL = -siff("AQ", lambda r: r["AB"] is not None and r["AB"] == H2)
    # 待摊销
    BD_sum = s("BD"); BE_sum = s("BE")
    AE = -BD_sum + AK*(1+P)      # 待摊销保险收入
    AF = -BE_sum + AL*(1+P)      # 待摊销获取现金流
    AG = AE*ctx["invest_r"]       # 待摊销投资成分
    AM = P*(AK+AL)               # 计息 (J2=1: 期初=0; AJ:AL = 0+AK+AL)
    # 保险收入 = (待摊销投资成分 - 待摊销保险收入) * 当期确认比例  (empirically matches verification)
    L = T["ctx"].get("L", 1.0/24.0)
    AN = (AG - AE)*L
    AO = -AF*ctx.get("M", L)      # 摊销获取 = -待摊销获取 * 获取现金流摊销比例
    AP_inv = -AG*L                 # 投资成分
    AQ = AK+AL+AM+AN+AO+AP_inv     # 期末非亏损
    # expected future  (mirror verification: AR=SUM(BD)-SUM(advance_written_premium); AT/AU/AV = SUM(BF/BG/BH) positive outflows)
    advance_written_premium_sum = s("advance_written_premium")
    AR_future = s("BD") - advance_written_premium_sum   # 预期未来保费现金流入 = PV未来保费 - 提前确认签单保费
    AS_future = s("BE")            # 预期未来IACF (0 for new biz, paid at inception)
    AT_future = s("BF")            # 预期未来赔付 (positive)
    AU_future = s("BG")            # 预期未来维持 (positive)
    AV_future = s("BH")            # 非金融风险调整 (positive)
    AW_future = AR_future+AS_future+AT_future+AU_future+AV_future
    # 亏损部分 / 摊回
    AX_loss = max(AW_future - AQ, 0.0)        # 未到期亏损部分 = MAX(预期未来合计 - 期末非亏损, 0)
    AY_recov = 0.0 if 分出 else -AX_loss*ctx["recov_r"]  # 亏损摊回
    # 现金流_支付
    AZ_pay = -siff("AV", lambda r: r["d"] == PERIOD)   # 累计实际赔款 where AA=J2 (AA = 发展期月度间隔 = d, J2=1 -> d=1)
    BA_pay = -siff("AW", lambda r: r["d"] == PERIOD)
    BB_maint = -siff("AS", lambda r: r["AB"] is not None and r["AB"] == H2)
    BC_pay = AZ_pay   # J2=1: 现金流_支付的赔付 = 累计
    BD_claim = BA_pay # J2=1: 理赔费用 = 间接累计
    # 未决 PV sums
    Y = s("BI"); Z = s("BJ"); AA_r = s("BK"); AB_r = s("BL"); AC_r = s("BM"); AD_r = s("BN")
    # 提转差
    BS = -(Y + BC_pay)              # J2=1: -(Y - 0 + BC)
    BT = -(AB_r)                   # -(AB - 0)
    BU = -(Z + BD_claim)           # -(Z - 0 + BD)
    BV = -(AC_r)                   # -(AC - 0)
    BY = -AM                       # IFIE未到期计息
    BZ = 0.0                       # IFIE已发生未决预期 (J2=1)
    CA_ = 0.0; CB_ = 0.0; CC_ = 0.0
    # outputs
    out = {}
    out["输出_未到期责任负债_非亏损部分"] = AQ
    out["输出_未到期责任负债_亏损部分"] = AX_loss
    out["输出_未到期责任负债_亏损摊回"] = AY_recov
    out["输出_已发生未决赔款负债_预期现金流"] = Y
    out["输出_间接理赔费用负债_预期现金流"] = Z
    out["输出_已发生未决赔款负债_再保人不履约_预期现金流"] = AA_r
    out["输出_已发生未决赔款负债_非金融风险调整"] = AB_r
    out["输出_间接理赔费用负债_非金融风险调整"] = AC_r
    out["输出_已发生未决赔款负债_再保人不履约_非金融风险调整"] = AD_r
    out["输出_保险合同收入"] = -AN
    out["输出_赔付与费用_分解的投资成分"] = -AP_inv
    out["输出_赔付与费用_摊销的保险获取现金流"] = -AO
    out["输出_亏损合同损益"] = -(AX_loss - 0.0)   # 期初亏损=0
    out["输出_亏损摊回损益"] = -(AY_recov - 0.0)
    out["输出_赔付与费用_已发生未决赔款负债提转差_预期现金流"] = BS
    out["输出_赔付与费用_已发生未决赔款负债提转差_非金融风险调整"] = BT
    out["输出_赔付与费用_间接理赔费用提转差_预期现金流"] = BU
    out["输出_赔付与费用_间接理赔费用提转差_非金融风险调整"] = BV
    out["输出_赔付与费用_再保人不履约风险提转差_预期现金流"] = -AA_r   # J2=1: -BJ
    out["输出_赔付与费用_再保人不履约风险提转差_非金融风险调整"] = -AD_r
    out["输出_IFIE_未到期_未到期计息"] = BY
    out["输出_IFIE_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流"] = 0.0  # J2=1
    out["输出_IFIE_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整"] = 0.0
    out["输出_IFIE_已发生未决_间接理赔费用计息与利率变化_预期现金流"] = 0.0
    out["输出_IFIE_已发生未决_间接理赔费用计息与利率变化_非金融风险调整"] = 0.0
    out["输出_现金流_支付的赔付与理赔费用"] = BC_pay + BD_claim
    out["输出_现金流_支付的维持费用"] = BB_maint
    out["输出_现金流_收到的保费"] = AK
    out["输出_现金流_支付的IACF"] = AL
    out["输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流"] = -(Y + BS + BZ)
    out["输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整"] = -(AB_r + BT + CA_)
    out["输出_OCI_已发生未决_间接理赔费用计息与利率变化_预期现金流"] = -(Z + BU + CB_)
    out["输出_OCI_已发生未决_间接理赔费用计息与利率变化_非金融风险调整"] = -(AC_r + BV + CC_)
    # also expose a few intermediate for diagnostics
    out["_diag"] = dict(BD_sum=BD_sum, BE_sum=BE_sum, AE=AE, AF=AF, AG=AG, AK=AK, AL=AL,
                        AM=AM, AN=AN, AO=AO, AP_inv=AP_inv, AQ=AQ, AX=AX_loss, AY=AY_recov,
                        AR_future=AR_future, AS_future=AS_future, AT_future=AT_future,
                        AU_future=AU_future, AV_future=AV_future,
                        AZ_pay=AZ_pay, BA_pay=BA_pay, BB_maint=BB_maint,
                        Y=Y, Z=Z, AB_r=AB_r, AC_r=AC_r,
                        BS=BS, BT=BT, BU=BU, BV=BV,
                        OCI_Y=-(Y+BS+BZ), OCI_AB=-(AB_r+BT+CA_), OCI_Z=-(Z+BU+CB_))
    return out

# ---------- load groups from 新业务整理 ----------
wz = wb["PAA计算_新业务整理"]; rz = list(wz.iter_rows(values_only=True)); hz = rz[0]
def zval(r, name):
    try: i = hz.index(name); return r[i]
    except: return None
zgroups = {}
for r in rz[1:]:
    gid = r[3]   # 合同组ID
    if gid is None: continue
    zgroups[str(gid)] = r

# int rate lookup (当月计息利率) from 即期利率曲线加工 by 评估日 & 预测间隔
_intrate = {}
wsr2 = wb["输入整理-即期利率曲线加工"]; rowsr2 = list(wsr2.iter_rows(values_only=True)); hdr_r2 = rowsr2[0]
jb = hdr_r2.index("进展月份") if "进展月份" in hdr_r2 else ci("E")
jj = hdr_r2.index("月度远期利率_预测时点")
jbdate = hdr_r2.index("评估时点") if "评估时点" in hdr_r2 else ci("B")
for r in rowsr2[1:]:
    if r[jb] is None: continue
    try: k = int(float(r[jb]))
    except: continue
    _intrate[k] = gv(r[jj])

total_diff = 0.0; worst = []; ngrp = 0; maxdiff_grp = None; maxdiff_val = 0.0
for gid, zrow in zgroups.items():
    ngrp += 1
    ka = keynew.get(gid, {})
    险类 = str(ka.get("精算险类") or zval(zrow, "精算险类"))
    预测组 = ka.get("预测组")
    grp = {
        "预测组ID": gid,
        "预测组": 预测组,
        "精算险类": 险类,
        "直保或分入/分出": ka.get("业务类型") or zval(zrow, "直保或分入/分出"),
        "premium_income": get(ka, "保费收入"),
        "acquisition_cost": get(ka, "跟单获取费用（净额结算手续费）") + get(ka, "非跟单获取费用"),
        "advance_written_premium": get(ka, "当期提前初始确认签单保费"),
        "expected_writing_period_months": get(ka, "评估期开始业务预期写入时间（月）"),
    }
    # period params
    L = get(ep_new.get(预测组, {}), PERIOD)  # placeholder; use 当期确认比例 from verification
    # We need 当期确认比例 and 获取现金流摊销比例 from verification prediction; approximate via earn[1]
    L = get(earn.get(gid, {}), 1)  # 当期确认比例 = earn[1]
    M = L
    P = _intrate.get(PERIOD, 0.0009347725)
    T = build_triangle(grp)
    T["ctx"]["L"] = L; T["ctx"]["M"] = M; T["ctx"]["_P"] = P
    out = aggregate(T)
    gdiff = 0.0
    for col in out:
        if col.startswith("_"): continue
        sv = out[col]; vv = zval(zrow, col)
        a = float(sv) if isinstance(sv, (int, float)) else 0.0
        b = float(vv) if isinstance(vv, (int, float)) else 0.0
        d = abs(a-b)
        if d > 0.01:
            total_diff += d; gdiff += d
            worst.append((gid, col, round(a,2), round(b,2), round(d,2)))
    if gdiff > maxdiff_val:
        maxdiff_val = gdiff; maxdiff_grp = (gid, gdiff, out["_diag"])
print(f"\nGroups compared: {ngrp}  Total abs diff (输出_ columns): {total_diff:.2f}")
print("Top 30 mismatches (group, col, mine, verify, absdiff):")
for w in sorted(worst, key=lambda x: -x[4])[:30]:
    print(f"  {w[0]} | {w[1]}: mine={w[2]} ver={w[3]} d={w[4]}")
if maxdiff_grp:
    print(f"\nWorst group: {maxdiff_grp[0]} diff={maxdiff_grp[1]:.2f}")
    for k, v in maxdiff_grp[2].items():
        print(f"    {k}={v}")
    # verify intermediate 预期未来* columns for this group
    zr = zgroups.get(maxdiff_grp[0])
    if zr is not None:
        print("  --- verify 预期未来* / 非亏损 ---")
        for i, h in enumerate(hz):
            if h is not None and ('预期未来' in str(h) or '期末未到期责任负债_非亏损部分' in str(h)):
                print(f"    {h}={zr[i]}")
wb.close()
