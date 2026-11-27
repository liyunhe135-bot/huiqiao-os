"""汇桥 OS 统一错误码与异常体系（M00 Core）."""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """全局标准化错误码，便于观测追踪与上层优雅降级。"""

    CONTRACT_VIOLATION = "HQ_CONTRACT_VIOLATION"
    BRICK_NOT_FOUND = "HQ_BRICK_NOT_FOUND"
    BRICK_LOAD_FAILED = "HQ_BRICK_LOAD_FAILED"
    BRICK_CONTRACT_MISMATCH = "HQ_BRICK_CONTRACT_MISMATCH"
    BRICK_UNHEALTHY = "HQ_BRICK_UNHEALTHY"
    CONSTITUTION_MISSING = "HQ_CONSTITUTION_MISSING"
    CONSTITUTION_REJECTED = "HQ_CONSTITUTION_REJECTED"
    CAPABILITY_BOUNDARY_EXCEEDED = "HQ_CAPABILITY_BOUNDARY_EXCEEDED"
    POLICY_DENIED = "HQ_POLICY_DENIED"
    OFFLINE_NETWORK_BLOCKED = "HQ_OFFLINE_NETWORK_BLOCKED"


class HuiQiaoError(Exception):
    """汇桥 OS 统一基础异常。"""

    def __init__(
        self,
        code: ErrorCode | str,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        # 兼容两种调用：HuiQiaoError(code, message) 与 HuiQiaoError("message")
        if message is None:
            message = str(code)
            code = ErrorCode.CONTRACT_VIOLATION
        if not isinstance(code, ErrorCode):
            code = ErrorCode.CONTRACT_VIOLATION
        super().__init__(f"[{code.value}] {message}")
        self.code = code
        self.message = message
        self.details = details or {}


class ContractViolationError(HuiQiaoError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.CONTRACT_VIOLATION, message, details)


class BrickRegistryError(HuiQiaoError):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code, message, details)


class ConstitutionError(HuiQiaoError):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code, message, details)


# --- 兼容别名（2026-11-27 M03）---
# 背景：M00 的 registry/contracts 与另一版错误体系并存。
# 保留上面的 ErrorCode 枚举不动，这里补回被调用方引用的符号，避免破坏任一版本。


class ContractError(HuiQiaoError):
    """数据契约校验失败（兼容 M00 接口）。"""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.CONTRACT_VIOLATION, message, details)


class BrickNotFoundError(HuiQiaoError):
    """积木未注册或 impl 不可导入（兼容 M00 接口）。"""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.BRICK_NOT_FOUND, message, details)


class ConstitutionViolation(HuiQiaoError):
    """C00 增上四问一票否决（兼容 M00 接口）。"""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.CONSTITUTION_REJECTED, message, details)


class CapabilityExceeded(HuiQiaoError):
    """超出本机实测能力边界（兼容 M00 接口）。"""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.CAPABILITY_BOUNDARY_EXCEEDED, message, details)
