# -*- coding: utf-8 -*-
"""Faithful port of existing-business PAA: reconstruct 3600-row triangle from verification inputs,
aggregate per PAA计算_现有业务预测 formulas, compare to PAA计算_现有业务整理 输出_* columns.
Replicates the decoded Excel formulas exactly (ground truth from fml_triangle1.txt / fml_forecast1.txt)."""
import os, sys, datetime, calendar
from openpyxl import load_workbook

ROOT="D:/IFRS17预测模型"
VBX=os.path.join(ROOT,"验证文件","IFRS17财务预测_改造版_0729_VBA.xlsx")
wb=load_workbook(VBX,data_only=True)

def ci(c):  # column letter -> 0-based index
    n=0
    for ch in c: n=n*26+(ord(ch)-64)
    return n-1

# ---------- generic readers ----------
def norm_key(v):
    # some tables store 险类 codes as Excel dates in the key column; normalize to serial string
    if isinstance(v, datetime.datetime):
        return str(v.toordinal() - datetime.date(1899,12,30).toordinal())
    return str(v)
def table_keyed(sheet, key_col, header_row=1):
    ws=wb[sheet]; rows=list(ws.iter_rows(values_only=True)); hdr=rows[header_row-1]
    ki=key_col-1 if isinstance(key_col,int) else ci(key_col)
    out={}
    for r in rows[header_row:]:
        if ki>=len(r) or r[ki] is None: continue
        key=norm_key(r[ki]); d={}
        for j,v in enumerate(r):
            h=hdr[j]
            if h is not None and j!=ki: d[h]=v
        out[key]=d
    return out

def table_keyed_monthcols(sheet, key_col, header_row=1):
    ws=wb[sheet]; rows=list(ws.iter_rows(values_only=True)); hdr=rows[header_row-1]
    ki=key_col-1 if isinstance(key_col,int) else ci(key_col)
    out={}
    for r in rows[header_row:]:
        if ki>=len(r) or r[ki] is None: continue
        key=norm_key(r[ki]); d={}
        for j,v in enumerate(r):
            if j==ki: continue
            h=hdr[j]
            if h is None: continue
            try: m=int(float(h))
            except: continue
            d[m]=v
        out[key]=d
    return out

def get(d,k,default=0.0):
    v=d.get(k)
    if v is None: return default
    try: return float(v)
    except: return default

# ---------- inputs ----------
keyassum = table_keyed("输入整理-关键假设", key_col=5)      # key=合同组ID(col E)
groupsplice = table_keyed("合同组拼接", key_col=5)           # key=预测组ID(col E)
ep = table_keyed_monthcols("输入整理-预期赔付率", key_col=5) # key=预测组(col E)
maint = table_keyed_monthcols("输入整理-维持费用率", key_col=5) # key by col E (holds 精算险类)
io_indir = table_keyed_monthcols("输入整理-未到期间接理赔费用率", key_col=5)
io_incur = table_keyed_monthcols("输入整理-未决间接理赔费用率", key_col=5)
recov = table_keyed_monthcols("预期摊回比例_现有业务", key_col=3) # key=预测组(col C)
invest = table_keyed_monthcols("投资成分比例", key_col=3)    # key=预测组(col C)
reins = table_keyed_monthcols("再保人不履约风险", key_col=3) # key=精算险类(col C)
riskadj = table_keyed("风险调整比例", key_col=3)             # key=精算险类(col C)
und_incur = table_keyed_monthcols("输入整理-未到期赔付模式", key_col=4)  # key=精算险类(col D)
dev = table_keyed_monthcols("输入整理-未决赔付模式", key_col=4)          # key=精算险类(col D)
cum = table_keyed_monthcols("输入整理-实际赔付比例_累计", key_col=4)     # key=精算险类(col D)
prem_mode = table_keyed_monthcols("输入整理-保费现金流模式", key_col=4)  # key=预测组ID(col D)
iacf_mode = table_keyed_monthcols("输入整理-IACF现金流模式", key_col=4)
earn = table_keyed_monthcols("输入整理-未到期赚取模式", key_col=4)

# 系统期初余额表: key=合同组名称(col C). header-keyed + positional (C:Y)
ws_open=wb["系统期初余额表"]; rows_o=list(ws_open.iter_rows(values_only=True)); hdr_o=rows_o[0]
opening={}; opening_pos={}
for r in rows_o[1:]:
    if r[2] is None: continue
    key=str(r[2]); d={}
    for j,v in enumerate(r):
        h=hdr_o[j]
        if h is not None and j!=2: d[h]=v
    opening[key]=d
    # positional slice cols C(3)..Y(25) -> indices 0..22
    opening_pos[key]=[ (r[j] if j<len(r) else None) for j in range(2,25)]

# 即期利率曲线加工: key=进展月份(col E); H=期末折现, I=期初折现
wsr=wb["输入整理-即期利率曲线加工"]; rowsr=list(wsr.iter_rows(values_only=True)); hdr_r=rowsr[0]
ie=hdr_r.index("进展月份") if "进展月份" in hdr_r else ci("E")
ih=hdr_r.index("月度折现因子（期末折现）_预测时点")
ii=hdr_r.index("月度折现因子（期初折现）_预测时点")
disc={}
for r in rowsr[1:]:
    if r[ie] is None: continue
    try: k=int(float(r[ie]))
    except: continue
    def f(v):
        try: return float(v)
        except: return 0.0
    disc[k]=(f(r[ih]), f(r[ii]))

# 初始确认利率曲线: ROW3 = 合同组名称 headers (cols D+), col D = 月度远期(period), data rows 4+
wsc=wb["初始确认利率曲线"]; rowsc=list(wsc.iter_rows(values_only=True)); hdr_c=rowsc[2]
name_cols={}
for j,h in enumerate(hdr_c):
    if h is not None and j>=3:
        name_cols[str(h)]=j
intrate={}
for r in rowsc[3:]:
    if r[3] is None: continue
    try: period=int(float(r[3]))
    except: continue
    for name,cj in name_cols.items():
        if cj<len(r) and r[cj] is not None:
            intrate.setdefault(name,{})[period]=r[cj]

EVAL_DATE=wb["基本信息"]["C2"].value

def eomonth(dt,months):
    y=dt.year+(dt.month-1+months)//12; m=(dt.month-1+months)%12+1
    return datetime.datetime(y,m,min(dt.day,calendar.monthrange(y,m)[1]))

PERIOD=1
PRED_TIME=eomonth(EVAL_DATE,PERIOD)  # 预测时点 = eval+1mo

# io_incur/io_indir 险类 coding differs from dev/und/cum for first two 险类:
# workbook stores 交强险=32 in dev but 33 in io_incur; 附加险=36 in dev but 39 in io_incur.
# 18 other codes (37,38,101..603ZX) match exactly. Map to align.
IO_RISK_REMAP = {"32":"33","36":"39"}

# ---------- triangle reconstruction ----------
def build_triangle(grp):
    """grp: dict with 预测组ID, 合同组名称, 精算险类, 直保/分出, 应收, 应付IACF, 评估期写入, UPR"""
    预测组ID=grp["预测组ID"]; 合同组名称=grp["合同组名称"]; 险类=grp["精算险类"]
    分出 = (grp["直保或分出"]=="分出")
    eval_write=get(grp,"评估期写入")
    UPR=get(grp,"UPR余额"); 应收=get(grp,"应收保费"); 应付IACF=get(grp,"应付IACF")
    pr=get(ep.get(grp["预测组"],{}),PERIOD)
    mr=0.0 if 分出 else get(maint.get(险类,{}),PERIOD)
    nra_und=get(riskadj.get(险类,{}),"未到期风险调整%")
    nra_inc=get(riskadj.get(险类,{}),"未决风险调整%")
    reins_r=get(reins.get(险类,{}),PERIOD) if 分出 else 0.0
    io_key=IO_RISK_REMAP.get(险类,险类)
    io_indir_r=0.0 if 分出 else get(io_indir.get(io_key,{}),PERIOD)
    io_incur_r=0.0 if 分出 else get(io_incur.get(io_key,{}),PERIOD)
    recov_r=0.0 if 分出 else get(recov.get(grp["预测组"],{}),PERIOD)
    invest_r=get(invest.get(grp["预测组"],{}),PERIOD)
    int_rate=get(intrate.get(grp.get("现有业务预测组") or 合同组名称,{}),PERIOD)
    # opening balances (by header name) — map to triangle X/Y/Z/AA/AB/AC
    op=opening.get(合同组名称,{})
    open_X=get(op,"已发生未决赔款负债_预期现金流")            # X
    open_Y=get(op,"间接理赔费用负债_预期现金流")              # Y
    open_Z=get(op,"已发生未决赔款负债_再保人不履约_预期现金流")  # Z
    open_AA=get(op,"已发生未决赔款负债_非金融风险调整")        # AA
    open_AB=get(op,"间接理赔费用负债_非金融风险调整")          # AB
    open_AC=get(op,"已发生未决赔款负债_再保人不履约_非金融风险调整")  # AC
    # positional opening
    opp=opening_pos.get(合同组名称,[None]*23)
    open_待摊销保险收入=get(opening.get(合同组名称,{}),"待摊销保险收入")
    open_UPR=get(opening.get(合同组名称,{}),"UPR余额")
    open_不含利净=get(opening.get(合同组名称,{}),"未到期责任负债_非亏损部分_不含利净口径未赚")
    open_待摊销获取现金流=get(op,"待摊销获取现金流")
    open_待摊销投资成分=get(op,"待摊销投资成分")
    open_亏损部分=get(op,"未到期责任负债_亏损部分")
    open_亏损摊回=get(op,"未到期责任负债_亏损摊回")
    open_非亏损=get(op,"未到期责任负债_非亏损部分")
    open_现值_预期现金流=get(op,"已发生未决赔款负债_预期现金流现值")
    open_现值_间接理赔=get(op,"间接理赔费用负债_预期现金流现值")
    open_现值_NRA=get(op,"已发生未决赔款负债_非金融风险调整现值")
    open_现值_间接理赔NRA=get(op,"间接理赔费用负债_非金融风险调整现值")

    # precompute per-(a) denominator for AR (未到期赔付模式修正)
    # AR = AP / SUMIFS(AP, AJ==AJ2, AK>H2). For fixed a: denom = sum over d (a+d>1) of AP(a,d).
    def ap_val(a,d): return get(und_incur.get(险类,{}), d+1-eval_write)
    denom_by_a={}
    for a in range(1,61):
        tot=0.0
        for d in range(0,60):
            if (a+d)>1:
                tot+=ap_val(a,d)
        denom_by_a[a]=tot

    # 3600 full grid: a(事故期 1..60, outer) x d(发展期 0..59, inner)
    # AD 事故期月度序列 = d+1 ONLY in a==1 block; AE 发展期月度序列 = d only in a==1 block
    rows=[]
    for a in range(1,61):
        for d in range(0,60):
            AD = (d+1) if a==1 else None
            AE = d if a==1 else None
            AG=a; AH=d
            AI = eomonth(EVAL_DATE, AD) if AD is not None else None
            AJ = eomonth(EVAL_DATE, a)
            AK = eomonth(AJ, d)
            # AL/AM: 保费/IACF现金流模式 by AD (only a==1 block)
            al = get(prem_mode.get(预测组ID,{}), AD) if AD is not None else 0.0
            am = get(iacf_mode.get(预测组ID,{}), AD) if AD is not None else 0.0
            # AN: 保费赚取比例_维持 by AD (drives S 当期确认比例); AO: 保费赚取比例_赔付 by a
            an = get(earn.get(预测组ID,{}), AD) if AD is not None else 0.0
            ao = get(earn.get(预测组ID,{}), a)
            ap = ap_val(a,d)
            aq = get(dev.get(险类,{}), d+1) if AE is not None else 0.0   # AQ 未决赔付模式 (a==1 block)
            denom = denom_by_a[a]
            ar = ap/denom if denom else 0.0
            # AS 累计实际赔付比例: VLOOKUP(险类,实际赔付比例_累计, J2-AG2+1) when AJ<=H2
            as_p = PERIOD - a + 1
            as_val = get(cum.get(险类,{}), as_p) if (AJ<=PRED_TIME and as_p>=1) else 0.0
            # 折现因子 index = AH - J2 + AG = d - 1 + a  (col H 期末 / col I 期初)
            midx = d - 1 + a
            disc_t,disc_i = disc.get(midx,(0.0,0.0))
            at = 0.0 if (AK<=PRED_TIME) else disc_t
            au = 0.0 if (AI is None or AI<=PRED_TIME) else disc_t
            av = 0.0 if (AI is None or AI<=PRED_TIME) else disc_i
            # cashflows
            aw = -应收*al
            ax = -应付IACF*am
            ay = (UPR*pr*ao*ap) if (AJ>PRED_TIME) else 0.0
            az = UPR*mr*an   # AN = 保费赚取比例_维持 = earn[预测组ID][AD]
            ba = (ay+az)*nra_und
            # 期初未决 (J2=1: opening * AQ 未决赔付模式), distributed over a==1 block
            bb=open_X*aq; bc=open_Y*aq; bd=open_Z*aq; be=open_AA*aq; bf=open_AB*aq; bg=open_AC*aq
            bh = (UPR*pr*ao) if (AJ<=PRED_TIME) else 0.0
            bi = bh*as_val
            bj = bi*io_incur_r
            bk = ((bh-bi)*ar) if ((AJ<=PRED_TIME) and (AK>PRED_TIME)) else 0.0
            bl = (bb+bk) if ((AJ<=PRED_TIME) and (AK>PRED_TIME)) else 0.0
            bm = bl*io_incur_r
            bn = (bl+bm)*reins_r
            bo = bl*nra_inc
            bp = bm*nra_inc
            bq = bn*nra_inc
            # 期末现值
            br=aw*av; bs=ax*av; bt=ay*at; bu=az*au; bv=ba*at
            bw=bl*at; bxm=bm*at; by=-bn*at; bz=bo*at; ca=bp*at; cb=-bq*at
            cc=bb*at; cd=bc*at; ce=bd*at; cf=be*at; cg=bf*at; ch=bg*at
            rows.append(dict(a=a,d=d,aw=aw,ax=ax,ay=ay,az=az,ba=ba,
                bb=bb,bc=bc,bd=bd,be=be,bf=bf,bg=bg,
                bi=bi,bj=bj,bl=bl,bm=bm,bn=bn,bo=bo,bp=bp,bq=bq,
                br=br,bs=bs,bt=bt,bu=bu,bv=bv,bw=bw,bx=bxm,by=by,bz=bz,ca=ca,cb=cb,
                cc=cc,cd=cd,ce=ce,cf=cf,cg=cg,ch=ch,
                ai=AI,aj=AJ,ak=AK,an=an,ad=AD,ao=ao))
    return dict(rows=rows, grp=grp, ctx=dict(
        pr=pr,mr=mr,nra_und=nra_und,nra_inc=nra_inc,reins_r=reins_r,io_incur_r=io_incur_r,
        recov_r=recov_r,invest_r=invest_r,int_rate=int_rate,
        open_X=open_X,open_Y=open_Y,open_Z=open_Z,open_AA=open_AA,open_AB=open_AB,open_AC=open_AC,
        open_待摊销保险收入=open_待摊销保险收入,open_UPR=open_UPR,open_不含利净=open_不含利净,
        open_待摊销获取现金流=open_待摊销获取现金流,open_待摊销投资成分=open_待摊销投资成分,
        open_亏损部分=open_亏损部分,open_亏损摊回=open_亏损摊回,open_非亏损=open_非亏损,
        open_现值_预期现金流=open_现值_预期现金流,open_现值_间接理赔=open_现值_间接理赔,
        open_现值_NRA=open_现值_NRA,open_现值_间接理赔NRA=open_现值_间接理赔NRA,
        分出=分出))

def aggregate(T):
    rows=T["rows"]; ctx=T["ctx"]
    def s(col): return sum(r[col] for r in rows)
    def siff(col,cond): return sum(r[col] for r in rows if cond(r))
    # group-level: S = 当期确认比例 = SUMIFS(AN, AD, J2) / SUMIFS(AN, AD, ">="&J2)
    # AN = 保费赚取比例_维持 keyed by AD (a==1 block only); AO = 保费赚取比例_赔付 keyed by a
    _an_den = siff("an", lambda r:r["ad"] is not None)
    S = (siff("an", lambda r:r["ad"]==PERIOD) / _an_den) if _an_den else 0.0
    T_ratio = S  # 获取现金流摊销比例 = 当期确认比例
    int_rate=ctx["int_rate"]
    # opening positional
    opp=dict(待摊销保险收入=ctx["open_待摊销保险收入"],UPR=ctx["open_UPR"],不含利净=ctx["open_不含利净"])
    AI_待摊销保险收入=(opp["待摊销保险收入"]+opp["UPR"]-opp["不含利净"])*(1+int_rate)
    AJ_待摊销获取现金流=ctx["open_待摊销获取现金流"]*(1+int_rate)
    AK_待摊销投资成分=ctx["open_待摊销投资成分"]*(1+int_rate)
    AL_期初亏损=ctx["open_亏损部分"]; AM_期初亏损摊回=ctx["open_亏损摊回"]; AN_期初非亏损=ctx["open_非亏损"]
    AO_当期收到保费=-siff("aw", lambda r:r["ai"] is not None and r["ai"]<=PRED_TIME)
    AP_当期支出IACF=-siff("ax", lambda r:r["ai"] is not None and r["ai"]<=PRED_TIME)
    AQ_未到期计息=int_rate*(AN_期初非亏损+AO_当期收到保费+AP_当期支出IACF)
    AT_分解投资成分=-AK_待摊销投资成分*S
    AR_保险收入=-AI_待摊销保险收入*S - AT_分解投资成分
    AS_摊销获取费用=-AJ_待摊销获取现金流*T_ratio
    AU_期末非亏损=AN_期初非亏损+AO_当期收到保费+AP_当期支出IACF+AQ_未到期计息+AR_保险收入+AS_摊销获取费用+AT_分解投资成分
    AV_预期未来保费=s("br"); AW_预期未来IACF=s("bs"); AX_预期未来赔付=s("bt"); AY_预期未来维持=s("bu"); AZ_NRA=s("bv")
    BA_预期未来合计=AV_预期未来保费+AW_预期未来IACF+AX_预期未来赔付+AY_预期未来维持+AZ_NRA
    BB_亏损部分=max(BA_预期未来合计-AU_期末非亏损,0.0)
    BC_亏损摊回=-BB_亏损部分*ctx["recov_r"]
    BD_支付赔付=-siff("bi", lambda r:r["d"]==PERIOD)
    BE_支付理赔费用=-siff("bj", lambda r:r["d"]==PERIOD)
    BF_支付维持=-siff("az", lambda r:r["ai"] is not None and r["ai"]<=PRED_TIME)
    BG_支付赔付=BD_支付赔付; BH_支付理赔费用=BE_支付理赔费用
    # 期末 LRC (期末现值_未决*_期末)
    AC_期末预期现金流=s("bw"); AD_期末间接=s("bx"); AE_期末再保=s("by"); AF_期末NRA=s("bz"); AG_期末间接NRA=s("ca"); AH_期末再保NRA=s("cb")
    # 期初 LRC (期末现值_未决*_期初)
    W_期初预期=s("cc"); X_期初间接=s("cd"); Y_期初再保=s("ce"); Z_期初NRA=s("cf"); AA_期初间接NRA=s("cg"); AB_期初再保NRA=s("ch")
    # 输出_ columns
    out={}
    out["输出_未到期责任负债_非亏损部分"]=AU_期末非亏损
    out["输出_未到期责任负债_亏损部分"]=BB_亏损部分
    out["输出_未到期责任负债_亏损摊回"]=BC_亏损摊回
    out["输出_已发生未决赔款负债_预期现金流"]=AC_期末预期现金流
    out["输出_间接理赔费用负债_预期现金流"]=AD_期末间接
    out["输出_已发生未决赔款负债_再保人不履约_预期现金流"]=AE_期末再保
    out["输出_已发生未决赔款负债_非金融风险调整"]=AF_期末NRA
    out["输出_间接理赔费用负债_非金融风险调整"]=AG_期末间接NRA
    out["输出_已发生未决赔款负债_再保人不履约_非金融风险调整"]=AH_期末再保NRA
    out["输出_保险合同收入"]=-AR_保险收入
    out["输出_赔付与费用_分解的投资成分"]=-AT_分解投资成分
    out["输出_赔付与费用_摊销的保险获取现金流"]=-AS_摊销获取费用
    out["输出_亏损合同损益"]=-(BB_亏损部分-AL_期初亏损)
    out["输出_亏损摊回损益"]=-(BC_亏损摊回-AM_期初亏损摊回)
    out["输出_赔付与费用_已发生未决赔款负债提转差_预期现金流"]=-(AC_期末预期现金流-W_期初预期+BG_支付赔付)
    out["输出_赔付与费用_已发生未决赔款负债提转差_非金融风险调整"]=-(AF_期末NRA-Z_期初NRA)
    out["输出_赔付与费用_间接理赔费用提转差_预期现金流"]=-(AD_期末间接-X_期初间接+BH_支付理赔费用)
    out["输出_赔付与费用_间接理赔费用提转差_非金融风险调整"]=-(AG_期末间接NRA-AA_期初间接NRA)
    out["输出_赔付与费用_再保人不履约风险提转差_预期现金流"]=-AE_期末再保
    out["输出_赔付与费用_再保人不履约风险提转差_非金融风险调整"]=-AH_期末再保NRA
    out["输出_IFIE_未到期_未到期计息"]=-AQ_未到期计息
    out["输出_IFIE_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流"]=-ctx["open_现值_预期现金流"]*int_rate
    out["输出_IFIE_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整"]=-ctx["open_现值_NRA"]*int_rate
    out["输出_IFIE_已发生未决_间接理赔费用计息与利率变化_预期现金流"]=-ctx["open_现值_间接理赔"]*int_rate
    out["输出_IFIE_已发生未决_间接理赔费用计息与利率变化_非金融风险调整"]=-ctx["open_现值_间接理赔NRA"]*int_rate
    out["输出_现金流_支付的赔付与理赔费用"]=BG_支付赔付+BH_支付理赔费用
    out["输出_现金流_支付的维持费用"]=BF_支付维持
    out["输出_现金流_收到的保费"]=AO_当期收到保费
    out["输出_现金流_支付的IACF"]=AP_当期支出IACF
    out["输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流"]=-(AC_期末预期现金流-ctx["open_现值_预期现金流"]+out["输出_赔付与费用_已发生未决赔款负债提转差_预期现金流"]+out["输出_IFIE_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流"])
    out["输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整"]=-(AF_期末NRA-ctx["open_现值_NRA"]+out["输出_赔付与费用_已发生未决赔款负债提转差_非金融风险调整"]+out["输出_IFIE_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整"])
    out["输出_OCI_已发生未决_间接理赔费用计息与利率变化_预期现金流"]=-(AD_期末间接-ctx["open_现值_间接理赔"]+out["输出_赔付与费用_间接理赔费用提转差_预期现金流"]+out["输出_IFIE_已发生未决_间接理赔费用计息与利率变化_预期现金流"])
    out["输出_OCI_已发生未决_间接理赔费用计息与利率变化_非金融风险调整"]=-(AG_期末间接NRA-ctx["open_现值_间接理赔NRA"]+out["输出_赔付与费用_间接理赔费用提转差_非金融风险调整"]+out["输出_IFIE_已发生未决_间接理赔费用计息与利率变化_非金融风险调整"])
    return out

# ---------- run & compare ----------
wz=wb["PAA计算_现有业务整理"]; rz=list(wz.iter_rows(values_only=True)); hz=rz[0]
def zval(r,name):
    try: i=hz.index(name); return r[i]
    except: return None
# groups from 整理
zgroups={}
for r in rz[1:]:
    gid=r[3]; biz=r[4]
    if gid is None: continue
    zgroups[(str(gid),str(biz))]=r

total_diff=0.0; worst=[]; ngrp=0
for (gid,biz),zrow in zgroups.items():
    ngrp+=1
    ka=keyassum.get(gid,{})
    sp=groupsplice.get(gid,{})
    险类=str(ka.get("精算险类") or sp.get("精算险类"))
    合同组名称=ka.get("合同组名称") or sp.get("合同组合名称")
    grp=dict(
        预测组ID=gid,
        预测组=sp.get("预测组"),
        现有业务预测组=sp.get("现有业务预测组"),
        合同组名称=合同组名称,
        精算险类=险类,
        直保或分出=ka.get("直保或分入/分出") or biz,
        应收保费=get(ka,"应收保费"),
        应付IACF=get(ka,"应付IACF"),
        UPR余额=get(opening.get(合同组名称,{}),"UPR余额"),
        评估期写入=get(ka,"评估期开始业务预期写入时间（月）"),
    )
    T=build_triangle(grp)
    out=aggregate(T)
    # compact diagnostic
    au_m=out.get("输出_未到期责任负债_非亏损部分",0.0); au_v=zval(zrow,"输出_未到期责任负债_非亏损部分")
    bb_m=out.get("输出_未到期责任负债_亏损部分",0.0); bb_v=zval(zrow,"输出_未到期责任负债_亏损部分")
    ac_m=out.get("输出_已发生未决赔款负债_预期现金流",0.0); ac_v=zval(zrow,"输出_已发生未决赔款负债_预期现金流")
    if len(sys.argv)>1 and sys.argv[1]=="diag":
        def s2(col): return sum(r[col] for r in T["rows"])
        av_=s2("br"); aw_=s2("bs"); ax_=s2("bt"); ay_=s2("bu"); az_=s2("bv"); ba_=av_+aw_+ax_+ay_+az_
        v_av=zval(zrow,"预期未来保费现金流入"); v_aw=zval(zrow,"预期未来保险获取现金流出")
        v_ax=zval(zrow,"预期未来赔付现金流出（含间接理赔费用）");         v_ay=zval(zrow,"预期未来维持费用现金流出"); v_ba=zval(zrow,"预期未来现金流合计")
        ctx=T["ctx"]
        sum_an=sum(r["an"] for r in T["rows"]); sum_ao=sum(r["ao"] for r in T["rows"])
        print(f"DIAG {gid[:14]:14s} 分出={grp['直保或分出']:5s} | AU {au_m:14.1f}/{au_v}")
        print(f"      mr={ctx.get('mr'):.5f} pr={ctx.get('pr'):.5f} UPR={grp.get('UPR余额'):.1f} sum_an={sum_an:.4f} sum_ao={sum_ao:.4f}")
        sum_az=sum(r["az"] for r in T["rows"]); sum_bu=sum(r["bu"] for r in T["rows"])
        print(f"      sum_az={sum_az:.1f} sum_bu(AY)={sum_bu:.1f}")
        print(f"      AV {av_:.1f}/{v_av} | AW {aw_:.1f}/{v_aw} | AX {ax_:.1f}/{v_ax} | AY {ay_:.1f}/{v_ay} | BA {ba_:.1f}/{v_ba} | AC {ac_m:.1f}/{ac_v}")
    for col in out:
        sv=out[col]; vv=zval(zrow,col)
        a=float(sv) if isinstance(sv,(int,float)) else 0.0
        b=float(vv) if isinstance(vv,(int,float)) else 0.0
        d=abs(a-b)
        if d>0.01:
            total_diff+=d; worst.append((gid,col,round(a,2),round(b,2),round(d,2)))
print(f"\nGroups compared: {ngrp}  Total abs diff (输出_ columns): {total_diff:.2f}")
print("Top 30 mismatches (group, col, mine, verify, absdiff):")
for w in sorted(worst,key=lambda x:-x[4])[:30]:
    print(f"  {w[0]} | {w[1]}: mine={w[2]} ver={w[3]} d={w[4]}")
wb.close()
