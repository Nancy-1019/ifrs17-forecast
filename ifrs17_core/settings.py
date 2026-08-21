"""IFRS17 预测模型系统 - Django 核心配置"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'ifrs17-django-secret-key-change-in-production-2026'

DEBUG = True

APPEND_SLASH = False

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'data_input',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'ifrs17_core.middleware.NoCacheHTMLMiddleware',
]

ROOT_URLCONF = 'ifrs17_core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.csrf',
                'ifrs17_core.context_processors.system_config',
            ],
        },
    },
]

WSGI_APPLICATION = 'ifrs17_core.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 6}},
]

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# CSRF 信任源 — Django 4.0+ 必须配置，否则通过 IP 访问时 POST 请求被 403 拒绝
# 默认允许 HTTP/HTTPS 所有源，生产环境可通过环境变量收紧
CSRF_TRUSTED_ORIGINS = ['http://*', 'https://*']

SYSTEM_VERSION = 'v5.9.92'
BUILD_DATE = '2026-08-19'

DATA_DIR = BASE_DIR / 'data_fixtures'

# ============================================================
# 文件上传配置
# ============================================================
# 上传接口采用 raw body (application/octet-stream) 方式，
# 完全绕过 Django multipart parser，无需 monkey-patch。
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024   # 50MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024    # 50MB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000             # 允许大量字段
DATA_UPLOAD_MAX_NUMBER_FILES = 100                # 允许批量文件
