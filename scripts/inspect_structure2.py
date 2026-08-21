# -*- coding: utf-8 -*-
import os
from openpyxl import load_workbook
ROOT="D:/IFRS17预测模型"
VBX=os.path.join(ROOT,"验证文件","IFRS17财务预测_改造版_0729_VBA.xlsx")
wb=load_workbook(VBX,data_only=True)
ws=wb["PAA计算_现有业务预测"]
rows=list(ws.iter_rows(values_only=True))
print("预测 table total rows (incl header)=",len(rows),"max_col=",ws.max_column)
print("--- first 3 rows, cols A..K ---")
for ri,r in enumerate(rows[:3]):
    print(f"row{ri+1}:", [r[j] for j in range(0,11)])
print("--- rows 2..14 cols A,C,D,E,J,K,L,M,N,O,P only ---")
for ri,r in enumerate(rows[1:15], start=2):
    print(f"row{ri}:", r[0], "|", r[2], "|", r[3], "|", r[4], "| J=",r[9], "| K=",r[10])
print()
print("=== 整理 table ===")
wz=wb["PAA计算_现有业务整理"]
rz=list(wz.iter_rows(values_only=True))
hz=rz[0]
print("整理 total rows=",len(rz),"max_col=",wz.max_column)
# find 合同组ID, 直保/分出, and a period-like column
def zci(n):
    try: return hz.index(n)
    except: return None
print("hz index 合同组ID=",zci("合同组ID")," 直保或分入/分出=",zci("直保或分入/分出"))
# dump first 6 rows cols: 合同组ID, 直保/分出, and columns around 预测间隔 if any
print("--- 整理 first 6 rows: A,B,C,D,E,F,G ---")
for ri,r in enumerate(rz[:7]):
    print(f"row{ri}:", [r[j] for j in range(0,7)])
wb.close()
