"""只读硬件画像采集：不执行命令、不联网、不改动系统。"""

from __future__ import annotations

import os
import platform
from typing import Any


def collect_hardware() -> dict[str, Any]:
    """采集 OS / CPU / 内存等基础信息。

    设计取舍：只用标准库能读到的，不调 wmic/nvidia-smi 等外部命令——
    M02 阶段保持纯离线可测。GPU 显存留到用户允许实测时再补。
    """
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "arch": platform.machine(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "gpu": {"status": "未采集", "reason": "需用户允许拉起服务后实测"},
    }
