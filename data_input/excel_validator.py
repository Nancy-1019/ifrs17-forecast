"""Excel文件解析与校验模块 - 全部使用Python openpyxl
替代前端SheetJS解析逻辑。
"""
import io
from datetime import datetime
from typing import Dict, Any, List, Optional
from openpyxl import load_workbook
from .excel_specs import EXCEL_UPLOAD_SPECS, SYSTEM_DOCK_SPECS, SheetSpec


def get_spec(source: str) -> Dict[str, SheetSpec]:
    """根据来源获取校验规范"""
    if source == 'excel':
        return EXCEL_UPLOAD_SPECS
    elif source == 'dock':
        return SYSTEM_DOCK_SPECS
    raise ValueError(f"Unknown source: {source}")


def validate_upload(file_bytes: bytes, source: str, eval_date: str = None) -> Dict[str, Any]:
    """主入口：接收文件字节流，解析并校验，返回与前端兼容的结果结构
    
    Args:
        file_bytes: Excel文件二进制数据
        source: 'excel' 或 'dock'
        eval_date: 可选，评估时点筛选（YYYY-MM-DD格式），仅保留匹配的数据行
    
    返回结构:
    {
        'success': bool,
        'errors': [str],
        'warnings': [str],
        'sheetResults': { sheetName: { 'valid': bool, 'errors': [str], 'rowCount': int, 'headerErrors': [...] } },
        'sheetData': { sheetName: { 'headers': [str], 'rows': [[...]], 'displayCols': int } },
        'totalRows': int,
        'sheetCount': int,
        'filteredRows': int,        # 被筛选掉的行数
    }
    """
    specs = get_spec(source)

    try:
        # read_only=True: 流式读取，大幅减少内存占用和解析耗时
        # 关键优化点：Excel文件中部分工作表因格式被撑到16384列，
        # 实际数据列数远小于此，后续通过动态检测实际列宽来裁剪迭代范围
        wb = load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
    except Exception as e:
        return {
            'success': False,
            'errors': [f'文件解析失败: {str(e)}'],
            'warnings': [],
            'sheetResults': {},
            'sheetData': {},
            'totalRows': 0,
            'sheetCount': 0,
        }

    errors = []
    warnings = []
    sheet_results = {}
    sheet_data = {}
    all_valid = True
    total_rows = 0
    filtered_rows = 0

    expected_sheets = list(specs.keys())
    actual_sheets = wb.sheetnames

    # 1. 校验工作表名称
    missing = [s for s in expected_sheets if s not in actual_sheets]
    extra = [s for s in actual_sheets if s not in expected_sheets]

    if missing:
        errors.append(f"缺少工作表: {', '.join(missing)}")
        all_valid = False
    if extra:
        warnings.append(f"多余工作表(将忽略): {', '.join(extra)}")

    # 2. 逐个工作表校验
    for sheet_name in expected_sheets:
        if sheet_name not in actual_sheets:
            sheet_results[sheet_name] = {
                'valid': False, 'errors': ['工作表不存在'],
                'rowCount': 0, 'headerErrors': [],
            }
            continue

        spec = specs[sheet_name]
        ws = wb[sheet_name]

        # 读取所有行（openpyxl的行从1开始）
        # 关键优化：部分工作表因格式被撑到16384列，实际数据列数远小于此
        # 迭代时动态检测实际列宽，后续统一裁剪，避免遍历海量空列
        all_rows = []
        actual_cols = 0
        for row in ws.iter_rows(values_only=True):
            filtered = [_normalize_cell(v) for v in row]
            all_rows.append(filtered)
            # 动态计算该行的实际非空列数，取全局最大值
            last = len(filtered)
            while last > 0 and filtered[last - 1] is None:
                last -= 1
            actual_cols = max(actual_cols, last)

        # 裁剪所有行到实际列宽，去除尾部空列
        if actual_cols > 0 and len(all_rows) > 0:
            all_rows = [row[:actual_cols] for row in all_rows]

        # 过滤全空行
        non_empty_rows = [
            row for row in all_rows
            if any(v not in (None, '') for v in row)
        ]

        if len(non_empty_rows) < 1:
            sheet_results[sheet_name] = {
                'valid': False, 'errors': ['工作表为空'],
                'rowCount': 0, 'headerErrors': [],
            }
            all_valid = False
            continue

        # 实际表头（支持两级表头等偏移表头：定位命中期望字段最多的行）
        header_idx = _detect_header_row(non_empty_rows, spec.headers)
        actual_headers = [
            str(h) if h is not None else ''
            for h in non_empty_rows[header_idx]
        ]
        expected_headers = spec.headers
        header_errors = []

        # 校验文本字段名
        for i, expected in enumerate(expected_headers):
            actual = actual_headers[i].strip() if i < len(actual_headers) else ''
            if actual != expected:
                msg = f'第{i+1}列字段名不符: 期望"{expected}", 实际"{actual or "(空)"}"'
                header_errors.append({
                    'position': i + 1,
                    'expected': expected,
                    'actual': actual or '(空)',
                    'message': msg,
                })

        # 校验数值列数量
        if spec.numeric_cols is not None:
            non_empty_header_count = len([h for h in actual_headers if h != ''])
            if non_empty_header_count < len(expected_headers):
                header_errors.append({
                    'position': -1,
                    'expected': f'{spec.numeric_cols}个数值列',
                    'actual': f'{max(0, non_empty_header_count - len(expected_headers))}个数值列',
                    'message': f'数值列数量不足: 期望至少{spec.numeric_cols}个数值列, 实际{max(0, non_empty_header_count - len(expected_headers))}个',
                })

        # 校验合同组列（仅系统对接接口）
        if spec.contract_cols:
            contract_col_count = len([
                h for i, h in enumerate(actual_headers)
                if i >= len(expected_headers) and h != ''
            ])
            if contract_col_count < 1:
                header_errors.append({
                    'position': -1,
                    'expected': '至少1个合同组利率列',
                    'actual': f'{contract_col_count}个',
                    'message': f'缺少合同组利率列: 期望至少1个合同组列, 实际{contract_col_count}个',
                })

        row_count = len(non_empty_rows) - 1  # 减去表头行
        total_rows += row_count

        # 提取数据行（跳过检测到的表头行）
        data_rows = non_empty_rows[header_idx + 1:]
        # 确保每行长度与表头一致
        num_cols = len(actual_headers)
        aligned_rows = []
        for row in data_rows:
            r = list(row)
            while len(r) < num_cols:
                r.append(None)
            aligned_rows.append(r[:num_cols])

        sheet_data[sheet_name] = {
            'headers': actual_headers,
            'rows': aligned_rows,
            'displayCols': len([h for h in actual_headers if h != '']),
        }

        # === 评估时点筛选 ===
        if eval_date:
            eval_col_idx = None
            for i, h in enumerate(actual_headers):
                if str(h).strip() == '评估时点':
                    eval_col_idx = i
                    break
            if eval_col_idx is not None:
                before_count = len(aligned_rows)
                filtered = []
                for row in aligned_rows:
                    cell_val = row[eval_col_idx] if eval_col_idx < len(row) else None
                    if _match_eval_date(cell_val, eval_date):
                        filtered.append(row)
                    else:
                        filtered_rows += 1
                aligned_rows = filtered
                sheet_data[sheet_name]['rows'] = aligned_rows
                if before_count > len(aligned_rows):
                    warnings.append(
                        f'工作表"{sheet_name}": 评估时点筛选 {eval_date}，'
                        f'保留 {len(aligned_rows)}/{before_count} 行'
                    )

        # === 模式类工作表行和校验（sum_to_one） ===
        # 模式类工作表的60列月度数值，每行之和的经验校验
        # 说明：引擎按源数据「原值」直接作为权重使用（与 VBA 口径自洽），
        # 并不要求模式权重严格归一化到 1.0，故此处仅作【提示性警告】，不阻断上传。
        row_errors = []
        if spec.sum_to_one and spec.numeric_cols:
            text_col_count = len(spec.headers)
            num_col_count = spec.numeric_cols
            tolerance = 0.01  # 放宽容差：仅提示明显异常（避免误报源数据自洽的轻微舍入）
            dev_rows = 0
            max_dev = 0.0
            for row_idx, row in enumerate(aligned_rows):
                numeric_vals = []
                for col_idx in range(text_col_count, text_col_count + num_col_count):
                    if col_idx < len(row):
                        v = row[col_idx]
                        if isinstance(v, (int, float)):
                            numeric_vals.append(float(v))
                if len(numeric_vals) == 0:
                    continue
                dev = abs(sum(numeric_vals) - 1.0)
                if dev > tolerance:
                    dev_rows += 1
                    max_dev = max(max_dev, dev)
            if dev_rows > 0:
                warnings.append(
                    f'工作表"{sheet_name}": 共{dev_rows}行模式权重之和偏离1.0(最大偏离{max_dev:.4f})，'
                    f'引擎按原值直接作为权重(与VBA自洽)，此检查已降级为提示，不阻断上传'
                )

        has_errors = len(header_errors) > 0
        if has_errors:
            all_valid = False

        sheet_results[sheet_name] = {
            'valid': not has_errors,
            'errors': [e['message'] for e in header_errors] + row_errors,
            'rowCount': row_count,
            'headerErrors': header_errors,
            'headers': actual_headers[:min(10, len(actual_headers))],
        }

    wb.close()

    return {
        'success': all_valid,
        'errors': errors,
        'warnings': warnings,
        'sheetResults': sheet_results,
        'sheetData': sheet_data,
        'totalRows': total_rows,
        'sheetCount': len(actual_sheets),
        'filteredRows': filtered_rows,
    }


def _normalize_cell(value) -> Optional[Any]:
    """将openpyxl单元格值标准化：
    - None → None
    - 日期时间 → ISO 格式字符串
    - 字符串 → strip（空串 → None）
    - 数值 → 保持不变
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return value


def _match_eval_date(cell_value, eval_date: str) -> bool:
    """判断单元格中的日期是否匹配指定的评估时点（YYYY-MM-DD）。
    
    兼容多种日期格式：
    - None / 空值 → 不匹配
    - datetime → 比较日期部分
    - "2025-12-31T00:00:00" → 取前10位
    - "2025/12/31" → 替换 / 为 -
    - "2025-12-31" → 直接比较
    """
    if cell_value is None:
        return False
    if isinstance(cell_value, datetime):
        return cell_value.strftime('%Y-%m-%d') == eval_date
    s = str(cell_value).strip()
    if not s:
        return False
    # 取日期部分（前10位，处理 ISO 格式带时间的情况）
    date_part = s[:10]
    # 统一分隔符
    date_part = date_part.replace('/', '-')
    return date_part == eval_date


def _detect_header_row(rows, expected_headers, window=6):
    """在表格前 window 行内定位真正的表头行。

    多数工作表表头在首行；但部分工作表（如「初始确认利率曲线」）为两级表头，
    字段名实际在下方若干行（如第 3 行），前几行为子表头/占位。
    选取「命中期望字段最多」的行作为表头；若首列命中期望首字段则加权优先。
    返回行索引（相对 rows 列表）。
    """
    if not rows:
        return 0
    best_idx, best_score = 0, -1.0
    anchor = expected_headers[0] if expected_headers else ''
    for i, row in enumerate(rows[:window]):
        cells = {str(c).strip() for c in row if c is not None and str(c).strip() != ''}
        if not cells:
            continue
        score = float(sum(1 for h in expected_headers if h in cells))
        # 首列命中期望首字段 → 强烈优先（避免误选子表头行）
        if row and str(row[0]).strip() == anchor:
            score += 0.5
        if score > best_score:
            best_score, best_idx = score, i
    return best_idx
