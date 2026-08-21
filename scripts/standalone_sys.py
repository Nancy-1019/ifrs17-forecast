# -*- coding: utf-8 -*-
import os, sys, django, calendar
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ifrs17_core.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()
from data_input.models import SheetData
import openpyxl

ROOT="D:/IFRS17预测模型"
VP=os.path.join(ROOT,"验证文件","IFRS17财务预测_改造版_0729_VBA.xlsx")
wb=openpyxl.load_workbook(VP,data_only=True)

def srow(sheet, key, idx):
    s=SheetData.objects.filter(is_active=True, sheet_name=sheet).first()
    for r in s.rows:
        if idx<len(r) and r[idx] is not None and str(r[idx])==str(key):
            return {h:r[i] for i,h in enumerate(s.headers) if h is not None}
    return {}
def mdict(d):
    out={}
    for k,v in d.items():
        if k is None: continue
        try:
            kk=int(float(k))
        except: continue
        if v is None: out[kk]=0.0
        else:
            try: out[kk]=float(v)
            except: out[kk]=0.0
    return out

def eomonth(dt, months):
    y=dt.year+(dt.month-1+months)//12; m=(dt.month-1+months)%12+1
    return dt.replace(year=y, month=m, day=min(dt.day, calendar.monthrange(y,m)[1]))

# inputs
g='交强险_直保或分入_现有业务'; gid='交强险_直保或分入_现有业务&0'; ac=32
op=srow('系统期初余额表', g, 2)
ep=mdict(srow('预期赔付率', g, 2))
earn=mdict(srow('未到期赚取模式_现有业务', g, 3))
und=mdict(srow('未到期赔付模式', ac, 3))
dev=mdict(srow('未决赔付模式', ac, 3))
cum=mdict(srow('实际赔付比例', ac, 3))  # note: system sheet name is 实际赔付比例
open_X=op.get('已发生未决赔款负债_预期现金流',0.0)
UPR=op.get('UPR余额',0.0)
pr=ep.get(1,0.0)
# discount factors from annual curve (verified == verification)
s=SheetData.objects.filter(is_active=True, sheet_name='即期利率曲线').first()
annual={}
for r in s.rows:
    if len(r)>2 and r[2] is not None:
        y=int(float(r[2])); annual[y]=float(r[3] or 0)
def df_end(m):
    yr=m//12 if m%12==0 else m//12+1
    return (1+annual.get(yr,0.03)/12)**(-m)
EVAL=__import__('datetime').datetime(2026,6,30)
PERIOD=1
pred=eomonth(EVAL,PERIOD)

ap_val=lambda a,d: und.get(d+1-PERIOD,0.0)  # eval_write=1
denom_by_a={}
for a in range(1,61):
    tot=0.0
    for d in range(0,60):
        if (a+d)>1: tot+=ap_val(a,d)
    denom_by_a[a]=tot

rows=[]
for a in range(1,61):
    for d in range(0,60):
        AJ=eomonth(EVAL,a); AK=eomonth(AJ,d)
        an=earn.get(d+1,0.0) if a==1 else 0.0
        ao=earn.get(a,0.0)
        ap=ap_val(a,d)
        aq=dev.get(d+1,0.0) if a==1 else 0.0
        denom=denom_by_a[a]; ar=ap/denom if denom else 0.0
        as_p=PERIOD-a+1
        as_val=cum.get(as_p,0.0) if (AJ<=pred and as_p>=1) else 0.0
        midx=d-1+a
        disc_t=df_end(midx)
        at=0.0 if (AK<=pred) else disc_t
        bb=open_X*aq; bh=(UPR*pr*ao) if (AJ<=pred) else 0.0
        bi=bh*as_val; bk=((bh-bi)*ar) if ((AJ<=pred) and (AK>pred)) else 0.0
        bl=bb+bk
        bw=bl*at
        rows.append((a,d,bb,bk,bw,at,midx))

sum_bb_at=sum(r[2]*r[5] for r in rows)
sum_bk_at=sum(r[3]*r[5] for r in rows)
AC=sum(r[4] for r in rows)
print("open_X=",open_X," UPR=",UPR," pr=",pr)
print("sum_bb_at (opening PV)=",sum_bb_at)
print("sum_bk_at (new PV)=",sum_bk_at)
print("AC (standalone system port) =", AC)

# verification reported AC
wz=wb["PAA计算_现有业务整理"]; rz=list(wz.iter_rows(values_only=True)); hz=rz[0]
for r in rz[1:]:
    if r[3]==gid:
        vac=r[hz.index('输出_已发生未决赔款负债_预期现金流')]
        print("VERIFY AC =", vac, " diff=", AC-vac)
        break
wb.close()
