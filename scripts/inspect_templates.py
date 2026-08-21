"""Inspect template headers for affected sheets."""
import openpyxl

SYSTEM_DOCK = r"验证文件/backup/系统对接输入表_模板.xlsx"
EXCEL_UPLOAD = r"验证文件/backup/手工输入表_模板.xlsx"

for path in (SYSTEM_DOCK, EXCEL_UPLOAD):
    print("=" * 70)
    print(path)
    wb = openpyxl.load_workbook(path)
    for ws in wb.worksheets:
        row1 = [c.value for c in ws[1]]
        # trim trailing None
        while row1 and row1[-1] is None:
            row1.pop()
        print(f"  [{ws.title}]  cols={len(row1)}  row1={row1}")
    wb.close()
