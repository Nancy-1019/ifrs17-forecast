# -*- coding: utf-8 -*-
"""
中英文 字段名 注册表 (Field Name Registry) — IFRS17 PAA 预测模型

目的
----
把系统里所有"中间计算过程字段 / 输入表字段 / 输出表字段 / 验证表字段"的
中文名，统一映射到标准 IFRS17 英文术语，供以下场景使用：

  1. 引擎内部计算统一使用英文字段名（代码可读性、便于对外/审计）；
  2. 上传的中文 Excel 表头在读取时自动翻译为英文（translate_in）；
  3. 导出 Excel / 前端展示时按需要回写为中文（translate_out）；
  4. 验证模块（六表零差异）读取中文 fixture 时映射为英文后再比对；
  5. 形成"中文 ↔ 英文"对照记录文档的数据来源。

命名规范（与用户确认）：标准 IFRS17 英文术语
  - 未到期责任负债        -> LRC   (Liability for Remaining Coverage)
  - 已发生未决赔款负债    -> LIC   (Liability for Incurred Claims)
  - 间接理赔费用负债      -> LAE   (Loss Adjustment Expense liability)
  - 非金融风险调整        -> RiskAdjustment / risk_adj
  - 再保人不履约风险      -> RNPR  (Reinsurer Non-Performance Risk)
  - 保险获取现金流        -> IACF  (Insurance Acquisition Cash Flow)
  - 投资成分              -> InvestmentComponent
  - 亏损合同 / 亏损摊回   -> Onerous / OnerousRecoverable
  - 计息                  -> Accretion
  - 提转差                -> Movement (change)
  - IFIE                  -> IFIE  (Insurance Finance Expense/Income)
  - OCI                   -> OCI   (Other Comprehensive Income)

本模块不依赖 Django，可独立 import 与测试。
"""

from typing import Any, Dict, Optional

# =====================================================================
# 1) 显式中文字段 -> 英文字段 映射（覆盖全部 274 个字段）
# =====================================================================
CN_TO_EN = {
    # ---------------- 维度 / 标识类 ----------------
    '合同组ID': 'contract_group_id',
    '合同组ID名称': 'contract_group_id_name',
    '合同组合名称': 'contract_portfolio_name',
    '合同组名称': 'contract_group_name',
    '子合同组合名称': 'sub_contract_portfolio_name',
    '业务类型': 'business_type',
    '业务标签': 'business_tag',
    '精算险类': 'actuarial_lob',
    '精算监管险类': 'regulatory_lob',
    '直保或分入/分出': 'direct_or_ceded',
    '预测维度': 'forecast_dimension',
    '预测组': 'forecast_group',
    '预测组ID': 'forecast_group_id',
    '新业务预测组': 'new_biz_forecast_group',
    '新业务预测组名称ID': 'new_biz_forecast_group_id',
    '现有业务预测组': 'exist_biz_forecast_group',
    '现有业务预测组名称ID': 'exist_biz_forecast_group_id',
    '签单年': 'policy_issue_year',
    '排列组合项': 'arrangement_combination',
    '数据来源表': 'source_table',

    # ---------------- 时间 / 期间类 ----------------
    '评估日': 'valuation_date',
    '评估时点': 'valuation_point',
    '评估期开始业务预期写入时间（月）': 'expected_writing_period_months',
    '预测时点': 'forecast_point',
    '预测时点年初': 'forecast_point_year_start',
    '预测间隔': 'forecast_interval',
    '预测间隔_排列': 'forecast_interval_arrangement',
    '预测期数': 'forecast_periods',
    '预测月份': 'forecast_month',
    '年度': 'year',
    '月度远期': 'monthly_forward_rate',
    '更新日期': 'updated_date',
    '更新人员': 'updated_by',

    # ---------------- 比率 / 比例假设类 ----------------
    '当期确认比例': 'current_recognition_ratio',
    '获取现金流摊销比例': 'iacf_amortization_ratio',
    '投资成分比例%': 'investment_component_ratio_pct',
    '预期摊回比例%': 'expected_recovery_ratio_pct',
    '未到期风险调整%': 'lrc_risk_adj_ratio_pct',
    '未决风险调整%': 'lic_risk_adj_ratio_pct',
    '风险调整比例': 'risk_adjustment_ratio',
    '实际维持费用分摊比例': 'actual_maintenance_alloc_ratio',
    '当月计息利率': 'current_accrual_rate',

    # ---------------- 收入 / 费用 / 现金流（输入 & 输出通用） ----------------
    '保费收入': 'premium_income',
    '获取费用': 'acquisition_cost',
    '保险服务收入': 'insurance_service_revenue',
    '保险服务费用': 'insurance_service_expense',
    '保险合同收入': 'insurance_contract_revenue',
    '保险合同负债': 'insurance_contract_liability',
    '当期收到的保费': 'premium_received_current',
    '当期支出的保险获取现金流': 'iacf_paid_current',
    '当期确认的保险收入': 'insurance_revenue_recognized',
    '摊销的获取费用': 'acquisition_cost_amortized',
    '当期分解的投资成分': 'investment_component_released',
    '待摊销保险收入': 'unamortized_insurance_revenue',
    '待摊销获取现金流': 'unamortized_iacf',
    '待摊销投资成分': 'unamortized_investment_component',
    '未到期责任负债计息': 'lrc_accretion',
    '复效保费': 'policy_reinstatement_premium',
    '调整手续费': 'adjusted_commission',
    '应付IACF': 'iacf_payable',
    '应收保费': 'premium_receivable',
    'UPR余额': 'upr_balance',

    # ---------------- 预期未来现金流（输出） ----------------
    '预期未来保费现金流入': 'expected_future_premium_inflow',
    '预期未来保险获取现金流出': 'expected_future_iacf_outflow',
    '预期未来赔付现金流出（含间接理赔费用）': 'expected_future_claims_outflow_incl_lae',
    '预期未来维持费用现金流出': 'expected_future_maintenance_outflow',
    '预期未来现金流合计': 'expected_future_cf_total',
    '非金融风险调整': 'risk_adjustment',
    '再保人不履约风险': 'rnpr',

    # ---------------- 未到期责任负债 (LRC) 明细 ----------------
    '未到期责任负债_非亏损部分': 'lrc_non_onerous',
    '未到期责任负债_亏损部分': 'lrc_onerous',
    '未到期责任负债_亏损摊回': 'lrc_onerous_recoverable',
    '期末未到期责任负债_非亏损部分': 'lrc_non_onerous_closing',
    '期初未到期责任负债_非亏损部分': 'lrc_non_onerous_opening',
    '期初未到期责任负债_亏损部分': 'lrc_onerous_opening',
    '期初未到期责任负债_亏损摊回': 'lrc_onerous_recoverable_opening',
    '未到期责任负债_非亏损部分_不含利净口径未赚': 'lrc_non_onerous_excl_int_unearned',

    # ---------------- 已发生未决赔款负债 (LIC) 明细 ----------------
    '已发生未决赔款负债_预期现金流': 'lic_expected_cf',
    '已发生未决赔款负债_非金融风险调整': 'lic_risk_adj',
    '已发生未决赔款负债_再保人不履约_预期现金流': 'lic_rnpr_expected_cf',
    '已发生未决赔款负债_再保人不履约_非金融风险调整': 'lic_rnpr_risk_adj',
    '已发生未决赔款负债_预期现金流现值': 'lic_expected_cf_pv',
    '已发生未决赔款负债_非金融风险调整现值': 'lic_risk_adj_pv',
    '已发生未决赔款负债_再保人不履约_预期现金流现值': 'lic_rnpr_expected_cf_pv',
    '已发生未决赔款负债_再保人不履约_非金融风险调整现值': 'lic_rnpr_risk_adj_pv',

    # ---------------- 间接理赔费用负债 (LAE) 明细 ----------------
    '间接理赔费用负债_预期现金流': 'lae_liability_expected_cf',
    '间接理赔费用负债_非金融风险调整': 'lae_liability_risk_adj',
    '间接理赔费用负债_预期现金流现值': 'lae_liability_expected_cf_pv',
    '间接理赔费用负债_非金融风险调整现值': 'lae_liability_risk_adj_pv',

    # ---------------- 期末现值（开发三角）相关 ----------------
    '期末现值_未决赔款现金流_期初': 'closing_pv_incurred_claims_cf_opening',
    '期末现值_未决赔款现金流_期末': 'closing_pv_incurred_claims_cf_closing',
    '期末现值_未决赔款现金流_非金融风险调整_期初': 'closing_pv_incurred_claims_cf_ra_opening',
    '期末现值_未决赔款现金流_非金融风险调整_期末': 'closing_pv_incurred_claims_cf_ra_closing',
    '期末现值_未决赔款现金流_再保人不履约风险_期初': 'closing_pv_incurred_claims_cf_rnpr_opening',
    '期末现值_未决赔款现金流_再保人不履约风险_期末': 'closing_pv_incurred_claims_cf_rnpr_closing',
    '期末现值_未决赔款现金流_再保人不履约风险_非金融风险调整_期初': 'closing_pv_incurred_claims_cf_rnpr_ra_opening',
    '期末现值_未决赔款现金流_再保人不履约风险_非金融风险调整_期末': 'closing_pv_incurred_claims_cf_rnpr_ra_closing',
    '期末现值_未决间接理赔费用现金流_期初': 'closing_pv_lae_cf_opening',
    '期末现值_未决间接理赔费用现金流_期末': 'closing_pv_lae_cf_closing',
    '期末现值_未决间接理赔费用现金流_非金融风险调整_期初': 'closing_pv_lae_cf_ra_opening',
    '期末现值_未决间接理赔费用现金流_非金融风险调整_期末': 'closing_pv_lae_cf_ra_closing',

    # ---------------- 期末（已发生未决）汇总类 ----------------
    '期末_预期现金流_已发生未决赔款负债': 'closing_expected_cf_lic',
    '期末_预期现金流_已发生未决赔款负债_再保人不履约': 'closing_expected_cf_lic_rnpr',
    '期末_预期现金流_间接理赔费用负债': 'closing_expected_cf_lae_liability',
    '期末_非金融风险调整_已发生未决赔款负债': 'closing_ra_lic',
    '期末_非金融风险调整_已发生未决赔款负债_再保人不履约': 'closing_ra_lic_rnpr',
    '期末_非金融风险调整_间接理赔费用负债': 'closing_ra_lae_liability',

    # ---------------- 现金流（实际支付）类 ----------------
    '现金流_支付的赔付': 'cf_claims_paid',
    '现金流_支付的理赔费用': 'cf_lae_paid',
    '现金流_支付的维持费用': 'cf_maintenance_paid',
    '现金流_支付的赔付_累计': 'cf_claims_paid_cumulative',
    '现金流_支付的间接理赔费用_累计': 'cf_indirect_lae_paid_cumulative',
    '现金流_支付的赔付_累计_未到期转': 'cf_claims_paid_cumulative_from_lrc',
    '现金流_支付的理赔费用_累计_未到期转': 'cf_lae_paid_cumulative_from_lrc',
    '现金流_支付的新赔付_累计': 'cf_new_claims_paid_cumulative',
    '现金流_支付的赔付与理赔费用': 'cf_claims_and_lae_paid',
    '现金流_收到的保费': 'cf_premium_received',
    '现金流_支付的IACF': 'cf_iacf_paid',
    '现金流_支付的理赔费用': 'cf_lae_paid',
    '现金流_支付的理赔费用_累计': 'cf_lae_paid_cumulative',

    # ---------------- 赔付与费用（直保，非输出前缀）明细 ----------------
    '赔付与费用_分解的投资成分': 'claims_expense_investment_component_released',
    '赔付与费用_摊销的保险获取现金流': 'claims_expense_iacf_amortized',
    '赔付与费用_已发生未决赔款负债提转差_预期现金流': 'claims_expense_lic_movement_expected_cf',
    '赔付与费用_已发生未决赔款负债提转差_非金融风险调整': 'claims_expense_lic_movement_risk_adj',
    '赔付与费用_间接理赔费用提转差_预期现金流': 'claims_expense_lae_movement_expected_cf',
    '赔付与费用_间接理赔费用提转差_非金融风险调整': 'claims_expense_lae_movement_risk_adj',
    '摊回赔付与费用_已发生未决_再保人不履约_预期现金流': 'recoverable_claims_expense_lic_rnpr_expected_cf',
    '摊回赔付与费用_已发生未决_再保人不履约_非金融风险调整': 'recoverable_claims_expense_lic_rnpr_risk_adj',
    '亏损合同损益': 'onerous_contract_result',
    '亏损摊回损益': 'onerous_recoverable_result',

    # ---------------- IFIE / OCI（直保，非输出前缀，期初余额表用） ----------------
    'IFIE_未到期_未到期计息': 'ifie_lrc_accretion',
    'IFIE_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流': 'ifie_lic_accretion_rate_change_expected_cf',
    'IFIE_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整': 'ifie_lic_accretion_rate_change_risk_adj',
    'IFIE_已发生未决_间接理赔费用计息与利率变化_预期现金流': 'ifie_lae_accretion_rate_change_expected_cf',
    'IFIE_已发生未决_间接理赔费用计息与利率变化_非金融风险调整': 'ifie_lae_accretion_rate_change_risk_adj',

    # ---------------- 输出：保险合同服务（分入/分出明细） ----------------
    '输出_保险合同收入': 'out_insurance_contract_revenue',
    '输出_新增保费减值': 'out_premium_impairment_addition',
    '输出_未到期责任负债_非亏损部分': 'out_lrc_non_onerous',
    '输出_未到期责任负债_亏损部分': 'out_lrc_onerous',
    '输出_未到期责任负债_亏损摊回': 'out_lrc_onerous_recoverable',
    '输出_已发生未决赔款负债_预期现金流': 'out_lic_expected_cf',
    '输出_已发生未决赔款负债_非金融风险调整': 'out_lic_risk_adj',
    '输出_已发生未决赔款负债_再保人不履约_预期现金流': 'out_lic_rnpr_expected_cf',
    '输出_已发生未决赔款负债_再保人不履约_非金融风险调整': 'out_lic_rnpr_risk_adj',
    '输出_间接理赔费用负债_预期现金流': 'out_lae_liability_expected_cf',
    '输出_间接理赔费用负债_非金融风险调整': 'out_lae_liability_risk_adj',
    '输出_亏损合同损益': 'out_onerous_contract_result',
    '输出_亏损摊回损益': 'out_onerous_recoverable_result',
    '输出_赔付与费用_分解的投资成分': 'out_claims_expense_investment_component_released',
    '输出_赔付与费用_摊销的保险获取现金流': 'out_claims_expense_iacf_amortized',
    '输出_赔付与费用_已发生未决赔款负债提转差_预期现金流': 'out_claims_expense_lic_movement_expected_cf',
    '输出_赔付与费用_已发生未决赔款负债提转差_非金融风险调整': 'out_claims_expense_lic_movement_risk_adj',
    '输出_赔付与费用_间接理赔费用提转差_预期现金流': 'out_claims_expense_lae_movement_expected_cf',
    '输出_赔付与费用_间接理赔费用提转差_非金融风险调整': 'out_claims_expense_lae_movement_risk_adj',
    '输出_赔付与费用_已发生未决_再保人不履约_预期现金流': 'out_claims_expense_lic_rnpr_expected_cf',
    '输出_赔付与费用_已发生未决_再保人不履约_非金融风险调整': 'out_claims_expense_lic_rnpr_risk_adj',
    '输出_赔付与费用_再保人不履约风险提转差_预期现金流': 'out_claims_expense_rnpr_movement_expected_cf',
    '输出_赔付与费用_再保人不履约风险提转差_非金融风险调整': 'out_claims_expense_rnpr_movement_risk_adj',
    '输出_现金流_支付的赔付与理赔费用': 'out_cf_claims_and_lae_paid',
    '输出_现金流_支付的维持费用': 'out_cf_maintenance_paid',
    '输出_现金流_支付的维持费用_计量': 'out_cf_maintenance_paid_measured',
    '输出_现金流_支付的维持费用_实际维持费用_分子合同组合': 'out_cf_maintenance_paid_actual_alloc',
    '输出_现金流_收到的保费': 'out_cf_premium_received',
    '输出_现金流_支付的IACF': 'out_cf_iacf_paid',

    # ---------------- 输出：IFIE（保险财务损益） ----------------
    '输出_IFIE_未到期_未到期计息': 'out_ifie_lrc_accretion',
    '输出_IFIE_已发生未决_已发生未决赔款负债计息_预期现金流': 'out_ifie_lic_accretion_expected_cf',
    '输出_IFIE_已发生未决_已发生未决赔款负债计息_非金融风险调整': 'out_ifie_lic_accretion_risk_adj',
    '输出_IFIE_已发生未决_间接理赔费用计息_预期现金流': 'out_ifie_lae_accretion_expected_cf',
    '输出_IFIE_已发生未决_间接理赔费用计息_非金融风险调整': 'out_ifie_lae_accretion_risk_adj',

    # ---------------- 输出：OCI（其他综合收益） ----------------
    '输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流': 'out_oci_lic_accretion_rate_change_expected_cf',
    '输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整': 'out_oci_lic_accretion_rate_change_risk_adj',
    '输出_OCI_已发生未决_间接理赔费用计息与利率变化_预期现金流': 'out_oci_lae_accretion_rate_change_expected_cf',
    '输出_OCI_已发生未决_间接理赔费用计息与利率变化_非金融风险调整': 'out_oci_lae_accretion_rate_change_risk_adj',
    '输出_IFIE_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流': 'out_ifie_lic_accretion_rate_change_expected_cf',
    '输出_IFIE_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整': 'out_ifie_lic_accretion_rate_change_risk_adj',
    '输出_IFIE_已发生未决_间接理赔费用计息与利率变化_预期现金流': 'out_ifie_lae_accretion_rate_change_expected_cf',
    '输出_IFIE_已发生未决_间接理赔费用计息与利率变化_非金融风险调整': 'out_ifie_lae_accretion_rate_change_risk_adj',

    # ---------------- 输出：期初余额字段 ----------------
    '待摊销保险收入_期初': 'opening_unamortized_insurance_revenue',
    '待摊销获取现金流_期初': 'opening_unamortized_iacf',
    '未到期责任负债_亏损摊回_期初': 'opening_lrc_onerous_recoverable',
    '未到期责任负债_亏损部分_期初': 'opening_lrc_onerous',
    '未到期责任负债_非亏损部分_期初': 'opening_lrc_non_onerous',
    '已发生未决赔款负债_预期现金流_期初': 'opening_lic_expected_cf',
    '已发生未决赔款负债_非金融风险调整_期初': 'opening_lic_risk_adj',
    '已发生未决赔款负债_再保人不履约_预期现金流_期初': 'opening_lic_rnpr_expected_cf',
    '已发生未决赔款负债_再保人不履约_非金融风险调整_期初': 'opening_lic_rnpr_risk_adj',
    '间接理赔费用负债_预期现金流_期初': 'opening_lae_liability_expected_cf',
    '间接理赔费用负债_非金融风险调整_期初': 'opening_lae_liability_risk_adj',

    # ---------------- 输出：新业务/现有业务通用字段 ----------------
    '保费写入时点': 'premium_written_at',
    '再保前生效保费': 'premium_before_reinsurance',
    '分出比例': 'ceded_ratio',
    '签单保费': 'written_premium',
    '现有业务预测组ID': 'exist_biz_forecast_group_id',
    'balance_sheet': 'balance_sheet',
    'income_statement': 'income_statement',

    # ---------------- 财务报表（利润表）行项目 ----------------
    '一、营业总收入': 'total_operating_revenue',
    '二、营业总支出': 'total_operating_expense',
    '三、营业利润（亏损以"-"号填列）': 'operating_profit',
    '四、利润总额（亏损总额以"-"号填列）': 'total_profit',
    '五、净利润（净亏损以"-"号填列）': 'net_profit',
    '六、其他综合收益的税后净额': 'oci_net_of_tax',
    '七、综合收益总额': 'total_comprehensive_income',
    '利息收入': 'interest_income',
    '投资收益（损失以"-"号填列）': 'investment_income',
    '其他收益（损失以"-"号填列）': 'other_income',
    '公允价值变动收益（损失以"-"号填列）': 'fair_value_change_income',
    '汇兑收益（损失以"-"号填列）': 'fx_gain',
    '其他业务收入': 'other_business_income',
    '资产处置收益（损失以"-"号填列）': 'asset_disposal_income',
    '分出保费的分摊': 'ceded_premium_allocation',
    '减：摊回保险服务费用': 'less_recoverable_service_expense',
    '减：分出再保险财务收益': 'less_ceded_reinsurance_finance_income',
    '提取保费准备金': 'premium_reserve_extraction',
    '利息支出': 'interest_expense',
    '税金及附加': 'tax_and_surcharge',
    '手续费及佣金支出': 'commission_expense',
    '业务及管理费': 'admin_expense',
    '信用减值损失': 'credit_impairment_loss',
    '其他资产减值损失': 'other_asset_impairment_loss',
    '其他业务成本': 'other_business_cost',
    '加：营业外收入': 'plus_non_operating_income',
    '减：营业外支出': 'less_non_operating_expense',
    '减：所得税费用': 'less_income_tax',
    '承保利润': 'underwriting_profit',
    '承保财务损失': 'underwriting_financial_loss',

    # ---------------- 财务报表（资产负债表）行项目 ----------------
    '资产': 'assets',
    '资产总计': 'total_assets',
    '负债': 'liabilities',
    '负债合计': 'total_liabilities',
    '负债及所有者权益总计': 'total_liabilities_and_equity',
    '其他资产': 'other_assets',
    '其他负债': 'other_liabilities',
    '分出再保险合同资产': 'reinsurance_contract_asset',

    # ---------------- 验证 fixture 中的分组/科目键 ----------------
    '科目': 'account',
    '财务科目': 'financial_account',
    'PAA计算_MTD': 'paa_mtd',
    'PAA计算_新业务整理': 'paa_new_business',
    'PAA计算_现有业务整理': 'paa_existing_business',
    'PAA计算_汇总': 'paa_summary',
    '输出财务报表_MTD': 'fs_mtd',
    '输出财务报表_YTD': 'fs_ytd',

    # ---------------- 压力情景配置 ----------------
    '情景': 'scenario',
    '情景描述': 'scenario_description',
    '原保险保费增长': 'gross_premium_growth',
    '预期赔付率上升': 'expected_claim_ratio_increase',
    '预期费用率上升': 'expected_expense_ratio_increase',
    '即期利率变动': 'spot_rate_change',
    '权益类资产下跌': 'equity_asset_decline',
    '投资性不动产价格下跌': 'investment_property_decline',
    '关注及不良类固收违约': 'credit_risk_default_soe',
    '其他固收违约': 'credit_risk_default_other',
    '外汇不利影响': 'fx_adverse_impact',
    '黄金等大宗商品下跌': 'commodity_price_decline',

    # ---------------- 利率曲线 / 期初余额 ----------------
    '初始确认利率曲线': 'initial_recognition_rate_curve',
    '即期利率曲线': 'spot_rate_curve',
    '期末余额': 'closing_balance',
    '数据类型': 'data_type',
    '数据类型（增加利润为正，减少利润为负）': 'data_type_pnl_sign',

    # ---------------- 利率曲线加工（中间表 C）字段 ----------------
    '月度折现远期利率': 'monthly_rate',
    '月度折现因子_期末': 'discount_factor_end',
    '月度折现因子_期初': 'discount_factor_begin',
    '年化利率_预测期': 'annual_rate_forecast',
    '年化利率_评估日': 'annual_rate_eval',

    # ---------------- 表4 PAA计算_MTD 财务科目（英文键补齐） ----------------
    '其他综合收益': 'OCI',
    '营业外收入': 'non_operating_income',
    '营业外支出': 'non_operating_expense',

    # ---------------- 中间表 A 字段：合同组关键假设_新业务 ----------------
    '当期提前初始确认签单保费': 'advance_written_premium',
}

# ---------------- 险类（业务线）拆分列（期初余额表 / 初始确认利率曲线用） ----------------
# 形如 "{险类}_直保或分入_现有业务" / "{险类}_分出_现有业务" 的拆分列，
# 由下方 _LOB_EN 循环批量登记，避免逐一手写。

# 险类（业务线）中文 -> 英文代码（财产险常用业务线缩写）
_LOB_EN = {
    '交强险': 'compulsory_auto',
    '附加险': 'additional',
    '商业三者险': 'commercial_tp',
    '车损险': 'vehicle_damage',
    '企业财产险': 'enterprise_property',
    '货运险': 'cargo',
    '责任险': 'liability',
    '保证保险': 'guarantee',
    '信用保险': 'credit',
    '特殊风险': 'special_risk',
    '家财险': 'home_property',
    '建工险': 'construction',
    '其他险': 'other_line',
    '船舶险': 'marine_hull',
    '种植业': 'crop',
    '养殖业': 'livestock',
    '意外险': 'accident',
    '商业性健康险': 'commercial_health',
    '大病保险': 'critical_illness',
    '其他政策性健康险': 'other_policy_health',
    '其他': 'other',
}
# 批量登记险类拆分列（直保或分入 / 分出）
for _lob, _code in _LOB_EN.items():
    CN_TO_EN[f'{_lob}_直保或分入_现有业务'] = f'{_code}_direct'
    CN_TO_EN[f'{_lob}_分出_现有业务'] = f'{_code}_ceded'

# 反向映射（英 -> 中），由显式表自动生成
EN_TO_CN: Dict[str, str] = {v: k for k, v in CN_TO_EN.items()}


# =====================================================================
# 2) 段（fragment）级兜底翻译：用于显式表未覆盖的复合字段前向兼容
# =====================================================================
_SEG = {
    '期末现值': 'closing_pv',
    '未决赔款现金流': 'incurred_claims_cf',
    '未决间接理赔费用现金流': 'incurred_lae_cf',
    '间接理赔费用现金流': 'lae_cf',
    '再保人不履约风险': 'rnpr',
    '非金融风险调整': 'risk_adj',
    '期初': 'opening',
    '期末': 'closing',
    '已发生未决赔款负债': 'lic',
    '已发生未决': 'incurred',
    '间接理赔费用负债': 'lae_liability',
    '预期现金流': 'expected_cf',
    '现值': 'pv',
    '未到期责任负债': 'lrc',
    '亏损摊回': 'onerous_recoverable',
    '亏损部分': 'onerous_part',
    '非亏损部分': 'non_onerous_part',
    '计息': 'accretion',
    '计息与利率变化': 'accretion_and_rate_change',
    '提转差': 'movement',
    '现金流': 'cf',
    '支付的': 'paid',
    '收到的': 'received',
    '赔付': 'claims',
    '理赔费用': 'lae',
    '维持费用': 'maintenance',
    '累计': 'cumulative',
    '新赔付': 'new_claims',
    '未到期转': 'from_lrc',
    '预期未来': 'expected_future',
    '保费现金流入': 'premium_inflow',
    '保险获取现金流出': 'iacf_outflow',
    '赔付现金流出': 'claims_outflow',
    '维持费用现金流出': 'maintenance_outflow',
    '现金流合计': 'cf_total',
    '含间接理赔费用': 'incl_lae',
    '待摊销': 'unamortized',
    '保险收入': 'insurance_revenue',
    '获取现金流': 'iacf',
    '投资成分': 'investment_component',
    '当期': 'current',
    '确认比例': 'recognition_ratio',
    '获取费用': 'acquisition_cost',
    '输出': 'out',
}


def _has_cjk(s: str) -> bool:
    return any('一' <= ch <= '鿿' for ch in s)


def _segment_fallback(cn: str) -> str:
    """显式表未命中时，按 '_' 分段做兜底翻译。"""
    if '_' not in cn:
        return cn  # 无法分段的单段，原样返回（会被覆盖率检查捕获）
    parts = cn.split('_')
    out = []
    for p in parts:
        out.append(_SEG.get(p, p))
    return '_'.join(out)


def to_en(cn: str) -> str:
    """中文 -> 英文。未命中显式表则走段兜底；仍含中文则返回原串（便于发现遗漏）。"""
    if not _has_cjk(cn):
        return cn  # 本身就是英文，原样返回（幂等）
    if cn in CN_TO_EN:
        return CN_TO_EN[cn]
    return _segment_fallback(cn)


def to_cn(en: str) -> str:
    """英文 -> 中文。未命中返回原串（幂等）。"""
    if _has_cjk(en):
        return en
    return EN_TO_CN.get(en, en)


def translate_keys(d: Dict[str, Any], to: str = 'en') -> Dict[str, Any]:
    """翻译 dict 的 key（默认 中->英）。value 不变。"""
    fn = to_en if to == 'en' else to_cn
    return {fn(k): v for k, v in d.items()}


def translate_in(row: Dict[str, Any]) -> Dict[str, Any]:
    """上传数据读取后调用：中文表头 -> 英文 key。"""
    return translate_keys(row, 'en')


def translate_out(row: Dict[str, Any]) -> Dict[str, Any]:
    """导出前调用：英文 key -> 中文表头（保持业务/安永中文习惯）。"""
    return translate_keys(row, 'cn')


def translate_out_deep(obj: Any) -> Any:
    """递归翻译：把任意嵌套 dict/list 的英文 key 还原为中文（导出/对外边界用）。

    保证引擎内部用英文计算、但对外（calc 结果 / Excel / 前端 / 验证比对）仍为
    中文列名——中文 key 经 to_cn 精确回写为原中文，未登记 key 原样保留。
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            nk = to_cn(k) if isinstance(k, str) else k
            out[nk] = translate_out_deep(v)
        return out
    if isinstance(obj, list):
        return [translate_out_deep(v) for v in obj]
    return obj


# =====================================================================
# 3) 自测：保证全部已知中文字段都有英文映射且翻译结果不含中文
# =====================================================================
def _self_test(cn_fields) -> None:
    missing = [f for f in cn_fields if f not in CN_TO_EN]
    leaked = [f for f in cn_fields if _has_cjk(to_en(f))]
    if missing or leaked:
        raise AssertionError(
            f"field_names 覆盖不全：missing={missing[:20]} leaked={leaked[:20]}")


if __name__ == '__main__':
    # 简单冒烟：打印若干示例
    samples = ['未到期责任负债_亏损部分', '输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流',
               '期末现值_未决赔款现金流_再保人不履约风险_期初', '保险服务收入', '预测时点']
    for s in samples:
        print(f"{s}  ->  {to_en(s)}  ->  {to_cn(to_en(s))}")
    print("CN_TO_EN size:", len(CN_TO_EN), "EN_TO_CN size:", len(EN_TO_CN))
