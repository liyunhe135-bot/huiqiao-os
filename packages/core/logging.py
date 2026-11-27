"""M00 统一日志：结构化、可审计、离线可用。"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Any


def emit(event_type: str, actor: str, payload: dict[str, Any] | None = None) -> None:
    """输出一条结构化 JSON 日志到 stderr（不污染 stdout 数据通道）。"""
    record = {
        "ts": datetime.now().isoformat(),
        "event_type": event_type,
        "actor": actor,
        "payload": payload or {},
    }
    sys.stderr.write(json.dumps(record, ensure_ascii=False) + "\n")
