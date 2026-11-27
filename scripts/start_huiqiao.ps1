# 汇桥 OS (HuiQiao OS) v1.0.0 — Windows 本地离线一键体检与工作台启动脚本
param(
    [int]$Port = 8765,
    [switch]$CheckOnly,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# 若本机安装了 Ollama 且 11434 尚未监听，自动在后台静默拉起本地推理引擎
if (-not $CheckOnly -and (Get-Command ollama -ErrorAction SilentlyContinue)) {
    $ollamaUp = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue
    if (-not $ollamaUp) {
        Write-Host "正在自动唤醒本机 Ollama 显卡推理服务 (127.0.0.1:11434)..." -ForegroundColor DarkYellow
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Milliseconds 1800
    }
}

Write-Host "=== 汇桥 OS (HuiQiao OS) v1.0.0 本地离线自检 ===" -ForegroundColor Yellow
python -m apps.cli.main status

if ($CheckOnly) {
    Write-Host "=== 自检通过 (CheckOnly 模式已完成) ===" -ForegroundColor Green
    exit 0
}

if (-not $NoBrowser) {
    Start-Job -ScriptBlock {
        param($TargetUrl)
        Start-Sleep -Milliseconds 1500
        Start-Process $TargetUrl
    } -ArgumentList "http://127.0.0.1:$Port" | Out-Null
}

Write-Host ""
Write-Host "正在启动觉悟赛博黑金工作台: http://127.0.0.1:$Port （仅本机回环访问，按 Ctrl+C 停止）" -ForegroundColor Yellow
python -m apps.cli.main serve --host 127.0.0.1 --port $Port
