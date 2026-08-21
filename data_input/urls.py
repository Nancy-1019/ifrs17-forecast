"""IFRS17 数据输入 - URL路由"""
from django.urls import path
from . import views

urlpatterns = [
    # 认证
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # 主页面
    path('', views.index, name='index'),

    # API: 版本信息
    path('api/version', views.api_version, name='api_version'),

    # API: 结果展示面板快照
    path('api/dashboard/snapshot', views.api_dashboard_snapshot, name='api_dashboard_snapshot'),

    # API: 数据查询
    path('api/data/<str:source>', views.api_data, name='api_data'),

    # API: 上传（数据落库）
    # 注意：所有 /api/upload/xxx 具体路径必须在 /api/upload/<str:source> 之前定义
    path('api/upload/verify', views.api_upload_verify, name='api_upload_verify'),
    path('api/upload/actual', views.api_upload_actual, name='api_upload_actual'),
    path('api/upload/old-standard', views.api_upload_old_standard, name='api_upload_old_standard'),
    path('api/upload/<str:source>', views.api_upload, name='api_upload'),

    # API: 上传历史
    path('api/upload-history/', views.api_upload_history, name='api_upload_history'),

    # API: Excel下载
    path('api/download/<str:source>', views.api_download_all, name='api_download_all'),
    path('api/download/<str:source>/<str:sheet_name>', views.api_download_sheet, name='api_download_sheet'),

    # API: 验证数据查询
    path('api/verify/data', views.api_verify_data, name='api_verify_data'),

    # API: 验证核对展示与导出
    path('api/verify/full', views.api_verify_full, name='api_verify_full'),
    path('api/verify/compare', views.api_verify_compare, name='api_verify_compare'),
    path('api/verify/merged/<str:sheet_name>', views.api_verify_merged, name='api_verify_merged'),
    path('api/verify/export/sheet/<str:sheet_name>', views.api_verify_export_sheet, name='api_verify_export_sheet'),
    path('api/verify/export/all', views.api_verify_export_all, name='api_verify_export_all'),

    # API: 计量结果输出导出
    path('api/output/export', views.api_output_export, name='api_output_export'),

    # API: 通用表格导出为 Excel（前端传入当前展示的表头/数据）
    path('api/export/table-xlsx', views.api_export_table_xlsx, name='api_export_table_xlsx'),

    # API: PAA计算
    path('api/calc/scenarios', views.api_calc_scenarios, name='api_calc_scenarios'),
    path('api/calc/run', views.api_calc_run, name='api_calc_run'),
    path('api/calc/progress', views.api_calc_progress, name='api_calc_progress'),
    path('api/calc/results', views.api_calc_results, name='api_calc_results'),
    path('api/calc/results/all', views.api_calc_results_all, name='api_calc_results_all'),
    path('api/calc/input-org', views.api_calc_input_org, name='api_calc_input_org'),
    path('api/calc/verify-output', views.api_calc_verify_output, name='api_calc_verify_output'),

    # API: 预实对比
    path('api/actual/compare', views.api_actual_compare, name='api_actual_compare'),

    # API: 新旧准则利润表桥接比对
    path('api/bridge/comparison', views.api_bridge_comparison, name='api_bridge_comparison'),

    # API: 数据及逻辑归集 - 计算逻辑概要
    path('api/logic/outline', views.api_logic_outline, name='api_logic_outline'),

    # API: 部署管理
    path('api/deploy/config', views.api_deploy_config, name='api_deploy_config'),
    path('api/deploy/test', views.api_deploy_test, name='api_deploy_test'),
    path('api/deploy/push', views.api_deploy_push, name='api_deploy_push'),

    # API: 系统运行日志 & SQL查询 & 计算版本入库
    path('api/system/log', views.api_system_log, name='api_system_log'),
    path('api/system/sql-query', views.api_system_sql_query, name='api_system_sql_query'),
    path('api/system/table-dict', views.api_system_table_dict, name='api_system_table_dict'),
    path('api/calc/versions', views.api_calc_versions, name='api_calc_versions'),
    path('api/calc/push-version', views.api_calc_push_version, name='api_calc_push_version'),
    path('api/calc/push-version-status', views.api_calc_push_version_status, name='api_calc_push_version_status'),
]
