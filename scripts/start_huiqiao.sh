#!/usr/bin/env bash
# 汇桥 OS (HuiQiao OS) v1.0.0 — Linux / macOS 本地离线一键体检与工作台启动脚本
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PORT="${1:-8765}"

echo "=== 汇桥 OS (HuiQiao OS) v1.0.0 本地离线自检 ==="
python3 -m apps.cli.main status

echo ""
echo "正在启动本地零外部依赖工作台: http://127.0.0.1:${PORT} （仅本机回环访问，按 Ctrl+C 停止）"
exec python3 -m apps.cli.main serve --host 127.0.0.1 --port "${PORT}"
