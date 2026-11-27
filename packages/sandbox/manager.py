"""M08 (B07) 分级本地安全沙箱统一管理器（实现 SandboxProtocol，支持三档热插拔与 GovernanceGuard 联动）."""

from __future__ import annotations

import pathlib
from typing import Any

from packages.core.contracts import PolicyDecision, SandboxTier
from packages.governance.guard import GovernanceGuard
from packages.governance.hooks import HookPoint
from packages.sandbox.models import (
    SandboxAdapterProtocol,
    SandboxLimits,
    SandboxRequest,
    SandboxResult,
)
from packages.sandbox.security import validate_workspace_path
from packages.sandbox.t1_light import T1WasmLightSandbox
from packages.sandbox.t2_os import T2OsRestrictedSandbox
from packages.sandbox.t3_container import T3ContainerSandbox


class SandboxManager:
    """B07 分级本地安全沙箱总控器（完整实现 SandboxProtocol 与 BrickProtocol）。

    核心安全铁律：
      1. 严格 Fail-Closed：默认 `offline_only=True`，拒绝 `SandboxTier.NONE` 裸奔；
      2. 绝不静默降级：`T3` 守护进程未运行且未显式指定安全降级目标时直接阻断；
      3. 治理钩子联动：若挂载 `GovernanceGuard`，执行前自动过 `PreToolUse` 安全门禁；
      4. 乐高热插拔：支持通过 `register_adapter()` / `swap_adapter()` 运行时替换任意层级引擎。
    """

    def __init__(
        self,
        *,
        default_tier: SandboxTier = SandboxTier.T2_OS_RESTRICTED,
        offline_only: bool = True,
        allowed_roots: tuple[str | pathlib.Path, ...] = (),
        governance_guard: GovernanceGuard | None = None,
        adapters: dict[SandboxTier, SandboxAdapterProtocol] | None = None,
    ) -> None:
        if default_tier == SandboxTier.NONE:
            raise ValueError("SandboxManager forbids SandboxTier.NONE as default_tier (fail-closed).")
        self.default_tier = default_tier
        self.offline_only = offline_only
        self.allowed_roots = allowed_roots
        self.governance_guard = governance_guard

        self._adapters: dict[SandboxTier, SandboxAdapterProtocol] = {
            SandboxTier.T1_WASM: T1WasmLightSandbox(),
            SandboxTier.T2_OS_RESTRICTED: T2OsRestrictedSandbox(allowed_roots=allowed_roots),
            SandboxTier.T3_ISOLATED_VM: T3ContainerSandbox(
                offline_only=offline_only,
                allowed_roots=allowed_roots,
            ),
        }
        if adapters:
            for tier, adapter in adapters.items():
                self.register_adapter(tier, adapter)

    def register_adapter(self, tier: SandboxTier, adapter: SandboxAdapterProtocol) -> None:
        if tier == SandboxTier.NONE:
            raise ValueError("Cannot register an unsandboxed SandboxTier.NONE adapter.")
        if not isinstance(adapter, SandboxAdapterProtocol):
            raise TypeError(f"Adapter {adapter!r} does not satisfy SandboxAdapterProtocol.")
        self._adapters[tier] = adapter

    def swap_adapter(self, tier: SandboxTier, adapter: SandboxAdapterProtocol) -> SandboxAdapterProtocol | None:
        """热插拔替换指定层级的沙箱后端，返回旧适配器。"""
        previous = self._adapters.get(tier)
        self.register_adapter(tier, adapter)
        return previous

    def get_adapter(self, tier: SandboxTier) -> SandboxAdapterProtocol | None:
        return self._adapters.get(tier)

    def tier_health(self) -> dict[str, bool]:
        return {tier.value: adapter.healthcheck() for tier, adapter in self._adapters.items()}

    def healthcheck(self) -> bool:
        """T1 与 T2 本地零依赖核心沙箱均健康即视为沙箱积木健康（T3 容器按需探活）。"""
        t1 = self._adapters.get(SandboxTier.T1_WASM)
        t2 = self._adapters.get(SandboxTier.T2_OS_RESTRICTED)
        return bool(t1 and t1.healthcheck() and t2 and t2.healthcheck())

    def run(self, request: SandboxRequest) -> SandboxResult:
        """执行结构化沙箱请求，返回强类型 SandboxResult。"""
        # 1. 硬拒绝 NONE 裸奔执行
        if request.tier == SandboxTier.NONE:
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=SandboxTier.NONE,
                exit_code=126,
                blocked=True,
                blocked_reason="UNSANDBOXED_TIER_FORBIDDEN",
                stderr="安全红线：禁止使用 SandboxTier.NONE 绕过沙箱执行代码。",
                backend="sandbox-manager",
            )

        # 2. 全局离线红线
        if self.offline_only and request.limits.allow_network:
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=request.tier,
                exit_code=126,
                blocked=True,
                blocked_reason="OFFLINE_NETWORK_BLOCKED",
                stderr="全局离线守卫（offline_only=True）拦截：沙箱禁止开启外网访问。",
                backend="sandbox-manager",
            )

        # 3. 工作区路径安全校验（防敏感目录挂载与路径穿越）
        ok_ws, err_ws, _ = validate_workspace_path(
            request.workspace_dir,
            allowed_roots=self.allowed_roots,
        )
        if not ok_ws:
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=request.tier,
                exit_code=126,
                blocked=True,
                blocked_reason=err_ws,
                stderr=f"工作区路径安全门禁拦截：{err_ws}",
                backend="sandbox-manager",
            )

        # 4. 联动 M04 GovernanceGuard 确定性生命周期守卫（若有挂载）
        if self.governance_guard is not None:
            ctx: dict[str, Any] = {
                "work_mode": request.work_mode,
                "permission": "READ" if request.limits.read_only_workspace and request.tier == SandboxTier.T1_WASM else "EXECUTE",
                "offline_only": self.offline_only,
                "allow_network": request.limits.allow_network,
                "target_path": request.workspace_dir,
                "allowed_paths": [request.workspace_dir] if request.workspace_dir else [],
            }
            verdict = self.governance_guard.evaluate(HookPoint.PRE_TOOL_USE, ctx)
            if verdict.decision != PolicyDecision.ALLOW:
                return SandboxResult(
                    ok=False,
                    tier_requested=request.tier,
                    tier_used=request.tier,
                    exit_code=126,
                    blocked=True,
                    blocked_reason=f"GOVERNANCE_{verdict.decision.value}:{verdict.reason}",
                    stderr=f"治理守卫拦截：{verdict.reason}",
                    backend="sandbox-manager",
                )

        # 5. 分发至对应层级适配器
        adapter = self._adapters.get(request.tier)
        if adapter is None:
            return SandboxResult(
                ok=False,
                tier_requested=request.tier,
                tier_used=request.tier,
                exit_code=126,
                blocked=True,
                blocked_reason=f"ADAPTER_NOT_REGISTERED:{request.tier.value}",
                stderr=f"未注册沙箱层级适配器：{request.tier.value}",
                backend="sandbox-manager",
            )

        result = adapter.execute_request(request)

        # 6. 仅当调用方显式指定了受控沙箱降级目标（绝不允许 NONE）且因 T3 守护进程离线受阻时才可控降级
        if (
            not result.ok
            and result.blocked_reason == "T3_DAEMON_UNAVAILABLE"
            and request.fallback_tier is not None
            and request.fallback_tier not in (SandboxTier.NONE, request.tier)
        ):
            fb_adapter = self._adapters.get(request.fallback_tier)
            if fb_adapter is not None:
                fb_req = request.model_copy(update={"tier": request.fallback_tier})
                fb_res = fb_adapter.execute_request(fb_req)
                return fb_res.model_copy(
                    update={
                        "tier_requested": request.tier,
                        "metadata": {
                            **fb_res.metadata,
                            "fallback_from": request.tier.value,
                            "fallback_reason": "T3_DAEMON_UNAVAILABLE",
                        },
                    }
                )

        return result

    def execute(
        self,
        code: str,
        *,
        language: str = "python",
        timeout_sec: int = 30,
        allow_network: bool = False,
        workspace_dir: str | None = None,
        tier: SandboxTier | str | None = None,
        max_memory_mb: int = 256,
        max_output_bytes: int = 65_536,
        read_only_workspace: bool = False,
        dry_run: bool = False,
        env_vars: dict[str, str] | None = None,
        fallback_tier: SandboxTier | str | None = None,
        work_mode: str = "execute",
    ) -> dict[str, Any]:
        """完全兼容 packages.core.interfaces.SandboxProtocol 的标准调用入口。"""
        resolved_tier = self.default_tier
        if tier is not None:
            resolved_tier = tier if isinstance(tier, SandboxTier) else SandboxTier(str(tier))

        resolved_fb: SandboxTier | None = None
        if fallback_tier is not None:
            resolved_fb = (
                fallback_tier
                if isinstance(fallback_tier, SandboxTier)
                else SandboxTier(str(fallback_tier))
            )

        req = SandboxRequest(
            code=code,
            language=language,
            tier=resolved_tier,
            workspace_dir=workspace_dir,
            limits=SandboxLimits(
                timeout_sec=float(timeout_sec),
                max_memory_mb=max_memory_mb,
                max_output_bytes=max_output_bytes,
                allow_network=allow_network,
                read_only_workspace=read_only_workspace,
            ),
            env_vars=env_vars or {},
            dry_run=dry_run,
            fallback_tier=resolved_fb,
            work_mode=work_mode,
        )
        return self.run(req).model_dump(mode="json")
