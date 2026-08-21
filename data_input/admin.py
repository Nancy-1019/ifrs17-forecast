"""IFRS17 数据输入 - Django 管理后台配置"""
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
from .models import UploadRecord, SheetData, DataWorksSyncLog


class SheetDataInline(admin.TabularInline):
    model = SheetData
    fields = ('sheet_name', 'row_count', 'is_active')
    readonly_fields = ('sheet_name', 'row_count', 'is_active')
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(UploadRecord)
class UploadRecordAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'source_badge', 'file_name', 'upload_user', 'upload_time',
        'sheet_count', 'total_rows', 'validation_status', 'review_status',
        'dw_sync_badge', 'actions_column'
    ]
    list_filter = [
        'source', 'status', 'validation_passed', 'dw_sync_status', 'upload_time'
    ]
    search_fields = ['file_name', 'upload_user__username', 'review_notes']
    readonly_fields = [
        'upload_time', 'sheet_count', 'total_rows', 'upload_user',
        'validation_errors', 'validation_warnings'
    ]
    date_hierarchy = 'upload_time'
    list_per_page = 30

    fieldsets = (
        ('基本信息', {
            'fields': ('source', 'file_name', 'upload_user', 'upload_time')
        }),
        ('上传统计', {
            'fields': ('sheet_count', 'total_rows')
        }),
        ('校验结果', {
            'fields': ('validation_passed', 'validation_errors', 'validation_warnings')
        }),
        ('审核信息', {
            'fields': ('status', 'reviewed_by', 'reviewed_at', 'review_notes')
        }),
        ('DataWorks同步', {
            'fields': ('dw_sync_status',)
        }),
    )

    inlines = [SheetDataInline]

    actions = ['approve_uploads', 'reject_uploads', 'mark_dw_pending']

    def source_badge(self, obj):
        colors = {'excel': '#3B82F6', 'dock': '#8B5CF6'}
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px">{}</span>',
            colors.get(obj.source, '#999'),
            obj.get_source_display()
        )
    source_badge.short_description = '来源'

    def validation_status(self, obj):
        if obj.validation_passed:
            return format_html('<span style="color:#10B981">✓ 通过</span>')
        return format_html('<span style="color:#EF4444">✗ 失败({})</span>', len(obj.validation_errors))
    validation_status.short_description = '校验'

    def review_status(self, obj):
        colors = {
            'pending': ('#F59E0B', '待审核'),
            'approved': ('#10B981', '已通过'),
            'rejected': ('#EF4444', '已驳回'),
        }
        c, label = colors.get(obj.status, ('#999', obj.status))
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>', c, label
        )
    review_status.short_description = '审核'

    def dw_sync_badge(self, obj):
        c_map = {'pending':'#9CA3AF','syncing':'#3B82F6','success':'#10B981','failed':'#EF4444'}
        l_map = {'pending':'待同步','syncing':'同步中','success':'已完成','failed':'失败'}
        return format_html(
            '<span style="color:{}">{}</span>',
            c_map.get(obj.dw_sync_status, '#999'),
            l_map.get(obj.dw_sync_status, obj.dw_sync_status)
        )
    dw_sync_badge.short_description = '同步'

    def actions_column(self, obj):
        return format_html(
            '<a class="button" href="{}">查看详情</a>',
            reverse('admin:data_input_uploadrecord_change', args=[obj.pk])
        )
    actions_column.short_description = '操作'

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.upload_user = request.user
        if 'status' in form.changed_data and obj.status in ('approved', 'rejected'):
            obj.reviewed_by = request.user
            obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)

    @admin.action(description='审核通过所选上传')
    def approve_uploads(self, request, queryset):
        updated = queryset.filter(status='pending').update(
            status='approved',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f'已通过 {updated} 条上传记录')

    @admin.action(description='驳回所选上传')
    def reject_uploads(self, request, queryset):
        updated = queryset.filter(status='pending').update(
            status='rejected',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f'已驳回 {updated} 条上传记录')

    @admin.action(description='标记为待同步DataWorks')
    def mark_dw_pending(self, request, queryset):
        updated = queryset.filter(
            status='approved', dw_sync_status__in=['failed', 'success']
        ).update(dw_sync_status='pending')
        self.message_user(request, f'已标记 {updated} 条记录为待同步')


@admin.register(SheetData)
class SheetDataAdmin(admin.ModelAdmin):
    list_display = ['sheet_name', 'source', 'row_count', 'is_active', 'upload_record_link', 'created_at']
    list_filter = ['source', 'is_active', 'created_at']
    search_fields = ['sheet_name']
    readonly_fields = ['source', 'sheet_name', 'row_count', 'created_at']
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def upload_record_link(self, obj):
        url = reverse('admin:data_input_uploadrecord_change', args=[obj.upload_record_id])
        return format_html('<a href="{}">#{}</a>', url, obj.upload_record_id)
    upload_record_link.short_description = '上传记录'


@admin.register(DataWorksSyncLog)
class DataWorksSyncLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'upload_record_link', 'sync_status_badge', 'table_name', 'retry_count', 'started_at', 'completed_at']
    list_filter = ['sync_status', 'created_at']
    readonly_fields = ['upload_record', 'created_at']
    list_per_page = 30

    def has_add_permission(self, request):
        return False

    def upload_record_link(self, obj):
        url = reverse('admin:data_input_uploadrecord_change', args=[obj.upload_record_id])
        return format_html('<a href="{}">#{}</a>', url, obj.upload_record_id)
    upload_record_link.short_description = '上传记录'

    def sync_status_badge(self, obj):
        c_map = {'pending':'#9CA3AF','syncing':'#3B82F6','success':'#10B981','failed':'#EF4444'}
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            c_map.get(obj.sync_status, '#999'),
            obj.get_sync_status_display()
        )
    sync_status_badge.short_description = '状态'


# 自定义Admin Site标题
admin.site.site_header = '新准则预测模型 - 管理后台'
admin.site.site_title = 'IFRS17 管理'
admin.site.index_title = '数据管理与审核'
