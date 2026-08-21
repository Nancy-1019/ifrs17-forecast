"""IFRS17 数据输入 - 自定义权限"""
from django.contrib.auth.models import Permission, Group
from django.contrib.contenttypes.models import ContentType
from data_input.models import UploadRecord


# 权限组名称
GROUP_UPLOADER = '数据上传者'
GROUP_REVIEWER = '数据审核者'
GROUP_VIEWER = '数据查看者'
GROUP_ADMIN = '系统管理员'


def setup_permission_groups():
    """创建默认权限组（在migration或数据迁移中调用）"""
    content_type = ContentType.objects.get_for_model(UploadRecord)

    groups_config = {
        GROUP_UPLOADER: {
            'permissions': ['can_upload'],
            'description': '可以上传Excel数据文件'
        },
        GROUP_REVIEWER: {
            'permissions': ['can_upload', 'can_review'],
            'description': '可以上传并审核数据'
        },
        GROUP_VIEWER: {
            'permissions': ['can_view_all'],
            'description': '可以查看所有数据，但不能上传'
        },
        GROUP_ADMIN: {
            'permissions': ['can_upload', 'can_review', 'can_view_all'],
            'description': '系统管理员，拥有全部权限'
        },
    }

    created_groups = {}
    for group_name, config in groups_config.items():
        group, created = Group.objects.get_or_create(name=group_name)
        if created:
            group.user_set.clear()
        for perm_codename in config['permissions']:
            perm = Permission.objects.get(
                content_type=content_type,
                codename=perm_codename
            )
            group.permissions.add(perm)
        created_groups[group_name] = {'group': group, 'created': created}

    return created_groups
