"""
Django管理命令: 初始化系统数据
从JSON fixtures加载预置数据到数据库，创建默认用户和权限组。

用法:
    python manage.py init_data
    python manage.py init_data --skip-auth   # 跳过用户创建
"""
import json
import os
from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from django.db import transaction
from data_input.models import UploadRecord, SheetData, DataWorksSyncLog
from data_input.permissions import setup_permission_groups
from data_input.permissions import (
    GROUP_UPLOADER, GROUP_REVIEWER, GROUP_VIEWER, GROUP_ADMIN
)


class Command(BaseCommand):
    help = '初始化IFRS17系统数据：创建权限组、默认用户、加载预置工作表数据'

    def add_arguments(self, parser):
        parser.add_argument('--skip-auth', action='store_true', help='跳过用户和权限组创建')
        parser.add_argument('--with-data', action='store_true', help='加载预置演示数据（默认不加载）')
        parser.add_argument('--admin-password', type=str, default='admin123',
                            help='管理员密码 (默认: admin123)')
        parser.add_argument('--uploader-password', type=str, default='upload123',
                            help='上传者密码 (默认: upload123)')
        parser.add_argument('--viewer-password', type=str, default='viewer123',
                            help='查看者密码 (默认: viewer123)')

    def handle(self, *args, **options):
        if not options['skip_auth']:
            self.setup_auth(options)

        if options['with_data']:
            self.load_initial_data()
        else:
            self.stdout.write(self.style.WARNING('跳过预置数据加载（默认行为）。如需加载演示数据，请使用 --with-data 参数。'))

        self.stdout.write(self.style.SUCCESS('数据初始化完成！'))
        self.stdout.write('')
        self.stdout.write('默认账户:')
        self.stdout.write(f'  管理员: admin / {options["admin_password"]}  (admin/uploader/viewer权限)')
        self.stdout.write(f'  上传者: uploader / {options["uploader_password"]}  (uploader权限)')
        self.stdout.write(f'  查看者: viewer / {options["viewer_password"]}  (viewer权限)')
        self.stdout.write('')
        self.stdout.write('访问管理后台: http://localhost:8000/admin/')
        self.stdout.write('访问系统主页: http://localhost:8000/')

    def setup_auth(self, options):
        """创建权限组和默认用户"""
        self.stdout.write('创建权限组...')
        setup_permission_groups()
        self.stdout.write(self.style.SUCCESS('权限组创建完成'))

        self.stdout.write('创建默认用户...')

        # 管理员 (超级用户 + 所有组)
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={'is_staff': True, 'is_superuser': True}
        )
        if created:
            admin.set_password(options['admin_password'])
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()
        for name in [GROUP_UPLOADER, GROUP_REVIEWER, GROUP_VIEWER, GROUP_ADMIN]:
            group = Group.objects.get(name=name)
            admin.groups.add(group)
        self.stdout.write(f'  {"创建" if created else "已存在"}: admin (管理员)')

        # 数据上传者
        uploader, created = User.objects.get_or_create(username='uploader')
        if created:
            uploader.set_password(options['uploader_password'])
        uploader.is_staff = False
        uploader.is_superuser = False
        uploader.save()
        uploader.groups.clear()
        uploader.groups.add(Group.objects.get(name=GROUP_UPLOADER))
        self.stdout.write(f'  {"创建" if created else "已存在"}: uploader (数据上传者)')

        # 数据查看者
        viewer, created = User.objects.get_or_create(username='viewer')
        if created:
            viewer.set_password(options['viewer_password'])
        viewer.is_staff = False
        viewer.is_superuser = False
        viewer.save()
        viewer.groups.clear()
        viewer.groups.add(Group.objects.get(name=GROUP_VIEWER))
        self.stdout.write(f'  {"创建" if created else "已存在"}: viewer (数据查看者)')

    @transaction.atomic
    def load_initial_data(self):
        """从JSON fixtures加载预置数据"""
        self.stdout.write('加载预置数据...')
        data_dir = settings.DATA_DIR

        for source, filename in [('excel', 'excel_upload_data.json'), ('dock', 'system_dock_data.json')]:
            filepath = data_dir / filename
            if not filepath.exists():
                self.stdout.write(self.style.WARNING(f'数据文件不存在: {filepath}'))
                continue

            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not data:
                continue

            # 创建系统初始化上传记录
            record = UploadRecord.objects.create(
                source=source,
                file_name=f'系统初始化数据 ({filename})',
                sheet_count=len(data),
                total_rows=sum(len(v.get('rows', [])) for v in data.values()),
                validation_passed=True,
                status='approved',
            )
            DataWorksSyncLog.objects.create(upload_record=record, sync_status='pending')

            for sheet_name, sheet_info in data.items():
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
                    upload_record=record,
                    is_active=True,
                )

            sheet_count = len(data)
            total_rows = record.total_rows
            self.stdout.write(self.style.SUCCESS(
                f'  {source}: 加载 {sheet_count} 个工作表, {total_rows} 行数据'
            ))
