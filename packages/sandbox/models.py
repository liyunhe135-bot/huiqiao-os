"""M08 (B07) 分级本地安全沙箱数据契约与适配器协议."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from packages.core.contracts import BaseContract, SandboxTier


class SandboxLimits(BaseContract):
    """沙箱硬资源与边界限额（默认断网、防炸弹、防磁盘写爆）。"""

    timeout_sec: float = Field(default=15.0, gt=0.0, le=300.0)
    max_memory_mb: int = Field(default=256, ge=16, le=4096)
    max_output_bytes: int = Field(default=65_536, ge=1024, le=10_485_760)
    max_cpu_sec: float = Field(default=15.0, gt=0.0, le=300.0)
    max_pids: int = Field(default=16, ge=1, le=256)
    max_write_files: int = Field(default=32, ge=0, le=1024)
    max_write_bytes: int = Field(default=2_097_152, ge=0, le=104_857_600)
    allow_network: bool = Field(default=False)
    read_only_workspace: bool = Field(default=False)


class SandboxRequest(BaseContract):
    """提交给分级安全沙箱的标准执行请求。"""

    code: str = Field(..., min_length=1)
    language: str = Field(default="python")
    tier: SandboxTier = Field(default=SandboxTier.T2_OS_RESTRICTED)
    workspace_dir: str | None = Field(default=None)
    limits: SandboxLimits = Field(default_factory=SandboxLimits)
    env_vars: dict[str, str] = Field(default_factory=dict)
    dry_run: bool = Field(default=False)
    fallback_tier: SandboxTier | None = Field(default=None)
    trace_id: str | None = Field(default=None)
    work_mode: str = Field(default="execute")


class SandboxResult(BaseContract):
    """分级安全沙箱统一结构化执行结果（Fail-Closed 可审计）。"""

    ok: bool
    tier_requested: SandboxTier
    tier_used: SandboxTier
    exit_code: int
    stdout: str = Field(default="")
    stderr: str = Field(default="")
    output_truncated: bool = Field(default=False)
    timed_out: bool = Field(default=False)
    blocked: bool = Field(default=False)
    blocked_reason: str | None = Field(default=None)
    killed_reason: str | None = Field(default=None)
    elapsed_ms: float = Field(default=0.0, ge=0.0)
    artifacts: list[str] = Field(default_factory=list)
    command_preview: list[str] = Field(default_factory=list)
    backend: str = Field(default="")


@runtime_checkable
class SandboxAdapterProtocol(Protocol):
    """单个沙箱级别的可热插拔适配器协议。"""

    tier: SandboxTier
    backend_name: str

    def healthcheck(self) -> bool: ...

    def execute_request(self, request: SandboxRequest) -> SandboxResult: ...
