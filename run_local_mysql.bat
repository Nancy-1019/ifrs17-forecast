@echo off
REM 本地 IFRS17 系统（MySQL 8.0 模式）一键启动
REM 前提：D:\mysql-8.0.28-winx64 已解压并初始化（首次由 WorkBuddy 完成）
cd /d D:\IFRS17预测模型\ifrs17-system

REM 若 MySQL 未运行则启动（前台窗口会一直开着，关掉即停库）
tasklist | findstr /i mysqld >nul 2>&1
if errorlevel 1 (
  start "MySQL80" "D:\mysql-8.0.28-winx64\bin\mysqld.exe" --defaults-file="D:\mysql-8.0.28-winx64\my.ini"
  timeout /t 6 >nul
)

set DJANGO_SETTINGS_MODULE=ifrs17_core.settings_local_mysql
"C:\Users\王宗彦\.workbuddy\binaries\python\envs\default\Scripts\python.exe" manage.py runserver 127.0.0.1:8000 --noreload
