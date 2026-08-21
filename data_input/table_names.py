"""系统落表的数据表 中文名 ↔ 英文表名 对照（数据字典）。

- 输入数据表：来自 excel_specs 的 SYSTEM_DOCK_SPECS（系统对接）+ EXCEL_UPLOAD_SPECS（手工输入）
- 计算结果数据表：PAA 引擎输出的六张结果表（PAA 计算三表 + PAA_MTD + 财务报表 MTD/YTD）

说明：
  英文表名（en）为系统内部约定的业务英文标识（snake_case），同时作为物理落库表名使用。
  输入表统一写入 ifrs17_sheet_data（按 sheet_name 区分中文输入表）。
  计算结果输出表按英文表名一一对应独立物理表（paa_* / financial_statement_*），
  同时保留 ifrs17_calc_snapshot 作为完整 JSON 快照。
"""
from data_input.excel_specs import SYSTEM_DOCK_SPECS, EXCEL_UPLOAD_SPECS
from data_input.input_table_schema import INPUT_TABLE_SCHEMA

# 输入表中文名 → 英文表名（系统约定，snake_case）
INPUT_TABLE_EN = {
    # —— 系统对接（10 张）——
    '合同组关键假设_现有业务': 'contract_group_key_assumptions_existing',
    '系统期初余额表': 'system_opening_balance',
    '保费现金流模式_现有业务': 'premium_cashflow_pattern_existing',
    'IACF现金流模式_现有业务': 'iacf_cashflow_pattern_existing',
    '未到期赚取模式_现有业务': 'unearned_earnings_pattern_existing',
    '预期摊回比例_现有业务': 'expected_recovery_ratio_existing',
    '提前确认保单_现有业务': 'early_confirmed_policies_existing',
    '财务报表实际数': 'financial_statement_actuals',
    '初始确认利率曲线': 'initial_recognition_rate_curve',
    '即期利率曲线': 'spot_rate_curve',
    # —— 手工输入（25 张）——
    '基本信息': 'basic_info',
    '对应关系配置表': 'correspondence_config',
    '压力情景配置表': 'stress_scenario_config',
    '合同组拼接': 'contract_group_concatenation',
    '生效保费_新业务': 'effective_premium_new_business',
    '签单保费_新业务': 'written_premium_new_business',
    '新增应收保费减值': 'new_receivable_premium_impairment',
    '跟单获取费用或净额结算比例_新业务': 'acquisition_cost_or_net_settlement_ratio_new_business',
    '非跟单获取费用比例_新业务': 'non_following_acquisition_cost_ratio_new_business',
    '保费现金流模式_新业务': 'premium_cashflow_pattern_new_business',
    'IACF现金流模式_新业务': 'iacf_cashflow_pattern_new_business',
    '未到期赚取模式_新业务': 'unearned_earnings_pattern_new_business',
    '预期摊回比例_新业务': 'expected_recovery_ratio_new_business',
    '预期赔付率': 'expected_claim_ratio',
    '维持费用率': 'maintenance_expense_ratio',
    '未到期间接理赔费用率': 'unearned_indirect_claim_expense_ratio',
    '未决间接理赔费用率': 'outstanding_indirect_claim_expense_ratio',
    '风险调整比例': 'risk_adjustment_ratio',
    '再保人不履约风险': 'reinsurer_non_performance_risk',
    '投资成分比例': 'investment_component_ratio',
    '未到期赔付模式': 'unearned_claim_pattern',
    '未决赔付模式': 'outstanding_claim_pattern',
    '实际赔付比例': 'actual_claim_ratio',
    '费用输入项': 'expense_inputs',
    '其他输入项': 'other_inputs',
}

# 计算表中文名 → 英文表名 + 分类 + JSON 路径 + 查询模板
OUTPUT_TABLE_DEFS = [
    {
        'cn': 'PAA计算_新业务整理',
        'en': 'paa_new_business_organized',
        'category': 'PAA计算结果',
        'json_path': '$.inputOrganized.newBusiness',
    },
    {
        'cn': 'PAA计算_现有业务整理',
        'en': 'paa_existing_business_organized',
        'category': 'PAA计算结果',
        'json_path': '$.inputOrganized.existingBusiness',
    },
    {
        'cn': 'PAA计算_汇总',
        'en': 'paa_summary',
        'category': 'PAA计算结果',
        'json_path': '$.combinedSummary',
    },
    {
        'cn': 'PAA计算_MTD',
        'en': 'paa_mtd',
        'category': 'PAA计算结果',
        'json_path': '$.financialStatementsV2.mtd',
    },
    {
        'cn': '输出财务报表_MTD',
        'en': 'financial_statement_mtd',
        'category': '财务报表',
        'json_path': '$.financialStatementsV2.mtd',
    },
    {
        'cn': '输出财务报表_YTD',
        'en': 'financial_statement_ytd',
        'category': '财务报表',
        'json_path': '$.financialStatementsV2.ytd',
    },
]


# 系统基础物理表（真实 db_table）
SYSTEM_PHYSICAL_TABLES = [
    ('上传记录', 'ifrs17_upload_record', '每次 Excel 上传生成一条记录'),
    ('上传工作表数据', 'ifrs17_sheet_data', '所有输入数据表的 JSON 宽表存储（PAA 引擎读取源）；输入数据同时按工作表拆为 35 张独立物理表（见输入数据表）'),
    ('系统运行日志', 'ifrs17_system_log', '系统每一步操作日志'),
    ('计算版本', 'ifrs17_calc_version', '入库的计算版本主表'),
    ('计算结果快照', 'ifrs17_calc_snapshot', '所有计算结果表统一落此表（按 version+scenario+result_json 区分）'),
]


def get_input_tables():
    """返回 35 张输入物理表字典：每张表均为与英文表名一致的独立物理表，
    且提供真实字段结构 columns（无 JSON 聚合列）。"""
    rows = []
    for cn, s in INPUT_TABLE_SCHEMA.items():
        en = s.get('en') or cn
        cols = [{'name': c['name'], 'label': c.get('cn') or c['name']}
                for c in s.get('columns', [])]
        rows.append({
            'cn': cn,
            'en': en,
            'category': s.get('category', ''),
            'kind': '系统对接' if s.get('source') == 'dock' else '手工输入',
            'db_table': en,
            'is_logical': False,
            'columns': cols,
            'query_template': (
                f"-- 输入表：{cn}（{en}）\n"
                f"-- 已拆为独立物理表，每列即 Excel 真实列（无 JSON 聚合字段）\n"
                f"--   is_active = 1 表示当前最新上传的有效数据\n"
                f"SELECT * FROM {en}\n"
                f"WHERE is_active = 1\n"
                f"LIMIT 20;"
            ),
        })
    return rows


def _output_table_columns(en):
    """返回某输出物理表的真实字段结构（列名 + 中文标签），用于数据字典展示。"""
    try:
        from data_input.models import OUTPUT_TABLE_MODELS
        model = OUTPUT_TABLE_MODELS.get(en)
        if not model:
            return []
        cols = []
        for f in model._meta.fields:
            cols.append({
                'name': f.name,
                'label': str(f.verbose_name),
            })
        return cols
    except Exception:
        return []


def get_output_tables():
    """返回计算结果输出表字典；db_table 与英文表名一致，均为物理表。

    每张表都提供真实字段结构 columns（无任何 JSON 聚合列）。
    """
    out = []
    for d in OUTPUT_TABLE_DEFS:
        en = d['en']
        is_fs = en in ('paa_mtd', 'financial_statement_mtd', 'financial_statement_ytd')
        if is_fs:
            query_template = (
                f"-- 输出结果物理表：{d['cn']}（{en}）\n"
                f"-- 已按「科目 × 期间」拆成明细行，无 JSON 聚合列：\n"
                f"--   statement_type : balance_sheet(资产负债表) / income_statement(利润表)\n"
                f"--   item           : 科目名称；indent: 缩进层级；is_total: 是否合计行\n"
                f"--   period_date    : 期间；period_idx: 期间序号；amount: 该科目该期间的单一数值\n"
                f"SELECT *\n"
                f"FROM {en}\n"
                f"WHERE version_id = (SELECT MAX(id) FROM ifrs17_calc_version)\n"
                f"  AND scenario = '基础情景'\n"
                f"  AND statement_type = 'income_statement'\n"
                f"ORDER BY line_idx, period_idx\n"
                f"LIMIT 100;"
            )
        else:
            query_template = (
                f"-- 输出结果物理表：{d['cn']}（{en}）\n"
                f"-- 行级数据已拆分为独立字段，可直接 SELECT 列\n"
                f"SELECT * FROM {en}\n"
                f"WHERE version_id = (SELECT MAX(id) FROM ifrs17_calc_version)\n"
                f"LIMIT 20;"
            )
        out.append({
            'cn': d['cn'],
            'en': d['en'],
            'category': d['category'],
            'kind': '计算结果',
            'db_table': d['en'],
            'is_logical': False,
            'json_path': d['json_path'],
            'columns': _output_table_columns(en),
            'query_template': query_template,
        })
    return out


def get_system_tables():
    return [{
        'cn': cn,
        'en': db,
        'category': '系统基础表',
        'kind': '物理表',
        'db_table': db,
        'desc': desc,
        'is_logical': False,
        'query_template': (
            f"-- 系统基础表：{cn}（{db}）\n"
            f"SELECT * FROM {db} LIMIT 20;"
        ),
    } for cn, db, desc in SYSTEM_PHYSICAL_TABLES]


def get_table_dict():
    return {
        'input_tables': get_input_tables(),
        'output_tables': get_output_tables(),
        'system_tables': get_system_tables(),
        'counts': {
            'input': len(get_input_tables()),
            'output': len(get_output_tables()),
            'system': len(get_system_tables()),
        },
    }
