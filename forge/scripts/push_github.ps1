param(
    [string]$RemoteUrl = "",
    [string]$MirrorDir = ""
)
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $RepoRoot

Write-Host "=== 1. 运行全库回归测试 (Evidence Gate) ===" -ForegroundColor Cyan
python forge/scripts/forge_guard.py test tests/
if ($LASTEXITCODE -ne 0) {
    Write-Error "测试未通过，已中止备份（遵守 Evidence Gate 铁律）。"
    exit 1
}

if ($MirrorDir) {
    Write-Host "=== 2. 同步至本地 GitHub Desktop 备份镜像: $MirrorDir ===" -ForegroundColor Cyan
    git -C $MirrorDir fetch $RepoRoot main
    git -C $MirrorDir reset --hard FETCH_HEAD
    git -C $MirrorDir fetch $RepoRoot --tags --force
    Write-Host "=== 镜像同步完成！请在 GitHub Desktop 中点击 Publish / Push origin ===" -ForegroundColor Green
    exit 0
}

if (-not $RemoteUrl) {
    $RemoteUrl = git remote get-url origin 2>$null
}
if (-not $RemoteUrl) {
    Write-Error "请提供 -RemoteUrl 或 -MirrorDir 参数。"
    exit 1
}

Write-Host "=== 2. 绑定并推送至 GitHub 远端 ===" -ForegroundColor Cyan
$existing = git remote get-url origin 2>$null
if (-not $existing) {
    git remote add origin $RemoteUrl
} else {
    git remote set-url origin $RemoteUrl
}
git push -u origin main --tags
Write-Host "=== 备份完成：$RemoteUrl ===" -ForegroundColor Green
