"""检查 输入整理-* 模式表中，同一 预测组 内不同 合同组ID 的模式是否一致。
若一致 -> 系统按 预测组 取数即可；若不一致 -> 必须按 合同组ID 取数。"""
import openpyxl

SRC = "D:/IFRS17预测模型/验证文件/IFRS17财务预测_改造版_0729_VBA.xlsx"
wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)

def check(sheet, key_col_name, group_col_name):
    ws = wb[sheet]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hdr = rows[0]
    # 去尾部空
    while hdr and (hdr[-1] is None or str(hdr[-1]).strip() == ""):
        hdr = hdr[:-1]
    ki = hdr.index(key_col_name)       # 合同组ID
    gi = hdr.index(group_col_name)     # 预测组
    # 数值列：整数月
    def is_int_month(h):
        try:
            v = float(str(h).strip()); return v == int(v) and v > 0
        except: return False
    num_idx = [i for i, h in enumerate(hdr) if is_int_month(h)]
    by_group = {}
    for r in rows[1:]:
        k = r[ki]; g = r[gi]
        if k is None or g is None:
            continue
        pat = tuple(round(float(r[i]), 10) if i < len(r) and isinstance(r[i], (int, float)) else 0.0 for i in num_idx)
        by_group.setdefault(str(g), {})[str(k)] = pat
    print(f"\n=== {sheet} (key={key_col_name}, group={group_col_name}) ===")
    for g, d in by_group.items():
        pats = set(d.values())
        if len(pats) > 1:
            print(f"  [不一致] 预测组 {g}: {len(d)} 个合同组ID, {len(pats)} 种不同模式")
            # 显示前2个不同
            seen = []
            for cid, p in d.items():
                if p not in seen:
                    seen.append(p)
                if len(seen) >= 3:
                    break
            for p in seen[:3]:
                print(f"      sample: {[round(x,6) for x in p[:5]]} ... sum={sum(p):.4f}")
        else:
            first_pat = next(iter(pats))
            print(f"  [一致] 预测组 {g}: {len(d)} 个合同组ID, 模式唯一 (sum={sum(first_pat):.6f})")

check('输入整理-保费现金流模式', '合同组ID', '预测组')
check('输入整理-IACF现金流模式', '合同组ID', '预测组')
check('输入整理-未到期赚取模式', '合同组ID', '预测组')
wb.close()
