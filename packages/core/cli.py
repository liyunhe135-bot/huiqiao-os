"""M00 体检 CLI：python -m packages.core.cli 打印积木合规体检报告。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .registry import BrickRegistry

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "bricks.yaml"


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    config = Path(args[0]) if args else DEFAULT_CONFIG
    try:
        reg = BrickRegistry.from_yaml(config)
        report = reg.health_report()
    except Exception as exc:  # noqa: BLE001
        print(f"体检失败: {exc}", file=sys.stderr)
        return 1

    print(f"汇桥 OS 积木体检（{config}）")
    print(f"  注册: {report['total']}  通过: {len(report['ok'])}  降级: {len(report['degraded'])}  失败: {len(report['failed'])}")
    for name in report["ok"]:
        print(f"  [OK] {name}")
    for name in report["degraded"]:
        print(f"  [FALLBACK] {name}")
    for item in report["failed"]:
        print(f"  [FAIL] {item['name']}: {item['error']}")
    return 0 if not report["failed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
