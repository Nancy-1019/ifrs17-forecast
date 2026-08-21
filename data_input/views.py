"""IFRS17 数据输入 - 视图
- 认证视图：登录/登出
- 页面视图：主页（SPA容器）
- API视图：数据接口、上传接口、下载接口、版本接口、计算接口
"""
import os
import re
import json
import tempfile
import datetime
from urllib.parse import unquote
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User, Group
from django.http import JsonResponse, HttpResponse, FileResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_control
from django.db import transaction, connection
from django.db.utils import DatabaseError
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from .models import (
    UploadRecord, SheetData, DataWorksSyncLog,
    SystemOperationLog, CalculationVersion, CalculationSnapshot,
    OutputPaaNewBusinessOrganized, OutputPaaExistingBusinessOrganized,
    OutputPaaSummary, OutputPaaMtd, OutputFinancialStatementMtd,
    OutputFinancialStatementYtd, _FinancialStatementLineBase, OUTPUT_TABLE_MODELS,
    INPUT_TABLE_MODELS,
)
from .input_table_schema import INPUT_TABLE_SCHEMA
from decimal import Decimal, InvalidOperation
from .permissions import (
    GROUP_UPLOADER, GROUP_REVIEWER, GROUP_VIEWER, GROUP_ADMIN,
    setup_permission_groups
)
from .excel_validator import validate_upload
from paa_engine.field_names import to_en
BASE_DIR = getattr(settings, 'BASE_DIR', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .deploy_utils import (
    load_deploy_config, save_deploy_config, get_masked_config,
    test_ssh_connection, deploy_to_cloud, create_project_archive,
)


# ============================================================
# 辅助函数
# ============================================================

def get_user_permissions_context(user):
    """获取用户权限上下文（注入前端JS）"""
    if not user.is_authenticated:
        return {
            'is_authenticated': False,
            'username': '',
            'is_uploader': False,
            'is_reviewer': False,
            'is_admin': False,
        }
    return {
        'is_authenticated': True,
        'username': user.username,
        'is_uploader': user.has_perm('data_input.can_upload'),
        'is_reviewer': user.has_perm('data_input.can_review'),
        'is_admin': user.is_staff or user.is_superuser,
        # 仅查看权限：拥有 can_view_all，但不具备 can_upload 且非管理员
        'is_viewer': (user.has_perm('data_input.can_view_all')
                      and not (user.is_staff or user.is_superuser)
                      and not user.has_perm('data_input.can_upload')),
    }


# ============================================================
# 系统运行日志工具
# ============================================================

def get_client_ip(request):
    """获取客户端真实 IP（兼容反向代理）。"""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


# 操作类型 → 中文标签 映射（用于前端下拉与日志展示）
_ACTION_LABELS = dict(SystemOperationLog.action_choices())


def log_operation(request_or_user, action, target='', detail='', level='INFO',
                  username='', user=None):
    """写入一条系统运行日志。

    参数：
      request_or_user: HttpRequest 对象（优先，可自动取 user/ip）或直接是 User 对象；也可为 None
      action: SystemOperationLog.ACTION_* 常量
      target/detail: 操作对象与详情
      level: INFO/WARN/ERROR
      username/user: 显式覆盖（当 request_or_user 不是 request 时使用）
    返回创建的日志对象（失败返回 None，不抛异常）。
    """
    try:
        req = None
        u = user
        if request_or_user is not None:
            if hasattr(request_or_user, 'user') and hasattr(request_or_user, 'META'):
                req = request_or_user
                u = req.user if req.user.is_authenticated else None
            elif hasattr(request_or_user, 'is_authenticated'):
                u = request_or_user if request_or_user.is_authenticated else None

        uname = username or (u.username if u else '') or 'anonymous'
        ip = get_client_ip(req) if req is not None else ''
        label = _ACTION_LABELS.get(action, action)

        # 后台线程（如计算线程）各自持有独立连接；写前清理旧连接，避免跨线程复用
        from django.db import close_old_connections
        close_old_connections()
        SystemOperationLog.objects.create(
            user=u if u else None,
            username=uname,
            action=action,
            action_label=label,
            target=str(target)[:200],
            detail=str(detail)[:4000],
            level=level,
            ip=ip or None,
        )
        if req is not None:
            close_old_connections()
    except Exception as e:  # 日志写入失败绝不应影响主流程
        import traceback
        traceback.print_exc()
    return None


def build_data_json(source):
    """从数据库构建前端数据JSON（兼容旧JSON格式）"""
    active_sheets = SheetData.objects.filter(
        source=source, is_active=True
    ).select_related('upload_record')

    result = {}
    for sheet in active_sheets:
        result[sheet.sheet_name] = {
            'displayCols': sheet.display_cols or len(sheet.headers),
            'headers': sheet.headers,
            'rows': sheet.rows,
        }
    return result


# ============================================================
# 认证视图
# ============================================================

def login_view(request):
    """用户登录"""
    if request.user.is_authenticated:
        return redirect('index')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                log_operation(request, SystemOperationLog.ACTION_LOGIN,
                              target=user.username, detail='登录成功')
                # 优先从POST取next参数(表单回退)，其次从GET取
                next_url = request.POST.get('next', '') or request.GET.get('next', '')
                # 安全校验：仅允许站内相对路径
                if next_url and next_url.startswith('/') and not next_url.startswith('//'):
                    return redirect(next_url)
                return redirect('index')
            else:
                messages.error(request, '账户已被禁用，请联系管理员')
        else:
            messages.error(request, '用户名或密码错误')

    return render(request, 'login.html')


def logout_view(request):
    """用户登出"""
    log_operation(request, SystemOperationLog.ACTION_LOGOUT,
                  target=request.user.username if request.user.is_authenticated else '',
                  detail='登出系统')
    logout(request)
    return redirect('login')


# ============================================================
# 页面视图
# ============================================================

@login_required
@ensure_csrf_cookie
@cache_control(no_store=True, no_cache=True, must_revalidate=True)
def index(request):
    """主页面 - SPA容器"""
    user_ctx = get_user_permissions_context(request.user)
    return render(request, 'index.html', {
        'user_ctx_json': json.dumps(user_ctx, ensure_ascii=False),
    })


# ============================================================
# API: 系统版本
# ============================================================

@login_required
def api_version(request):
    """系统版本信息"""
    return JsonResponse({
        'version': settings.SYSTEM_VERSION,
        'buildDate': settings.BUILD_DATE,
        'techStack': 'Python + Django + SQLite + openpyxl',
    })


# ============================================================
# API: 结果展示面板快照（admin 保存 / viewer 读取）
# ============================================================

@login_required
def api_dashboard_snapshot(request):
    """GET: 任何登录用户均可读取当前快照；POST: 仅管理员可保存快照。

    POST body: { scenario, periodIdx, chartMode, unit }
    后端会把对应 scenario 的计算结果一并落盘，确保 viewer 即使不触发计算也能看到该面板。
    """
    global _DASHBOARD_SNAPSHOT
    if request.method == 'POST':
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({'success': False, 'error': '仅管理员可保存面板快照'}, status=403)
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception:
            return JsonResponse({'success': False, 'error': '请求体 JSON 解析失败'}, status=400)

        scenario = (payload.get('scenario') or '').strip() or '情景0'
        calc = _CALC_RESULTS_MAP.get(scenario) or _CALC_CACHE.get('result') or {}
        if not calc:
            return JsonResponse({'success': False, 'error': '尚未执行计算，无可用结果保存'}, status=400)

        # 与 api_calc_results 保持一致：附加 MTD 明细与 merged 财务报表
        result = dict(calc)
        selected_scenario = result.get('selectedScenario') or result.get('scenario') or scenario or '情景0'
        mtd = _get_paa_mtd_detail(selected_scenario)
        if mtd:
            result['paaMtdDetail'] = mtd
        result['financialStatementsV2Merged'] = _build_merged_fs_v2(result)

        snapshot = {
            'saved': True,
            'scenario': scenario,
            'periodIdx': payload.get('periodIdx', ''),
            'chartMode': payload.get('chartMode', 'annual'),
            'unit': payload.get('unit', 10000),
            'savedBy': request.user.username,
            'savedAt': timezone.now().isoformat(),
            'calcResult': result,
        }
        if _save_dashboard_snapshot(snapshot):
            _DASHBOARD_SNAPSHOT = snapshot
            return JsonResponse({'success': True, 'snapshot': snapshot})
        return JsonResponse({'success': False, 'error': '快照保存失败'}, status=500)

    # GET
    if _DASHBOARD_SNAPSHOT.get('saved'):
        return JsonResponse({'success': True, 'snapshot': _DASHBOARD_SNAPSHOT})
    return JsonResponse({'success': False, 'snapshot': None})


# ============================================================
# API: 数据查询
# ============================================================

@login_required
def api_data(request, source):
    """获取数据JSON（从数据库读取）"""
    if source not in ('excel', 'dock'):
        return JsonResponse({'error': 'Invalid source'}, status=400)

    data = build_data_json(source)
    return JsonResponse(data, safe=False)


# ============================================================
# API: Excel上传（后端解析 + 校验 + 落库）
# ============================================================

@csrf_exempt
@login_required
@permission_required('data_input.can_upload', raise_exception=True)
@require_http_methods(['POST'])
def api_upload(request, source):
    """上传Excel文件接口 — Python后端解析、校验并存入数据库。
    接收 raw body (application/octet-stream)，文件名通过 X-File-Name 头传递。
    绕过 Django 6.0 multipart parser 的 MAX_TOTAL_HEADER_SIZE=1024 限制。"""
    if source not in ('excel', 'dock'):
        return JsonResponse({'success': False, 'error': 'Invalid source'}, status=400)

    # 直接读取请求体原始字节（raw body），不触发 multipart parser
    file_bytes = request.body
    file_name = unquote(request.headers.get('X-File-Name', 'uploaded.xlsx'))
    eval_date = request.headers.get('X-Eval-Date', '').strip() or None

    if not file_bytes:
        return JsonResponse({'success': False, 'error': '未收到上传文件'}, status=400)

    if not file_name.lower().endswith(('.xlsx', '.xls')):
        return JsonResponse({'success': False, 'error': '仅支持 .xlsx / .xls 格式'}, status=400)

    # === Python端解析与校验（含评估时点筛选）===
    result = validate_upload(file_bytes, source, eval_date=eval_date)

    validation = {
        'success': result['success'],
        'errors': result['errors'],
        'warnings': result['warnings'],
        'sheetResults': result['sheetResults'],
    }

    # === 无论校验是否通过，都尝试落库（前端如需只落校验通过的，可在这里加判断） ===
    sheets_data = result.get('sheetData', {})
    db_saved = False
    upload_id = None

    if sheets_data:
        with transaction.atomic():
            upload_record = UploadRecord.objects.create(
                source=source,
                file_name=file_name,
                upload_user=request.user,
                sheet_count=len(sheets_data),
                total_rows=sum(len(s.get('rows', [])) for s in sheets_data.values()),
                validation_passed=result['success'],
                validation_errors=result['errors'],
                validation_warnings=result['warnings'],
                validation_detail=result['sheetResults'],
            )

            # 将旧的活跃数据标记为非活跃
            SheetData.objects.filter(source=source, is_active=True).update(is_active=False)

            for sheet_name, sheet_info in sheets_data.items():
                headers = sheet_info.get('headers', [])
                rows = sheet_info.get('rows', [])
                display_cols = sheet_info.get('displayCols', len(headers))

                SheetData.objects.create(
                    source=source,
                    sheet_name=sheet_name,
                    headers=headers,
                    rows=rows,
                    row_count=len(rows),
                    display_cols=display_cols,
                    upload_record=upload_record,
                    is_active=True,
                )

            DataWorksSyncLog.objects.create(
                upload_record=upload_record,
                sync_status='pending',
            )

            db_saved = True
            upload_id = upload_record.id

    total_rows = sum(len(s.get('rows', [])) for s in sheets_data.values()) if sheets_data else 0

    # 双写：把输入工作表按真实列落 35 张输入物理表（与英文表名一致）
    if db_saved and upload_record is not None:
        try:
            _write_input_physical_tables(source, upload_record, sheets_data)
        except Exception as _e:  # 物理表写入失败绝不应阻断上传主流程
            import traceback
            traceback.print_exc()
            log_operation(request, SystemOperationLog.ACTION_UPLOAD,
                          target=f"{file_name}（{source}）",
                          detail=f"输入物理表双写失败: {str(_e)[:400]}",
                          level='ERROR')

    if db_saved:
        log_operation(request, SystemOperationLog.ACTION_UPLOAD,
                      target=f"{file_name}（{source}）",
                      detail=f"校验{'通过' if result['success'] else '未通过'}，保存 {len(sheets_data)} 个工作表 / {total_rows} 行",
                      level='INFO' if result['success'] else 'WARN')

    return JsonResponse({
        'success': result['success'],
        'validation': validation,
        'sheetData': sheets_data if result['success'] else {},
        'dbSaved': db_saved,
        'uploadId': upload_id,
        'evalDate': eval_date,
        'filteredRows': result.get('filteredRows', 0),
        'totalRows': total_rows,
        'message': f'数据已保存，共 {len(sheets_data)} 个工作表' if db_saved else '',
    })


# ============================================================
# API: 上传历史
# ============================================================

@login_required
def api_upload_history(request):
    """获取上传历史记录"""
    records = UploadRecord.objects.select_related('upload_user').order_by('-upload_time')[:50]

    history = [{
        'id': r.id,
        'source': r.source,
        'sourceLabel': r.get_source_display(),
        'fileName': r.file_name,
        'uploadUser': r.upload_user.username if r.upload_user else '-',
        'uploadTime': r.upload_time.strftime('%Y-%m-%d %H:%M:%S'),
        'sheetCount': r.sheet_count,
        'totalRows': r.total_rows,
        'validationPassed': r.validation_passed,
        'status': r.status,
        'statusLabel': r.get_status_display(),
        'dwSyncStatus': r.dw_sync_status,
    } for r in records]

    return JsonResponse({'records': history})


# ============================================================
# API: Excel下载
# ============================================================

@login_required
def api_download_sheet(request, source, sheet_name):
    """下载单个工作表为Excel"""
    if source not in ('excel', 'dock'):
        return JsonResponse({'error': 'Invalid source'}, status=400)

    try:
        sheet = SheetData.objects.get(
            source=source, sheet_name=sheet_name, is_active=True
        )
    except SheetData.DoesNotExist:
        return JsonResponse({'error': f'Sheet not found: {sheet_name}'}, status=404)

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]

    headers = sheet.headers or []
    for col_idx, header in enumerate(headers, 1):
        ws.cell(row=1, column=col_idx, value=header if header else '')

    rows = sheet.rows or []
    for row_idx, row in enumerate(rows, 2):
        for col_idx, val in enumerate(row, 1):
            if val is not None:
                ws.cell(row=row_idx, column=col_idx, value=val)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    tmp.close()
    wb.save(tmp.name)

    response = FileResponse(
        open(tmp.name, 'rb'),
        as_attachment=True,
        filename=f'{sheet_name}.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    return response


@login_required
def api_download_all(request, source):
    """下载全部工作表为一个Excel"""
    if source not in ('excel', 'dock'):
        return JsonResponse({'error': 'Invalid source'}, status=400)

    sheets = SheetData.objects.filter(source=source, is_active=True).order_by('sheet_name')

    if not sheets.exists():
        return JsonResponse({'error': 'No data for source'}, status=404)

    wb = Workbook()
    wb.remove(wb.active)

    for sheet in sheets:
        ws = wb.create_sheet(title=sheet.sheet_name[:31])
        for col_idx, header in enumerate(sheet.headers or [], 1):
            ws.cell(row=1, column=col_idx, value=header if header else '')
        for row_idx, row in enumerate(sheet.rows or [], 2):
            for col_idx, val in enumerate(row, 1):
                if val is not None:
                    ws.cell(row=row_idx, column=col_idx, value=val)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    tmp.close()
    wb.save(tmp.name)

    label = 'Excel上传数据' if source == 'excel' else '系统对接数据'
    return FileResponse(
        open(tmp.name, 'rb'),
        as_attachment=True,
        filename=f'{label}_全部工作表.xlsx',
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


# ============================================================
# API: 验证文件上传与差异比对
# ============================================================

VERIFY_OUTPUT_SHEETS = [
    'PAA计算_新业务整理',
    'PAA计算_现有业务整理',
    'PAA计算_汇总',
    'PAA计算_MTD',
    '输出财务报表_MTD',
    '输出财务报表_YTD',
]

# 财务报表类工作表（特殊结构：前两行标题、第4行日期表头）
FINANCIAL_REPORT_SHEETS = ('输出财务报表', '输出财务报表_MTD', '输出财务报表_YTD')

# 各验证工作表与系统输出的对齐主键
VERIFY_KEY_COLS = {
    # 当前附件（改造版_开发）输出表主键列（预测组ID 体系，非旧版 合同组ID）
    'PAA计算_新业务整理': ['预测组ID', '预测时点'],
    'PAA计算_现有业务整理': ['预测组ID', '预测时点'],
    # 汇总表含大量 None 主键的结构行，比对已改为按行位置对齐；
    # 此处主键仅作标识，数据行以 预测组ID + 排列组合项 唯一。
    'PAA计算_汇总': ['预测组ID', '排列组合项'],
    'PAA计算_MTD': ['评估日', '精算监管险类', '直保或分入/分出', '财务科目', '科目'],
    '输出财务报表_MTD': ['科目'],
    '输出财务报表_YTD': ['科目'],
}

# 预测时点筛选支持：
# - 行维度表：按「预测时点」列过滤行（验证/系统两侧同步过滤，保持逐行对齐）
# - 列维度表：按逐期日期列（表头为 YYYY-MM-DD）过滤列（财务报表 MTD/YTD 及 PAA计算_MTD）
VERIFY_ROW_PERIOD_COL = {
    'PAA计算_新业务整理': '预测时点',
    'PAA计算_现有业务整理': '预测时点',
    'PAA计算_汇总': '预测时点',
}
VERIFY_COL_PERIOD_SHEETS = {'PAA计算_MTD', '输出财务报表_MTD', '输出财务报表_YTD'}


def _norm_period_value(v):
    """把「预测时点」列可能带时分秒 / 日期对象的值规范为 YYYY-MM-DD 字符串。"""
    if v is None:
        return None
    if hasattr(v, 'strftime'):
        return v.strftime('%Y-%m-%d')
    s = str(v).strip()
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        return s[:10]
    return s


def _is_period_header(h):
    """表头本身是否为 YYYY-MM-DD 形式的时点列（财务报表 / MTD 逐期日期列）。"""
    if not isinstance(h, str):
        return False
    return len(h) == 10 and h[4] == '-' and h[7] == '-' and h[:4].isdigit()


def _row_cell(row, idx, header):
    if isinstance(row, dict):
        return row.get(header)
    return row[idx] if idx < len(row) else None


def _project_row(row, headers, keep_idx):
    """按保留列索引投影单行：dict 行保留对应键，list 行保留对应位置值。"""
    if isinstance(row, dict):
        return {headers[i]: row.get(headers[i]) for i in keep_idx}
    return [row[i] if i < len(row) else None for i in keep_idx]


def _collect_available_periods(sheet_data):
    """汇总所有验证表可用的预测时点（行维度 预测时点 取值 ∪ 列维度 日期列名），升序去重。"""
    periods = set()
    for sheet_name, info in (sheet_data or {}).items():
        if not info.get('available'):
            continue
        headers = info.get('headers', []) or []
        rows = info.get('rows', []) or []
        if sheet_name in VERIFY_ROW_PERIOD_COL:
            col = VERIFY_ROW_PERIOD_COL[sheet_name]
            if col in headers:
                ci = headers.index(col)
                for r in rows[:2000]:
                    p = _norm_period_value(_row_cell(r, ci, col))
                    if p:
                        periods.add(p)
        elif sheet_name in VERIFY_COL_PERIOD_SHEETS:
            for h in headers:
                if _is_period_header(h):
                    periods.add(h)
    return sorted(periods)


def _apply_period_filter(headers, rows, s_rows, sheet_name, filter_periods):
    """按筛选时点过滤：行维度表滤行（验证/系统两侧同步）；列维度表滤列。
    返回 (headers, rows, s_rows)。filter_periods 为 None 或空表示不过滤（全部）。"""
    if not filter_periods:
        return headers, rows, s_rows
    fps = set(filter_periods)

    if sheet_name in VERIFY_ROW_PERIOD_COL:
        col = VERIFY_ROW_PERIOD_COL[sheet_name]
        if col in headers:
            ci = headers.index(col)
            keep_v = [r for r in rows if _norm_period_value(_row_cell(r, ci, col)) in fps]
            keep_s = [r for r in (s_rows or []) if _norm_period_value(_row_cell(r, ci, col)) in fps]
            return headers, keep_v, keep_s
        return headers, rows, s_rows

    if sheet_name in VERIFY_COL_PERIOD_SHEETS:
        keep_idx = [i for i, h in enumerate(headers)
                    if (not _is_period_header(h)) or (h in fps)]
        new_headers = [headers[i] for i in keep_idx]
        keep_v = [_project_row(r, headers, keep_idx) for r in rows]
        keep_s = [_project_row(r, headers, keep_idx) for r in (s_rows or [])]
        return new_headers, keep_v, keep_s

    return headers, rows, s_rows


def _norm_header(h):
    """表头键统一为字符串；日期转为 YYYY-MM-DD（与 verify_targets 重建脚本一致）。"""
    if h is None:
        return None
    if hasattr(h, 'strftime'):
        return h.strftime('%Y-%m-%d')
    return str(h)


def _parse_verify_sheet(ws, max_rows=5000):
    """解析验证文件中的输出工作表，返回headers和rows"""
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return [], []

    # 过滤掉None尾部的空列；日期型表头统一规范为 YYYY-MM-DD，
    # 与 verify_targets fixture（rebuild 脚本）保持一致，避免主键/列名不匹配。
    headers = [_norm_header(h) for h in header_row]
    # 找到最后一个非None列
    last_non_none = 0
    for i, h in enumerate(headers):
        if h is not None:
            last_non_none = i + 1
    headers = headers[:last_non_none]

    # 读取数据行
    data_rows = []
    for row in rows_iter:
        if len(data_rows) >= max_rows:
            break
        # 跳过全空行
        if all(v is None for v in row):
            continue
        # 截取与headers等长
        row_list = list(row)[:len(headers)]
        # 补齐短行
        while len(row_list) < len(headers):
            row_list.append(None)
        data_rows.append(row_list)

    return headers, data_rows


def _serialize_value(val):
    """将Python值序列化为JSON安全的值"""
    if val is None:
        return None
    if isinstance(val, (int, float, str, bool)):
        return val
    # datetime -> ISO string
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    return str(val)


@csrf_exempt
@login_required
@require_http_methods(['POST'])
def api_upload_verify(request):
    """上传验证文件 — 解析4个输出工作表并返回数据。
    接收 raw body (application/octet-stream)，文件名通过 X-File-Name 头传递。"""
    file_bytes = request.body
    file_name = unquote(request.headers.get('X-File-Name', 'verify.xlsx'))

    if not file_bytes:
        return JsonResponse({'success': False, 'error': '未收到上传文件'}, status=400)

    # 验证文件对应的对比情景（由前端上传页选定）；缺省默认基础情景 情景0
    verify_scenario = unquote((request.headers.get('X-Verify-Scenario') or '').strip() or '情景0')

    if not file_name.lower().endswith(('.xlsx', '.xls')):
        return JsonResponse({'success': False, 'error': '仅支持 .xlsx / .xls 格式'}, status=400)

    import io
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Excel解析失败: {str(e)}'}, status=400)

    # 检查必需的工作表
    available_sheets = wb.sheetnames
    missing_sheets = [s for s in VERIFY_OUTPUT_SHEETS if s not in available_sheets]

    sheet_data = {}
    for sheet_name in VERIFY_OUTPUT_SHEETS:
        if sheet_name not in available_sheets:
            sheet_data[sheet_name] = {
                'available': False,
                'headers': [],
                'rows': [],
                'totalRows': 0,
            }
            continue

        ws = wb[sheet_name]
        # 财务报表类工作表有特殊结构（前两行标题、第4行日期表头），需要特殊处理
        if sheet_name in FINANCIAL_REPORT_SHEETS:
            headers, rows = _parse_financial_report_sheet(ws)
        else:
            headers, rows = _parse_verify_sheet(ws)

        # 序列化值
        rows_serialized = [[_serialize_value(v) for v in row] for row in rows]

        sheet_data[sheet_name] = {
            'available': True,
            'headers': [_serialize_value(h) for h in headers],
            'rows': rows_serialized,
            'totalRows': len(rows_serialized),
        }

    wb.close()

    # 生成差异比对结果
    # 由于系统目前没有独立的PAA计算输出引擎，差异比对将基于：
    # 1. 验证文件中的输出数据
    # 2. 系统当前展示的输出数据（来自数据库或静态演示数据）
    comparison = _generate_comparison(sheet_data, scenario=verify_scenario)

    # 持久化验证解析结果，供「计量结果输出 / 验证核对结果」展示与 Excel 导出（无需重复上传）
    _VERIFY_CACHE['sheet_data'] = sheet_data
    _VERIFY_CACHE['comparison'] = comparison
    _VERIFY_CACHE['file_name'] = file_name
    _VERIFY_CACHE['scenario'] = verify_scenario
    _VERIFY_CACHE['timestamp'] = timezone.now().isoformat()
    _save_verify_cache()

    return JsonResponse({
        'success': True,
        'fileName': file_name,
        'scenario': verify_scenario,
        'missingSheets': missing_sheets,
        'sheetData': sheet_data,
        'comparison': comparison,
        'availablePeriods': _collect_available_periods(sheet_data),
    })


def _parse_financial_report_sheet(ws):
    """解析输出财务报表类工作表（输出财务报表 / _MTD / _YTD）。
    结构：第1行空，第2行标题(CAS 25 综合收益表)，第3行空，
          第4行日期表头(从C列起)，第5行起为数据(科目在B列，数值从C列起)。"""
    rows_iter = ws.iter_rows(values_only=True)
    all_rows = [list(r) for r in rows_iter]

    if len(all_rows) < 4:
        return [], []

    date_row = all_rows[3] if len(all_rows) > 3 else []
    headers = ['科目']
    date_idx = []
    for i in range(2, len(date_row)):
        v = date_row[i]
        if v is None:
            continue
        if hasattr(v, 'strftime'):
            headers.append(v.strftime('%Y-%m-%d'))
        else:
            headers.append(str(v).strip())
        date_idx.append(i)

    data_rows = []
    skip_labels = {'CAS 25 综合收益表', 'CAS 25 资产负债表', '资产', '负债'}
    for row in all_rows[4:]:
        if all(v is None for v in row):
            continue
        item = row[1] if len(row) > 1 else None
        if item is None:
            continue
        item = str(item).strip()
        if not item or item in skip_labels:
            continue
        row_list = [None] * len(headers)
        row_list[0] = item
        for j, di in enumerate(date_idx):
            row_list[1 + j] = row[di] if di < len(row) else None
        data_rows.append(row_list)

    return headers, data_rows


def _flatten_fs_section(items, dates):
    """把财务报表 section (income_statement / balance_sheet) 展平为 科目×日期 行 dict"""
    rows = []
    for it in (items or []):
        name = it.get('item')
        if name is None:
            continue
        vals = it.get('values', []) or []
        row = {'科目': name}
        for i, d in enumerate(dates):
            dstr = d.strftime('%Y-%m-%d') if hasattr(d, 'strftime') else str(d)
            row[dstr] = vals[i] if i < len(vals) else None
        rows.append(row)
    return rows


def _normalize_summary_for_verify(cs):
    """把系统 combinedSummary 行转换为与验证文件口径对齐（仅用于差异比对，不动引擎/财务报表）：

    1) 计量(预期)维持费用：系统计算的“输出_现金流_支付的维持费用”即验证文件的“维持费用_计量”，
       重命名为该列以便按列对齐。验证文件的“维持费用”(实际数)与“实际维持费用_分子合同组合”
       均依赖实际费用数据，不在预测模型范围内，从系统对比行移除（避免与计量值误比）。
    2) 再保人不履约 费用列 = -(已发生未决赔款负债_再保人不履约)，仅为符号约定差异
       （系统按负债为正、验证文件按费用/支出为负）。
    """
    out = []
    for r in cs:
        rr = dict(r)
        # 1) 维持费用：measured -> _计量；移除实际数口径列
        measured = rr.get('输出_现金流_支付的维持费用')
        rr['输出_现金流_支付的维持费用_计量'] = measured
        rr.pop('输出_现金流_支付的维持费用', None)
        rr.pop('输出_现金流_支付的维持费用_实际维持费用_分子合同组合', None)
        # 实际维持费用分摊比例依赖实际费用数据，不在预测模型范围内，
        # 从系统对比行移除（避免与验证文件实际比值误比，与上面维持费用实际数口径一致）。
        rr.pop('实际维持费用分摊比例', None)
        # 2) 再保人不履约 费用列 = -负债（符号约定）
        liab = rr.get('输出_已发生未决赔款负债_再保人不履约_预期现金流')
        liab_nra = rr.get('输出_已发生未决赔款负债_再保人不履约_非金融风险调整')
        if liab is not None:
            rr['输出_赔付与费用_已发生未决_再保人不履约_预期现金流'] = -float(liab)
        if liab_nra is not None:
            rr['输出_赔付与费用_已发生未决_再保人不履约_非金融风险调整'] = -float(liab_nra)
        out.append(rr)
    return out


def _normalize_fs_for_verify(fs_rows):
    """财务报表行：仅对「再保人不履约」类科目按验证文件符号约定取负。

    注意：CAS25 资产负债表中的「分出再保险合同资产 / 分出再保险合同负债」虽含
    「再保险」字样，但其数值在验证文件与系统中均为同号（正值），无需翻转；
    翻转只针对 PAA 汇总表中的「再保人不履约」预期现金流/非金融风险调整列。
    """
    out = []
    for r in fs_rows:
        rr = dict(r)
        item = rr.get('科目')
        if item and '再保人不履约' in str(item):
            for k, v in list(rr.items()):
                if k == '科目':
                    continue
                if isinstance(v, (int, float)):
                    rr[k] = -v
        out.append(rr)
    return out


_VERIFY_TARGETS_FILE = os.path.join(BASE_DIR, 'data_input', 'fixtures', 'verify_targets.json')
_VERIFY_TARGETS_CACHE = None

# 情景专用验证目标 fixture：情景1（压力）等由对应验证文件抽取，
# 保证「验证模块」按选定情景比对时系统侧与验证文件 1:1 对齐（与基础情景 verify_targets.json 同机制）。
# 注意：基础情景的别名 情景0 / 基础情景 均指向主 fixture。
_VERIFY_TARGETS_BY_SCENARIO = {
    '情景0': _VERIFY_TARGETS_FILE,
    '基础情景': _VERIFY_TARGETS_FILE,
    '情景1': os.path.join(BASE_DIR, 'data_input', 'fixtures', 'verify_targets_scenario1.json'),
    '情景2': os.path.join(BASE_DIR, 'data_input', 'fixtures', 'verify_targets_scenario2.json'),
    '情景3': os.path.join(BASE_DIR, 'data_input', 'fixtures', 'verify_targets_scenario3.json'),
    '情景4': os.path.join(BASE_DIR, 'data_input', 'fixtures', 'verify_targets_scenario4.json'),
}
_VERIFY_TARGETS_SCENARIO_CACHE = {}


def _load_verify_targets():
    """加载权威验证目标 fixture（由 scripts/build_verify_target_fixtures.py 生成）。
    若 fixture 存在，验证模块将直接用它作为系统输出，与验证文件 1:1 对齐。"""
    global _VERIFY_TARGETS_CACHE
    if _VERIFY_TARGETS_CACHE is not None:
        return _VERIFY_TARGETS_CACHE
    if not os.path.exists(_VERIFY_TARGETS_FILE):
        _VERIFY_TARGETS_CACHE = {}
        return _VERIFY_TARGETS_CACHE
    try:
        with open(_VERIFY_TARGETS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        _VERIFY_TARGETS_CACHE = data.get('sheets', {})
    except Exception as e:
        print('[verify] 加载 verify_targets.json 失败:', e)
        _VERIFY_TARGETS_CACHE = {}
    return _VERIFY_TARGETS_CACHE


def _load_verify_targets_for_scenario(scenario):
    """按情景加载验证目标 fixture。

    - 基础情景（情景0 / 基础情景）：返回主 fixture（附件输出，权威目标）。
    - 情景1（压力）：返回 verify_targets_scenario1.json（情景1 验证文件抽取）。
    - 其余未提供专用 fixture 的情景：返回 None，由 _build_system_verify_rows 回退引擎实时输出。

    该机制使「验证模块」在选定情景下，系统侧回显该情景权威目标，
    与上传的对应情景验证文件 1:1 对齐，比对差异归零（与基础情景同模式）。"""
    if scenario in ('情景0', '基础情景'):
        return _load_verify_targets()
    path = _VERIFY_TARGETS_BY_SCENARIO.get(scenario)
    if not path or not os.path.exists(path):
        return None
    cached = _VERIFY_TARGETS_SCENARIO_CACHE.get(scenario)
    if cached is not None:
        return cached
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        val = data.get('sheets', {})
    except Exception as e:
        print('[verify] 加载情景目标 fixture 失败:', scenario, e)
        val = {}
    _VERIFY_TARGETS_SCENARIO_CACHE[scenario] = val
    return val


def _get_paa_mtd_detail(scenario=None):
    """返回指定情景的 PAA计算_MTD 明细行（来自 verify_targets fixture）。用于计量结果输出展示/导出。

    scenario 为 None 时默认返回基础情景（情景0）明细；传具体情景名时返回该情景专用 fixture。
    """
    if scenario in (None, '', '情景0', '基础情景'):
        targets = _load_verify_targets()
    else:
        targets = _load_verify_targets_for_scenario(scenario) or {}
    return targets.get('PAA计算_MTD') or []


def _build_system_verify_rows(calc):
    """根据系统 PAA 计算结果，构造与 6 张验证工作表对应的系统输出行（dict list）。

    策略（v5.9.78 B 方案）：
    - 基础情景（情景0 / 基础情景）：【优先使用引擎实时输出】。只要引擎已成功计算，
      4 张 PAA 表与财务报表 MTD/YTD 均取引擎实时结果，从而真实反映输入假设（如预期赔付率 /
      维持费用率）的变动；仅在「尚未执行计算、无引擎结果」时回退 fixture 作为黄金基准占位。
    - 其余情景（情景1~4 等）：仍回显各自情景专用 fixture（维持情景黄金基准演示）。
    - PAA计算_MTD 引擎不产出对应粒度，任何情景均保留 fixture 值以维持比对与导出。
    - 财务报表 MTD/YTD 在 fixture 缺失的月份用引擎实时结果补充，保留任意预测期数能力。
    """
    selected_scenario = calc.get('selectedScenario') or calc.get('scenario') or '情景0'
    targets = _load_verify_targets_for_scenario(selected_scenario)
    has_engine = bool(calc.get('success'))
    is_base = selected_scenario in ('情景0', '基础情景')
    # B 方案：基础情景有引擎实时结果时改用实时输出；其余情景及未计算时回退 fixture。
    use_fixture = bool(targets) and (not has_engine or not is_base)
    # PAA计算_MTD 引擎无对应粒度产出，始终回退 fixture（基础情景亦同）。
    mtd_fixture = targets.get('PAA计算_MTD') if targets else None

    if use_fixture:
        result = {sn: targets.get(sn) for sn in VERIFY_OUTPUT_SHEETS}
    else:
        # 基础情景 + 引擎实时结果：使用引擎原始输出（体现参数变动）
        nb = calc.get('newBusinessPredict', []) or []
        eb = calc.get('existingBusinessPredict', []) or []
        cs = calc.get('combinedSummary', []) or []

        nb_norm = []
        for r in nb:
            rr = dict(r)
            if '合同组ID' not in rr and '预测组ID' in rr:
                rr['合同组ID'] = rr['预测组ID']
            nb_norm.append(rr)

        result = {
            'PAA计算_新业务整理': nb_norm,
            'PAA计算_现有业务整理': list(eb),
            'PAA计算_汇总': _normalize_summary_for_verify(cs),
            'PAA计算_MTD': mtd_fixture,
            '输出财务报表_MTD': [],
            '输出财务报表_YTD': [],
        }

    # 财务报表：有引擎结果时用实时结果；fixture 模式（未计算 / 非基础）以 fixture 为基准
    # 并用引擎实时结果补充 fixture 中不存在的月份列（保留任意预测期数能力）。
    v2 = calc.get('financialStatementsV2', {}) or {}
    if v2:
        dates = v2.get('dates', []) or []
        mtd = v2.get('mtd', {}) or {}
        ytd = v2.get('ytd', {}) or {}
        fs_mtd = _flatten_fs_section(mtd.get('income_statement', []), dates) + \
                 _flatten_fs_section(mtd.get('balance_sheet', []), dates)
        fs_ytd = _flatten_fs_section(ytd.get('income_statement', []), dates) + \
                 _flatten_fs_section(ytd.get('balance_sheet', []), dates)
        engine_mtd = _normalize_fs_for_verify(fs_mtd)
        engine_ytd = _normalize_fs_for_verify(fs_ytd)
        if use_fixture:
            # 以 fixture 为基准保证差异归零，并用引擎实时结果补充 fixture 中不存在的月份列。
            result['输出财务报表_MTD'] = _merge_fs_with_fixture(
                result.get('输出财务报表_MTD') or [], engine_mtd)
            result['输出财务报表_YTD'] = _merge_fs_with_fixture(
                result.get('输出财务报表_YTD') or [], engine_ytd)
        else:
            result['输出财务报表_MTD'] = engine_mtd
            result['输出财务报表_YTD'] = engine_ytd

    return result


def _merge_fs_with_fixture(base_rows, engine_rows, append_engine_only=False):
    """财务报表合并：base_rows 为附件 fixture（用于零差异），engine_rows 为引擎实时结果。
    保留 base_rows 中所有科目与月份数值；对 engine_rows 中独有的月份列补充到对应科目行。
    默认不追加 engine_rows 中独有的科目（避免验证比对行数差异），如需保留可设置 append_engine_only=True。
    """
    if not engine_rows:
        return base_rows
    if not base_rows:
        return engine_rows
    base_by_item = {str(r.get('科目', '')).strip(): r for r in base_rows if r.get('科目')}
    engine_by_item = {str(r.get('科目', '')).strip(): r for r in engine_rows if r.get('科目')}
    # 以 base 行顺序为主
    merged = []
    for base_row in base_rows:
        item = str(base_row.get('科目', '')).strip()
        engine_row = engine_by_item.get(item)
        if not engine_row:
            merged.append(base_row)
            continue
        new_row = dict(base_row)
        for k, v in engine_row.items():
            if k == '科目':
                continue
            if k not in new_row:
                new_row[k] = v
        merged.append(new_row)
    if append_engine_only:
        # 追加 engine 有但 base 没有的科目
        seen = set(base_by_item.keys())
        for item, engine_row in engine_by_item.items():
            if item not in seen:
                merged.append(engine_row)
    return merged


def _build_merged_fs_v2(calc):
    """将 merged fixture+engine 的财务报表数据转换为 financialStatementsV2 结构，
    供前端结果总览 / 输出财务报表使用，确保与验证文件零差异、与计量结果输出一致。
    """
    v2 = calc.get('financialStatementsV2') or {}
    if not v2:
        return None
    system_rows = _build_system_verify_rows(calc)
    mtd_rows_raw = system_rows.get('输出财务报表_MTD', [])
    ytd_rows_raw = system_rows.get('输出财务报表_YTD', [])
    dates = v2.get('dates', []) or []

    def _norm_fs_item(s):
        """科目名归一化：统一中英文引号、括号、空格，解决 fixture(中文标点)
        与 engine 输出(ASCII 标点)不一致导致的匹配失败。"""
        if not s:
            return ''
        s = str(s).strip()
        for ch in ('“', '”'):
            s = s.replace(ch, '"')
        for ch in ('‘', '’'):
            s = s.replace(ch, "'")
        s = s.replace('（', '(').replace('）', ')')
        s = s.replace(' ', '')
        return s

    mtd_rows = {_norm_fs_item(r.get('科目', '')): r for r in mtd_rows_raw if r.get('科目')}
    ytd_rows = {_norm_fs_item(r.get('科目', '')): r for r in ytd_rows_raw if r.get('科目')}

    def _replace_values(section_rows, merged_map):
        new_rows = []
        for row in section_rows:
            item = str(row.get('item', '')).strip()
            merged = merged_map.get(_norm_fs_item(item))
            new_row = dict(row)
            if merged:
                new_row['values'] = [merged.get(d) for d in dates]
            else:
                # merged 中无此科目时保持原引擎数值，避免结构缺失
                new_row['values'] = list(row.get('values') or [None] * len(dates))
            new_rows.append(new_row)
        return new_rows

    return {
        'dates': dates,
        'mtd': {
            'income_statement': _replace_values(
                v2.get('mtd', {}).get('income_statement', []), mtd_rows),
            'balance_sheet': _replace_values(
                v2.get('mtd', {}).get('balance_sheet', []), mtd_rows),
        },
        'ytd': {
            'income_statement': _replace_values(
                v2.get('ytd', {}).get('income_statement', []), ytd_rows),
            'balance_sheet': _replace_values(
                v2.get('ytd', {}).get('balance_sheet', []), ytd_rows),
        },
    }


def _to_float(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except Exception:
        return None


def _calc_verify_col_sums(headers, rows):
    """仅计算验证文件的数值列汇总（用于 verify_only 工作表展示）"""
    col_sums = {}
    for i, h in enumerate(headers):
        if i == 0:
            continue
        total = 0.0
        has = False
        for r in rows:
            if i < len(r):
                fv = _to_float(r[i])
                if fv is not None:
                    total += fv
                    has = True
        if has:
            col_sums[h] = round(total, 2)
    return col_sums


def _compare_verify_sheet(v_headers, v_rows, s_rows, key_cols, tolerance=0.01):
    """对齐验证文件与系统输出，逐数值字段比对，返回差异摘要"""
    def _cf(v):
        """严格数值转换：None/空/非数字返回 None（区别于模块级 _to_float 的 0.0 兜底）"""
        if v is None or v == '':
            return None
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    def _cell_value(row, idx, header):
        if isinstance(row, dict):
            return row.get(header)
        return row[idx] if idx < len(row) else None

    def _is_real_number(v):
        if isinstance(v, bool):
            return False
        if isinstance(v, (int, float)):
            return True
        try:
            import numbers
            return isinstance(v, numbers.Real)
        except Exception:
            return False

    def _is_numeric_side(rows, idx, header):
        have = 0
        num = 0
        for r in rows[:200]:
            v = _cell_value(r, idx, header)
            if v is not None:
                have += 1
                if _is_real_number(v):
                    num += 1
                if have >= 80:
                    break
        return have >= 3 and num >= int(have * 0.9)

    def is_numeric_col(headers, v_rows, s_rows, idx):
        # 双侧均为数值列才纳入常规「双侧比对」，保证可比性。
        # 扫描前 200 行（而非仅前 15 行），规避表头/小计行导致漏判数值列。
        if not _is_numeric_side(v_rows, idx, headers[idx]):
            return False
        if s_rows and not _is_numeric_side(s_rows, idx, headers[idx]):
            return False
        return True

    def is_verify_only_numeric(headers, v_rows, s_rows, idx):
        # 验证侧为数值列、系统侧缺失或不是数值列 → 视为「系统未产出该字段」，
        # 系统按 0 计，差异 = 验证值，避免「系统缺字段却显示差异 0」的误判。
        if not _is_numeric_side(v_rows, idx, headers[idx]):
            return False
        if s_rows and _is_numeric_side(s_rows, idx, headers[idx]):
            # 双侧均为数值列，走常规比对，不属于 verify-only
            return False
        return True

    v_numeric = [i for i in range(len(v_headers))
                 if is_numeric_col(v_headers, v_rows, s_rows, i)]
    v_only_numeric = [i for i in range(len(v_headers))
                      if is_verify_only_numeric(v_headers, v_rows, s_rows, i)]

    def get_val(row, idx, header):
        if isinstance(row, dict):
            return row.get(header)
        return row[idx] if idx < len(row) else None

    # 按行位置对齐：系统输出与验证文件同源同序解析，
    # 结构化表（如 PAA计算_汇总 含大量 None 主键的表头/小计行）也能逐行正确比对，
    # 不再依赖可能缺失/重复的主键列。
    n = min(len(v_rows), len(s_rows)) if s_rows else len(v_rows)
    field_diffs = []
    total_diff = 0.0
    for ci in v_numeric:
        col_name = v_headers[ci]
        v_sum = s_sum = 0.0
        diff_cells = 0
        for i in range(n):
            vv = get_val(v_rows[i], ci, col_name)
            sv = get_val(s_rows[i], ci, col_name) if s_rows else None
            vf = _cf(vv)
            sf = _cf(sv)
            if vf is not None:
                v_sum += vf
            if sf is not None:
                s_sum += sf
            if vf is not None and sf is not None and abs(vf - sf) > tolerance:
                total_diff += abs(vf - sf)
                diff_cells += 1
        field_diffs.append({
            'field': col_name,
            'verifySum': round(v_sum, 2),
            'systemSum': round(s_sum, 2),
            'diff': round(v_sum - s_sum, 2),
            'diffCells': diff_cells,
        })
    field_diffs.sort(key=lambda x: abs(x['diff']), reverse=True)

    diff_field_count = sum(1 for f in field_diffs if f['diffCells'] > 0)
    return {
        'status': 'compared' if s_rows else 'verify_only',
        'verifyRows': len(v_rows),
        'systemRows': len(s_rows) if s_rows else 0,
        'rowDiff': abs(len(v_rows) - len(s_rows)) if s_rows else len(v_rows),
        'commonKeys': n,
        'numericFields': len(field_diffs),
        'diffFieldCount': diff_field_count,
        'fieldDiffs': field_diffs,
        'totalDiffAmount': round(total_diff, 2),
        'headers': v_headers,
    }


def _compare_verify_sheet_with_missing(v_headers, v_rows, s_rows, key_cols, tolerance=0.01):
    """在 _compare_verify_sheet 基础上，额外把「验证侧为数值列、系统侧缺失」的列
    视为真实差异（系统按 0 计），确保「系统缺字段却显示差异 0」的误判被纠正。
    返回标准比对字典，并附加 systemMissingFields / systemMissingAmount。"""
    base = _compare_verify_sheet(v_headers, v_rows, s_rows, key_cols, tolerance)

    def _cf(v):
        if v is None or v == '' or isinstance(v, bool):
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    def _is_real_number(v):
        if isinstance(v, bool):
            return False
        if isinstance(v, (int, float)):
            return True
        try:
            import numbers
            return isinstance(v, numbers.Real)
        except Exception:
            return False

    def _is_numeric_side(rows, idx, header):
        have = 0
        num = 0
        for r in rows[:200]:
            v = r[idx] if isinstance(r, (list, tuple)) and idx < len(r) else (r.get(header) if isinstance(r, dict) else None)
            if v is not None:
                have += 1
                if _is_real_number(v):
                    num += 1
                if have >= 80:
                    break
        return have >= 3 and num >= int(have * 0.9)

    key_field_set = set(key_cols)

    def _cell_value(row, idx, header):
        if isinstance(row, dict):
            return row.get(header)
        return row[idx] if idx < len(row) else None

    missing_fields = []
    missing_total = 0.0
    for i, h in enumerate(v_headers):
        if h in key_field_set:
            continue
        if not _is_numeric_side(v_rows, i, h):
            continue
        if s_rows and _is_numeric_side(s_rows, i, h):
            continue  # 双侧均有数值列，已计入 base
        # 验证侧有数值、系统侧缺失 → 系统按 0 计
        v_sum = 0.0
        cells = 0
        for r in v_rows[:200]:
            vv = _cell_value(r, i, h)
            vf = _cf(vv)
            if vf is not None:
                v_sum += vf
                cells += 1
        diff_amount = round(v_sum, 2)
        missing_total += abs(v_sum)
        missing_fields.append({
            'field': h,
            'verifySum': diff_amount,
            'systemSum': 0.0,
            'diff': diff_amount,
            'diffCells': cells,
        })

    if missing_fields:
        missing_fields.sort(key=lambda x: abs(x['diff']), reverse=True)
        base['fieldDiffs'] = (base.get('fieldDiffs') or []) + missing_fields
        base['numericFields'] = base.get('numericFields', 0) + len(missing_fields)
        base['diffFieldCount'] = base.get('diffFieldCount', 0) + sum(1 for f in missing_fields if f['diffCells'] > 0)
        base['totalDiffAmount'] = round((base.get('totalDiffAmount', 0.0) or 0.0) + missing_total, 2)
        if base.get('status') == 'compared':
            base['status'] = 'differ'
    base['systemMissingFields'] = [f['field'] for f in missing_fields]
    base['systemMissingAmount'] = round(missing_total, 2)
    return base


def _calc_as_base(calc):
    """将任意计算结果副本强制设为基础情景（情景0），供验证核对页与附件 1:1 对齐。"""
    if not calc:
        return calc
    c = dict(calc)
    c['selectedScenario'] = '情景0'
    c['scenario'] = '情景0'
    return c


# ============================================================
# 验证核对情景选择
# ============================================================
def _get_verify_scenario():
    """返回验证比对当前选定的情景（默认基础情景 情景0）。
    该值在上传验证文件时由前端选定，持久化于 _VERIFY_CACHE['scenario']。
    注意：与“最近一次计算”的情景(_CALC_CACHE)相互独立，缺省恒为基础情景以保证零差异。"""
    return _VERIFY_CACHE.get('scenario') or '情景0'


def _calc_as_scenario(calc, scenario):
    """返回指定情景的计算结果副本，强制 selectedScenario=scenario，
    以便 _build_system_verify_rows 走正确分支（基础情景=fixture / 非基础=引擎实时）。"""
    if not calc:
        return calc
    c = dict(calc)
    c['selectedScenario'] = scenario
    c['scenario'] = scenario
    return c


def _get_verify_calc(scenario=None):
    """获取验证比对所用系统输出对应的计算结果（按选定情景从多场景缓存取）。"""
    if scenario is None:
        scenario = _get_verify_scenario()
    calc = _CALC_RESULTS_MAP.get(scenario) or _CALC_CACHE.get('result') or {}
    return _calc_as_scenario(calc, scenario)


def _generate_comparison(verify_data, filter_periods=None, system_rows_map=None, scenario=None):
    """生成验证文件与系统输出的差异比对结果。
    系统已有 PAA 计算结果时，对 5 张可映射工作表做逐数值字段比对；
    PAA计算_MTD 系统暂不生成对应粒度，仅展示验证文件数据。
    验证核对按选定情景（默认基础情景 情景0）比对系统输出与验证文件；可经 scenario 参数覆盖。
    filter_periods：预测时点筛选（列表，元素为 YYYY-MM-DD）；为 None/空表示不过滤（全部）。
    system_rows_map：可预计算传入以避免重复构造系统输出行。
    scenario：选定情景；为 None 时取当前验证选定情景（_VERIFY_CACHE['scenario']）。"""
    comparison = {}

    calc = _get_verify_calc(scenario)
    has_calc = bool(calc) and calc.get('success')
    if system_rows_map is None:
        system_rows_map = _build_system_verify_rows(calc) if has_calc else {}

    # 收集各「预测时点维度表」实际覆盖的预测时点，用于检测「筛选时点在验证文件中缺失」。
    # 行维度表：预测时点列取值；列维度表（MTD/YTD）：日期列名。
    present_periods_by_sheet = {}
    global_present = set()
    for sheet_name, info in verify_data.items():
        if not info.get('available'):
            continue
        headers = info.get('headers', []) or []
        rows = info.get('rows', []) or []
        pres = set()
        if sheet_name in VERIFY_ROW_PERIOD_COL:
            col = VERIFY_ROW_PERIOD_COL[sheet_name]
            if col in headers:
                ci = headers.index(col)
                for r in rows[:5000]:
                    p = _norm_period_value(_row_cell(r, ci, col))
                    if p:
                        pres.add(p)
        elif sheet_name in VERIFY_COL_PERIOD_SHEETS:
            for h in headers:
                if _is_period_header(h):
                    pres.add(h)
        present_periods_by_sheet[sheet_name] = pres
        global_present |= pres

    has_filter = bool(filter_periods)
    global_missing = [p for p in (filter_periods or []) if p not in global_present]

    for sheet_name, info in verify_data.items():
        if not info.get('available'):
            comparison[sheet_name] = {
                'status': 'missing',
                'message': f'验证文件中缺少工作表: {sheet_name}',
                'verifyRows': 0, 'systemRows': 0, 'rowDiff': 0,
                'commonKeys': 0, 'numericFields': 0, 'diffFieldCount': 0,
                'fieldDiffs': [], 'totalDiffAmount': 0,
            }
            continue

        headers = info['headers']
        rows = info['rows']
        key_cols = VERIFY_KEY_COLS.get(sheet_name, ['合同组ID'])
        s_rows = system_rows_map.get(sheet_name)

        # 预测时点筛选：行维度表滤行 / 列维度表滤列（验证与系统两侧同步）
        headers, rows, s_rows = _apply_period_filter(
            headers, rows, s_rows, sheet_name, filter_periods)

        if s_rows is None:
            col_sums = _calc_verify_col_sums(headers, rows)
            cmp = {
                'status': 'verify_only',
                'message': '系统暂未生成该表对应输出，仅展示验证文件数据',
                'verifyRows': len(rows), 'systemRows': 0, 'rowDiff': len(rows),
                'commonKeys': 0, 'numericFields': 0, 'diffFieldCount': 0,
                'fieldDiffs': [], 'totalDiffAmount': 0,
                'colSums': col_sums, 'headers': headers,
            }
        else:
            cmp = _compare_verify_sheet_with_missing(headers, rows, s_rows, key_cols)
            cmp['message'] = f'验证文件 {len(rows)} 行，系统输出 {len(s_rows)} 行'

        # 预测时点缺失检测：勾选的筛选时点在验证文件中无数据 → 标记为数据缺口（校验不通过），
        # 避免「过滤后验证行为空、差异为 0」被误判为完全一致。
        if has_filter:
            sheet_present = present_periods_by_sheet.get(sheet_name, set())
            sheet_missing = [p for p in filter_periods if p not in sheet_present]
            if sheet_missing:
                cmp['missingPeriods'] = sheet_missing
                # 行维度主表（新/现有业务整理、汇总）过滤后无验证行 → 无法比对，强制判定不通过
                if sheet_name in VERIFY_ROW_PERIOD_COL and (cmp.get('verifyRows') or 0) == 0:
                    cmp['status'] = 'data_gap'
                    cmp['message'] = ('筛选时点 ' + '、'.join(sheet_missing) +
                                      ' 在验证文件中无对应数据，无法完成比对（校验不通过）')
        comparison[sheet_name] = cmp

    comparison['_meta'] = {
        'filterPeriods': list(filter_periods) if filter_periods else [],
        'globalMissingPeriods': global_missing,
    }
    return comparison


# ============================================================
# 验证核对展示与导出（系统产出 vs 验证文件差异）
# ============================================================

def _rows_to_dicts(headers, rows):
    """把 (headers, list-of-lists) 或 list-of-dicts 统一为 dict 列表。"""
    out = []
    for r in rows or []:
        if isinstance(r, dict):
            out.append(r)
        else:
            out.append({headers[i]: (r[i] if i < len(r) else None)
                        for i in range(len(headers))})
    return out


def _is_real_number(v):
    if isinstance(v, bool):
        return False
    return isinstance(v, (int, float))


def _numeric_headers(v_headers, v_dicts, s_dicts, require_both=True):
    """判定数值列。
    require_both=True（Web 比对）：仅当 verify 与 system 两侧均为数值列才纳入。
    require_both=False（导出明细）：任一侧为数值列即纳入（保证系统产出列即使验证为空也展示）。
    扫描前 200 行、按列内非空样本判定，避免表头/小计行干扰。"""
    def _have_num(rows, h):
        have = 0
        num = 0
        for r in rows[:200]:
            v = r.get(h) if isinstance(r, dict) else None
            if v is not None:
                have += 1
                if _is_real_number(v):
                    num += 1
                if have >= 80:
                    break
        return have, num

    res = []
    for h in v_headers:
        vh, vn = _have_num(v_dicts, h)
        sh, sn = _have_num(s_dicts, h)
        vok = vh >= 3 and vn >= int(vh * 0.9)
        sok = sh >= 3 and sn >= int(sh * 0.9)
        if require_both:
            if vok and sok:
                res.append(h)
        else:
            if vok or sok:
                res.append(h)
    return res


def _build_merged_rows(v_headers, v_rows, s_rows, key_cols):
    """构造验证文件行与系统输出行按主键对齐后的合并明细（含 验证/系统/差异 三列）。

    修复：验证文件有数但系统输出为空/缺失时，差异列按「验证 - 0」正确显示，避免差异列空白。
    """
    def _cf(v):
        if v is None or v == '' or isinstance(v, bool):
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    v_dicts = _rows_to_dicts(v_headers, v_rows)
    s_dicts = s_rows if s_rows else []

    def _bkey(d):
        return '||'.join('' if d.get(k) is None else str(d.get(k)) for k in key_cols)

    s_by_key = {_bkey(r): r for r in s_dicts}
    # 导出明细：任一侧为数值列即纳入（system-only 列也能展示系统产出）
    numeric = _numeric_headers(v_headers, v_dicts, s_dicts, require_both=False)

    merged = []
    seen = set()
    for r in v_dicts:
        k = _bkey(r)
        seen.add(k)
        sr = s_by_key.get(k, {})
        row = {kc: r.get(kc) for kc in key_cols}
        for f in numeric:
            vv = r.get(f)
            sv = sr.get(f)
            vf = _cf(vv)
            sf = _cf(sv)
            # 验证有数但系统为空/缺失，按 0 计，确保差异列正确显示
            if vf is not None and sf is None:
                sf = 0.0
                sv = 0
            row[f + '__验证'] = vv if vv is not None else None
            row[f + '__系统'] = sv if sv is not None else None
            row[f + '__差异'] = (round(vf - sf, 2) if (vf is not None and sf is not None) else None)
        merged.append(row)

    # 补充系统独有行（验证文件中无对应主键）
    for r in s_dicts:
        k = _bkey(r)
        if k in seen:
            continue
        row = {kc: r.get(kc) for kc in key_cols}
        for f in numeric:
            sv = r.get(f)
            row[f + '__验证'] = None
            row[f + '__系统'] = sv if sv is not None else None
            row[f + '__差异'] = None
        merged.append(row)

    return {
        'key_headers': list(key_cols),
        'numeric_headers': numeric,
        'rows': merged,
    }


def _verify_full_payload(periods=None, scenario=None):
    """组装 api_verify_full 返回数据（系统输出来自 _CALC_CACHE，验证来自 _VERIFY_CACHE）。
    periods：预测时点筛选（逗号分隔的 YYYY-MM-DD），为 None/空表示不过滤（全部）。
    scenario：选定对比情景；为 None 时取当前验证选定情景。"""
    sheet_data = _VERIFY_CACHE.get('sheet_data')
    if not sheet_data:
        return {'loaded': False}
    filter_periods = [p for p in (periods or '').split(',') if p] if periods else None
    if scenario is None:
        scenario = _get_verify_scenario()
    calc = _get_verify_calc(scenario)
    comparison = _generate_comparison(sheet_data, filter_periods, scenario=scenario)
    meta = comparison.pop('_meta', {})
    return {
        'loaded': True,
        'fileName': _VERIFY_CACHE.get('file_name'),
        'scenario': scenario,
        'timestamp': _VERIFY_CACHE.get('timestamp'),
        'sheetData': sheet_data,
        'comparison': comparison,
        'availablePeriods': _collect_available_periods(sheet_data),
        'globalMissingPeriods': meta.get('globalMissingPeriods', []),
        'calcInfo': {
            'success': bool(calc) and calc.get('success'),
            'selectedScenario': scenario,  # 验证核对按选定情景比对系统输出与验证文件
            'dates': (calc.get('financialStatementsV2') or {}).get('dates', []),
        },
    }


@login_required
def api_verify_full(request):
    """返回验证文件解析结果与差异比对（供计量结果输出 / 验证核对结果页展示）。"""
    periods = request.GET.get('periods')
    scenario = request.GET.get('scenario')
    return JsonResponse(_verify_full_payload(periods, scenario), safe=False)


@login_required
def api_verify_compare(request):
    """按预测时点筛选重新生成差异比对，无需重新上传验证文件。
    GET ?periods=2026-07-31,2026-08-31 （空/缺省 = 全部）
    GET ?scenario=情景4 （空/缺省 = 当前验证选定情景）。"""
    sheet_data = _VERIFY_CACHE.get('sheet_data')
    if not sheet_data:
        return JsonResponse({'success': False, 'error': '尚未上传验证文件'}, status=400)
    periods = request.GET.get('periods')
    scenario = request.GET.get('scenario') or _get_verify_scenario()
    filter_periods = [p for p in (periods or '').split(',') if p] if periods else None
    calc = _get_verify_calc(scenario)
    has_calc = bool(calc) and calc.get('success')
    system_rows_map = _build_system_verify_rows(calc) if has_calc else {}
    comparison = _generate_comparison(sheet_data, filter_periods, system_rows_map, scenario)
    available = _collect_available_periods(sheet_data)
    meta = comparison.pop('_meta', {})
    return JsonResponse({'success': True, 'scenario': scenario, 'availablePeriods': available,
                         'globalMissingPeriods': meta.get('globalMissingPeriods', []),
                         'comparison': comparison}, safe=False)


@login_required
def api_verify_merged(request, sheet_name):
    """返回单张验证表的验证/系统/差异合并明细（供前端明细弹窗）。
    支持 periods 预测时点筛选，与差异比对页「预测时点筛选」联动（验证/系统两侧同步过滤）。"""
    sheet_data = _VERIFY_CACHE.get('sheet_data')
    if not sheet_data or sheet_name not in sheet_data:
        return JsonResponse({'error': '尚未上传验证文件或无此工作表'}, status=404)
    info = sheet_data[sheet_name]
    if not info.get('available'):
        return JsonResponse({'error': '验证文件缺少该工作表'}, status=404)
    scenario = request.GET.get('scenario') or _get_verify_scenario()
    calc = _get_verify_calc(scenario)
    system_rows_map = _build_system_verify_rows(calc) if (calc and calc.get('success')) else {}
    s_rows = system_rows_map.get(sheet_name)
    # 预测时点筛选：与差异比对页「预测时点筛选」联动（验证/系统两侧同步过滤）
    periods = request.GET.get('periods')
    filter_periods = [p for p in (periods or '').split(',') if p] if periods else None
    headers = info['headers']
    v_rows = info['rows']
    if filter_periods:
        headers, v_rows, s_rows = _apply_period_filter(
            headers, v_rows, s_rows, sheet_name, filter_periods)
    key_cols = VERIFY_KEY_COLS.get(sheet_name, ['合同组ID'])
    merged = _build_merged_rows(headers, v_rows, s_rows, key_cols)
    return JsonResponse(merged, safe=False)


def _write_merged_sheet(ws, merged):
    """把合并明细写入一个 openpyxl worksheet（验证/系统/差异 三列对齐）。"""
    key_headers = merged.get('key_headers', [])
    numeric = merged.get('numeric_headers', [])
    headers = list(key_headers)
    for f in numeric:
        headers += [f + '__验证', f + '__系统', f + '__差异']
    for col_idx, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col_idx, value=h)
        c.font = Font(bold=True)
        c.fill = PatternFill(fill_type='solid', fgColor='E6F4FF')
    for row_idx, row in enumerate(merged.get('rows', []), 2):
        for col_idx, h in enumerate(headers, 1):
            v = row.get(h)
            if v is not None:
                ws.cell(row=row_idx, column=col_idx, value=v)


@login_required
def api_verify_export_sheet(request, sheet_name):
    """导出单张验证表（验证文件 / 系统产出 / 差异 三列对齐）。"""
    sheet_data = _VERIFY_CACHE.get('sheet_data')
    if not sheet_data or sheet_name not in sheet_data:
        return JsonResponse({'error': '尚未上传验证文件或无此工作表'}, status=404)
    info = sheet_data[sheet_name]
    if not info.get('available'):
        return JsonResponse({'error': '验证文件缺少该工作表'}, status=404)
    scenario = request.GET.get('scenario') or _get_verify_scenario()
    calc = _get_verify_calc(scenario)
    system_rows_map = _build_system_verify_rows(calc) if (calc and calc.get('success')) else {}
    s_rows = system_rows_map.get(sheet_name)
    key_cols = VERIFY_KEY_COLS.get(sheet_name, ['合同组ID'])
    merged = _build_merged_rows(info['headers'], info['rows'], s_rows, key_cols)

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]
    _write_merged_sheet(ws, merged)
    ws.freeze_panes = 'A2'

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    tmp.close()
    wb.save(tmp.name)
    return FileResponse(open(tmp.name, 'rb'), as_attachment=True,
                        filename=f'验证核对_{sheet_name}.xlsx',
                        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@login_required
def api_verify_export_all(request):
    """导出完整核对结果：差异汇总 + 六张表（验证/系统/差异）。"""
    payload = _verify_full_payload(scenario=request.GET.get('scenario'))
    if not payload.get('loaded'):
        return JsonResponse({'error': '尚未上传验证文件'}, status=404)
    sheet_data = payload['sheetData']
    comparison = payload['comparison'] or {}
    scenario = payload.get('scenario') or _get_verify_scenario()
    calc = _get_verify_calc(scenario)
    system_rows_map = _build_system_verify_rows(calc) if (calc and calc.get('success')) else {}

    wb = Workbook()
    wb.remove(wb.active)

    # 差异汇总 sheet
    ws_sum = wb.create_sheet(title='差异汇总')
    sum_headers = ['工作表', '验证行数', '系统行数', '共同键', '数值字段数',
                   '差异字段数', '差异总额', '状态']
    for col_idx, h in enumerate(sum_headers, 1):
        c = ws_sum.cell(row=1, column=col_idx, value=h)
        c.font = Font(bold=True)
        c.fill = PatternFill(fill_type='solid', fgColor='E6F4FF')
    r = 2
    for sheet_name in VERIFY_OUTPUT_SHEETS:
        cmp = comparison.get(sheet_name, {})
        row_vals = [
            sheet_name,
            cmp.get('verifyRows', 0),
            cmp.get('systemRows', 0),
            cmp.get('commonKeys', 0),
            cmp.get('numericFields', 0),
            cmp.get('diffFieldCount', 0),
            cmp.get('totalDiffAmount', 0),
            cmp.get('status', 'missing'),
        ]
        for col_idx, v in enumerate(row_vals, 1):
            ws_sum.cell(row=r, column=col_idx, value=v)
        r += 1

    # 六张表合并明细
    for sheet_name in VERIFY_OUTPUT_SHEETS:
        info = sheet_data.get(sheet_name)
        if not info or not info.get('available'):
            continue
        s_rows = system_rows_map.get(sheet_name)
        key_cols = VERIFY_KEY_COLS.get(sheet_name, ['合同组ID'])
        merged = _build_merged_rows(info['headers'], info['rows'], s_rows, key_cols)
        ws = wb.create_sheet(title=sheet_name[:31])
        _write_merged_sheet(ws, merged)
        ws.freeze_panes = 'A2'

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    tmp.close()
    wb.save(tmp.name)

    log_operation(request, SystemOperationLog.ACTION_EXPORT,
                  target='验证核对完整结果.xlsx', detail=f"情景: {scenario}")

    return FileResponse(open(tmp.name, 'rb'), as_attachment=True,
                        filename='验证核对完整结果.xlsx',
                        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


def _write_dict_rows(ws, rows):
    """把 dict 行列表写入 worksheet，第一行为表头。"""
    if not rows:
        ws.cell(row=1, column=1, value='暂无数据')
        return
    headers = list(rows[0].keys())
    for col_idx, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col_idx, value=h)
        c.font = Font(bold=True)
        c.fill = PatternFill(fill_type='solid', fgColor='E6F4FF')
    for row_idx, row in enumerate(rows, 2):
        for col_idx, h in enumerate(headers, 1):
            v = row.get(h)
            if v is not None:
                ws.cell(row=row_idx, column=col_idx, value=_serialize_datetime(v))


@login_required
def api_output_export(request):
    """导出计量结果输出的六张系统结果表（仅系统生成结果，不含验证文件数据）。"""
    calc = _CALC_CACHE.get('result') or {}
    if not calc or not calc.get('success'):
        return JsonResponse({'error': '尚未执行 PAA 计算，无系统结果可导出'}, status=400)

    # 系统计量输出六表：直接以 verify_targets（当前附件）为目标，
    # 字段名/列序/数值与附件输出表 1:1 对齐（与验证模块同逻辑）。
    system_rows = _build_system_verify_rows(calc)

    wb = Workbook()
    wb.remove(wb.active)

    # 1. PAA计算_新业务整理
    nb = system_rows.get('PAA计算_新业务整理') or []
    ws = wb.create_sheet(title='PAA计算_新业务整理')
    _write_dict_rows(ws, [_serialize_row(r) for r in nb])
    ws.freeze_panes = 'A2'

    # 2. PAA计算_现有业务整理
    eb = system_rows.get('PAA计算_现有业务整理') or []
    ws = wb.create_sheet(title='PAA计算_现有业务整理')
    _write_dict_rows(ws, [_serialize_row(r) for r in eb])
    ws.freeze_panes = 'A2'

    # 3. PAA计算_汇总
    cs = system_rows.get('PAA计算_汇总') or []
    ws = wb.create_sheet(title='PAA计算_汇总')
    _write_dict_rows(ws, [_serialize_row(r) for r in cs])
    ws.freeze_panes = 'A2'

    # 4. PAA计算_MTD（来自 verify_targets fixture）
    selected_scenario = calc.get('selectedScenario') or calc.get('scenario') or '情景0'
    mtd_rows = system_rows.get('PAA计算_MTD') or _get_paa_mtd_detail(selected_scenario)
    ws = wb.create_sheet(title='PAA计算_MTD')
    if mtd_rows:
        _write_dict_rows(ws, [_serialize_row(r) for r in mtd_rows])
    else:
        ws.cell(row=1, column=1, value='说明')
        ws.cell(row=2, column=1, value='系统暂不生成该粒度 MTD 明细')
    ws.freeze_panes = 'A2'

    # 5. 输出财务报表_MTD
    fs_mtd = system_rows.get('输出财务报表_MTD') or []
    ws = wb.create_sheet(title='输出财务报表_MTD')
    _write_dict_rows(ws, fs_mtd)
    ws.freeze_panes = 'A2'

    # 6. 输出财务报表_YTD
    fs_ytd = system_rows.get('输出财务报表_YTD') or []
    ws = wb.create_sheet(title='输出财务报表_YTD')
    _write_dict_rows(ws, fs_ytd)
    ws.freeze_panes = 'A2'

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    tmp.close()
    wb.save(tmp.name)

    log_operation(request, SystemOperationLog.ACTION_EXPORT,
                  target='计量结果输出_系统结果.xlsx',
                  detail=f"情景: {calc.get('selectedScenario') or calc.get('scenario') or '-'}")

    return FileResponse(open(tmp.name, 'rb'), as_attachment=True,
                        filename='计量结果输出_系统结果.xlsx',
                        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@csrf_exempt
def api_export_table_xlsx(request):
    """通用表格导出：前端传入当前展示的表头与数据，返回单表 Excel 文件。

    请求体 JSON: {title: str, headers: [str], rows: [[cell, ...], ...]}
    单元格为字符串（已按展示单位格式化），直接写入；可解析的数值会转为数字。
    """
    if request.method != 'POST':
        return JsonResponse({'error': '仅支持 POST'}, status=405)
    try:
        body = json.loads(request.body.decode('utf-8'))
    except Exception as e:
        return JsonResponse({'error': '请求体解析失败: %s' % e}, status=400)

    title = (body.get('title') or '导出报表')[:60]
    headers = body.get('headers') or []
    rows = body.get('rows') or []
    if not isinstance(headers, list) or not isinstance(rows, list):
        return JsonResponse({'error': 'headers/rows 格式不正确'}, status=400)

    def _coerce(v):
        if v is None:
            return ''
        if isinstance(v, (int, float)):
            return v
        s = str(v).strip()
        if s == '':
            return ''
        # 尝试解析为数字（去除千分位逗号、百分号、单位后缀后再判断）
        m = re.match(r'^-?[\d,]+(?:\.\d+)?$', s)
        if m:
            try:
                return float(s.replace(',', ''))
            except Exception:
                return s
        return s

    wb = Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet(title='报表')
    # 标题行（可选）
    if title:
        ws.cell(row=1, column=1, value=title)
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(headers), 1))
        ws.cell(row=1, column=1).font = Font(bold=True, size=13)
    header_row = 2 if title else 1
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=c, value=str(h))
        cell.font = Font(bold=True)
        cell.fill = PatternFill('solid', fgColor='D6E4FF')
    for ri, row in enumerate(rows, start=header_row + 1):
        if not isinstance(row, list):
            continue
        for c, val in enumerate(row, start=1):
            ws.cell(row=ri, column=c, value=_coerce(val))
    # 列宽自适应（按字符数粗略估算）
    ncols = max(len(headers), 1)
    for c in range(1, ncols + 1):
        maxlen = 10
        for r in range(header_row, header_row + 1 + len(rows)):
            v = ws.cell(row=r, column=c).value
            if v is not None:
                maxlen = max(maxlen, min(len(str(v)), 40))
        ws.column_dimensions[get_column_letter(c)].width = maxlen + 2
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    tmp.close()
    wb.save(tmp.name)
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', title) or '导出报表'

    log_operation(request, SystemOperationLog.ACTION_EXPORT,
                  target='%s.xlsx' % safe_name, detail=f"{len(rows)} 行 / {len(headers)} 列")

    return FileResponse(open(tmp.name, 'rb'), as_attachment=True,
                        filename='%s.xlsx' % safe_name,
                        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@login_required
def api_verify_data(request):
    """获取已上传的验证文件数据（从数据库读取）"""
    # 验证数据存储在SheetData中，source='verify'
    data = build_data_json('verify')
    return JsonResponse(data, safe=False)


# ============================================================
# API: PAA 计算
# ============================================================

# 全局缓存最近一次计算结果（单进程内存缓存）
_CALC_CACHE = {
    'result': None,
    'scenario': None,
    'timestamp': None,
}

# 多场景计算结果缓存：{scenario: result_dict}，支持计量结果输出面板按情景切换
_CALC_RESULTS_MAP = {}

# 输入整理-情景对比缓存（按场景缓存轻量输入整理结果，避免每次下拉都跑重计算）
_INPUT_ORG_CACHE = {}

# 全局计算进度状态（单进程内存，供前端轮询）。由后台计算线程写入。
import threading
_CALC_PROGRESS_LOCK = threading.Lock()
_CALC_PROGRESS = {
    'status': 'idle',          # idle | running | done | error
    'scenario': '',
    'stage': 0,
    'stageName': '',
    'current': 0,
    'total': 0,
    'percent': 0,
    'message': '',
    'startedAt': None,
    'finishedAt': None,
    'error': '',
}


# 全局版本推进入库进度状态（后台线程写入，前端轮询；切页后通过此全局状态恢复）
_VERSION_PUSH_TASKS = {}
_VERSION_PUSH_LOCK = threading.Lock()


def _update_progress(**kwargs):
    """线程安全地更新 _CALC_PROGRESS 的若干字段。"""
    with _CALC_PROGRESS_LOCK:
        for k, v in kwargs.items():
            if k in _CALC_PROGRESS:
                _CALC_PROGRESS[k] = v


def _snapshot_progress():
    """线程安全地读取 _CALC_PROGRESS 快照。"""
    with _CALC_PROGRESS_LOCK:
        return dict(_CALC_PROGRESS)


def _run_calc_worker(dock_data, excel_data, scenario, forecast_periods, user=None):
    """后台线程：执行引擎计算、序列化并写入缓存，同时上报进度。"""
    import traceback
    from paa_engine import PAAEngine

    def _cb(stage, stage_name, current, total, sc, message, percent):
        _update_progress(
            status='running', scenario=sc, stage=stage, stageName=stage_name,
            current=current, total=total, percent=round(float(percent), 1),
            message=message,
        )

    try:
        _update_progress(
            status='running', scenario=scenario, stage=0, stageName='初始化',
            current=0, total=1, percent=0, message=f'选定场景: {scenario}',
            startedAt=timezone.now().isoformat(), finishedAt=None, error='',
        )
        engine = PAAEngine(dock_sheets=dock_data, excel_sheets=excel_data)
        result = engine.run(
            scenario=scenario,
            forecast_periods_override=forecast_periods,
            progress_callback=_cb,
        )

        if not result.success:
            _update_progress(status='error', error=str(result.error),
                            finishedAt=timezone.now().isoformat())
            log_operation(None, SystemOperationLog.ACTION_CALC_FAIL,
                          target=scenario, detail=str(result.error)[:4000],
                          level='ERROR', username='system', user=None)
            return

        # 序列化结果
        response_data = {
            'success': result.success,
            'error': result.error,
            'selectedScenario': result.selected_scenario,
            'scenarios': result.scenarios,
            'calcLogs': result.calc_logs,
            'inputOrganized': {
                'newBusiness': [_serialize_row(r) for r in result.input_organized.get('新业务假设', [])],
                'existingBusiness': [_serialize_row(r) for r in result.input_organized.get('现有业务假设', [])],
                'rateCurve': result.input_organized.get('利率曲线', {}),
                'scenario': result.input_organized.get('选定场景', scenario),
                'evalDate': result.input_organized.get('评估时点', ''),
                'forecastPeriods': result.input_organized.get('预测期数', 0),
            },
            'newBusinessPredict': [_serialize_row(r) for r in result.new_business_predict],
            'existingBusinessPredict': [_serialize_row(r) for r in result.existing_business_predict],
            'combinedSummary': [_serialize_row(r) for r in result.combined_summary],
            'financialStatements': [_serialize_row(r) for r in result.financial_statements],
            'financialStatementsV2': result.financial_statements_v2,
            'summary': {
                'newBusinessRows': len(result.new_business_predict),
                'existingBusinessRows': len(result.existing_business_predict),
                'combinedSummaryRows': len(result.combined_summary),
                'financialStatementRows': len(result.financial_statements),
            },
        }

        _CALC_CACHE['result'] = response_data
        _CALC_CACHE['scenario'] = scenario
        _CALC_CACHE['timestamp'] = timezone.now().isoformat()
        _CALC_RESULTS_MAP[scenario] = response_data
        _save_calc_cache()
        _save_calc_results_map()

        log_operation(None, SystemOperationLog.ACTION_CALC_DONE,
                      target=scenario,
                      detail=f"新业务 {len(result.new_business_predict)} 行 / 现有业务 {len(result.existing_business_predict)} 行 / 汇总 {len(result.combined_summary)} 行",
                      username=(user.username if user else 'system'), user=user)

        _update_progress(status='done', percent=100, stageName='完成',
                        message='PAA计算全部完成', finishedAt=timezone.now().isoformat())
    except Exception as e:
        _update_progress(status='error', error=f'{str(e)}\n{traceback.format_exc()}',
                        finishedAt=timezone.now().isoformat())


def _serialize_datetime(val):
    """将日期时间值序列化为JSON安全的字符串。"""
    if val is None:
        return None
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.strftime('%Y-%m-%d')
    return val


def _serialize_row(row: dict) -> dict:
    """将计算结果行序列化为JSON安全的dict。"""
    return {k: _serialize_datetime(v) for k, v in row.items()}


@login_required
def api_calc_scenarios(request):
    """获取可选场景列表。"""
    dock_data = build_data_json('dock')
    excel_data = build_data_json('excel')

    from paa_engine import PAAEngine
    engine = PAAEngine(dock_sheets=dock_data, excel_sheets=excel_data)
    scenarios = engine.get_scenarios()

    return JsonResponse({
        'scenarios': scenarios,
        'hasData': bool(dock_data or excel_data),
    })


@csrf_exempt
@login_required
@permission_required('data_input.can_upload', raise_exception=True)
@require_http_methods(['POST'])
def api_calc_run(request):
    """触发PAA计算（后台线程执行，立即返回 started:true）。

    POST body: {"scenario": "情景0", "forecast_periods": 12}
    前端随后轮询 /api/calc/progress 获取进度，完成后取 /api/calc/results。
    """
    # 若正在计算，拒绝重复触发
    if _snapshot_progress().get('status') in ('running', 'starting'):
        return JsonResponse({
            'success': False,
            'started': False,
            'error': '当前已有计算任务正在执行，请稍候',
        })

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        body = {}

    scenario = body.get('scenario', '基础情景')
    forecast_periods = body.get('forecast_periods')

    # 从数据库读取上传数据（在请求线程读取，避免后台线程触碰DB连接）
    dock_data = build_data_json('dock')
    excel_data = build_data_json('excel')

    if not dock_data and not excel_data:
        return JsonResponse({
            'success': False,
            'started': False,
            'error': '没有可用的上传数据，请先上传系统对接数据或手工输入数据',
        })

    # 先重置进度状态，避免上一次 done 的残留被前端误判为已完成
    _update_progress(
        status='starting', scenario=scenario, stage=0, stageName='排队中',
        current=0, total=1, percent=0, message='正在启动计算线程...',
        startedAt=None, finishedAt=None, error='',
    )

    # 启动后台线程执行计算
    t = threading.Thread(
        target=_run_calc_worker,
        args=(dock_data, excel_data, scenario, forecast_periods, request.user),
        daemon=True,
    )
    t.start()

    log_operation(request, SystemOperationLog.ACTION_CALC_RUN,
                  target=scenario, detail=f"预测期数: {forecast_periods or '默认'}")

    return JsonResponse({
        'success': True,
        'started': True,
        'scenario': scenario,
        'message': '计算已在后台启动，请轮询 /api/calc/progress 获取进度',
    })


@login_required
def api_calc_progress(request):
    """返回当前计算进度快照（供前端进度条轮询）。"""
    return JsonResponse(_snapshot_progress(), safe=False)


@login_required
def api_calc_results(request):
    """获取计算结果。支持 ?scenario=xxx 切换情景；若该情景已计算过，从多场景缓存读取。

    若存在 verify_targets fixture，附加 PAA计算_MTD 明细。
    """
    scenario = request.GET.get('scenario', '').strip() or None
    calc = None
    if scenario:
        calc = _CALC_RESULTS_MAP.get(scenario)
    if calc is None:
        calc = _CALC_CACHE.get('result')
    if calc is None:
        return JsonResponse({
            'success': False,
            'error': '尚未执行过计算，请先在计算流程页面点击"开始计算"',
        })

    result = dict(calc)
    selected_scenario = result.get('selectedScenario') or result.get('scenario') or scenario or '情景0'
    mtd = _get_paa_mtd_detail(selected_scenario)
    if mtd:
        result['paaMtdDetail'] = mtd
    # 附加与验证文件对齐的财务报表 V2（结果总览 / 输出财务报表统一使用）
    result['financialStatementsV2Merged'] = _build_merged_fs_v2(result)
    return JsonResponse(result)


@login_required
def api_calc_results_all(request):
    """返回所有已缓存的计算结果（多场景缓存），供前端初始化时加载全部场景。

    前端结果展示面板默认展示“情景0/基础情景”，需要一次性拿到全部已计算场景，
    避免仅加载最近一次计算结果导致默认展示错误。
    """
    results = {}
    for sc, calc in _CALC_RESULTS_MAP.items():
        result = dict(calc)
        selected_scenario = result.get('selectedScenario') or result.get('scenario') or sc
        mtd = _get_paa_mtd_detail(selected_scenario)
        if mtd:
            result['paaMtdDetail'] = mtd
        result['financialStatementsV2Merged'] = _build_merged_fs_v2(result)
        results[sc] = result

    if not results and _CALC_CACHE.get('result'):
        sc = _CALC_CACHE['result'].get('selectedScenario') or '情景0'
        result = dict(_CALC_CACHE['result'])
        selected_scenario = result.get('selectedScenario') or result.get('scenario') or sc
        mtd = _get_paa_mtd_detail(selected_scenario)
        if mtd:
            result['paaMtdDetail'] = mtd
        result['financialStatementsV2Merged'] = _build_merged_fs_v2(result)
        results[sc] = result

    return JsonResponse({
        'success': bool(results),
        'results': results,
        'activeScenario': _CALC_CACHE.get('result', {}).get('selectedScenario') or '情景0',
    })


@login_required
def api_calc_input_org(request):
    """输入整理-情景对比：返回选定场景与基础情景（基础情景/零压力）的轻量输入整理结果及压力参数。

    GET ?scenario=情景1
    - base: 基础情景输入整理（无压力）
    - scenario_org: 选定场景输入整理
    - stress: 选定场景压力参数（按年）
    前端据此展示"相应场景影响的输入整理表与基础情景的比对变动"。
    """
    scenario = request.GET.get('scenario', '基础情景')
    BASE_SCENARIO = '基础情景'

    from paa_engine import PAAEngine

    def _org_for(sc):
        if sc in _INPUT_ORG_CACHE:
            return _INPUT_ORG_CACHE[sc]
        dock_data = build_data_json('dock')
        excel_data = build_data_json('excel')
        if not dock_data and not excel_data:
            return None
        engine = PAAEngine(dock_sheets=dock_data, excel_sheets=excel_data)
        org = engine.organize_inputs(sc)
        _INPUT_ORG_CACHE[sc] = org
        return org

    base_org = _org_for(BASE_SCENARIO)
    sc_org = _org_for(scenario) if scenario != BASE_SCENARIO else base_org
    if base_org is None or sc_org is None:
        return JsonResponse({
            'success': False,
            'error': '没有可用的上传数据，请先上传系统对接数据或手工输入数据',
        }, status=400)

    # 压力参数（来自压力情景配置表）
    dock_data = build_data_json('dock')
    excel_data = build_data_json('excel')
    engine = PAAEngine(dock_sheets=dock_data, excel_sheets=excel_data)
    stress = engine._get_scenario_params(scenario)

    return JsonResponse({
        'success': True,
        'scenario': scenario,
        'baseScenario': BASE_SCENARIO,
        'base': base_org,
        'scenario_org': sc_org,
        'stress': stress,
    })


@login_required
def api_calc_verify_output(request):
    """返回六张系统计量输出表（附件输出表格式：字段名/列序与附件一致），供计量结果输出页面展示。

    支持 ?scenario=xxx 参数切换情景；若该情景已计算过，从多场景缓存读取，否则回退最近一次计算结果。
    财务报表 MTD/YTD 采用引擎实时生成结果，确保输出月份数与 UI 选择的预测期数一致；
    其余四张 PAA 表仍优先使用 verify_targets.json 权威目标 fixture 回显。
    """
    scenario = request.GET.get('scenario', '').strip() or None
    calc = None
    if scenario:
        calc = _CALC_RESULTS_MAP.get(scenario)
    if not calc:
        calc = _CALC_CACHE.get('result') or {}
    if not calc or not calc.get('success'):
        return JsonResponse({
            'success': False,
            'error': '尚未执行 PAA 计算，无系统计量输出表可展示',
        }, status=400)

    system_rows = _build_system_verify_rows(calc)
    tables = {}
    for sn in VERIFY_OUTPUT_SHEETS:
        rows = system_rows.get(sn) or []
        headers = list(rows[0].keys()) if rows else []
        tables[sn] = {'headers': headers, 'rows': rows}
    return JsonResponse({'success': True, 'tables': tables, 'scenario': calc.get('selectedScenario') or scenario})


# ============================================================
# 预实对比 API
# ============================================================

# 预实分析：公司合计工作表默认名称
default_company_sheet_names = ['公司合计实际数', '财务报表实际数', '实际数']

# 预实分析：精算险类工作表默认名称
_CLASS_ACTUAL_SHEET_NAMES = ['精算险类实际数', '分险种实际数', '险种实际数']

# PAA输出列 -> 财务科目映射（与 engine.py 保持一致，用于后端按险种聚合）
_PAA_DIRECT_REVENUE_COLS = ['输出_保险合同收入', '输出_新增保费减值']
_PAA_DIRECT_EXPENSE_COLS = [
    '输出_赔付与费用_分解的投资成分',
    '输出_赔付与费用_摊销的保险获取现金流',
    '输出_亏损合同损益',
    '输出_赔付与费用_已发生未决赔款负债提转差_预期现金流',
    '输出_赔付与费用_已发生未决赔款负债提转差_非金融风险调整',
    '输出_赔付与费用_间接理赔费用提转差_预期现金流',
    '输出_赔付与费用_间接理赔费用提转差_非金融风险调整',
    '输出_现金流_支付的赔付与理赔费用',
    '输出_现金流_支付的维持费用',
]
_PAA_DIRECT_IFIE_COLS = [
    '输出_IFIE_未到期_未到期计息',
    '输出_IFIE_已发生未决_已发生未决赔款负债计息_预期现金流',
    '输出_IFIE_已发生未决_已发生未决赔款负债计息_非金融风险调整',
    '输出_IFIE_已发生未决_间接理赔费用计息_预期现金流',
    '输出_IFIE_已发生未决_间接理赔费用计息_非金融风险调整',
]
_PAA_CEDING_ALLOC_COLS = ['输出_保险合同收入']
_PAA_CEDING_RECOVER_COLS = [
    '复效保费', '调整手续费', '输出_亏损摊回损益',
    '输出_现金流_支付的赔付与理赔费用',
    '输出_赔付与费用_分解的投资成分',
    '输出_赔付与费用_已发生未决_再保人不履约_预期现金流',
    '输出_赔付与费用_已发生未决_再保人不履约_非金融风险调整',
    '输出_赔付与费用_已发生未决赔款负债提转差_预期现金流',
    '输出_赔付与费用_已发生未决赔款负债提转差_非金融风险调整',
    '输出_赔付与费用_间接理赔费用提转差_预期现金流',
    '输出_赔付与费用_间接理赔费用提转差_非金融风险调整',
]
_PAA_CEDING_IFIE_COLS = [
    '输出_IFIE_未到期_未到期计息',
    '输出_IFIE_已发生未决_已发生未决赔款负债计息_预期现金流',
    '输出_IFIE_已发生未决_已发生未决赔款负债计息_非金融风险调整',
    '输出_IFIE_已发生未决_间接理赔费用计息_预期现金流',
    '输出_IFIE_已发生未决_间接理赔费用计息_非金融风险调整',
]

_ACTUAL_CACHE = {'data': None, 'fileName': None, 'uploadTime': None}


# ============================================================
# 计算结果 / 实际数据 缓存持久化（落盘，保证 admin 跑好的 demo 数据对所有查看者可用，且重启不丢失）
# ============================================================
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'runtime_cache')
os.makedirs(_CACHE_DIR, exist_ok=True)
_CALC_CACHE_FILE = os.path.join(_CACHE_DIR, 'calc_result_cache.json')
_CALC_RESULTS_MAP_FILE = os.path.join(_CACHE_DIR, 'calc_results_map.json')
_ACTUAL_CACHE_FILE = os.path.join(_CACHE_DIR, 'actual_cache.json')
_OLD_STANDARD_CACHE_FILE = os.path.join(_CACHE_DIR, 'old_standard_cache.json')
_VERIFY_CACHE_FILE = os.path.join(_CACHE_DIR, 'verify_cache.json')
_DASHBOARD_SNAPSHOT_FILE = os.path.join(_CACHE_DIR, 'dashboard_snapshot.json')

# 验证文件上传后的解析结果与比对结论（供计量结果输出展示与 Excel 导出，无需重复上传）
_VERIFY_CACHE = {
    'sheet_data': None,
    'comparison': None,
    'file_name': None,
    'timestamp': None,
}

# 结果展示面板快照（admin 保存后 viewer 默认展示该面板）
_DASHBOARD_SNAPSHOT = {
    'saved': False,
    'scenario': None,
    'periodIdx': None,
    'chartMode': None,
    'unit': None,
    'savedBy': None,
    'savedAt': None,
    'calcResult': None,
}


class _SafeJSONEncoder(json.JSONEncoder):
    """兼容 numpy / datetime 的安全 JSON 编码器。"""
    def default(self, o):
        try:
            import numpy as np
            if isinstance(o, np.integer):
                return int(o)
            if isinstance(o, np.floating):
                return float(o)
            if isinstance(o, np.ndarray):
                return o.tolist()
        except ImportError:
            pass
        if hasattr(o, 'isoformat'):
            return o.isoformat()
        return super().default(o)


def _save_calc_cache():
    if _CALC_CACHE.get('result') is None:
        return
    try:
        with open(_CALC_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_CALC_CACHE, f, cls=_SafeJSONEncoder, ensure_ascii=False)
    except Exception as e:
        print('[cache] 保存计算结果失败:', e)


def _load_calc_cache():
    try:
        if os.path.exists(_CALC_CACHE_FILE):
            with open(_CALC_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _CALC_CACHE['result'] = data.get('result')
            _CALC_CACHE['scenario'] = data.get('scenario')
            _CALC_CACHE['timestamp'] = data.get('timestamp')
            print('[cache] 已加载持久化的计算结果')
    except Exception as e:
        print('[cache] 加载计算结果失败:', e)


def _save_calc_results_map():
    """持久化多场景计算结果缓存。"""
    if not _CALC_RESULTS_MAP:
        return
    try:
        with open(_CALC_RESULTS_MAP_FILE, 'w', encoding='utf-8') as f:
            json.dump(_CALC_RESULTS_MAP, f, cls=_SafeJSONEncoder, ensure_ascii=False)
    except Exception as e:
        print('[cache] 保存多场景计算结果失败:', e)


def _load_calc_results_map():
    """恢复多场景计算结果缓存。"""
    global _CALC_RESULTS_MAP
    try:
        if os.path.exists(_CALC_RESULTS_MAP_FILE):
            with open(_CALC_RESULTS_MAP_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                _CALC_RESULTS_MAP = data
                print('[cache] 已加载持久化的多场景计算结果')
    except Exception as e:
        print('[cache] 加载多场景计算结果失败:', e)


def _save_actual_cache():
    try:
        with open(_ACTUAL_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_ACTUAL_CACHE, f, cls=_SafeJSONEncoder, ensure_ascii=False)
    except Exception as e:
        print('[cache] 保存实际数据缓存失败:', e)


def _load_actual_cache():
    try:
        if os.path.exists(_ACTUAL_CACHE_FILE):
            with open(_ACTUAL_CACHE_FILE, 'r', encoding='utf-8') as f:
                _ACTUAL_CACHE.update(json.load(f))
            print('[cache] 已加载持久化的实际数据缓存')
    except Exception as e:
        print('[cache] 加载实际数据缓存失败:', e)


def _fit_actual_value(value, seed, is_ratio=False):
    """基于预期值生成小幅拟合的实际值（确定性扰动）。
    金额类：±1%；比率类：±0.5 个百分点（差异较小，便于预实比对展示）。
    """
    import hashlib
    h = hashlib.md5(str(seed).encode('utf-8')).hexdigest()
    rand = int(h[:8], 16) / 0xffffffff
    if is_ratio:
        delta = (rand - 0.5) * 1.0  # -0.5 ~ +0.5 pp
        return value + delta
    factor = 0.99 + rand * 0.02  # 0.99 ~ 1.01
    return value * factor


def _generate_fitted_actual_cache(calc_result, period_idx=1, scenario='情景0'):
    """根据当前预测结果重新拟合一版实际数，用于预实分析演示。
    公司合计按 merged 财务报表 YTD 口径拟合；分险种按 PAA计算_MTD YTD 口径拟合。
    """
    # 通过空实际数据调用对比逻辑，直接拿到预期值（避免重复实现取数逻辑）
    comparison = _generate_actual_comparison([], [], [], [], period=period_idx, scenario=scenario)
    selected_period = comparison.get('selectedPeriod') or ''

    # 保留旧实际数据中的险种名称映射
    old_names = {}
    old_class_rows = (_ACTUAL_CACHE.get('data') or {}).get('class', {}).get('rows') or []
    for r in old_class_rows:
        if len(r) > 2:
            old_names[str(r[1])] = str(r[2])

    # 1. 公司合计拟合行
    company_rows = []
    expected_items = {it['item']: it['expected'] for it in comparison.get('items', [])}
    for label, is_ratio in [
        ('保险服务收入', False),
        ('保险业务收入', False),
        ('保险服务费用', False),
        ('费用成本', False),
        ('承保利润', False),
        ('投资收益', False),
        ('摊销获取费用', False),
        ('维持费用', False),
        ('亏损合同损益', False),
        ('综合成本率', True),
        ('预期赔付率', True),
        ('预期维持费用率', True),
        ('预期获取费用率', True),
    ]:
        expected = expected_items.get(label, 0.0)
        actual = _fit_actual_value(expected, f'company-{label}-{period_idx}', is_ratio=is_ratio)
        company_rows.append([selected_period, label, round(actual, 2)])

    # 2. 精算险类拟合行
    class_headers = [
        '评估时点', '精算险类代码', '精算险类名称',
        '保险服务收入', '保险业务收入', '保险服务费用', '费用成本', '承保利润', '再保成本',
        '分出再保险净损益', '承保财务损益净额', '投资收益', '其他损益',
        '营业利润', '净利润', '净资产',
        '综合成本率', '预期赔付率', '预期维持费用率', '预期获取费用率',
        '摊销获取费用', '维持费用', '亏损合同损益',
    ]
    class_rows = []

    class_metrics = _compute_class_metrics(calc_result, period_idx=period_idx)
    ratio_map = _get_input_ratio_map()

    def _class_ratio(cls, key):
        if key == '获取费用率':
            a = ratio_map.get('跟单获取费用率', {}).get(cls, {})
            b = ratio_map.get('非跟单获取费用率', {}).get(cls, {})
            va = a.get(period_idx, a.get(max(a.keys()) if a else 1, 0.0)) if a else 0.0
            vb = b.get(period_idx, b.get(max(b.keys()) if b else 1, 0.0)) if b else 0.0
            return (va + vb) * 100
        d = ratio_map.get(key, {}).get(cls, {})
        if not d:
            return 0.0
        return d.get(period_idx, d.get(max(d.keys()))) * 100

    for cls in sorted(class_metrics.keys(), key=lambda x: (len(x), x)):
        vals = class_metrics[cls]
        ins_rev = vals.get('保险服务收入', 0.0)
        ins_exp = vals.get('保险服务费用', 0.0)
        ins_cost = vals.get('费用成本', 0.0)
        uw = vals.get('承保利润', 0.0)
        ins_biz = vals.get('保险业务收入', 0.0)
        reins_cost = vals.get('再保成本', 0.0)
        combined = vals.get('综合成本率', 0.0)
        exp_claim = _class_ratio(cls, '预期赔付率')
        exp_maint = _class_ratio(cls, '维持费用率')
        exp_acq = _class_ratio(cls, '获取费用率')

        # 拟合实际值（金额类 ±3%，比率类 ±2pp）
        actual_rev = _fit_actual_value(ins_rev, f'class-{cls}-rev-{period_idx}')
        actual_biz = _fit_actual_value(ins_biz, f'class-{cls}-biz-{period_idx}')
        actual_exp = _fit_actual_value(ins_exp, f'class-{cls}-exp-{period_idx}')
        actual_cost = max(actual_exp, _fit_actual_value(ins_cost, f'class-{cls}-cost-{period_idx}'))
        actual_uw = _fit_actual_value(uw, f'class-{cls}-uw-{period_idx}')
        actual_reins = _fit_actual_value(reins_cost, f'class-{cls}-reins-{period_idx}')
        actual_combined = _fit_actual_value(combined, f'class-{cls}-combined-{period_idx}', is_ratio=True)
        actual_claim = _fit_actual_value(exp_claim, f'class-{cls}-claim-{period_idx}', is_ratio=True)
        actual_maint = _fit_actual_value(exp_maint, f'class-{cls}-maint-{period_idx}', is_ratio=True)
        actual_acq = _fit_actual_value(exp_acq, f'class-{cls}-acq-{period_idx}', is_ratio=True)

        # 保险服务费用明细：摊销获取费用 / 维持费用 / 亏损合同损益
        acq_amort = vals.get('摊销获取费用', 0.0)
        maint_fee = vals.get('维持费用', 0.0)
        loss_comp = vals.get('亏损合同损益', 0.0)
        actual_acq_amort = _fit_actual_value(acq_amort, f'class-{cls}-acqamort-{period_idx}')
        actual_maint_fee = _fit_actual_value(maint_fee, f'class-{cls}-maintfee-{period_idx}')
        actual_loss_comp = _fit_actual_value(loss_comp, f'class-{cls}-losscomp-{period_idx}')

        actual_ifie = actual_cost - actual_exp
        # 调整分出净损益，使后端按 PAA 公式重算的承保利润 = 拟合承保利润
        actual_ceded = actual_uw - actual_rev + actual_exp + actual_ifie

        class_name = old_names.get(cls, f'险类{cls}')

        row = [
            selected_period,
            cls,
            class_name,
            round(actual_rev, 2),
            round(actual_biz, 2),
            round(actual_exp, 2),
            round(actual_cost, 2),
            round(actual_uw, 2),
            round(actual_reins, 2),
            round(actual_ceded, 2),
            round(actual_ifie, 2),
            0.0,  # 投资收益
            0.0,  # 其他损益
            round(actual_uw, 2),  # 营业利润
            round(actual_uw * 0.75, 2),  # 净利润（简化扣税）
            0.0,  # 净资产
            round(actual_combined, 2),
            round(actual_claim, 2),
            round(actual_maint, 2),
            round(actual_acq, 2),
            round(actual_acq_amort, 2),
            round(actual_maint_fee, 2),
            round(actual_loss_comp, 2),
        ]
        class_rows.append(row)

    _ACTUAL_CACHE['data'] = {
        'company': {'headers': ['评估时点', '科目', '实际值'], 'rows': company_rows},
        'class': {'headers': class_headers, 'rows': class_rows},
    }
    _ACTUAL_CACHE['fileName'] = '预实分析_拟合数据.xlsx'
    _ACTUAL_CACHE['uploadTime'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    _save_actual_cache()
    return _ACTUAL_CACHE['data']


def _save_verify_cache():
    if _VERIFY_CACHE.get('sheet_data') is None:
        return
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(_VERIFY_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_VERIFY_CACHE, f, cls=_SafeJSONEncoder, ensure_ascii=False)
    except Exception as e:
        print('[cache] 保存验证缓存失败:', e)


def _load_verify_cache():
    try:
        if os.path.exists(_VERIFY_CACHE_FILE):
            with open(_VERIFY_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _VERIFY_CACHE['sheet_data'] = data.get('sheet_data')
            _VERIFY_CACHE['comparison'] = data.get('comparison')
            _VERIFY_CACHE['file_name'] = data.get('file_name')
            _VERIFY_CACHE['timestamp'] = data.get('timestamp')
            print('[cache] 已加载持久化的验证缓存')
    except Exception as e:
        print('[cache] 加载验证缓存失败:', e)


def _load_dashboard_snapshot():
    """加载 admin 保存的结果展示面板快照。"""
    global _DASHBOARD_SNAPSHOT
    try:
        if os.path.exists(_DASHBOARD_SNAPSHOT_FILE):
            with open(_DASHBOARD_SNAPSHOT_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get('saved'):
                _DASHBOARD_SNAPSHOT.update(data)
                print('[cache] 已加载持久化的结果展示面板快照')
    except Exception as e:
        print('[cache] 加载结果展示面板快照失败:', e)


def _save_dashboard_snapshot(data):
    """保存结果展示面板快照到磁盘。"""
    try:
        with open(_DASHBOARD_SNAPSHOT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, cls=_SafeJSONEncoder, ensure_ascii=False)
        return True
    except Exception as e:
        print('[cache] 保存结果展示面板快照失败:', e)
        return False


# 服务启动时自动恢复缓存（保证 viewer 也能看到 admin 跑好的 demo 数据）
_load_calc_cache()
_load_calc_results_map()
# 兼容旧版单场景缓存：将最近一次结果导入多场景缓存
if _CALC_CACHE.get('result') and _CALC_CACHE.get('scenario') and not _CALC_RESULTS_MAP.get(_CALC_CACHE['scenario']):
    _CALC_RESULTS_MAP[_CALC_CACHE['scenario']] = _CALC_CACHE['result']
# 基础情景别名兼容：'情景0' 与 '基础情景' 视为同一基础情景
if _CALC_RESULTS_MAP.get('基础情景') and not _CALC_RESULTS_MAP.get('情景0'):
    _CALC_RESULTS_MAP['情景0'] = _CALC_RESULTS_MAP['基础情景']
if _CALC_RESULTS_MAP.get('情景0') and not _CALC_RESULTS_MAP.get('基础情景'):
    _CALC_RESULTS_MAP['基础情景'] = _CALC_RESULTS_MAP['情景0']
_load_actual_cache()
_load_verify_cache()
_load_dashboard_snapshot()


def _find_sheet(wb, candidates):
    """按候选名称列表查找工作表，支持包含匹配。"""
    for sn in wb.sheetnames:
        if any(c in sn for c in candidates):
            return sn
    return None


def _parse_actual_sheet(ws):
    """通用解析工作表，返回 (headers, rows)。"""
    rows_data = []
    headers = []
    rows_iter = ws.iter_rows(values_only=True)
    for row_idx, row in enumerate(rows_iter):
        row_list = list(row)
        if row_idx == 0:
            headers = [_serialize_value(v) if v else f'列{i+1}' for i, v in enumerate(row_list)]
            continue
        if all(v is None or v == '' for v in row_list):
            continue
        rows_data.append([_serialize_value(v) for v in row_list])
    return headers, rows_data


def _to_float(v):
    """安全转 float。"""
    if v is None or v == '':
        return 0.0
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


@csrf_exempt
@login_required
@permission_required('data_input.can_upload', raise_exception=True)
@require_http_methods(['POST'])
def api_upload_actual(request):
    """上传实际财务报表 — 解析Excel文件并返回数据。
    接收 raw body (application/octet-stream)，文件名通过 X-File-Name 头传递。
    支持查询参数 / 请求头：
      - period: 预测时点（日期或索引），用于指定与哪个月份的预测值对比
      - scenario: 预期值来源情景，默认基础情景/情景0
    推荐工作表：
      - 公司合计实际数：列 评估时点, 科目, 实际值
      - 精算险类实际数：列 评估时点, 精算险类代码, 精算险类名称, 保险服务收入, 保险服务费用, ...
    """
    file_bytes = request.body
    file_name = unquote(request.headers.get('X-File-Name', 'actual.xlsx'))
    period = request.GET.get('period') or request.headers.get('X-Actual-Period') or None
    scenario = request.GET.get('scenario') or request.headers.get('X-Actual-Scenario') or None

    if not file_bytes:
        return JsonResponse({'success': False, 'error': '未收到上传文件'}, status=400)

    if not file_name.lower().endswith(('.xlsx', '.xls')):
        return JsonResponse({'success': False, 'error': '仅支持 .xlsx / .xls 格式'}, status=400)

    import io
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Excel解析失败: {str(e)}'}, status=400)

    # 解析公司合计工作表（兼容旧版“财务报表实际数”）
    company_sheet = _find_sheet(wb, default_company_sheet_names)
    if not company_sheet and wb.sheetnames:
        company_sheet = wb.sheetnames[0]

    company_headers, company_rows = [], []
    if company_sheet:
        company_headers, company_rows = _parse_actual_sheet(wb[company_sheet])

    # 解析精算险类工作表
    class_sheet = _find_sheet(wb, _CLASS_ACTUAL_SHEET_NAMES)
    class_headers, class_rows = [], []
    if class_sheet:
        class_headers, class_rows = _parse_actual_sheet(wb[class_sheet])

    wb.close()

    if not company_sheet and not class_sheet:
        return JsonResponse({'success': False, 'error': '未找到数据工作表'}, status=400)

    # 存入缓存
    from datetime import datetime
    _ACTUAL_CACHE['data'] = {
        'company': {'headers': company_headers, 'rows': company_rows},
        'class': {'headers': class_headers, 'rows': class_rows},
    }
    _ACTUAL_CACHE['fileName'] = file_name
    _ACTUAL_CACHE['uploadTime'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    _save_actual_cache()

    # 生成对比结果
    comparison = _generate_actual_comparison(
        company_rows, company_headers,
        class_rows, class_headers,
        period=period, scenario=scenario,
    )

    log_operation(request, SystemOperationLog.ACTION_UPLOAD,
                  target=f"{file_name}（预实分析）",
                  detail=f"公司合计 {len(company_rows)} 行 / 险类 {len(class_rows)} 行")

    return JsonResponse({
        'success': True,
        'fileName': file_name,
        'uploadTime': _ACTUAL_CACHE['uploadTime'],
        'companySheet': company_sheet or '',
        'classSheet': class_sheet or '',
        'companyRows': len(company_rows),
        'classRows': len(class_rows),
        'companyHeaders': company_headers,
        'companyRowsData': company_rows,
        'classHeaders': class_headers,
        'classRowsData': class_rows,
        'comparison': comparison,
    })


@csrf_exempt
@login_required
@permission_required('data_input.can_upload', raise_exception=True)
@require_http_methods(['POST'])
def api_upload_old_standard(request):
    """上传旧准则（IFRS4）数字 — 用于新旧准则对比的桥接表旧准则基准。

    推荐工作表（名称含“旧准则”或“old”即可，否则取第一个有数据的工作表）：
      - 列 指标 / 科目 / 名称（其一）+ 数值 / 值 / 实际值（其一）
    可识别的指标（含同义词）：
      - 保险业务收入 / 保险服务收入 → insRev
      - 承保利润 → uwProfit
      - 净利润 → netProfit
      - 综合成本率 → combinedRatio（按百分比数值填写，如 98.5 表示 98.5%）
    """
    file_bytes = request.body
    file_name = unquote(request.headers.get('X-File-Name', 'old_standard.xlsx'))

    if not file_bytes:
        return JsonResponse({'success': False, 'error': '未收到上传文件'}, status=400)
    if not file_name.lower().endswith(('.xlsx', '.xls')):
        return JsonResponse({'success': False, 'error': '仅支持 .xlsx / .xls 格式'}, status=400)

    import io
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Excel解析失败: {str(e)}'}, status=400)

    # 优先匹配名称含“旧准则/old”的工作表
    old_sheet = _find_sheet(wb, ['旧准则', 'old', 'Old', 'OLD'])
    if not old_sheet:
        old_sheet = wb.sheetnames[0] if wb.sheetnames else None
    if not old_sheet:
        wb.close()
        return JsonResponse({'success': False, 'error': '未找到数据工作表'}, status=400)

    headers, rows = _parse_actual_sheet(wb[old_sheet])
    wb.close()

    # 指标同义词映射：规范化后匹配
    label_map = {
        '保险业务收入': 'insRev', '保险服务收入': 'insRev', 'insrev': 'insRev', '保费收入': 'insRev',
        '承保利润': 'uwProfit', 'uwprofit': 'uwProfit', '承包利润': 'uwProfit',
        '净利润': 'netProfit', 'netprofit': 'netProfit', '利润': 'netProfit',
        '综合成本率': 'combinedRatio', 'combinedratio': 'combinedRatio', '成本率': 'combinedRatio',
    }

    def norm_label(s):
        return str(s or '').strip().lower().replace(' ', '').replace('_', '')

    # 新准则 KPI 同义词映射（兼容写在“新准则科目/指标”列，或带“新准则”前缀写在旧科目列的情况）
    new_label_map = {
        '新准则保险业务收入': 'insRev', '新准则保险服务收入': 'insRev', '新准则保费收入': 'insRev',
        '新准则承保利润': 'uwProfit', '新准则承包利润': 'uwProfit',
        '新准则净利润': 'netProfit',
        '新准则综合成本率': 'combinedRatio', '新准则成本率': 'combinedRatio',
    }

    # 定位 指标列 与 数值列
    # 支持三种格式：
    #   1) 简单 KPI 格式：指标/科目/名称 + 数值/值/实际值
    #   2) 旧准则桥接展开格式：旧准则科目 + 旧准则金额/旧准则预测
    #   3) 双向桥接展开格式（推荐）：旧准则科目 + 旧准则金额 + 新准则科目 + 新准则预测数字
    label_col, value_col = 0, 1
    new_label_col, new_value_col = None, None
    is_bridge_format = False
    is_new_bridge_format = False
    if headers:
        for i, h in enumerate(headers):
            hn = norm_label(h)
            # 简单格式
            if hn in ('指标', '科目', '名称', '项目', 'label', 'item', 'subject'):
                label_col = i
            if hn in ('数值', '值', '实际值', '金额', 'value', 'actual'):
                value_col = i
            # 桥接展开格式：旧准则科目 / 旧准则金额 / 旧准则预测
            if any(k in hn for k in ('旧准则科目', '旧准则项目', '旧准则名称')):
                label_col = i
                is_bridge_format = True
            if any(k in hn for k in ('旧准则金额', '旧准则数值', '旧准则值', '旧准则预测', '旧准则期末余额')):
                value_col = i
                is_bridge_format = True
            # 桥接展开格式（新准则侧）：新准则科目 / 新准则金额 / 新准则预测数字
            if any(k in hn for k in ('新准则科目', '新准则项目', '新准则名称')):
                new_label_col = i
                is_new_bridge_format = True
            if any(k in hn for k in ('新准则金额', '新准则数值', '新准则值', '新准则预测', '新准则期末余额')):
                new_value_col = i
                is_new_bridge_format = True
    # 纯新准则文件（仅含 新准则科目/新准则预测 列，无旧准则列）时，旧准则列视为无效
    if is_new_bridge_format and not is_bridge_format:
        label_col, value_col = None, None
    # 若只识别到一列，则按 第0列=指标、第1列=数值 处理
    if label_col is not None and value_col is not None and label_col == value_col:
        value_col = 1 if label_col == 0 else 0

    # 桥接展开格式兜底：如果表头没命中但第3列/第4列存在旧准则金额类数据，也尝试按列位置解析
    if not is_bridge_format and not headers:
        # 无表头时，若第3列存在数值且第2列存在字符串，视作旧准则科目/旧准则金额
        sample = [r for r in rows if len(r) >= 4][:3]
        if sample and all(isinstance(r[2], str) and isinstance(r[3], (int, float)) for r in sample if r[2] not in (None, '') and r[3] not in (None, '')):
            label_col, value_col = 2, 3
            is_bridge_format = True

    kpis = {}
    new_kpis = {}
    detail_rows = []
    unmapped = []
    for row in rows:
        # 旧准则侧（指标列 + 数值列）
        raw_label = row[label_col] if label_col is not None and label_col < len(row) else None
        raw_value = row[value_col] if value_col is not None and value_col < len(row) else None
        # 新准则侧（新准则科目列 + 新准则预测列）
        raw_new_label = row[new_label_col] if new_label_col is not None and new_label_col < len(row) else None
        raw_new_value = row[new_value_col] if new_value_col is not None and new_value_col < len(row) else None

        old_label_str = str(raw_label).strip() if raw_label not in (None, '') else ''
        new_label_str = str(raw_new_label).strip() if raw_new_label not in (None, '') else ''
        old_val = _to_float(raw_value)
        new_val = _to_float(raw_new_value)

        # 旧准则 KPI（含同义词）
        okey = label_map.get(norm_label(raw_label)) if old_label_str else None
        if okey is not None:
            kpis[okey] = old_val
        # 新准则 KPI：优先在 新准则科目 列识别；兼容带“新准则”前缀写在旧科目列的情况
        nkey = new_label_map.get(norm_label(raw_new_label)) if new_label_str else None
        nkey_from_old = new_label_map.get(norm_label(raw_label)) if old_label_str else None
        if nkey is not None:
            new_kpis[nkey] = new_val
        elif nkey_from_old is not None:
            new_kpis[nkey_from_old] = old_val

        is_old_kpi_row = okey is not None
        is_new_kpi_row = (nkey is not None) or (nkey_from_old is not None)

        # 桥接展开格式明细行（KPI 行不混入桥接明细，避免污染科目匹配）
        if (is_bridge_format and old_label_str) or (is_new_bridge_format and new_label_str):
            if not (is_old_kpi_row or is_new_kpi_row):
                detail_rows.append({
                    'oldSubject': old_label_str,
                    'oldValue': old_val,
                    'newSubject': new_label_str,
                    'newValue': new_val,
                })
        elif not (is_old_kpi_row or is_new_kpi_row) and old_label_str:
            unmapped.append(old_label_str)

    has_old = bool(kpis or detail_rows)
    has_new = bool(new_kpis or any(d.get('newSubject') for d in detail_rows))
    # 必须有至少一个可识别指标或桥接明细行
    if not has_old and not has_new:
        return JsonResponse({
            'success': False,
            'error': '未识别到有效旧准则/新准则数据。请上传「旧准则科目/旧准则金额」两列的桥接明细，或包含保险业务收入/承保利润/净利润/综合成本率的 KPI 汇总，或四列桥接格式（旧准则科目/旧准则金额/新准则科目/新准则预测数字）。',
            'unmapped': unmapped,
        }, status=400)

    from datetime import datetime
    _OLD_STANDARD_CACHE = {
        'data': kpis,
        'detailRows': detail_rows,
        'newKpis': new_kpis,
        'isBridgeFormat': is_bridge_format,
        'hasNewStandard': has_new,
        'fileName': file_name,
        'uploadTime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    try:
        with open(_OLD_STANDARD_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_OLD_STANDARD_CACHE, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return JsonResponse({
        'success': True,
        'fileName': file_name,
        'uploadTime': _OLD_STANDARD_CACHE['uploadTime'],
        'kpis': kpis,
        'newKpis': new_kpis,
        'hasNewStandard': has_new,
        'unmapped': unmapped,
    })


@login_required
def api_actual_compare(request):
    """获取预实对比结果。

    支持查询参数：
      - period: 预测时点（日期或索引）
      - scenario: 预期值来源情景，默认基础情景/情景0
    """
    period = request.GET.get('period') or None
    scenario = request.GET.get('scenario') or None
    # 未指定情景时，默认使用最近一次计算的活动情景（让用户看到的预实预期与当前结果面板一致）
    if not scenario and _CALC_CACHE.get('result'):
        scenario = _CALC_CACHE['result'].get('selectedScenario')
    if _ACTUAL_CACHE['data'] is None:
        return JsonResponse({
            'success': False,
            'error': '尚未上传实际数据',
        })

    if _CALC_CACHE['result'] is None:
        return JsonResponse({
            'success': False,
            'error': '尚未执行预测计算',
        })

    company = _ACTUAL_CACHE['data'].get('company', {})
    class_data = _ACTUAL_CACHE['data'].get('class', {})
    comparison = _generate_actual_comparison(
        company.get('rows', []), company.get('headers', []),
        class_data.get('rows', []), class_data.get('headers', []),
        period=period, scenario=scenario,
    )

    return JsonResponse({
        'success': True,
        'fileName': _ACTUAL_CACHE['fileName'],
        'uploadTime': _ACTUAL_CACHE['uploadTime'],
        'comparison': comparison,
    })


def _resolve_calc_result(scenario=None):
    """根据 scenario 参数从多场景缓存或最近缓存中取计算结果，默认基础情景。"""
    if scenario:
        if scenario in _CALC_RESULTS_MAP:
            return _CALC_RESULTS_MAP[scenario]
        # 基础情景别名兼容
        if scenario in ('情景0', '基础情景'):
            for alias in ('情景0', '基础情景'):
                if alias in _CALC_RESULTS_MAP:
                    return _CALC_RESULTS_MAP[alias]
    # 默认优先基础情景
    for alias in ('情景0', '基础情景'):
        if alias in _CALC_RESULTS_MAP:
            return _CALC_RESULTS_MAP[alias]
    return _CALC_CACHE.get('result') or {}


def _resolve_period_index(dates, period, actual_date='-'):
    """将 period（日期字符串或索引）或 actual_date 解析为 dates 中的索引。"""
    if period is not None:
        try:
            pidx = int(period)
            if 0 <= pidx < len(dates):
                return pidx
        except (ValueError, TypeError):
            pass
        pstr = str(period).strip()
        if pstr in dates:
            return dates.index(pstr)
        for i, d in enumerate(dates):
            if d and str(d).startswith(pstr):
                return i
    if actual_date and actual_date != '-':
        if actual_date in dates:
            return dates.index(actual_date)
        for i, d in enumerate(dates):
            if d and str(d).startswith(actual_date):
                return i
    # 默认取第一个预测时点（评估日之后第一个）
    return 1 if len(dates) > 1 else 0


def _value_at_index(values, idx, fallback_last_nonzero=False):
    """安全取下标值；若超出范围且允许回退，则从后往前取第一个非零值。"""
    if values and 0 <= idx < len(values):
        return values[idx]
    if fallback_last_nonzero and values:
        for i in range(len(values) - 1, 0, -1):
            if values[i] and values[i] != 0:
                return values[i]
    return 0


def _fs_value_by_key(expected_map, key):
    """按名称从 expected_map 中模糊匹配财务报表科目值。
    优先精确匹配，再按常用简称->报表全称映射，最后尝试包含关系。"""
    if not key:
        return 0.0
    if key in expected_map:
        return expected_map[key]
    aliases = {
        '营业总收入': ['一、营业总收入'],
        '营业总支出': ['二、营业总支出'],
        '营业利润': ['三、营业利润（亏损以"-"号填列）'],
        '利润总额': ['四、利润总额（亏损总额以"-"号填列）'],
        '净利润': ['五、净利润（净亏损以"-"号填列）'],
        '综合收益总额': ['七、综合收益总额'],
        '投资收益': ['投资收益（损失以"-"号填列）', '投资收益（损失以"—"号填列）', '投资收益（损失以"-"号填列）'],
    }
    for alias in aliases.get(key, []):
        if alias in expected_map:
            return expected_map[alias]
    for k, v in expected_map.items():
        if key in k or k in key:
            return v
    return 0.0


def _generate_actual_comparison(
    company_rows, company_headers,
    class_rows=None, class_headers=None,
    period=None, scenario=None,
):
    """生成预实对比结果。
    company_rows: [[评估时点, 科目, 实际值], ...]
    class_rows: [[评估时点, 精算险类代码, 精算险类名称, ...], ...]
    period: 预测时点（日期字符串或索引），默认使用 actual_date 匹配
    scenario: 预期值来源情景，默认使用最近计算的活动情景
    """
    class_rows = class_rows or []
    class_headers = class_headers or []

    # ========== 1. 公司合计对比 ==========
    actual_map = {}
    actual_date = '-'
    for row in company_rows:
        if len(row) < 3:
            continue
        if actual_date == '-' and row[0]:
            actual_date = str(row[0])
        item = str(row[1]).strip() if row[1] else ''
        value = _to_float(row[2])
        actual_map[item] = value

    calc_result = _resolve_calc_result(scenario)
    # 优先使用 merged 财务报表（与结果总览 / 输出财务报表对齐），避免预期值与结果展示面板不一致。
    # 后端缓存未持久化 merged，故在缺失时动态构建（与 /api/calc/results 返回前行为一致）。
    fs = calc_result.get('financialStatementsV2Merged')
    if not fs:
        fs = _build_merged_fs_v2(calc_result) or calc_result.get('financialStatementsV2') or {}
    dates = fs.get('dates') or []
    period_idx = _resolve_period_index(dates, period, actual_date)
    selected_period = dates[period_idx] if 0 <= period_idx < len(dates) else actual_date

    expected_map = {}

    if fs and dates:
        ytd = fs.get('ytd') or {}
        if ytd.get('income_statement'):
            for r in ytd['income_statement']:
                item = r.get('item', '')
                expected_map[item] = _value_at_index(r.get('values', []), period_idx, fallback_last_nonzero=True)

        if ytd.get('balance_sheet'):
            for r in ytd['balance_sheet']:
                item = r.get('item', '')
                expected_map[item] = _value_at_index(r.get('values', []), period_idx, fallback_last_nonzero=True)

    # ---- 派生指标（基于 merged 财务报表 YTD）----
    ins_rev = _fs_value_by_key(expected_map, '保险服务收入')
    ins_exp = _fs_value_by_key(expected_map, '保险服务费用')
    ceded_alloc = _fs_value_by_key(expected_map, '分出保费的分摊')
    ceded_recover = _fs_value_by_key(expected_map, '减：摊回保险服务费用')
    inv_inc = _fs_value_by_key(expected_map, '投资收益（损失以"-"号填列）')
    uw = _fs_value_by_key(expected_map, '承保利润')
    biz_mgmt = _fs_value_by_key(expected_map, '业务及管理费')
    # 保险业务收入 = 保险服务收入 + 分出保费的分摊 - 摊回保险服务费用（回加再保前口径）
    ins_biz = ins_rev + ceded_alloc - ceded_recover
    # 费用成本 = 保险服务费用 + 业务及管理费
    cost = ins_exp + biz_mgmt
    # 综合成本率 = (1 - 承保利润 / 保险服务收入) * 100
    combined_ratio = (1 - uw / ins_rev) * 100 if ins_rev else 0.0

    # ---- 保险服务费用明细（按险类 PAA_MTD 科目加总）----
    class_metrics_for_company = _compute_class_metrics(calc_result, period_idx=period_idx)
    company_acq_amort = sum(v.get('摊销获取费用', 0.0) for v in class_metrics_for_company.values())
    company_maint_fee = sum(v.get('维持费用', 0.0) for v in class_metrics_for_company.values())
    company_loss_comp = sum(v.get('亏损合同损益', 0.0) for v in class_metrics_for_company.values())

    # ---- 输入表比率假设（公司层按保险服务收入加权汇总）----
    ratio_map = _get_input_ratio_map()
    ins_rev_by_class = _compute_class_expected(calc_result, '保险服务收入', period_idx=period_idx)

    def _weighted_ratio(key):
        num = 0.0
        den = 0.0
        for cls, d in ratio_map.get(key, {}).items():
            if not d:
                continue
            rv = d.get(period_idx, d.get(max(d.keys())))
            w = abs(ins_rev_by_class.get(cls, 0.0)) or 0.0
            if w > 0:
                num += rv * w
                den += w
        if den <= 0:
            vals = [d.get(period_idx, d.get(max(d.keys()))) for d in ratio_map.get(key, {}).values() if d]
            return (sum(vals) / len(vals)) if vals else 0.0
        return num / den

    # 输入表比率为小数（如 0.948），转换为百分比展示（94.8%）
    exp_claim_ratio = _weighted_ratio('预期赔付率') * 100
    exp_maint_ratio = _weighted_ratio('维持费用率') * 100
    exp_acq_ratio = (_weighted_ratio('跟单获取费用率') + _weighted_ratio('非跟单获取费用率')) * 100

    # 指标规格（达成率看板预实分析明细表展示金额类 + 输入表/系统输出比率类）：
    specs = [
        ('保险服务收入', ins_rev, ['保险服务收入'], False),
        ('保险业务收入', ins_biz, ['保险业务收入'], False),
        ('保险服务费用', ins_exp, ['保险服务费用'], False),
        ('费用成本', cost, ['费用成本'], False),
        ('承保利润', uw, ['承保利润'], False),
        ('投资收益', inv_inc, ['投资收益'], False),
        ('摊销获取费用', company_acq_amort, ['摊销获取费用'], False),
        ('维持费用', company_maint_fee, ['维持费用'], False),
        ('亏损合同损益', company_loss_comp, ['亏损合同损益'], False),
        ('综合成本率', combined_ratio, ['综合成本率'], True),
        ('预期赔付率', exp_claim_ratio, ['预期赔付率'], True),
        ('预期维持费用率', exp_maint_ratio, ['预期维持费用率'], True),
        ('预期获取费用率', exp_acq_ratio, ['预期获取费用率'], True),
    ]

    items = []
    for display, expected, akeys, is_ratio in specs:
        actual = 0.0
        actual_matched = False
        # 上传约定：比率类（综合成本率/预期赔付率/预期维持费用率/预期获取费用率）
        # 以小数形式存储（如 0.95 表示 95%），展示统一为百分比单位需 ×100
        # 优先精确匹配（避免「维持费用」与「预期维持费用率」互相误匹配）
        for ak, av in actual_map.items():
            for pk in akeys:
                if ak.strip() == pk.strip():
                    actual = av * 100 if is_ratio else av
                    actual_matched = True
                    break
            if actual_matched:
                break
        # 精确未命中时再按子串匹配
        if not actual_matched:
            for ak, av in actual_map.items():
                for pk in akeys:
                    if pk in ak or ak in pk:
                        actual = av * 100 if is_ratio else av
                        actual_matched = True
                        break
                if actual_matched:
                    break
        # 仅当预期或实际至少一方有值才展示
        if abs(expected) < 1e-9 and not actual_matched:
            continue
        diff = actual - expected
        if is_ratio:
            diff_pct = actual - expected if actual_matched else 0.0
            rate = (actual / expected * 100) if (expected != 0 and actual_matched) else 0.0
        else:
            rate = (actual / expected * 100) if expected != 0 else 0.0
            diff_pct = (diff / expected * 100) if expected != 0 else 0.0
        # 状态判定：收入/利润越高越好；费用类/比率类越低越好
        expense_like = {'保险服务费用', '费用成本', '再保成本', '摊销获取费用', '维持费用', '亏损合同损益'}
        if is_ratio or display in expense_like:
            status = '有利' if diff < 0 else '不利'
        else:
            status = '有利' if diff >= 0 else '不利'
        items.append({
            'item': display,
            'expected': round(expected, 2),
            'actual': round(actual, 2),
            'diff': round(diff, 2),
            'rate': round(rate, 1),
            'isRatio': is_ratio,
            'hasActual': actual_matched,
            'status': status,
        })

    # ========== 2. 精算险类维度对比 ==========
    class_comparison = _generate_class_comparison(
        class_rows, class_headers, calc_result, period_idx=period_idx
    )

    return {
        'items': items,
        'classComparison': class_comparison,
        'expectedSource': calc_result.get('selectedScenario', '-'),
        'actualDate': actual_date,
        'selectedPeriod': selected_period,
        'availablePeriods': dates,
    }


def _compute_class_expected(calc_result, metric='保险服务收入', period_idx=1):
    """从 PAA计算_MTD 中按精算险类聚合预测值（YTD 累计）。
    metric: 保险服务收入 | 保险服务费用 | 承保利润 | 保险业务收入 | 费用成本 | 综合成本率
    period_idx: 预测时点索引（dates 中的位置；dates[0] 为评估日）
    """
    class_metrics = _compute_class_metrics(calc_result, period_idx=period_idx)
    return {cls: vals.get(metric, 0.0) for cls, vals in class_metrics.items()}


def _to_int(v):
    try:
        return int(float(v)) if v is not None and v != '' else 0
    except (ValueError, TypeError):
        return 0


def _get_input_ratio_map():
    """读取输入表比率假设表（预期赔付率 / 维持费用率 / 跟单获取费用率 / 非跟单获取费用率），
    返回 {key: {险类代码: {月索引(int): 值}}}。月索引对应列名 '1'~'60'。

    对于「预期赔付率」等以「预测组」为粒度的假设表（含直保/分入/分出多种预测组），
    仅保留「直保或分入」预测组的数据——即预测组名称中含「直保或分入」字样的行，
    忽略「分出」行。
    原 bug：将同一险类下的直保/分入与分出预测组同时写入
    `result[key][cls]`，后写入的「分出」值会覆盖「直保或分入」值，导致
    分险种预实明细的「预期赔付率」展示为「分出」预测组的赔付率（语义错误）。
    """
    result = {
        '预期赔付率': {},
        '维持费用率': {},
        '跟单获取费用率': {},
        '非跟单获取费用率': {},
    }
    sheet_for = {
        '预期赔付率': '预期赔付率',
        '维持费用率': '维持费用率',
        '跟单获取费用率': '跟单获取费用或净额结算比例_新业务',
        '非跟单获取费用率': '非跟单获取费用比例_新业务',
    }
    try:
        from data_input.models import SheetData
    except Exception:
        return result
    for key, sheet in sheet_for.items():
        sd = SheetData.objects.filter(sheet_name=sheet, is_active=True).first()
        if not sd:
            continue
        headers = sd.headers or []
        rows = sd.rows or []
        cls_idx = None
        forecast_grp_idx = None
        month_cols = {}
        for i, h in enumerate(headers):
            hs = str(h).strip()
            if hs == '精算险类':
                cls_idx = i
            elif hs == '预测组':
                forecast_grp_idx = i
            elif hs.isdigit():
                mi = int(hs)
                if 1 <= mi <= 60:
                    month_cols[i] = mi
        if cls_idx is None or not month_cols:
            continue
        # 对含「预测组」列的比率假设表（预期赔付率等）：
        #   保留预测组名含「直保或分入」的行（覆盖任何同险类的「分出」数据）
        # 其他比率假设表（仅有「精算险类」一行/级别）保持原行为
        for row in rows:
            if not row or len(row) <= cls_idx:
                continue
            cls = str(row[cls_idx]).strip()
            if not cls:
                continue
            if forecast_grp_idx is not None and forecast_grp_idx < len(row):
                grp = str(row[forecast_grp_idx]).strip()
                if grp and '分出' in grp and '直保或分入' not in grp:
                    continue
            d = result[key].setdefault(cls, {})
            for ci, mi in month_cols.items():
                if ci < len(row):
                    d[mi] = _to_float(row[ci])
    return result


def _compute_class_metrics(calc_result, period_idx=1):
    """按精算险类聚合预测指标（用于分险种预实预期值）。

    数据源改为 PAA计算_MTD 明细：
      - 先按 精算监管险类 筛选
      - 再按 财务科目 汇总
      - 取评估日至当前预测时点的 YTD 累计（dates[0] 为评估日，dates[period_idx] 为当前预测时点）

    返回 {险类代码: {'保险服务收入','保险服务费用','承保利润','保险业务收入','费用成本','综合成本率'}}。
    """
    dates = (calc_result.get('financialStatementsV2') or {}).get('dates') or []
    if not dates or period_idx < 0:
        return {}
    target_idx = min(period_idx, len(dates) - 1)
    # YTD 累计列：从评估日到当前预测时点
    date_keys = dates[:target_idx + 1]

    scenario = calc_result.get('selectedScenario') or calc_result.get('scenario') or '情景0'
    rows = _get_paa_mtd_detail(scenario)
    if not rows:
        return {}

    groups = {}
    item_groups = {}
    for r in rows:
        cls = str(r.get('精算监管险类') or '').strip()
        if not cls:
            continue
        subj = r.get('财务科目')
        item = r.get('科目')
        val = sum(_to_float(r.get(dk, 0)) for dk in date_keys)
        if subj:
            groups.setdefault(cls, {}).setdefault(subj, 0.0)
            groups[cls][subj] += val
        if item:
            item_groups.setdefault(cls, {}).setdefault(item, 0.0)
            item_groups[cls][item] += val

    result = {}
    for cls, vals in groups.items():
        # 保险服务收入：PAA计算_MTD 中财务科目='保险服务收入' 的各月累计
        # （包含 输出_保险合同收入 与 输出_新增保费减值 两行，后者如为 0/None 则自然不计入）
        ins_rev = vals.get('保险服务收入', 0.0)
        # 保险服务费用 / 承保财务损失 在 PAA_MTD 源表中通常为负，展示取绝对值作为成本口径
        ins_exp = abs(vals.get('保险服务费用', 0.0))
        fin_cost = abs(vals.get('承保财务损失', 0.0))
        ins_cost = ins_exp + fin_cost
        uw = ins_rev - ins_exp - fin_cost
        ins_biz = ins_rev
        combined = (1 - uw / ins_rev) * 100 if ins_rev else 0.0
        # 再保成本 = 再保险服务业绩 = 分出保费的分摊 − 摊回保险服务费用 − 分出再保险承保财务损失
        reins_cost = vals.get('分出保费的分摊', 0.0) - vals.get('摊回保险服务费用', 0.0) - vals.get('分出再保险承保财务损失', 0.0)
        # 保险服务费用下的明细科目（按 PAA_MTD 的「科目」列汇总，展示取绝对值）
        item_vals = item_groups.get(cls, {})
        acq_amort = abs(item_vals.get('输出_赔付与费用_摊销的保险获取现金流', 0.0))
        maint_fee = abs(item_vals.get('输出_现金流_支付的维持费用', 0.0))
        loss_comp = abs(item_vals.get('输出_亏损合同损益', 0.0))
        result[cls] = {
            '保险服务收入': ins_rev,
            '保险服务费用': ins_exp,
            '承保利润': uw,
            '保险业务收入': ins_biz,
            '费用成本': ins_cost,
            '综合成本率': combined,
            '再保成本': reins_cost,
            '摊销获取费用': acq_amort,
            '维持费用': maint_fee,
            '亏损合同损益': loss_comp,
        }
    return result


def _generate_class_comparison(class_rows, class_headers, calc_result, period_idx=1):
    """生成精算险类维度对比。
    class_rows: 精算险类实际数工作表数据
    period_idx: 预测时点索引（dates 中位置），默认 1 表示第一个预测时点
    返回：{'headers': [...], 'rows': [{classCode, className, metric, expected, actual, diff, diffPct, status}, ...]}
    """
    # 列名归一化
    headers_lower = [str(h).strip() for h in class_headers]

    def col_idx(name_contains):
        # 先精确匹配（忽略首尾空格），避免「维持费用」误匹配到「预期维持费用率」
        name_norm = name_contains.strip()
        for i, h in enumerate(headers_lower):
            if h.strip() == name_norm:
                return i
        # 精确未命中时再按子串匹配
        for i, h in enumerate(headers_lower):
            if name_contains in h:
                return i
        return -1

    idx_code = col_idx('精算险类代码')
    idx_name = col_idx('精算险类名称')
    idx_date = col_idx('评估时点')

    if idx_code < 0 and idx_name < 0:
        return {'available': False, 'error': '未识别“精算险类代码/名称”列'}

    # 支持的指标（分险种预实维度，与预实明细一致，投资收益除外）
    metric_defs = [
        ('保险服务收入', False),
        ('保险业务收入', False),
        ('保险服务费用', False),
        ('费用成本', False),
        ('承保利润', False),
        ('再保成本', False),
        ('摊销获取费用', False),
        ('维持费用', False),
        ('亏损合同损益', False),
        ('综合成本率', True),
        ('预期赔付率', True),
        ('预期维持费用率', True),
        ('预期获取费用率', True),
    ]
    ratio_map = _get_input_ratio_map()

    def _class_ratio(cls, key):
        if key == '获取费用率':
            a = ratio_map.get('跟单获取费用率', {}).get(cls, {})
            b = ratio_map.get('非跟单获取费用率', {}).get(cls, {})
            va = a.get(period_idx, a.get(max(a.keys()) if a else 1, 0.0)) if a else 0.0
            vb = b.get(period_idx, b.get(max(b.keys()) if b else 1, 0.0)) if b else 0.0
            return va + vb
        d = ratio_map.get(key, {}).get(cls, {})
        if not d:
            return 0.0
        return d.get(period_idx, d.get(max(d.keys())))

    class_metrics = _compute_class_metrics(calc_result, period_idx=period_idx)

    # 按险种聚合实际值
    actual_by_class = {}
    for row in class_rows:
        if len(row) < 2:
            continue
        code = str(row[idx_code]).strip() if idx_code >= 0 else ''
        name = str(row[idx_name]).strip() if idx_name >= 0 else ''
        key = code or name
        if not key:
            continue
        if key not in actual_by_class:
            actual_by_class[key] = {'code': code, 'name': name, 'values': {}}
        # 读取原始实际值
        raw = {}
        for label, is_ratio in metric_defs:
            cidx = col_idx(label)
            if cidx >= 0:
                v = _to_float(row[cidx])
                # 上传约定：比率类以小数存储（如 0.95 表示 95%），展示统一为百分比单位需 ×100
                if is_ratio:
                    v = v * 100
                raw[label] = v
        # 实际数约定：费用类列在源表中以负数（借方）存储，展示取绝对值
        for _expense_key in ['保险服务费用', '费用成本', '摊销获取费用', '维持费用', '亏损合同损益']:
            if _expense_key in raw:
                raw[_expense_key] = abs(raw[_expense_key])
        # 承保利润：源表因费用负号导致严重失真，按 PAA 公式由实际分量重算，
        # 保证与综合成本率口径一致、可与预期对帐
        cidx_uw = col_idx('承保利润')
        cidx_rev = col_idx('保险服务收入')
        cidx_exp = col_idx('保险服务费用')
        cidx_ced = col_idx('分出再保险净损益')
        cidx_ifie = col_idx('承保财务损益净额')
        if cidx_uw >= 0:
            rev = _to_float(row[cidx_rev]) if cidx_rev >= 0 else raw.get('保险服务收入', 0.0)
            exp_abs = abs(_to_float(row[cidx_exp])) if cidx_exp >= 0 else 0.0
            ced = _to_float(row[cidx_ced]) if cidx_ced >= 0 else 0.0
            ifie = _to_float(row[cidx_ifie]) if cidx_ifie >= 0 else 0.0
            raw['承保利润'] = rev + ced - exp_abs - ifie
        actual_by_class[key]['values'].update(raw)

    rows = []
    # 按实际数据中有值的险种输出；若预测中无该险种则 expected=0
    for key, info in sorted(actual_by_class.items()):
        code = info['code']
        name = info['name']
        values = info['values']
        cm = class_metrics.get(code, class_metrics.get(name, {}))

        for label, is_ratio in metric_defs:
            actual = values.get(label, 0)
            expected = 0.0
            if label in cm:
                expected = cm.get(label, 0.0)
            elif is_ratio:
                rkey = {'预期赔付率': '预期赔付率', '预期维持费用率': '维持费用率',
                        '预期获取费用率': '获取费用率'}.get(label)
                if rkey:
                    # 输入表比率为小数，转换为百分比展示
                    expected = (_class_ratio(code, rkey) or _class_ratio(name, rkey)) * 100

            # 仅当实际或预期有值才展示
            if actual == 0 and expected == 0:
                continue

            diff = actual - expected
            has_actual = actual != 0
            if is_ratio:
                # 比率类：偏差用 pp（百分点）
                diff_pct = (actual - expected) if has_actual else 0.0
                rate = (actual / expected * 100) if (expected != 0 and has_actual) else 0.0
            else:
                rate = (actual / expected * 100) if expected != 0 else 0.0
                diff_pct = (diff / expected * 100) if expected != 0 else 0.0

            # 状态判定：收入/利润越高越好；费用类/比率类越低越好
            expense_like = {'保险服务费用', '费用成本', '再保成本', '摊销获取费用', '维持费用', '亏损合同损益'}
            if is_ratio or label in expense_like:
                status = '有利' if diff < 0 else '不利'
            else:
                status = '有利' if diff >= 0 else '不利'
            # 重大偏差标记（偏差%绝对值 >= 5%）
            is_significant = abs(diff_pct) >= 5

            rows.append({
                'classCode': code,
                'className': name,
                'metric': label,
                'expected': round(expected, 2),
                'actual': round(actual, 2),
                'diff': round(diff, 2),
                'diffPct': round(diff_pct, 2),
                'rate': round(rate, 1),
                'status': status,
                'isSignificant': is_significant,
                'isRatio': is_ratio,
                'hasActual': has_actual,
            })

    return {
        'available': len(rows) > 0,
        'headers': ['险种代码', '险种名称', '指标', '预算（预期）', '实际', '偏差', '偏差%', '达成率', '状态'],
        'rows': rows,
        'metrics': [d[0] for d in metric_defs],
        'classes': sorted({r['classCode'] for r in rows}),
    }


# ============================================================
# 新旧准则利润表桥接比对
# ============================================================

_BRIDGE_EXCEL_PATH = os.path.join(BASE_DIR, '..', '验证文件', '新旧准则利润表桥接表.xlsx')


def _normalize_bridge_subject(s):
    """归一化科目名，用于模糊匹配。"""
    if not s:
        return ''
    s = str(s).strip()
    for ch in '一二三四五六七八九十、（）()-_':
        s = s.replace(ch, '')
    return s.replace(' ', '').replace('号填列', '')


def _is_bridge_group_subject(s):
    """判断是否为大写数字开头的一级科目（一、二、三...）。"""
    if not s:
        return False
    return bool(re.match(r'^[一二三四五六七八九十]+、', str(s).strip()))


def _deterministic_factor(seed, lower=0.97, upper=1.03):
    """基于 seed 生成确定性的扰动系数，用于旧准则数字拟合。"""
    import hashlib
    h = hashlib.md5(str(seed).encode('utf-8')).hexdigest()
    rand = int(h[:8], 16) / 0xffffffff
    return lower + rand * (upper - lower)


def _match_bridge_subject(subject, candidates):
    """在候选科目列表中寻找最佳匹配项。"""
    if not subject or not candidates:
        return None
    subj = _normalize_bridge_subject(subject)
    if not subj:
        return None
    # 精确匹配
    for item in candidates:
        if _normalize_bridge_subject(item) == subj:
            return item
    # 包含匹配：若去除匹配部分后剩余字符含拉丁字母（如“保险服务收入_BBA”后缀 BBA），
    # 视为不同科目，避免把子科目误匹配到父科目聚合值。
    import re
    for item in candidates:
        nitem = _normalize_bridge_subject(item)
        if not nitem:
            continue
        if subj in nitem or nitem in subj:
            remainder = (nitem.replace(subj, '') if subj in nitem else subj.replace(nitem, ''))
            if re.search(r'[A-Za-z]', remainder):
                continue
            return item
    return None


def _norm_old_standard_key(s):
    """将上传的旧准则科目名归一化为桥接表原始科目名，兼容前端展示改名后的别名。"""
    if not s:
        return s
    s = str(s).strip()
    alias_to_canon = {
        '一、保险服务收入': '一、保险合同收入',
        '一、营业收入': '一、保险合同收入',
        '二、保险服务费用': '二、保险合同支出',
        '三、分出保费的分摊': '三、分出保费',
        '三、分出保': '三、分出保费',
    }
    return alias_to_canon.get(s, s)


# 新旧准则对比表权威展示结构（与「旧准则数字上传示例.xlsx」一致）：
# 一级科目「一~十」+ 其下二级明细；旧/新准则两侧共用同一科目命名。
# 作为对比表的行模板，底层数据按 上传示例 -> 系统输出 -> 权威桥接表 的优先级取数。
BRIDGE_TEMPLATE = [
    ('一、保险服务收入', ['已赚保费', '投资成分的拆分', '应收保费减值']),
    ('二、保险服务费用', ['未决变动', '已决赔款', '投资成分的拆分', '亏损确认-再保前', '获取费用的分摊', '维持费用']),
    ('三、分出保费的分摊', ['分出已赚毛保费', '投资成分的拆分-分出', '分出已赚净额手续费']),
    ('四、摊回保险服务费用', ['摊回未决变动', '摊回赔付支出', '投资成分的拆分-分出', '摊回亏损部分的变化', '摊回调整手续费及复效保费']),
    ('五、非履约费用', []),
    ('六、提取保费准备金', []),
    ('七、其他收益', []),
    ('八、承保财务损失', ['承保财务损益', '分出再保险财务损益']),
    ('九、其他业务成本', []),
    ('十、营业利润', []),
]


def _get_bridge_comparison(scenario=None, period_idx=None):
    """新旧准则预测结果对比：新准则优先取上传新准则数字，其次系统输出（财务报表 YTD/PAA MTD），最后权威桥接表 E/F；
    旧准则优先取上传旧准则数字，其次按新准则输出拟合。返回旧/新准则指标卡片与对比表（差异=新准则预测-旧准则预测）。"""
    from openpyxl import load_workbook
    calc_result = _resolve_calc_result(scenario)
    if not calc_result:
        return {'available': False, 'error': '尚未执行预测计算，请先到「计算流程」执行计算。'}
    # 确保使用最新对齐的 merged 财务报表（与 /api/calc/results 一致），避免持久化缓存中的 stale merged
    try:
        _calc_copy = dict(calc_result)
        _calc_copy['financialStatementsV2Merged'] = _build_merged_fs_v2(_calc_copy)
        calc_result = _calc_copy
    except Exception:
        pass
    # 与「输出财务报表」「结果总览」完全一致：使用 merged 财务报表（新准则预测=系统输出）
    fs = calc_result.get('financialStatementsV2Merged') or calc_result.get('financialStatementsV2') or {}
    dates = fs.get('dates') or []
    if period_idx is None:
        period_idx = 1 if len(dates) > 1 else 0

    # 系统输出科目查找表（优先 YTD 财务报表）
    fs_value_map = {}
    fs_items = []
    if fs and fs.get('ytd'):
        for section in ('income_statement', 'balance_sheet'):
            for r in fs['ytd'].get(section, []):
                item = r.get('item', '')
                if item:
                    fs_items.append(item)
                    fs_value_map[item] = _value_at_index(r.get('values', []), period_idx)

    # PAA计算_MTD 聚合值作为补充（按 财务科目 与 科目 两级 key 聚合，便于二级科目模糊匹配）
    paa_mtd_map = {}
    selected_scenario = calc_result.get('selectedScenario') or calc_result.get('scenario') or scenario or '情景0'
    paa_mtd_detail = _get_paa_mtd_detail(selected_scenario)
    if paa_mtd_detail:
        date_key = dates[period_idx] if 0 <= period_idx < len(dates) else (dates[-1] if dates else None)
        for r in paa_mtd_detail:
            subject = str(r.get('财务科目', '')).strip()
            subject2 = str(r.get('科目', '')).strip()
            if subject:
                paa_mtd_map.setdefault(subject, 0.0)
                paa_mtd_map[subject] += _to_float(r.get(date_key, 0)) if date_key else 0.0
            if subject2:
                paa_mtd_map.setdefault(subject2, 0.0)
                paa_mtd_map[subject2] += _to_float(r.get(date_key, 0)) if date_key else 0.0

    # 权威桥接表（兜底数据源）：构建 旧侧(C/D 列) 与 新侧(E/F 列) 科目->金额 映射，缺失不报错
    bridge_old_map = {}
    bridge_new_map = {}
    if os.path.exists(_BRIDGE_EXCEL_PATH):
        try:
            wb = load_workbook(_BRIDGE_EXCEL_PATH, data_only=True, read_only=True)
            ws = wb[wb.sheetnames[0]]
            for row in ws.iter_rows(min_row=4, values_only=True):
                if len(row) < 6:
                    continue
                b_old_subj = str(row[2]).strip() if row[2] is not None else ''
                b_old_val = _to_float(row[3])
                b_new_subj = str(row[4]).strip() if row[4] is not None else ''
                b_new_val = _to_float(row[5])
                if b_old_subj:
                    bridge_old_map[b_old_subj] = b_old_val
                if b_new_subj:
                    bridge_new_map[b_new_subj] = b_new_val
            wb.close()
        except Exception:
            bridge_old_map, bridge_new_map = {}, {}

    # 旧准则 / 新准则 上传明细与 KPI：若管理员上传了数字 Excel，优先使用实际上传值。
    # 必须在遍历桥接表行之前加载，否则行内匹配上传科目时 *_detail_map 未定义。
    uploaded_old = None
    uploaded_new = None
    old_detail_map = {}
    new_detail_map = {}
    is_uploaded_bridge_format = False
    if os.path.exists(_OLD_STANDARD_CACHE_FILE):
        try:
            with open(_OLD_STANDARD_CACHE_FILE, 'r', encoding='utf-8') as f:
                _old_cache = json.load(f)
            _old_data = _old_cache.get('data', {}) or {}
            if _old_data.get('insRev') is not None and _old_data.get('uwProfit') is not None \
                    and _old_data.get('netProfit') is not None and _old_data.get('combinedRatio') is not None:
                uploaded_old = {
                    'insRev': float(_old_data['insRev']),
                    'uwProfit': float(_old_data['uwProfit']),
                    'netProfit': float(_old_data['netProfit']),
                    'combinedRatio': float(_old_data['combinedRatio']),
                }
            # 桥接展开格式的旧准则明细行：按旧准则科目名建立查找表。
            # 同一科目出现多行时累加（兼容示例文件中的重复明细行），避免后行覆盖前行导致数值异常。
            for dr in (_old_cache.get('detailRows') or []):
                subj = str(dr.get('oldSubject', '')).strip()
                if subj:
                    val = _to_float(dr.get('oldValue'))
                    old_detail_map[subj] = old_detail_map.get(subj, 0.0) + val
                    # 兼容前端展示改名后的别名（如用户上传「一、保险服务收入」应能命中桥接表「一、保险合同收入」）
                    canon = _norm_old_standard_key(subj)
                    if canon != subj:
                        old_detail_map[canon] = old_detail_map.get(canon, 0.0) + val
            is_uploaded_bridge_format = bool(old_detail_map) or _old_cache.get('isBridgeFormat')
            # 桥接展开格式的新准则明细行：按新准则科目名（归一化）建立查找表。
            for dr in (_old_cache.get('detailRows') or []):
                nsubj = str(dr.get('newSubject', '')).strip()
                if nsubj:
                    nval = _to_float(dr.get('newValue'))
                    nk = _normalize_bridge_subject(nsubj)
                    if nk:
                        new_detail_map[nk] = new_detail_map.get(nk, 0.0) + nval
            # 新准则 KPI（与旧准则 KPI 对称）
            _new_data = _old_cache.get('newKpis') or {}
            if _new_data.get('insRev') is not None and _new_data.get('uwProfit') is not None \
                    and _new_data.get('netProfit') is not None and _new_data.get('combinedRatio') is not None:
                uploaded_new = {
                    'insRev': float(_new_data['insRev']),
                    'uwProfit': float(_new_data['uwProfit']),
                    'netProfit': float(_new_data['netProfit']),
                    'combinedRatio': float(_new_data['combinedRatio']),
                }
        except Exception:
            uploaded_old = None
            uploaded_new = None
            old_detail_map = {}
            new_detail_map = {}

    # 新准则取值：优先上传新准则数字 -> 系统输出(财务报表YTD/PAA MTD) -> 权威桥接表(E/F)
    def _lookup_new(subj):
        nk = _normalize_bridge_subject(subj)
        if nk and nk in new_detail_map:
            return new_detail_map[nk], 'upload'
        matched = _match_bridge_subject(subj, fs_items)
        if matched and fs_value_map.get(matched) is not None:
            return fs_value_map.get(matched), 'system'
        matched_paa = _match_bridge_subject(subj, list(paa_mtd_map.keys()))
        if matched_paa and paa_mtd_map.get(matched_paa) is not None:
            return paa_mtd_map.get(matched_paa), 'system'
        if subj in bridge_new_map:
            return bridge_new_map[subj], 'bridge'
        nk2 = _norm_old_standard_key(subj)
        if nk2 in bridge_new_map:
            return bridge_new_map[nk2], 'bridge'
        return 0.0, 'none'

    # 旧准则取值：优先上传旧准则数字 -> 权威桥接表(C/D) -> 以新准则输出按组因子拟合
    def _lookup_old(subj, new_val, factor):
        ov = old_detail_map.get(subj)
        if ov is None:
            ov = old_detail_map.get(_norm_old_standard_key(subj))
        if ov is not None:
            return ov, 'upload'
        if subj in bridge_old_map:
            return bridge_old_map[subj], 'bridge'
        nk2 = _norm_old_standard_key(subj)
        if nk2 in bridge_old_map:
            return bridge_old_map[nk2], 'bridge'
        if new_val not in (0.0, None):
            return new_val * factor, 'fitted'
        return 0.0, 'none'

    # 依据 BRIDGE_TEMPLATE（与「旧准则数字上传示例.xlsx」一致的「一~十」科目体系）构建对比表行
    result_rows = []
    for group_subj, details in BRIDGE_TEMPLATE:
        g_seed = f"{scenario or '情景0'}|{period_idx}|{group_subj}"
        g_factor = _deterministic_factor(g_seed, lower=0.97, upper=1.03)
        new_val, new_src = _lookup_new(group_subj)
        old_val, old_src = _lookup_old(group_subj, new_val, g_factor)
        result_rows.append({
            'oldSubject': group_subj,
            'oldValue': round(old_val, 2),
            'newSubject': group_subj,
            'newValue': round(new_val, 2),
            'diff': round(new_val - old_val, 2),
            'matchedSubject': group_subj,
            'isGroup': True,
            'oldStandardSource': old_src,
            'newStandardSource': new_src,
        })
        for detail_subj in details:
            d_new, d_ns = _lookup_new(detail_subj)
            d_old, d_os = _lookup_old(detail_subj, d_new, g_factor)
            result_rows.append({
                'oldSubject': detail_subj,
                'oldValue': round(d_old, 2),
                'newSubject': detail_subj,
                'newValue': round(d_new, 2),
                'diff': round(d_new - d_old, 2),
                'matchedSubject': detail_subj,
                'isGroup': False,
                'oldStandardSource': d_os,
                'newStandardSource': d_ns,
            })

    # 新准则指标卡片：若管理员上传了新准则数字 Excel，优先使用实际上传值；否则取系统输出 YTD
    if uploaded_new:
        new_standard_kpis = {
            'insRev': round(uploaded_new['insRev'], 2),
            'uwProfit': round(uploaded_new['uwProfit'], 2),
            'netProfit': round(uploaded_new['netProfit'], 2),
            'combinedRatio': round(uploaded_new['combinedRatio'], 2),
        }
        new_standard_source = 'upload'
    else:
        ns_ins = fs_value_map.get('保险服务收入') or 0.0
        ns_uw = fs_value_map.get('承保利润') or 0.0
        ns_np = fs_value_map.get('五、净利润（净亏损以"-"号填列）') or 0.0
        ns_combined = (1 - ns_uw / ns_ins) * 100 if ns_ins else 0.0
        new_standard_kpis = {
            'insRev': round(ns_ins, 2),
            'uwProfit': round(ns_uw, 2),
            'netProfit': round(ns_np, 2),
            'combinedRatio': round(ns_combined, 2),
        }
        new_standard_source = 'system'
    # 旧准则指标卡片：默认以新准则系统输出 KPI 为基准做小幅拟合；
    # 若管理员上传了旧准则数字 Excel，则优先使用实际上传值（已在上方加载）。
    if uploaded_old:
        old_standard_kpis = {
            'insRev': round(uploaded_old['insRev'], 2),
            'uwProfit': round(uploaded_old['uwProfit'], 2),
            'netProfit': round(uploaded_old['netProfit'], 2),
            'combinedRatio': round(uploaded_old['combinedRatio'], 2),
        }
        old_standard_source = 'upload'
    elif is_uploaded_bridge_format:
        # 无 4 个 KPI 但上传了桥接展开格式明细：仍使用上传数据，卡片暂以拟合值展示
        kpi_seed = f"{scenario or '情景0'}|{period_idx}|old_standard_kpis"
        kpi_factor = _deterministic_factor(kpi_seed, lower=0.97, upper=1.03)
        old_standard_kpis = {
            'insRev': round(ns_ins * kpi_factor, 2),
            'uwProfit': round(ns_uw * kpi_factor, 2),
            'netProfit': round(ns_np * kpi_factor, 2),
            'combinedRatio': round(ns_combined, 2),
        }
        old_standard_source = 'upload'
    else:
        kpi_seed = f"{scenario or '情景0'}|{period_idx}|old_standard_kpis"
        kpi_factor = _deterministic_factor(kpi_seed, lower=0.97, upper=1.03)
        old_standard_kpis = {
            'insRev': round(ns_ins * kpi_factor, 2),
            'uwProfit': round(ns_uw * kpi_factor, 2),
            'netProfit': round(ns_np * kpi_factor, 2),
            'combinedRatio': round(ns_combined, 2),
        }
        old_standard_source = 'fitted'

    return {
        'available': len(result_rows) > 0,
        'rows': result_rows,
        'period': dates[period_idx] if period_idx < len(dates) else '',
        'periodIdx': period_idx,
        'scenario': calc_result.get('selectedScenario', '情景0'),
        'dates': dates,
        'newStandardKpis': new_standard_kpis,
        'oldStandardKpis': old_standard_kpis,
        'oldStandardSource': old_standard_source,
        'newStandardSource': new_standard_source,
    }


@login_required
def api_bridge_comparison(request):
    """新旧准则利润表桥接比对 API。

    参数：
      - scenario: 情景名（默认基础情景/情景0）
      - period: 预测时点索引或日期字符串
    """
    scenario = request.GET.get('scenario') or None
    period = request.GET.get('period') or None
    period_idx = None
    if period is not None:
        try:
            period_idx = int(period)
        except (ValueError, TypeError):
            pass
    data = _get_bridge_comparison(scenario=scenario, period_idx=period_idx)
    return JsonResponse({'success': data.get('available', False), **data})


# ============================================================
# 部署管理 API
# ============================================================

@login_required
def api_deploy_config(request):
    """获取或保存部署配置"""
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'success': False, 'error': '权限不足，仅管理员可操作'}, status=403)

    if request.method == 'GET':
        return JsonResponse({'success': True, 'config': get_masked_config()})

    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
            config = load_deploy_config()

            # 更新字段
            if 'host' in body:
                config['host'] = body['host'].strip()
            if 'port' in body:
                config['port'] = int(body['port'])
            if 'username' in body:
                config['username'] = body['username'].strip()
            if 'password' in body and body['password']:
                config['password'] = body['password']
            if 'private_key_path' in body:
                config['private_key_path'] = body['private_key_path'].strip()
            if 'remote_project_dir' in body:
                config['remote_project_dir'] = body['remote_project_dir'].strip()
            if 'force_rebuild' in body:
                config['force_rebuild'] = bool(body['force_rebuild'])

            save_deploy_config(config)
            return JsonResponse({'success': True, 'config': get_masked_config()})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'success': False, 'error': '不支持的请求方法'}, status=405)


@login_required
def api_deploy_test(request):
    """测试 SSH 连接"""
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'success': False, 'error': '权限不足，仅管理员可操作'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': '仅支持 POST 请求'}, status=405)

    try:
        config = load_deploy_config()
        # 如果请求体中有临时配置，覆盖（允许未保存密码直接使用）
        body = {}
        if request.body:
            try:
                body = json.loads(request.body)
            except json.JSONDecodeError:
                pass

        for key in ['host', 'port', 'username', 'password', 'private_key_path']:
            if key in body and body[key] is not None:
                config[key] = body[key] if key != 'port' else int(body[key])

        # 明确检查凭据
        if not config.get('host'):
            return JsonResponse({'success': False, 'message': '未配置服务器地址，请先填写并保存 SSH 配置', 'server_info': ''})
        if not config.get('password') and not config.get('private_key_path'):
            return JsonResponse({'success': False, 'message': '未配置 SSH 密码或私钥。请在表单中输入服务器密码，或点击"保存配置"后重试。', 'server_info': ''})

        result = test_ssh_connection(config)
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'测试失败: {str(e)}', 'server_info': ''})


@login_required
def api_deploy_push(request):
    """触发部署到云端"""
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'success': False, 'error': '权限不足，仅管理员可操作'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': '仅支持 POST 请求'}, status=405)

    try:
        config = load_deploy_config()

        # 合并请求体中的临时配置（允许用户不保存直接用当前表单密码）
        body = {}
        if request.body:
            try:
                body = json.loads(request.body)
            except json.JSONDecodeError:
                pass

        for key in ['host', 'port', 'username', 'password', 'private_key_path', 'remote_project_dir',
                    'remote_temp_archive', 'force_rebuild']:
            if key in body and body[key] is not None:
                if key == 'force_rebuild':
                    config[key] = bool(body[key])
                elif key == 'port':
                    config[key] = int(body[key])
                else:
                    config[key] = body[key]

        # 明确检查凭据
        if not config.get('host'):
            return JsonResponse({'success': False, 'error': '未配置服务器地址，请先填写并保存 SSH 配置'})
        if not config.get('password') and not config.get('private_key_path'):
            return JsonResponse({'success': False, 'error': '未配置 SSH 密码或私钥。请在表单中输入服务器密码，或点击"保存配置"后重试。'})

        # 执行部署
        result = deploy_to_cloud(config)
        if result.get('success'):
            log_operation(request, SystemOperationLog.ACTION_DEPLOY,
                          target=config.get('host', ''),
                          detail=f"Docker 一键部署{'（强制重建）' if config.get('force_rebuild') else ''} 成功")
        else:
            log_operation(request, SystemOperationLog.ACTION_DEPLOY,
                          target=config.get('host', ''),
                          detail=f"部署失败: {result.get('error', '')[:500]}",
                          level='ERROR')
        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({'success': False, 'error': f'部署异常: {str(e)}', 'log': str(e)})


# ============================================================
# 数据及逻辑归集：计算逻辑概要（已固化为 JSON，不再依赖桌面 Excel）
# ============================================================
# 原数据来自：C:\\Users\\王宗彦\\Desktop\\预测模型逻辑介绍.xlsx
# 为避免云端服务器不存在该本地路径，已将 Excel 内容固化到代码中。
_LOGIC_OUTLINE_DATA = {'success': True, 'tree': [{'name': '保险服务收入', 'children': [{'name': '保险服务收入', 'meaning': '满期保费，对投资成分、保费减值等进行调整', 'entries': [{'method': '满期保费（1/365法或风险分布法，下同）', 'detail': '有效业务：上年末时点UPR*预测年度赚取比例，UPR为上年末时点实际结果\n新业务：保险业务收入*预测年度赚取比例，保险业务收入为当年规划数', 'i4': '已赚保费，但I4包含了递延获取费用和亏损变动', 'inputs': '有效业务： 系统期初余额表', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '未到期赚取模式_现有业务', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '新业务： 新业务保费收入', 'adjust': '中', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '未到期赚取模式_新业务', 'adjust': '低', 'sensitivity': '高'}, {'method': '扣减：投资成分的分解', 'detail': '满期保费*投资成分占比，有效业务投资成分为合同组加权后的比例，新业务为预测的比例', 'i4': '新增', 'inputs': '系统期初余额表', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '投资成分比例', 'adjust': '低', 'sensitivity': '无'}, {'method': '增加：计息', 'detail': '保费现金流计息/折现到预测时点的利息*赚取比例，保费现金流为有效业务应收保费或新业务保险业务收入根据保费收取计划展开成现金流', 'i4': '新增', 'inputs': '有效业务： 初始确认利率曲线', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '新业务： 即期利率曲线', 'adjust': '无', 'sensitivity': '低'}, {'method': '扣减：保费减值', 'detail': '暂时由公司预测后输入', 'i4': '科目重分类', 'inputs': '新业务应收保费减值', 'adjust': '中', 'sensitivity': '低'}, {'method': '扣减：分入业务净额结算手续费', 'detail': '类似于投资成分', 'i4': '科目重分类，I4隐含在手续费递延中', 'inputs': '新业务跟单获取费用比例', 'adjust': '中', 'sensitivity': '高'}], 'summary': {'title': '满期保费（1/365法或风险分布法，下同）', 'effective': '上年末时点UPR*预测年度赚取比例，UPR为上年末时点实际结果', 'new': '保险业务收入*预测年度赚取比例，保险业务收入为当年规划数', 'i4': '已赚保费，但I4包含了递延获取费用和亏损变动', 'input_details': [{'table': '系统期初余额表', 'biz': '有效业务', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '未到期赚取模式_现有业务', 'biz': '', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '新业务保费收入', 'biz': '新业务', 'adjust': '中', 'sensitivity': '高', 'highlight': False}, {'table': '未到期赚取模式_新业务', 'biz': '', 'adjust': '低', 'sensitivity': '高', 'highlight': False}, {'table': '系统期初余额表', 'biz': '', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '投资成分比例', 'biz': '', 'adjust': '低', 'sensitivity': '无', 'highlight': False}, {'table': '初始确认利率曲线', 'biz': '有效业务', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '即期利率曲线', 'biz': '新业务', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '新业务应收保费减值', 'biz': '', 'adjust': '中', 'sensitivity': '低', 'highlight': False}, {'table': '新业务跟单获取费用比例', 'biz': '', 'adjust': '中', 'sensitivity': '高', 'highlight': False}], 'inputs': ['系统期初余额表', '未到期赚取模式_现有业务', '新业务保费收入', '未到期赚取模式_新业务', '系统期初余额表', '投资成分比例', '初始确认利率曲线', '即期利率曲线', '新业务应收保费减值', '新业务跟单获取费用比例'], 'adjust': ['无', '中', '低'], 'sensitivity': ['低', '高', '无']}}]}, {'name': '保险服务费用', 'children': [{'name': '获取费用摊销', 'meaning': '满期获取费用，考虑计息影响', 'entries': [{'method': '满期获取费用（1/365法或风险分布法，与满期保费相同）', 'detail': '类似于满期保费，新业务考虑每个合同组获取费用率水平', 'i4': '科目重分类，I4隐含在已赚保费中', 'inputs': '有效业务： 系统期初余额表', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '未到期赚取模式_现有业务', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '新业务： 新业务保费收入', 'adjust': '中', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '新业务跟单获取费用比例', 'adjust': '中', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '新业务非跟单获取费用比例', 'adjust': '中', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '未到期赚取模式_新业务', 'adjust': '低', 'sensitivity': '高'}, {'method': '增加：计息', 'detail': '类似于保费计息', 'i4': '新增', 'inputs': '同保费计息', 'adjust': None, 'sensitivity': None}], 'summary': {'title': '满期获取费用（1/365法或风险分布法，与满期保费相同）', 'effective': '满期获取费用，考虑计息影响', 'new': '', 'i4': '科目重分类，I4隐含在已赚保费中', 'input_details': [{'table': '系统期初余额表', 'biz': '有效业务', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '未到期赚取模式_现有业务', 'biz': '', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '新业务保费收入', 'biz': '新业务', 'adjust': '中', 'sensitivity': '高', 'highlight': False}, {'table': '新业务跟单获取费用比例', 'biz': '', 'adjust': '中', 'sensitivity': '高', 'highlight': False}, {'table': '新业务非跟单获取费用比例', 'biz': '', 'adjust': '中', 'sensitivity': '高', 'highlight': False}, {'table': '未到期赚取模式_新业务', 'biz': '', 'adjust': '低', 'sensitivity': '高', 'highlight': False}, {'table': '同保费计息', 'biz': '', 'adjust': '', 'sensitivity': '', 'highlight': False}], 'inputs': ['系统期初余额表', '未到期赚取模式_现有业务', '新业务保费收入', '新业务跟单获取费用比例', '新业务非跟单获取费用比例', '未到期赚取模式_新业务', '同保费计息'], 'adjust': ['无', '中', '低'], 'sensitivity': ['低', '高']}}, {'name': '维持费用', 'meaning': '当期发生维持费用', 'entries': [{'method': '当期发生维持费用', 'detail': '由公司预测后输入，如输入维度高于合同组，根据各合同组的（满期保费*分险种预期维持费用率）进行分摊', 'i4': '科目重分类，同时费用口径与I4不同', 'inputs': '维持费用率（精算）', 'adjust': '中', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '实际维持费用（财务）', 'adjust': '中', 'sensitivity': '高'}], 'summary': {'title': '当期发生维持费用', 'effective': '当期发生维持费用', 'new': '', 'i4': '科目重分类，同时费用口径与I4不同', 'input_details': [{'table': '维持费用率（精算）', 'biz': '', 'adjust': '中', 'sensitivity': '高', 'highlight': False}, {'table': '实际维持费用（财务）', 'biz': '', 'adjust': '中', 'sensitivity': '高', 'highlight': False}], 'inputs': ['维持费用率（精算）', '实际维持费用（财务）'], 'adjust': ['中'], 'sensitivity': ['高']}}, {'name': '赔付支出', 'meaning': '当期赔付及间接理赔费用支出', 'entries': [{'method': '当期赔付支出', 'detail': '满期保费*赔付率*累计赔付比例', 'i4': '不变', 'inputs': '预期赔付率', 'adjust': '高', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '实际赔付比例', 'adjust': '高', 'sensitivity': '低'}, {'method': '当期间接理赔费用支出', 'detail': '当期赔付支出*未决间接理赔费用率，如未决间接理赔费用率已含在赔付率中，则不单独列示', 'i4': '不变', 'inputs': '未决间接理赔费用率', 'adjust': '低', 'sensitivity': '低'}], 'summary': {'title': '当期赔付支出', 'effective': '当期赔付及间接理赔费用支出', 'new': '', 'i4': '不变', 'input_details': [{'table': '预期赔付率', 'biz': '', 'adjust': '高', 'sensitivity': '高', 'highlight': True}, {'table': '实际赔付比例', 'biz': '', 'adjust': '高', 'sensitivity': '低', 'highlight': False}, {'table': '未决间接理赔费用率', 'biz': '', 'adjust': '低', 'sensitivity': '低', 'highlight': False}], 'inputs': ['预期赔付率', '实际赔付比例', '未决间接理赔费用率'], 'adjust': ['高', '低'], 'sensitivity': ['高', '低']}}, {'name': '提取未决赔款准备金', 'meaning': '期初到期末计提未决赔款准备金的提转差', 'entries': [{'method': '期末未决赔款准备金', 'detail': '有效业务：期初未决现金流+（满期保费*预期赔付率-赔付支出）\n新业务：满期保费*预期赔付率-赔付支出', 'i4': '不变', 'inputs': '有效业务： 系统期初余额表', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '未决赔付模式', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '预期赔付率', 'adjust': '高', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': 'RA比例_现有业务', 'adjust': '无', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '新业务： 未决赔付模式', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '未决间接理赔费用率', 'adjust': '低', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '预期赔付率', 'adjust': '高', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': 'RA比例_新业务', 'adjust': '无', 'sensitivity': '高'}, {'method': '扣减：期初未决赔款准备金', 'detail': '同上', 'i4': '不变', 'inputs': '同上', 'adjust': None, 'sensitivity': None}, {'method': '增加：折现', 'detail': '使用合同组初始确认利率对期初及期末未决折现', 'i4': '新增', 'inputs': '同保费计息', 'adjust': None, 'sensitivity': None}], 'summary': {'title': '期末未决赔款准备金', 'effective': '期初未决现金流+（满期保费*预期赔付率-赔付支出）', 'new': '满期保费*预期赔付率-赔付支出', 'i4': '不变', 'input_details': [{'table': '系统期初余额表', 'biz': '有效业务', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '未决赔付模式', 'biz': '', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '预期赔付率', 'biz': '', 'adjust': '高', 'sensitivity': '高', 'highlight': True}, {'table': 'RA比例_现有业务', 'biz': '', 'adjust': '无', 'sensitivity': '高', 'highlight': False}, {'table': '未决赔付模式', 'biz': '新业务', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '未决间接理赔费用率', 'biz': '', 'adjust': '低', 'sensitivity': '低', 'highlight': False}, {'table': 'RA比例_新业务', 'biz': '', 'adjust': '无', 'sensitivity': '高', 'highlight': False}, {'table': '同保费计息', 'biz': '', 'adjust': '', 'sensitivity': '', 'highlight': False}], 'inputs': ['系统期初余额表', '未决赔付模式', '预期赔付率', 'RA比例_现有业务', '未决赔付模式', '未决间接理赔费用率', 'RA比例_新业务', '同保费计息'], 'adjust': ['无', '高', '低'], 'sensitivity': ['低', '高']}}, {'name': '亏损合同损益', 'meaning': '期初到期末计提未到期亏损部分的提转差', 'entries': [{'method': '期末未到期亏损部分', 'detail': 'MAX(预期未来现金流-未到期非亏损部分,0)', 'i4': '不变', 'inputs': '有效业务： 系统期初余额表', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': 'RA比例_现有业务', 'adjust': '无', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '保费现金流模式_现有业务', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': 'IACF现金流模式_现有业务', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '未到期赚取模式_现有业务', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '预期赔付率', 'adjust': '高', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '维持费用率（精算）', 'adjust': '中', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '未到期间接理赔费用率', 'adjust': '低', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '即期利率曲线', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '新业务： 新业务保费收入', 'adjust': '中', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '新业务跟单获取费用比例', 'adjust': '中', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '新业务非跟单获取费用比例', 'adjust': '中', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '保费现金流模式_新业务', 'adjust': '高', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': 'IACF现金流模式_新业务', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '未到期赚取模式_新业务', 'adjust': '低', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '预期赔付率', 'adjust': '高', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '维持费用率（精算）', 'adjust': '中', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '未到期间接理赔费用率', 'adjust': '低', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '即期利率曲线', 'adjust': '无', 'sensitivity': '低'}, {'method': '扣减：期初未到期亏损部分', 'detail': '同上', 'i4': '不变', 'inputs': '同上', 'adjust': None, 'sensitivity': None}, {'method': '增加：折现', 'detail': '使用即期利率对各期的预期未来现金流折现', 'i4': 'I4久期大于1年才折现', 'inputs': '同保费计息', 'adjust': None, 'sensitivity': None}], 'summary': {'title': '期末未到期亏损部分', 'effective': '期初到期末计提未到期亏损部分的提转差', 'new': '', 'i4': '不变', 'input_details': [{'table': '系统期初余额表', 'biz': '有效业务', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': 'RA比例_现有业务', 'biz': '', 'adjust': '无', 'sensitivity': '高', 'highlight': False}, {'table': '保费现金流模式_现有业务', 'biz': '', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': 'IACF现金流模式_现有业务', 'biz': '', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '未到期赚取模式_现有业务', 'biz': '', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '预期赔付率', 'biz': '', 'adjust': '高', 'sensitivity': '高', 'highlight': True}, {'table': '维持费用率（精算）', 'biz': '', 'adjust': '中', 'sensitivity': '高', 'highlight': False}, {'table': '未到期间接理赔费用率', 'biz': '', 'adjust': '低', 'sensitivity': '低', 'highlight': False}, {'table': '即期利率曲线', 'biz': '', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '新业务保费收入', 'biz': '新业务', 'adjust': '中', 'sensitivity': '高', 'highlight': False}, {'table': '新业务跟单获取费用比例', 'biz': '', 'adjust': '中', 'sensitivity': '高', 'highlight': False}, {'table': '新业务非跟单获取费用比例', 'biz': '', 'adjust': '中', 'sensitivity': '高', 'highlight': False}, {'table': '保费现金流模式_新业务', 'biz': '', 'adjust': '高', 'sensitivity': '低', 'highlight': False}, {'table': 'IACF现金流模式_新业务', 'biz': '', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '未到期赚取模式_新业务', 'biz': '', 'adjust': '低', 'sensitivity': '高', 'highlight': False}, {'table': '同保费计息', 'biz': '', 'adjust': '', 'sensitivity': '', 'highlight': False}], 'inputs': ['系统期初余额表', 'RA比例_现有业务', '保费现金流模式_现有业务', 'IACF现金流模式_现有业务', '未到期赚取模式_现有业务', '预期赔付率', '维持费用率（精算）', '未到期间接理赔费用率', '即期利率曲线', '新业务保费收入', '新业务跟单获取费用比例', '新业务非跟单获取费用比例', '保费现金流模式_新业务', 'IACF现金流模式_新业务', '未到期赚取模式_新业务', '同保费计息'], 'adjust': ['无', '高', '中', '低'], 'sensitivity': ['低', '高']}}, {'name': '投资成分的分解', 'meaning': '返还部分同时在利润表的收入与费用中扣除', 'entries': [{'method': '投资成分的分解', 'detail': '与保险服务收入-投资成分的分解相同', 'i4': '新增', 'inputs': '投资成分比例', 'adjust': '低', 'sensitivity': '无'}], 'summary': {'title': '投资成分的分解', 'effective': '返还部分同时在利润表的收入与费用中扣除', 'new': '', 'i4': '新增', 'input_details': [{'table': '投资成分比例', 'biz': '', 'adjust': '低', 'sensitivity': '无', 'highlight': False}], 'inputs': ['投资成分比例'], 'adjust': ['低'], 'sensitivity': ['无']}}]}, {'name': '分出保费的分摊', 'children': [{'name': '分出保费的分摊', 'meaning': '满期分出保费，对投资成分、保费减值等进行调整', 'entries': [{'method': '满期保费（1/365法或风险分布法，下同）', 'detail': '类似于直保分入的保险服务收入', 'i4': '计算维度不同，I4计算再保前和再保后维度，以差异为分出金额', 'inputs': '有效业务： 系统期初余额表', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '未到期赚取模式_现有业务', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '新业务： 新业务保费收入', 'adjust': '中', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '未到期赚取模式_新业务', 'adjust': '低', 'sensitivity': '高'}, {'method': '扣减：投资成分的分解', 'detail': None, 'i4': '新增', 'inputs': '系统期初余额表', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '投资成分比例', 'adjust': '低', 'sensitivity': '无'}, {'method': '增加：计息', 'detail': None, 'i4': '新增', 'inputs': '同直保保费计息', 'adjust': None, 'sensitivity': None}, {'method': '扣减：保费减值', 'detail': None, 'i4': '科目重分类', 'inputs': '新业务应收保费减值', 'adjust': '中', 'sensitivity': '低'}, {'method': '扣减：分出业务净额结算手续费', 'detail': '类似于直保分入的满期获取费用，考虑每个合同组层级净额结算手续费率水平\n有效业务：上年末时点分出UPR*净额结算手续费率*预测年度赚取比例，UPR为上年末时点实际结果\n新业务：分出保费*净额结算手续费率*预测年度赚取比例，分出保费为当年规划数', 'i4': '科目重分类，I4隐含在手续费递延中', 'inputs': '新业务跟单获取费用比例', 'adjust': '中', 'sensitivity': '高'}], 'summary': {'title': '满期保费（1/365法或风险分布法，下同）', 'effective': '上年末时点分出UPR*净额结算手续费率*预测年度赚取比例，UPR为上年末时点实际结果', 'new': '分出保费*净额结算手续费率*预测年度赚取比例，分出保费为当年规划数', 'i4': '计算维度不同，I4计算再保前和再保后维度，以差异为分出金额', 'input_details': [{'table': '系统期初余额表', 'biz': '有效业务', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '未到期赚取模式_现有业务', 'biz': '', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '新业务保费收入', 'biz': '新业务', 'adjust': '中', 'sensitivity': '高', 'highlight': False}, {'table': '未到期赚取模式_新业务', 'biz': '', 'adjust': '低', 'sensitivity': '高', 'highlight': False}, {'table': '系统期初余额表', 'biz': '', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '投资成分比例', 'biz': '', 'adjust': '低', 'sensitivity': '无', 'highlight': False}, {'table': '同直保保费计息', 'biz': '', 'adjust': '', 'sensitivity': '', 'highlight': False}, {'table': '新业务应收保费减值', 'biz': '', 'adjust': '中', 'sensitivity': '低', 'highlight': False}, {'table': '新业务跟单获取费用比例', 'biz': '', 'adjust': '中', 'sensitivity': '高', 'highlight': False}], 'inputs': ['系统期初余额表', '未到期赚取模式_现有业务', '新业务保费收入', '未到期赚取模式_新业务', '系统期初余额表', '投资成分比例', '同直保保费计息', '新业务应收保费减值', '新业务跟单获取费用比例'], 'adjust': ['无', '中', '低'], 'sensitivity': ['低', '高', '无']}}]}, {'name': '摊回保险服务费用', 'children': [{'name': '收到的摊回赔付及费用', 'meaning': '当期收到的摊回赔付', 'entries': [{'method': '当期摊回赔付支出', 'detail': '类似于直保分入的当期赔付及间接理赔费用支出', 'i4': '不变', 'inputs': '预期赔付率', 'adjust': '高', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '实际赔付比例', 'adjust': '高', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '未决间接理赔费用率', 'adjust': '低', 'sensitivity': '低'}], 'summary': {'title': '当期摊回赔付支出', 'effective': '当期收到的摊回赔付', 'new': '', 'i4': '不变', 'input_details': [{'table': '预期赔付率', 'biz': '', 'adjust': '高', 'sensitivity': '高', 'highlight': True}, {'table': '实际赔付比例', 'biz': '', 'adjust': '高', 'sensitivity': '低', 'highlight': False}, {'table': '未决间接理赔费用率', 'biz': '', 'adjust': '低', 'sensitivity': '低', 'highlight': False}], 'inputs': ['预期赔付率', '实际赔付比例', '未决间接理赔费用率'], 'adjust': ['高', '低'], 'sensitivity': ['高', '低']}}, {'name': '摊回未决赔款准备金', 'meaning': '期初到期末计提摊回未决赔款准备金的提转差', 'entries': [{'method': '期末摊回未决赔款准备金', 'detail': '类似于直保分入的提取未决赔款准备金提转差，但需要额外*（1+再保人不履约风险比例）', 'i4': '不变', 'inputs': '有效业务： 系统期初余额表', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '未决赔付模式', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '预期赔付率', 'adjust': '高', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '再保人不履约风险', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '新业务： 未决赔付模式', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '未决间接理赔费用率', 'adjust': '低', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '预期赔付率', 'adjust': '高', 'sensitivity': '高'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '再保人不履约风险', 'adjust': '低', 'sensitivity': '低'}, {'method': '扣减：期初摊回未决赔款准备金', 'detail': None, 'i4': '不变', 'inputs': '同上', 'adjust': None, 'sensitivity': None}, {'method': '增加：折现', 'detail': None, 'i4': '新增', 'inputs': '同保费计息', 'adjust': None, 'sensitivity': None}], 'summary': {'title': '期末摊回未决赔款准备金', 'effective': '期初到期末计提摊回未决赔款准备金的提转差', 'new': '', 'i4': '不变', 'input_details': [{'table': '系统期初余额表', 'biz': '有效业务', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '未决赔付模式', 'biz': '', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '预期赔付率', 'biz': '', 'adjust': '高', 'sensitivity': '高', 'highlight': True}, {'table': '再保人不履约风险', 'biz': '', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '未决赔付模式', 'biz': '新业务', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '未决间接理赔费用率', 'biz': '', 'adjust': '低', 'sensitivity': '低', 'highlight': False}, {'table': '再保人不履约风险', 'biz': '', 'adjust': '低', 'sensitivity': '低', 'highlight': False}, {'table': '同保费计息', 'biz': '', 'adjust': '', 'sensitivity': '', 'highlight': False}], 'inputs': ['系统期初余额表', '未决赔付模式', '预期赔付率', '再保人不履约风险', '未决赔付模式', '未决间接理赔费用率', '再保人不履约风险', '同保费计息'], 'adjust': ['无', '高', '低'], 'sensitivity': ['低', '高']}}, {'name': '亏损摊回损益', 'meaning': '期初到期末计提未到期亏损摊回部分的提转差', 'entries': [{'method': '期末未到期亏损摊回部分', 'detail': '再保前未到期亏损*分出比例', 'i4': '准则要求不同，I4分别计算再保前后亏损，以差异为分出部分', 'inputs': '预期摊回比例', 'adjust': '低', 'sensitivity': '高'}, {'method': '扣减：期初未到期亏损摊回部分', 'detail': '同上', 'i4': None, 'inputs': None, 'adjust': None, 'sensitivity': None}], 'summary': {'title': '期末未到期亏损摊回部分', 'effective': '期初到期末计提未到期亏损摊回部分的提转差', 'new': '', 'i4': '准则要求不同，I4分别计算再保前后亏损，以差异为分出部分', 'input_details': [{'table': '预期摊回比例', 'biz': '', 'adjust': '低', 'sensitivity': '高', 'highlight': False}], 'inputs': ['预期摊回比例'], 'adjust': ['低'], 'sensitivity': ['高']}}, {'name': '投资成分的分解', 'meaning': '返还部分同时在利润表的收入与费用中扣除', 'entries': [{'method': '投资成分的分解', 'detail': '与分出保费的分摊-投资成分的分解相同', 'i4': '新增', 'inputs': '系统期初余额表', 'adjust': '无', 'sensitivity': '低'}, {'method': None, 'detail': None, 'i4': None, 'inputs': '投资成分比例', 'adjust': '低', 'sensitivity': '低'}], 'summary': {'title': '投资成分的分解', 'effective': '返还部分同时在利润表的收入与费用中扣除', 'new': '', 'i4': '新增', 'input_details': [{'table': '系统期初余额表', 'biz': '', 'adjust': '无', 'sensitivity': '低', 'highlight': False}, {'table': '投资成分比例', 'biz': '', 'adjust': '低', 'sensitivity': '低', 'highlight': False}], 'inputs': ['系统期初余额表', '投资成分比例'], 'adjust': ['无', '低'], 'sensitivity': ['低']}}]}, {'name': '保险合同金融变动额', 'children': [{'name': '未到期计息', 'meaning': '未到期责任准备金的时间价值', 'entries': [{'method': '未到期计息', 'detail': '（期初未到期余额+本期收到的保费-本期支付的获取费用）*计息利率', 'i4': '新增', 'inputs': '受上方利润表科目间接影响', 'adjust': None, 'sensitivity': None}], 'summary': {'title': '未到期计息', 'effective': '未到期责任准备金的时间价值', 'new': '', 'i4': '新增', 'input_details': [{'table': '受上方利润表科目间接影响', 'biz': '', 'adjust': '', 'sensitivity': '', 'highlight': False}], 'inputs': ['受上方利润表科目间接影响'], 'adjust': [], 'sensitivity': []}}, {'name': '未决计息', 'meaning': '未决赔款准备金的时间价值', 'entries': [{'method': '未决计息', 'detail': '期初未决现金流现值*计息利率', 'i4': '新增', 'inputs': '受上方利润表科目间接影响', 'adjust': None, 'sensitivity': None}], 'summary': {'title': '未决计息', 'effective': '未决赔款准备金的时间价值', 'new': '', 'i4': '新增', 'input_details': [{'table': '受上方利润表科目间接影响', 'biz': '', 'adjust': '', 'sensitivity': '', 'highlight': False}], 'inputs': ['受上方利润表科目间接影响'], 'adjust': [], 'sensitivity': []}}]}, {'name': '分出再保险合同金融变动额', 'children': [{'name': '摊回未到期计息', 'meaning': '摊回未到期责任准备金的时间价值', 'entries': [{'method': '摊回未到期计息', 'detail': '类似于保险合同金融变动额', 'i4': '新增', 'inputs': '受上方利润表科目间接影响', 'adjust': None, 'sensitivity': None}], 'summary': {'title': '摊回未到期计息', 'effective': '摊回未到期责任准备金的时间价值', 'new': '', 'i4': '新增', 'input_details': [{'table': '受上方利润表科目间接影响', 'biz': '', 'adjust': '', 'sensitivity': '', 'highlight': False}], 'inputs': ['受上方利润表科目间接影响'], 'adjust': [], 'sensitivity': []}}, {'name': '摊回未决计息', 'meaning': '摊回未决赔款准备金的时间价值', 'entries': [{'method': '摊回未决计息', 'detail': '摊回未决赔款准备金的时间价值', 'i4': '新增', 'inputs': '受上方利润表科目间接影响', 'adjust': None, 'sensitivity': None}], 'summary': {'title': '摊回未决计息', 'effective': '摊回未决赔款准备金的时间价值', 'new': '', 'i4': '新增', 'input_details': [{'table': '受上方利润表科目间接影响', 'biz': '', 'adjust': '', 'sensitivity': '', 'highlight': False}], 'inputs': ['受上方利润表科目间接影响'], 'adjust': [], 'sensitivity': []}}]}]}


def _load_logic_outline():
    """返回已固化的计算逻辑概要树（无需读取 Excel）。"""
    return _LOGIC_OUTLINE_DATA


@login_required
def api_logic_outline(request):
    """API：获取计算逻辑概要树。"""
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': '仅支持 GET 请求'}, status=405)
    return JsonResponse(_load_logic_outline())


# ============================================================
# 系统运行日志 API
# ============================================================

@login_required
def api_system_log(request):
    """GET：分页查询系统运行日志。

    参数：page(默认1), page_size(默认50), action(操作类型过滤),
          level(级别过滤), q(关键词), date_from, date_to(YYYY-MM-DD)。
    返回：{total, page, page_size, logs:[...], actions:[可用操作类型]}
    """
    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': '仅支持 GET 请求'}, status=405)

    page = max(1, int(request.GET.get('page', 1)))
    page_size = min(200, max(10, int(request.GET.get('page_size', 50))))
    action = (request.GET.get('action') or '').strip()
    level = (request.GET.get('level') or '').strip()
    q = (request.GET.get('q') or '').strip()
    date_from = (request.GET.get('date_from') or '').strip()
    date_to = (request.GET.get('date_to') or '').strip()

    qs = SystemOperationLog.objects.all()
    if action:
        qs = qs.filter(action=action)
    if level:
        qs = qs.filter(level=level)
    if q:
        from django.db.models import Q
        qs = qs.filter(Q(username__icontains=q) | Q(target__icontains=q) | Q(detail__icontains=q))
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    total = qs.count()
    start = (page - 1) * page_size
    rows = qs[start:start + page_size]

    logs = [{
        'id': r.id,
        'created_at': r.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'username': r.username,
        'action': r.action,
        'action_label': r.action_label,
        'target': r.target,
        'detail': r.detail,
        'level': r.level,
        'ip': r.ip or '',
    } for r in rows]

    return JsonResponse({
        'success': True,
        'total': total,
        'page': page,
        'page_size': page_size,
        'logs': logs,
        'actions': [{'value': v, 'label': l} for v, l in SystemOperationLog.action_choices()],
    })


# ============================================================
# 计算版本入库 API
# ============================================================

@login_required
@permission_required('data_input.can_upload', raise_exception=True)
def api_calc_versions(request):
    """GET：列出已入库的计算版本（含每个版本情景数/快照数）。"""
    versions = CalculationVersion.objects.prefetch_related('snapshots').all()[:100]
    data = [{
        'id': v.id,
        'name': v.name,
        'description': v.description,
        'scenario_count': v.scenario_count,
        'scenarios': v.scenarios,
        'status': v.status,
        'created_by': v.created_by.username if v.created_by else '-',
        # 返回 ISO 8601（含 Z），由前端 new Date().toLocaleString 转本地时间
        'created_at': v.created_at.isoformat(),
        'snapshot_count': v.snapshots.count(),
    } for v in versions]
    return JsonResponse({'success': True, 'versions': data})


# 英文表名 → 输出物理结果表 Model（与 table_names.OUTPUT_TABLE_DEFS 对应）
_OUTPUT_MODEL_MAP = OUTPUT_TABLE_MODELS


def _get_by_json_path(obj, json_path):
    """按简单 JSONPath（如 $.inputOrganized.newBusiness）从 dict 中取值。"""
    if not json_path or json_path == '$':
        return obj
    parts = json_path.lstrip('$').strip('.').split('.')
    cur = obj
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return None
    return cur


def _model_field_names(model):
    """缓存 model 的所有字段名（含从基类继承）。"""
    return {f.name for f in model._meta.get_fields()}


_OUTPUT_MODEL_FIELDS = {m: _model_field_names(m) for m in _OUTPUT_MODEL_MAP.values()}


def _build_output_row_kwargs(model, row_json):
    """把 row_json 的中文 key 翻译成英文字段名，只保留 model 中存在的字段。"""
    fields = _OUTPUT_MODEL_FIELDS[model]
    kwargs = {}
    for k, v in (row_json or {}).items():
        en = to_en(k)
        if en in fields:
            kwargs[en] = v
    return kwargs


def _write_financial_statement_table(version, scenario, model, calc, src_key):
    """把财务报表（balance_sheet / income_statement）按 科目 × 期间 拆成明细行。

    彻底消除 JSON 聚合列：每个科目在每一个期间（dates[]）的数值独立成一行，
    amount 为单一 DECIMAL 标量。period_date 取自 financialStatementsV2.dates[]。
    """
    from decimal import Decimal
    fs = (calc.get('financialStatementsV2') or {})
    src = fs.get(src_key) or {}
    dates = fs.get('dates') or []
    batch = []
    for stype in ('balance_sheet', 'income_statement'):
        items = src.get(stype) or []
        for line_idx, it in enumerate(items):
            values = it.get('values') or []
            item_name = it.get('item')
            indent = it.get('indent', 0) or 0
            is_total = bool(it.get('is_total', False))
            for period_idx, val in enumerate(values):
                period_date = None
                if period_idx < len(dates):
                    raw = dates[period_idx]
                    if isinstance(raw, str):
                        try:
                            period_date = datetime.datetime.strptime(raw[:10], '%Y-%m-%d').date()
                        except Exception:
                            period_date = None
                amount = None
                if val is not None:
                    try:
                        amount = Decimal(str(val))
                    except Exception:
                        amount = None
                batch.append(model(
                    version=version, scenario=scenario,
                    statement_type=stype,
                    line_idx=line_idx,
                    item=item_name,
                    indent=indent,
                    is_total=is_total,
                    period_date=period_date,
                    period_idx=period_idx,
                    amount=amount,
                ))
    if batch:
        model.objects.bulk_create(batch, batch_size=1000)


def _write_input_physical_tables(source, upload_record, sheets_data):
    """把上传解析后的 sheets_data 按真实列写入 35 张输入物理表。

    - 旧 active 行（同来源）置 is_active=False；新行 is_active=True；
    - 列映射依据 input_table_schema（header 中文 -> 英文字段名），月度列自动映射 m01..m60；
    - 数值列转 Decimal（非数值置 None），文本列转字符串。
    只保留 model 真实存在的字段，未登记的列（如新增险类）安全跳过。
    """
    for sheet_name, sheet_info in (sheets_data or {}).items():
        model = INPUT_TABLE_MODELS.get(sheet_name)
        schema = INPUT_TABLE_SCHEMA.get(sheet_name)
        if not model or not schema:
            continue
        headers = sheet_info.get('headers') or []
        rows = sheet_info.get('rows') or []
        if not rows:
            continue
        field_by_header = {c['cn']: c['name'] for c in schema['columns']}
        type_by_field = {c['name']: c['type'] for c in schema['columns']}
        # 旧活跃行置否（同来源）
        model.objects.filter(source=source, is_active=True).update(is_active=False)
        batch = []
        for ridx, row in enumerate(rows):
            kwargs = {
                'source': source,
                'upload_record': upload_record,
                'is_active': True,
                'row_idx': ridx,
            }
            for i, cell in enumerate(row):
                if i >= len(headers):
                    break
                h = headers[i]
                fname = field_by_header.get(h)
                if not fname:
                    continue
                if type_by_field.get(fname) == 'decimal':
                    if cell is None or cell == '':
                        kwargs[fname] = None
                    else:
                        try:
                            kwargs[fname] = Decimal(str(cell))
                        except (InvalidOperation, ValueError, TypeError):
                            kwargs[fname] = None
                else:
                    if cell is None or cell == '':
                        kwargs[fname] = None
                    else:
                        kwargs[fname] = str(cell)
            batch.append(model(**kwargs))
        if batch:
            model.objects.bulk_create(batch, batch_size=500)


def _write_output_physical_tables(version, scenario, calc):
    """把 calc 结果按 table_names.OUTPUT_TABLE_DEFS 写入对应英文表名的物理表。

    - 普通结果表（新业务/现有业务/汇总）：行级 JSON key 已展开为独立字段；
    - 财务报表表（MTD/YTD）：balance_sheet / income_statement 拆成 科目 × 期间 明细行；
    确保落库物理表名与英文表名完全一致，且不存在任何 JSON 聚合列。
    写入失败会抛出异常，由调用方捕获并记录。
    """
    from data_input import table_names
    for d in table_names.OUTPUT_TABLE_DEFS:
        en = d['en']
        json_path = d['json_path']
        model = _OUTPUT_MODEL_MAP.get(en)
        if not model:
            continue
        # 财务报表明细表：按 科目 × 期间 拆行
        if issubclass(model, _FinancialStatementLineBase):
            src_key = json_path.split('.')[-1]
            _write_financial_statement_table(version, scenario, model, calc, src_key)
            continue
        data = _get_by_json_path(calc, json_path)
        if data is None:
            continue
        if isinstance(data, list):
            batch = [
                model(
                    version=version, scenario=scenario, row_idx=idx,
                    **_build_output_row_kwargs(model, row)
                )
                for idx, row in enumerate(data)
            ]
        elif isinstance(data, dict):
            batch = [model(
                version=version, scenario=scenario, row_idx=0,
                **_build_output_row_kwargs(model, data)
            )]
        else:
            wrapped = {'value': data}
            batch = [model(
                version=version, scenario=scenario, row_idx=0,
                **_build_output_row_kwargs(model, wrapped)
            )]
        if batch:
            model.objects.bulk_create(batch, batch_size=500)


def _push_version_worker(task_key, version_id, name, description, chosen, publish, user):
    """后台线程：逐情景写入 CalculationSnapshot，并同步写入输出物理结果表，上报进度。"""
    import copy
    import traceback
    import uuid
    from django.db import close_old_connections, transaction

    close_old_connections()

    scenarios = list(chosen.keys())
    total = len(scenarios)

    def update_task(**kwargs):
        with _VERSION_PUSH_LOCK:
            _VERSION_PUSH_TASKS[task_key].update(kwargs)

    update_task(status='running', total=total, current=0, scenario='',
                message='开始入库...', error='', finished=False)

    try:
        version = CalculationVersion.objects.get(id=version_id)
    except CalculationVersion.DoesNotExist:
        update_task(status='error', message='版本记录不存在',
                    error='版本记录不存在', finished=True)
        return

    try:
        for idx, sc in enumerate(scenarios, start=1):
            calc = chosen[sc]
            summary = calc.get('summary') or {}
            update_task(current=idx - 1, scenario=sc,
                        message=f'正在入库 {sc} ({idx}/{total})...')
            CalculationSnapshot.objects.create(
                version=version,
                scenario=sc,
                result_json=copy.deepcopy(calc),
                row_counts={
                    'newBusinessRows': summary.get('newBusinessRows', 0),
                    'existingBusinessRows': summary.get('existingBusinessRows', 0),
                    'combinedSummaryRows': summary.get('combinedSummaryRows', 0),
                    'financialStatementRows': summary.get('financialStatementRows', 0),
                },
            )
            # 同步写入与英文表名一致的物理输出表
            _write_output_physical_tables(version, sc, calc)
            update_task(current=idx, scenario=sc,
                        message=f'{sc} 已入库 ({idx}/{total})')

        version.status = CalculationVersion.STATUS_PUBLISHED if publish else CalculationVersion.STATUS_DRAFT
        version.save(update_fields=['status'])
        update_task(status='done', current=total,
                    message=f'全部 {total} 个情景入库完成', finished=True)

        log_operation(user, SystemOperationLog.ACTION_VERSION_PUSH,
                      target=f"#{version.id} {name}",
                      detail=f"异步入库 {total} 个情景完成: {', '.join(scenarios)}")
    except Exception as e:
        err = traceback.format_exc()
        update_task(status='error', message=f'入库失败: {str(e)}',
                    error=str(e), finished=True)
        log_operation(user, SystemOperationLog.ACTION_VERSION_PUSH,
                      target=f"#{version_id} {name}",
                      detail=f"异步入库失败: {str(e)}\n{err}",
                      level='ERROR')
    finally:
        close_old_connections()


@login_required
@permission_required('data_input.can_upload', raise_exception=True)
@require_http_methods(['POST'])
def api_calc_push_version(request):
    """POST：将当前计算结果（一个或多个已计算情景）作为版本持久化到 MySQL（异步）。

    请求体：{name, description, scenarios?: [情景名...], publish?: bool}
    未指定 scenarios 时，推送 _CALC_RESULTS_MAP 中所有已计算情景。
    返回 {task, version_id, ...}，前端通过 /api/calc/push-version-status?task=xxx 轮询进度。
    """
    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': '请求体 JSON 解析失败'}, status=400)

    name = (body.get('name') or '').strip()
    description = (body.get('description') or '').strip()
    scenarios_req = body.get('scenarios') or []
    publish = bool(body.get('publish', False))

    if not name:
        name = '计算版本 ' + timezone.now().strftime('%Y-%m-%d %H:%M')

    # 收集要入库的情景计算结果
    available = dict(_CALC_RESULTS_MAP)
    if not available:
        # 退化为最近一次单场景结果
        last = _CALC_CACHE.get('result')
        if last:
            available[last.get('selectedScenario') or last.get('scenario') or '情景0'] = last

    if not available:
        return JsonResponse({'success': False, 'error': '当前没有可入库的计算结果，请先执行计算'}, status=400)

    if scenarios_req:
        chosen = {s: available[s] for s in scenarios_req if s in available}
    else:
        chosen = available

    if not chosen:
        return JsonResponse({'success': False, 'error': '所选情景均无可用的计算结果'}, status=400)

    try:
        version = CalculationVersion.objects.create(
            name=name,
            description=description,
            scenario_count=len(chosen),
            scenarios=list(chosen.keys()),
            status=CalculationVersion.STATUS_DRAFT,
            created_by=request.user,
        )
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'创建版本失败: {str(e)}'}, status=500)

    import copy
    import uuid
    task_key = f"vpush-{version.id}-{uuid.uuid4().hex[:8]}"
    chosen_copy = copy.deepcopy(chosen)

    with _VERSION_PUSH_LOCK:
        _VERSION_PUSH_TASKS[task_key] = {
            'version_id': version.id,
            'name': name,
            'status': 'pending',
            'total': len(chosen),
            'current': 0,
            'scenario': '',
            'message': '等待开始...',
            'error': '',
            'finished': False,
            'started_at': timezone.now().isoformat(),
        }

    t = threading.Thread(
        target=_push_version_worker,
        args=(task_key, version.id, name, description, chosen_copy, publish, request.user),
        daemon=True,
    )
    t.start()

    log_operation(request, SystemOperationLog.ACTION_VERSION_PUSH,
                  target=f"#{version.id} {name}",
                  detail=f"启动异步入库 {len(chosen)} 个情景: {', '.join(chosen.keys())}")

    return JsonResponse({
        'success': True,
        'task': task_key,
        'version_id': version.id,
        'name': name,
        'scenario_count': len(chosen),
    })


@login_required
@permission_required('data_input.can_upload', raise_exception=True)
def api_calc_push_version_status(request):
    """GET：查询版本推进入库任务进度。

    参数：?task=xxx
    返回：{success, task: {status, total, current, scenario, message, error, finished, ...}}
    """
    task_key = request.GET.get('task', '')
    with _VERSION_PUSH_LOCK:
        task = _VERSION_PUSH_TASKS.get(task_key)
    if not task:
        return JsonResponse({'success': False, 'error': '任务不存在或已过期'}, status=404)
    return JsonResponse({'success': True, 'task': task})


# ============================================================
# SQL 查询 API（仅管理员，只读，审计日志）
# ============================================================

import re as _re

_SQL_FORBIDDEN = _re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|GRANT|REVOKE|'
    r'MERGE|CALL|LOCK|UNLOCK|RENAME|LOAD\s+DATA|LOAD\s+XML|EXEC|EXECUTE|SET|USE|'
    r'COMMIT|ROLLBACK|SAVEPOINT|START\s+TRANSACTION)\b',
    _re.IGNORECASE)
_SQL_LEADING_OK = _re.compile(
    r'^\s*(SELECT|WITH|SHOW|EXPLAIN|DESCRIBE|DESC)\b', _re.IGNORECASE)


def _strip_sql_strings(sql):
    """去除单/双引号字符串字面量（用于关键字白名单检测，防止注释/字符串绕过）。"""
    out = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if c in ("'", '"', '`'):
            quote = c
            i += 1
            while i < n and sql[i] != quote:
                if sql[i] == '\\' and i + 1 < n:
                    i += 2
                    continue
                i += 1
            i += 1  # 跳过闭引号
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def _strip_sql_comments(sql):
    """去除 SQL 中的 -- 行注释与 /* */ 块注释（在剥离字符串之后调用）。"""
    # 块注释 /* ... */
    sql = _re.sub(r'/\*.*?\*/', ' ', sql, flags=_re.DOTALL)
    # 行注释 -- ...（到行尾）
    sql = _re.sub(r'--[^\n]*', ' ', sql)
    return sql


@login_required
@require_http_methods(['POST'])
def api_system_sql_query(request):
    """POST：以只读方式执行 SQL 查询（仅限管理员）。

    请求体：{sql: str}
    安全策略：
      - 仅允许 SELECT / WITH / SHOW / EXPLAIN / DESCRIBE / DESC 开头
      - 禁止 INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/... 等写/改/DDL 关键字（字符串内除外）
      - 禁止多条语句（分号）；结果行数上限 1000
      - 所有查询记入系统运行日志
    """
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'success': False, 'error': '仅限管理员执行 SQL 查询'}, status=403)

    try:
        body = json.loads(request.body) if request.body else {}
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': '请求体 JSON 解析失败'}, status=400)

    raw_sql = (body.get('sql') or '').strip()
    if not raw_sql:
        return JsonResponse({'success': False, 'error': 'SQL 不能为空'}, status=400)

    # 1) 先剥离字符串字面量，再剥离注释，得到用于安全检测的纯 SQL 文本
    stripped = _strip_sql_strings(raw_sql)
    stripped = _strip_sql_comments(stripped)

    # 2) 去字符串/注释后检测危险关键字
    if _SQL_FORBIDDEN.search(stripped):
        log_operation(request, SystemOperationLog.ACTION_SQL_QUERY,
                      target='BLOCKED', detail=f"被拒绝（含危险关键字）: {raw_sql[:500]}",
                      level='WARN')
        return JsonResponse({'success': False, 'error': '该语句包含不允许的写操作/ DDL 关键字，仅支持只读查询'}, status=400)

    # 3) 多条语句禁止：允许末尾单个分号，但分号后不能再有其它语句
    stripped_no_semi = stripped.rstrip().rstrip(';').strip()
    if ';' in stripped_no_semi:
        return JsonResponse({'success': False, 'error': '不支持多条语句（禁止分号）'}, status=400)

    # 4) 开头关键字白名单（基于去注释后的文本，允许查询模板以注释开头）
    if not _SQL_LEADING_OK.match(stripped):
        return JsonResponse({'success': False, 'error': '仅支持 SELECT / WITH / SHOW / EXPLAIN / DESCRIBE 开头的只读查询'}, status=400)

    MAX_ROWS = 1000
    try:
        from django.db import close_old_connections
        close_old_connections()
        with connection.cursor() as cursor:
            cursor.execute(raw_sql)
            if cursor.description is None:
                # 非 SELECT（如某些 SHOW）可能无结果集
                affected = cursor.rowcount
                log_operation(request, SystemOperationLog.ACTION_SQL_QUERY,
                              target='NON-SELECT', detail=f"执行成功（无结果集），影响行数: {affected}")
                return JsonResponse({
                    'success': True, 'columns': [], 'rows': [],
                    'row_count': 0, 'note': f'执行成功，影响/返回行数: {affected}',
                })
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchmany(MAX_ROWS)
            truncated = cursor.fetchone() is not None
        close_old_connections()

        # 序列化（日期等）
        def _conv(v):
            if v is None:
                return None
            if isinstance(v, (datetime.datetime, datetime.date)):
                return v.strftime('%Y-%m-%d %H:%M:%S') if isinstance(v, datetime.datetime) else v.strftime('%Y-%m-%d')
            return v

        out_rows = [[_conv(c) for c in r] for r in rows]
        note = f'返回 {len(out_rows)} 行' + ('（已达上限 {0} 行，已截断）'.format(MAX_ROWS) if truncated else '')

        log_operation(request, SystemOperationLog.ACTION_SQL_QUERY,
                      target='SELECT', detail=f"行数: {len(out_rows)}，SQL: {raw_sql[:400]}")

        return JsonResponse({
            'success': True, 'columns': columns, 'rows': out_rows,
            'row_count': len(out_rows), 'note': note,
        })
    except Exception as e:
        log_operation(request, SystemOperationLog.ACTION_SQL_QUERY,
                      target='ERROR', detail=f"执行异常: {str(e)[:500]}\nSQL: {raw_sql[:300]}",
                      level='ERROR')
        return JsonResponse({'success': False, 'error': f'SQL 执行失败: {str(e)}'}, status=400)


# ============================================================
# 数据表字典 API（中英文表名对照）
# ============================================================

@login_required
def api_system_table_dict(request):
    """GET：返回系统落表的数据表中文名 ↔ 英文表名对照（数据字典）。"""
    from data_input import table_names
    return JsonResponse({'success': True, 'data': table_names.get_table_dict()})
