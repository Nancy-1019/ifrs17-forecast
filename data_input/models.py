"""IFRS17 数据输入 - 数据模型
- UploadRecord: 上传记录（落库、审核）
- SheetData: 工作表数据存储（JSON格式）
- DataWorksSyncLog: DataWorks同步日志（预留）
"""
from django.db import models
from django.contrib.auth.models import User


class UploadRecord(models.Model):
    """Excel上传记录表 - 每次上传生成一条记录"""
    SOURCE_EXCEL = 'excel'
    SOURCE_DOCK = 'dock'
    SOURCE_CHOICES = [
        (SOURCE_EXCEL, 'Excel上传接口'),
        (SOURCE_DOCK, '系统对接接口'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, '待审核'),
        (STATUS_APPROVED, '已通过'),
        (STATUS_REJECTED, '已驳回'),
    ]

    source = models.CharField('数据来源', max_length=10, choices=SOURCE_CHOICES)
    file_name = models.CharField('文件名', max_length=255)
    upload_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='uploads', verbose_name='上传人'
    )
    upload_time = models.DateTimeField('上传时间', auto_now_add=True)
    sheet_count = models.IntegerField('工作表数量')
    total_rows = models.IntegerField('总数据行数')

    validation_passed = models.BooleanField('校验通过', default=False)
    validation_errors = models.JSONField('校验错误', default=list, blank=True)
    validation_warnings = models.JSONField('校验警告', default=list, blank=True)
    validation_detail = models.JSONField('校验明细', default=dict, blank=True)

    status = models.CharField(
        '审核状态', max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_uploads', verbose_name='审核人'
    )
    reviewed_at = models.DateTimeField('审核时间', null=True, blank=True)
    review_notes = models.TextField('审核备注', blank=True)

    # DataWorks同步状态
    dw_sync_status = models.CharField(
        'DataWorks同步', max_length=10,
        choices=[('pending','待同步'),('syncing','同步中'),('success','成功'),('failed','失败')],
        default='pending'
    )

    class Meta:
        db_table = 'ifrs17_upload_record'
        verbose_name = '上传记录'
        verbose_name_plural = '上传记录'
        ordering = ['-upload_time']
        permissions = [
            ('can_upload', '可以上传数据'),
            ('can_review', '可以审核上传'),
            ('can_view_all', '可以查看所有数据'),
        ]

    def __str__(self):
        return f"[{self.get_source_display()}] {self.file_name} ({self.upload_time.strftime('%Y-%m-%d %H:%M')})"


class SheetData(models.Model):
    """工作表数据存储 - 按工作表粒度存储Excel数据"""
    SOURCE_EXCEL = 'excel'
    SOURCE_DOCK = 'dock'
    SOURCE_CHOICES = [
        (SOURCE_EXCEL, 'Excel上传接口'),
        (SOURCE_DOCK, '系统对接接口'),
    ]

    source = models.CharField('数据来源', max_length=10, choices=SOURCE_CHOICES)
    sheet_name = models.CharField('工作表名称', max_length=100)
    headers = models.JSONField('表头', default=list)
    rows = models.JSONField('数据行', default=list)
    row_count = models.IntegerField('行数', default=0)
    display_cols = models.IntegerField('显示列数', default=0)

    upload_record = models.ForeignKey(
        UploadRecord, on_delete=models.CASCADE, related_name='sheets',
        verbose_name='所属上传记录'
    )
    is_active = models.BooleanField('当前有效', default=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'ifrs17_sheet_data'
        verbose_name = '工作表数据'
        verbose_name_plural = '工作表数据'
        ordering = ['source', 'sheet_name']
        indexes = [
            models.Index(fields=['source', 'sheet_name', '-created_at']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"[{self.get_source_display()}] {self.sheet_name} ({self.row_count}行)"


class DataWorksSyncLog(models.Model):
    """DataWorks同步日志（预留接口）"""
    STATUS_CHOICES = [
        ('pending', '待同步'),
        ('syncing', '同步中'),
        ('success', '成功'),
        ('failed', '失败'),
    ]

    upload_record = models.OneToOneField(
        UploadRecord, on_delete=models.CASCADE, related_name='dw_sync_log',
        verbose_name='关联上传记录'
    )
    sync_status = models.CharField('同步状态', max_length=10, choices=STATUS_CHOICES, default='pending')
    table_name = models.CharField('目标表名', max_length=200, blank=True)
    started_at = models.DateTimeField('开始时间', null=True, blank=True)
    completed_at = models.DateTimeField('完成时间', null=True, blank=True)
    error_message = models.TextField('错误信息', blank=True)
    retry_count = models.IntegerField('重试次数', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'ifrs17_dw_sync_log'
        verbose_name = 'DataWorks同步日志'
        verbose_name_plural = 'DataWorks同步日志'
        ordering = ['-created_at']

    def __str__(self):
        return f"同步日志 #{self.id} [{self.get_sync_status_display()}]"


class SystemOperationLog(models.Model):
    """系统运行日志 — 记录系统每一步操作（登录/上传/计算/导出/部署/查询等）。"""

    LEVEL_INFO = 'INFO'
    LEVEL_WARN = 'WARN'
    LEVEL_ERROR = 'ERROR'
    LEVEL_CHOICES = [
        (LEVEL_INFO, '信息'),
        (LEVEL_WARN, '警告'),
        (LEVEL_ERROR, '错误'),
    ]

    # 操作类型常量
    ACTION_LOGIN = 'login'
    ACTION_LOGOUT = 'logout'
    ACTION_UPLOAD = 'upload'
    ACTION_CALC_RUN = 'calc_run'
    ACTION_CALC_DONE = 'calc_done'
    ACTION_CALC_FAIL = 'calc_fail'
    ACTION_EXPORT = 'export'
    ACTION_DEPLOY = 'deploy'
    ACTION_VERSION_PUSH = 'version_push'
    ACTION_SQL_QUERY = 'sql_query'
    ACTION_OTHER = 'other'

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='op_logs', verbose_name='操作用户'
    )
    username = models.CharField('用户名快照', max_length=150, blank=True)
    action = models.CharField('操作类型', max_length=40, db_index=True)
    action_label = models.CharField('操作名称', max_length=60, blank=True)
    target = models.CharField('操作对象', max_length=200, blank=True)
    detail = models.TextField('操作详情', blank=True)
    level = models.CharField('级别', max_length=10, choices=LEVEL_CHOICES, default=LEVEL_INFO)
    ip = models.GenericIPAddressField('来源IP', null=True, blank=True)
    created_at = models.DateTimeField('操作时间', auto_now_add=True)

    class Meta:
        db_table = 'ifrs17_system_log'
        verbose_name = '系统运行日志'
        verbose_name_plural = '系统运行日志'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['level', '-created_at']),
        ]

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M:%S}] {self.username} {self.action_label}"

    @classmethod
    def action_choices(cls):
        return [
            (cls.ACTION_LOGIN, '登录'),
            (cls.ACTION_LOGOUT, '登出'),
            (cls.ACTION_UPLOAD, '数据上传'),
            (cls.ACTION_CALC_RUN, '触发计算'),
            (cls.ACTION_CALC_DONE, '计算完成'),
            (cls.ACTION_CALC_FAIL, '计算失败'),
            (cls.ACTION_EXPORT, '导出'),
            (cls.ACTION_DEPLOY, '部署'),
            (cls.ACTION_VERSION_PUSH, '版本入库'),
            (cls.ACTION_SQL_QUERY, 'SQL查询'),
            (cls.ACTION_OTHER, '其他'),
        ]


class CalculationVersion(models.Model):
    """计算版本 — 把一次（或一批）计算完成的结果作为版本持久化到 MySQL。"""

    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_CHOICES = [
        (STATUS_DRAFT, '草稿'),
        (STATUS_PUBLISHED, '已发布'),
    ]

    name = models.CharField('版本名称', max_length=200)
    description = models.TextField('版本说明', blank=True)
    scenario_count = models.IntegerField('情景数量', default=0)
    scenarios = models.JSONField('包含情景', default=list, blank=True)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='calc_versions', verbose_name='创建人'
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'ifrs17_calc_version'
        verbose_name = '计算版本'
        verbose_name_plural = '计算版本'
        ordering = ['-created_at']

    def __str__(self):
        return f"#{self.id} {self.name} ({self.scenario_count}个情景)"


class CalculationSnapshot(models.Model):
    """计算版本明细 — 单个情景的完整计算结果快照（JSON）。"""

    version = models.ForeignKey(
        CalculationVersion, on_delete=models.CASCADE, related_name='snapshots',
        verbose_name='所属版本'
    )
    scenario = models.CharField('情景', max_length=40)
    result_json = models.JSONField('结果数据', default=dict)
    row_counts = models.JSONField('行数统计', default=dict, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        db_table = 'ifrs17_calc_snapshot'
        verbose_name = '计算结果快照'
        verbose_name_plural = '计算结果快照'
        ordering = ['id']
        indexes = [
            models.Index(fields=['version', 'scenario']),
        ]

    def __str__(self):
        return f"版本#{self.version_id} · {self.scenario}"


# ============================================================
# 计算结果输出物理表（与数据表字典英文表名一一对应）
# 每张表存储一个输出结果表的行级 JSON 数据
# ============================================================

class _OutputResultTableBase(models.Model):
    """计算结果输出物理表公共抽象基类。

    行级数据已拆分为独立字段，便于外部系统 / BI 直接 SELECT。
    """

    version = models.ForeignKey(
        CalculationVersion, on_delete=models.CASCADE,
        verbose_name='所属版本'
    )
    scenario = models.CharField('情景', max_length=40)
    row_idx = models.IntegerField('行序号', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['version', 'scenario']),
        ]


class OutputPaaNewBusinessOrganized(_OutputResultTableBase):
    """PAA计算_新业务整理（行级字段展开）。"""

    advance_written_premium = models.DecimalField('当期提前初始确认签单保费', max_digits=38, decimal_places=10, null=True, blank=True)
    business_type = models.CharField('业务类型', max_length=255, null=True, blank=True)
    premium_written_at = models.CharField('保费写入时点', max_length=50, null=True, blank=True)
    premium_income = models.DecimalField('保费收入', max_digits=38, decimal_places=10, null=True, blank=True)
    premium_before_reinsurance = models.DecimalField('再保前生效保费', max_digits=38, decimal_places=10, null=True, blank=True)
    ceded_ratio = models.DecimalField('分出比例', max_digits=38, decimal_places=10, null=True, blank=True)
    contract_portfolio_name = models.CharField('合同组合名称', max_length=255, null=True, blank=True)
    current_recognition_ratio = models.DecimalField('当期确认比例', max_digits=38, decimal_places=10, null=True, blank=True)
    written_premium = models.DecimalField('签单保费', max_digits=38, decimal_places=10, null=True, blank=True)
    actuarial_lob = models.CharField('精算险类', max_length=255, null=True, blank=True)
    iacf_amortization_ratio = models.DecimalField('获取现金流摊销比例', max_digits=38, decimal_places=10, null=True, blank=True)
    acquisition_cost = models.DecimalField('获取费用', max_digits=38, decimal_places=10, null=True, blank=True)
    expected_writing_period_months = models.DecimalField('评估期开始业务预期写入时间（月）', max_digits=38, decimal_places=10, null=True, blank=True)
    forecast_group = models.CharField('预测组', max_length=255, null=True, blank=True)
    forecast_group_id = models.CharField('预测组ID', max_length=255, null=True, blank=True)

    class Meta(_OutputResultTableBase.Meta):
        db_table = 'paa_new_business_organized'
        verbose_name = 'PAA计算_新业务整理'
        verbose_name_plural = 'PAA计算_新业务整理'


class OutputPaaExistingBusinessOrganized(_OutputResultTableBase):
    """PAA计算_现有业务整理（行级字段展开）。"""

    premium_written_at = models.CharField('保费写入时点', max_length=50, null=True, blank=True)
    premium_income = models.DecimalField('保费收入', max_digits=38, decimal_places=10, null=True, blank=True)
    contract_group_id = models.CharField('合同组ID', max_length=255, null=True, blank=True)
    contract_group_name = models.CharField('合同组名称', max_length=255, null=True, blank=True)
    opening_lic_rnpr_risk_adj = models.DecimalField('已发生未决赔款负债_再保人不履约_非金融风险调整_期初', max_digits=38, decimal_places=10, null=True, blank=True)
    opening_lic_rnpr_expected_cf = models.DecimalField('已发生未决赔款负债_再保人不履约_预期现金流_期初', max_digits=38, decimal_places=10, null=True, blank=True)
    opening_lic_risk_adj = models.DecimalField('已发生未决赔款负债_非金融风险调整_期初', max_digits=38, decimal_places=10, null=True, blank=True)
    opening_lic_expected_cf = models.DecimalField('已发生未决赔款负债_预期现金流_期初', max_digits=38, decimal_places=10, null=True, blank=True)
    iacf_payable = models.DecimalField('应付IACF', max_digits=38, decimal_places=10, null=True, blank=True)
    premium_receivable = models.DecimalField('应收保费', max_digits=38, decimal_places=10, null=True, blank=True)
    opening_unamortized_insurance_revenue = models.DecimalField('待摊销保险收入_期初', max_digits=38, decimal_places=10, null=True, blank=True)
    opening_unamortized_iacf = models.DecimalField('待摊销获取现金流_期初', max_digits=38, decimal_places=10, null=True, blank=True)
    lic_risk_adj_ratio_pct = models.DecimalField('未决风险调整%', max_digits=38, decimal_places=10, null=True, blank=True)
    opening_lrc_onerous_recoverable = models.DecimalField('未到期责任负债_亏损摊回_期初', max_digits=38, decimal_places=10, null=True, blank=True)
    opening_lrc_onerous = models.DecimalField('未到期责任负债_亏损部分_期初', max_digits=38, decimal_places=10, null=True, blank=True)
    opening_lrc_non_onerous = models.DecimalField('未到期责任负债_非亏损部分_期初', max_digits=38, decimal_places=10, null=True, blank=True)
    lrc_risk_adj_ratio_pct = models.DecimalField('未到期风险调整%', max_digits=38, decimal_places=10, null=True, blank=True)
    exist_biz_forecast_group = models.CharField('现有业务预测组', max_length=255, null=True, blank=True)
    exist_biz_forecast_group_id = models.CharField('现有业务预测组ID', max_length=255, null=True, blank=True)
    direct_or_ceded = models.CharField('直保或分入/分出', max_length=255, null=True, blank=True)
    actuarial_lob = models.CharField('精算险类', max_length=255, null=True, blank=True)
    acquisition_cost = models.DecimalField('获取费用', max_digits=38, decimal_places=10, null=True, blank=True)
    expected_writing_period_months = models.DecimalField('评估期开始业务预期写入时间（月）', max_digits=38, decimal_places=10, null=True, blank=True)
    opening_lae_liability_risk_adj = models.DecimalField('间接理赔费用负债_非金融风险调整_期初', max_digits=38, decimal_places=10, null=True, blank=True)
    opening_lae_liability_expected_cf = models.DecimalField('间接理赔费用负债_预期现金流_期初', max_digits=38, decimal_places=10, null=True, blank=True)
    forecast_group = models.CharField('预测组', max_length=255, null=True, blank=True)
    forecast_group_id = models.CharField('预测组ID', max_length=255, null=True, blank=True)

    class Meta(_OutputResultTableBase.Meta):
        db_table = 'paa_existing_business_organized'
        verbose_name = 'PAA计算_现有业务整理'
        verbose_name_plural = 'PAA计算_现有业务整理'


class OutputPaaSummary(_OutputResultTableBase):
    """PAA计算_汇总（行级字段展开）。"""

    business_type = models.CharField('业务类型', max_length=255, null=True, blank=True)
    contract_group_id = models.CharField('合同组ID', max_length=255, null=True, blank=True)
    contract_group_id_name = models.CharField('合同组ID名称', max_length=255, null=True, blank=True)
    contract_portfolio_name = models.CharField('合同组合名称', max_length=255, null=True, blank=True)
    contract_group_name = models.CharField('合同组名称', max_length=255, null=True, blank=True)
    sub_contract_portfolio_name = models.CharField('子合同组合名称', max_length=255, null=True, blank=True)
    actual_maintenance_alloc_ratio = models.DecimalField('实际维持费用分摊比例', max_digits=38, decimal_places=10, null=True, blank=True)
    arrangement_combination = models.CharField('排列组合项', max_length=255, null=True, blank=True)
    actuarial_lob = models.CharField('精算险类', max_length=255, null=True, blank=True)
    valuation_date = models.CharField('评估日', max_length=50, null=True, blank=True)
    expected_writing_period_months = models.DecimalField('评估期开始业务预期写入时间（月）', max_digits=38, decimal_places=10, null=True, blank=True)
    out_ifie_lic_accretion_risk_adj = models.DecimalField('输出_IFIE_已发生未决_已发生未决赔款负债计息_非金融风险调整', max_digits=38, decimal_places=10, null=True, blank=True)
    out_ifie_lic_accretion_expected_cf = models.DecimalField('输出_IFIE_已发生未决_已发生未决赔款负债计息_预期现金流', max_digits=38, decimal_places=10, null=True, blank=True)
    out_ifie_lae_accretion_risk_adj = models.DecimalField('输出_IFIE_已发生未决_间接理赔费用计息_非金融风险调整', max_digits=38, decimal_places=10, null=True, blank=True)
    out_ifie_lae_accretion_expected_cf = models.DecimalField('输出_IFIE_已发生未决_间接理赔费用计息_预期现金流', max_digits=38, decimal_places=10, null=True, blank=True)
    out_ifie_lrc_accretion = models.DecimalField('输出_IFIE_未到期_未到期计息', max_digits=38, decimal_places=10, null=True, blank=True)
    out_oci_lic_accretion_rate_change_risk_adj = models.DecimalField('输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整', max_digits=38, decimal_places=10, null=True, blank=True)
    out_oci_lic_accretion_rate_change_expected_cf = models.DecimalField('输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流', max_digits=38, decimal_places=10, null=True, blank=True)
    out_oci_lae_accretion_rate_change_risk_adj = models.DecimalField('输出_OCI_已发生未决_间接理赔费用计息与利率变化_非金融风险调整', max_digits=38, decimal_places=10, null=True, blank=True)
    out_oci_lae_accretion_rate_change_expected_cf = models.DecimalField('输出_OCI_已发生未决_间接理赔费用计息与利率变化_预期现金流', max_digits=38, decimal_places=10, null=True, blank=True)
    out_onerous_contract_result = models.DecimalField('输出_亏损合同损益', max_digits=38, decimal_places=10, null=True, blank=True)
    out_onerous_recoverable_result = models.DecimalField('输出_亏损摊回损益', max_digits=38, decimal_places=10, null=True, blank=True)
    out_insurance_contract_revenue = models.DecimalField('输出_保险合同收入', max_digits=38, decimal_places=10, null=True, blank=True)
    out_lic_rnpr_risk_adj = models.DecimalField('输出_已发生未决赔款负债_再保人不履约_非金融风险调整', max_digits=38, decimal_places=10, null=True, blank=True)
    out_lic_rnpr_expected_cf = models.DecimalField('输出_已发生未决赔款负债_再保人不履约_预期现金流', max_digits=38, decimal_places=10, null=True, blank=True)
    out_lic_risk_adj = models.DecimalField('输出_已发生未决赔款负债_非金融风险调整', max_digits=38, decimal_places=10, null=True, blank=True)
    out_lic_expected_cf = models.DecimalField('输出_已发生未决赔款负债_预期现金流', max_digits=38, decimal_places=10, null=True, blank=True)
    out_lrc_onerous_recoverable = models.DecimalField('输出_未到期责任负债_亏损摊回', max_digits=38, decimal_places=10, null=True, blank=True)
    out_lrc_onerous = models.DecimalField('输出_未到期责任负债_亏损部分', max_digits=38, decimal_places=10, null=True, blank=True)
    out_lrc_non_onerous = models.DecimalField('输出_未到期责任负债_非亏损部分', max_digits=38, decimal_places=10, null=True, blank=True)
    out_cf_iacf_paid = models.DecimalField('输出_现金流_支付的IACF', max_digits=38, decimal_places=10, null=True, blank=True)
    out_cf_maintenance_paid = models.DecimalField('输出_现金流_支付的维持费用', max_digits=38, decimal_places=10, null=True, blank=True)
    out_cf_maintenance_paid_actual_alloc = models.DecimalField('输出_现金流_支付的维持费用_实际维持费用_分子合同组合', max_digits=38, decimal_places=10, null=True, blank=True)
    out_cf_maintenance_paid_measured = models.DecimalField('输出_现金流_支付的维持费用_计量', max_digits=38, decimal_places=10, null=True, blank=True)
    out_cf_claims_and_lae_paid = models.DecimalField('输出_现金流_支付的赔付与理赔费用', max_digits=38, decimal_places=10, null=True, blank=True)
    out_cf_premium_received = models.DecimalField('输出_现金流_收到的保费', max_digits=38, decimal_places=10, null=True, blank=True)
    out_claims_expense_investment_component_released = models.DecimalField('输出_赔付与费用_分解的投资成分', max_digits=38, decimal_places=10, null=True, blank=True)
    out_claims_expense_lic_rnpr_risk_adj = models.DecimalField('输出_赔付与费用_已发生未决_再保人不履约_非金融风险调整', max_digits=38, decimal_places=10, null=True, blank=True)
    out_claims_expense_lic_rnpr_expected_cf = models.DecimalField('输出_赔付与费用_已发生未决_再保人不履约_预期现金流', max_digits=38, decimal_places=10, null=True, blank=True)
    out_claims_expense_lic_movement_risk_adj = models.DecimalField('输出_赔付与费用_已发生未决赔款负债提转差_非金融风险调整', max_digits=38, decimal_places=10, null=True, blank=True)
    out_claims_expense_lic_movement_expected_cf = models.DecimalField('输出_赔付与费用_已发生未决赔款负债提转差_预期现金流', max_digits=38, decimal_places=10, null=True, blank=True)
    out_claims_expense_iacf_amortized = models.DecimalField('输出_赔付与费用_摊销的保险获取现金流', max_digits=38, decimal_places=10, null=True, blank=True)
    out_claims_expense_lae_movement_risk_adj = models.DecimalField('输出_赔付与费用_间接理赔费用提转差_非金融风险调整', max_digits=38, decimal_places=10, null=True, blank=True)
    out_claims_expense_lae_movement_expected_cf = models.DecimalField('输出_赔付与费用_间接理赔费用提转差_预期现金流', max_digits=38, decimal_places=10, null=True, blank=True)
    out_lae_liability_risk_adj = models.DecimalField('输出_间接理赔费用负债_非金融风险调整', max_digits=38, decimal_places=10, null=True, blank=True)
    out_lae_liability_expected_cf = models.DecimalField('输出_间接理赔费用负债_预期现金流', max_digits=38, decimal_places=10, null=True, blank=True)
    forecast_point = models.CharField('预测时点', max_length=50, null=True, blank=True)
    forecast_interval = models.DecimalField('预测间隔', max_digits=38, decimal_places=10, null=True, blank=True)
    forecast_interval_arrangement = models.DecimalField('预测间隔_排列', max_digits=38, decimal_places=10, null=True, blank=True)

    class Meta(_OutputResultTableBase.Meta):
        db_table = 'paa_summary'
        verbose_name = 'PAA计算_汇总'
        verbose_name_plural = 'PAA计算_汇总'


class _FinancialStatementLineBase(models.Model):
    """财务报表输出物理表公共抽象基类（按 科目 × 期间 拆行，无 JSON 聚合字段）。

    彻底消除 balance_sheet / income_statement 这类 JSON 聚合列：
    - 每个科目（资产负债表科目 / 利润表科目）对应一个 line_idx；
    - 该科目在每一个期间（financialStatementsV2.dates[]）的数值独立成一行，
      amount 为单一标量，不再出现「多字段集中在一字段」的情况。
    """

    version = models.ForeignKey(
        CalculationVersion, on_delete=models.CASCADE,
        verbose_name='所属版本'
    )
    scenario = models.CharField('情景', max_length=40)
    statement_type = models.CharField(
        '报表类型', max_length=20, default='income_statement',
        help_text='balance_sheet=资产负债表；income_statement=利润表'
    )
    line_idx = models.IntegerField('科目行序', default=0)
    item = models.CharField('科目名称', max_length=255, null=True, blank=True)
    indent = models.IntegerField('缩进层级', default=0)
    is_total = models.BooleanField('是否合计行', default=False)
    period_date = models.DateField('期间', null=True, blank=True)
    period_idx = models.IntegerField('期间序号', default=0)
    amount = models.DecimalField('数值', max_digits=26, decimal_places=4, null=True, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['version', 'scenario', 'statement_type']),
            models.Index(fields=['version', 'scenario', 'statement_type', 'period_date']),
        ]


class OutputPaaMtd(_FinancialStatementLineBase):
    """PAA计算_MTD（财务报表明细：科目 × 期间，每行单一数值）。"""

    class Meta(_FinancialStatementLineBase.Meta):
        db_table = 'paa_mtd'
        verbose_name = 'PAA计算_MTD'
        verbose_name_plural = 'PAA计算_MTD'


class OutputFinancialStatementMtd(_FinancialStatementLineBase):
    """输出财务报表_MTD（财务报表明细：科目 × 期间，每行单一数值）。"""

    class Meta(_FinancialStatementLineBase.Meta):
        db_table = 'financial_statement_mtd'
        verbose_name = '输出财务报表_MTD'
        verbose_name_plural = '输出财务报表_MTD'


class OutputFinancialStatementYtd(_FinancialStatementLineBase):
    """输出财务报表_YTD（财务报表明细：科目 × 期间，每行单一数值）。"""

    class Meta(_FinancialStatementLineBase.Meta):
        db_table = 'financial_statement_ytd'
        verbose_name = '输出财务报表_YTD'
        verbose_name_plural = '输出财务报表_YTD'


# 英文表名 → 输出物理结果表 Model（与 table_names.OUTPUT_TABLE_DEFS 对应；
# 同时供数据字典读取真实字段结构使用）
OUTPUT_TABLE_MODELS = {
    'paa_new_business_organized': OutputPaaNewBusinessOrganized,
    'paa_existing_business_organized': OutputPaaExistingBusinessOrganized,
    'paa_summary': OutputPaaSummary,
    'paa_mtd': OutputPaaMtd,
    'financial_statement_mtd': OutputFinancialStatementMtd,
    'financial_statement_ytd': OutputFinancialStatementYtd,
}


# ============================================================
# 输入数据物理表（35 张，与数据字典英文表名一一对应）
# 每张表存储一个输入工作表的行级数据，文本维度列与月度/度量列均为独立真实列，
# 不再以 ifrs17_sheet_data 的 rows(JSON) 形式集中存储。
# 列结构来源于 data_input/input_table_schema.py（由当前活跃上传数据生成，静态快照）。
# ============================================================

try:
    from data_input.input_table_schema import INPUT_TABLE_SCHEMA as _INPUT_SCHEMA
except Exception:  # pragma: no cover - 生成脚本未跑时降级为空
    _INPUT_SCHEMA = {}


class _InputSheetBase(models.Model):
    """输入物理表公共抽象基类。

    - source: 数据来源（excel / dock），便于按来源隔离激活行；
    - upload_record: 关联上传记录（数据血缘）；
    - is_active: 仅最新一次上传的该来源行标记为活跃（旧上传行置否）；
    - row_idx: 原 Excel 数据行序号；
    - created_at: 落库时间。
    """

    source = models.CharField('数据来源', max_length=10)
    upload_record = models.ForeignKey(
        UploadRecord, on_delete=models.CASCADE,
        verbose_name='所属上传记录'
    )
    is_active = models.BooleanField('当前有效', default=True)
    row_idx = models.IntegerField('行序号', default=0)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['source', 'is_active']),
            models.Index(fields=['upload_record']),
        ]


def _input_class_name(en: str) -> str:
    parts = [p for p in en.split('_') if p]
    return 'Input' + ''.join(p[:1].upper() + p[1:] for p in parts) if parts else 'InputX'


# 动态构建 35 张输入物理表并注册到 INPUT_TABLE_MODELS（cn -> Model）
INPUT_TABLE_MODELS = {}

for _cn, _s in _INPUT_SCHEMA.items():
    _en = _s.get('en') or _cn
    _attrs = {
        '__module__': __name__,
        'Meta': type('Meta', (object,), {
            'db_table': _en,
            'verbose_name': _cn,
            'verbose_name_plural': _cn,
            'app_label': 'data_input',
            'indexes': [
                models.Index(fields=['source', 'is_active']),
                models.Index(fields=['upload_record', 'row_idx']),
            ],
        }),
    }
    for _c in _s.get('columns', []):
        _fname = _c['name']
        _vname = _c.get('cn') or _fname
        if _c['type'] == 'decimal':
            _attrs[_fname] = models.DecimalField(
                _vname, max_digits=38, decimal_places=10, null=True, blank=True
            )
        else:
            _attrs[_fname] = models.CharField(
                _vname, max_length=512, null=True, blank=True
            )
    _cls = type(_input_class_name(_en), (_InputSheetBase,), _attrs)
    INPUT_TABLE_MODELS[_cn] = _cls
