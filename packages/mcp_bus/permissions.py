"""工具权限分级：Read / Write / Execute。

C00 挂钩：Ask 模式物理拦截一切写删执行；最小权限由声明决定，不由模型临时起意。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from packages.core.errors import HuiQiaoError


class Permission(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    EXECUTE = "EXECUTE"


class PermissionDenied(HuiQiaoError):
    code = "HQ301"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    permission: Permission
    input_schema: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()

    def estimated_tokens(self) -> int:
        """粗估工具 schema 的 token 占用（中文按字、英文按 4 字符/token 保守估）。"""
        text = f"{self.name} {self.description} {self.input_schema}"
        cn = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        other = len(text) - cn
        return cn + other // 4


class PermissionGuard:
    """按模式与白名单拦截工具调用。纯确定性代码，不经过模型。"""

    def __init__(self, mode: str = "Ask", allowed_paths: tuple[str, ...] = ()) -> None:
        if mode not in {"Ask", "Plan", "Execute"}:
            raise ValueError(f"非法模式: {mode}")
        self.mode = mode
        self.allowed_paths = allowed_paths

    def check(self, tool: ToolSpec, params: dict[str, Any] | None = None) -> None:
        params = params or {}
        if self.mode == "Ask" and tool.permission != Permission.READ:
            raise PermissionDenied(f"Ask 模式禁止 {tool.permission.value} 工具: {tool.name}")
        if self.mode == "Plan" and tool.permission == Permission.EXECUTE:
            raise PermissionDenied(f"Plan 模式禁止 EXECUTE 工具: {tool.name}")
        path = params.get("path")
        if path and self.allowed_paths and not any(str(path).startswith(p) for p in self.allowed_paths):
            raise PermissionDenied(f"路径越出白名单: {path}")
