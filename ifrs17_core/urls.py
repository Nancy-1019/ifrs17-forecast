"""IFRS17 预测模型系统 - 根 URL 路由"""
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('data_input.urls')),
]
