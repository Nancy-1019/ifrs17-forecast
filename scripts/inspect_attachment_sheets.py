"""Inspect attachment sheets that fail validation: header offset + sum_to_one."""
import openpyxl

ATT = r"验证文件/IFRS17财务预测_改造版_开发.xlsx"
wb = openpyxl.load_workbook(ATT, data_only=True, read_only=True)


def dump(sheet, nrows=5, ncols=8):
    print(f"===== {sheet} =====")
    ws = wb[sheet]
    for ri, row in enumerate(ws.iter_rows(values_only=True)):
        if ri >= nrows:
            break
        print(f"  r{ri+1}: {list(row[:ncols])}")


dump('初始确认利率曲线', 5, 6)
dump('IACF现金流模式_新业务', 5, 8)
dump('IACF现金流模式_现有业务', 5, 8)
dump('未到期赚取模式_现有业务', 3, 8)
dump('未决赔付模式', 3, 8)
wb.close()
