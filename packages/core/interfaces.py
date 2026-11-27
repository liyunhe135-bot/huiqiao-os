"""汇桥 OS 十大乐高积木标准协议接口（typing.Protocol，零强耦合鸭子类型）."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from packages.core.contracts import (
    CapabilityProfile,
    PolicyDecision,
    RouteDecision,
    StepInput,
    StepOutput,
    TaskEnvelope,
)


@runtime_checkable
class BrickProtocol(Protocol):
    """所有乐高积木的最小健康检查协议。"""

    def healthcheck(self) -> bool: ...


@runtime_checkable
class RouterProtocol(BrickProtocol, Protocol):
    """B02 二维五通道智能路由协议。"""

    def route(
        self,
        envelope: TaskEnvelope,
        profile: CapabilityProfile | None = None,
    ) -> RouteDecision: ...


@runtime_checkable
class LLMGatewayProtocol(BrickProtocol, Protocol):
    """B04 本地模型网关与显存调度协议。"""

    def complete(
        self,
        *,
        role: str,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any] | None = None,
        thinking_mode: str = "off",
        affinity_key: str | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]: ...


@runtime_checkable
class WorkerProtocol(BrickProtocol, Protocol):
    """B05 可插拔 Agent 执行内核协议。"""

    def run(self, step: StepInput) -> StepOutput: ...


@runtime_checkable
class SandboxProtocol(BrickProtocol, Protocol):
    """B07 分级本地安全沙箱协议。"""

    def execute(
        self,
        code: str,
        *,
        language: str = "python",
        timeout_sec: int = 30,
        allow_network: bool = False,
        workspace_dir: str | None = None,
    ) -> dict[str, Any]: ...


@runtime_checkable
class MemoryStoreProtocol(BrickProtocol, Protocol):
    """B08 分层本地记忆引擎协议。"""

    def recall(self, query: str, *, scope: str = "default", top_k: int = 5) -> list[dict[str, Any]]: ...

    def commit(self, record: dict[str, Any], *, scope: str = "default") -> str: ...


@runtime_checkable
class PolicyHookProtocol(BrickProtocol, Protocol):
    """B10 确定性生命周期钩子与策略守卫协议。"""

    def check(self, hook_point: str, context: dict[str, Any]) -> PolicyDecision: ...
