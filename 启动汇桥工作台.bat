@echo off
chcp 65001 >nul
title 汇桥 OS · 觉悟赛博本地共生工作台 (127.0.0.1:8765)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\start_huiqiao.ps1"
pause
