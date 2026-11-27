# 汇桥 OS (HuiQiao OS) v1.0.0 — Windows 本地离线一键体检与工作台启动脚本
param(
    [int]$Port = 8765,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "=== 汇桥 OS (HuiQiao OS) v1.0.0 本地离线自检 ===" -ForegroundColor Cyan
python -m apps.cli.main status

if ($CheckOnly) {
    Write-Host "=== 自检通过 (CheckOnly 模式已完成) ===" -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "正在启动本地零外部依赖工作台: http://127.0.0.1:$Port （仅本机回环访问，按 Ctrl+C 停止）" -ForegroundColor Green
python -m apps.cli.main serve --host 127.0.0.1 --port $Port
