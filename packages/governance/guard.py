"""M04 统一安全守卫积木（GovernanceGuard）：实现 PolicyHookProtocol，可热插拔注册."""

from __future__ import annotations

import pathlib
from typing import Any
from urllib.parse import urlparse

import yaml

from packages.core.contracts import PolicyDecision, WorkMode
from packages.governance.evidence import (
    DEFAULT_SENSITIVE_KEYWORDS,
    EvidenceLedger,
    PathGuard,
    generate_unified_diff,
)
from packages.governance.hooks import HookFn, HookPipeline, HookPoint, HookVerdict

_WRITE_PERMISSIONS = {"WRITE", "DELETE", "EXECUTE", "NETWORK"}
_DEFAULT_HIGH_RISK = frozenset(
    {"delete", "rmtree", "overwrite_core", "pkg_install", "shell_destructive"}
)


def _normalize_mode(raw: Any) -> WorkMode:
    if isinstance(raw, WorkMode):
        return raw
    s = str(raw or "ask").strip().lower()
    return WorkMode(s)


def _normalize_permission(context: dict[str, Any]) -> str:
    tool = context.get("tool")
    if tool is not None and hasattr(tool, "permission"):
        perm = tool.permission
        return str(perm.value if hasattr(perm, "value") else perm).upper()
    return str(context.get("permission", "READ")).strip().upper()


class GovernanceGuard:
    """确定性安全治理守卫：纯代码零模型依赖，单次检查 < 1ms。

    内置五道确定性防线（均可在不破坏硬红线前提下追加自定义 Hook）：
      1. 离线网络硬拦截（offline_only=True 仅允许回环地址）；
      2. 敏感路径与路径穿越硬死锁（~/.ssh / .env / 系统目录 / .. 穿越）；
      3. WorkBuddy 三档心智模式硬锁（Ask 物理禁写 / Plan 必预审 / Execute 白名单受控）；
      4. 高危动作与 Claude 证据闸门（PreCommit 缺 test_passed 拦截；删除缺 human_approved 拦审）；
      5. 写操作自动附带 Unified Diff 预览，保障人类知情权（C00 A1）。
    """

    def __init__(
        self,
        *,
        offline_only: bool = True,
        loopback_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "::1"),
        allowed_roots: tuple[str | pathlib.Path, ...] = (),
        sensitive_keywords: tuple[str, ...] = DEFAULT_SENSITIVE_KEYWORDS,
        high_risk_actions: frozenset[str] = _DEFAULT_HIGH_RISK,
        commit_evidence_required: tuple[str, ...] = ("test_passed",),
        base_dir: pathlib.Path | None = None,
        evidence_ledger: EvidenceLedger | None = None,
    ) -> None:
        self.offline_only = offline_only
        self.loopback_hosts = {h.lower() for h in loopback_hosts}
        self.high_risk_actions = set(high_risk_actions)
        self.commit_evidence_required = commit_evidence_required
        self.path_guard = PathGuard(
            allowed_roots=allowed_roots,
            sensitive_keywords=sensitive_keywords,
            base_dir=base_dir,
        )
        self.evidence = evidence_ledger or EvidenceLedger()
        self.pipeline = HookPipeline()
        self._install_default_hooks()

    @classmethod
    def from_yaml(
        cls,
        yaml_path: pathlib.Path | str,
        *,
        base_dir: pathlib.Path | None = None,
        evidence_ledger: EvidenceLedger | None = None,
    ) -> GovernanceGuard:
        p = pathlib.Path(yaml_path)
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        gates = data.get("evidence_gates", {}) or {}
        commit_req = tuple(gates.get("PreCommit", {}).get("required", ["test_passed"]))
        return cls(
            offline_only=bool(data.get("offline_only", True)),
            loopback_hosts=tuple(data.get("loopback_hosts", ["127.0.0.1", "localhost", "::1"])),
            allowed_roots=tuple(data.get("default_allowed_paths", [])),
            sensitive_keywords=tuple(
                data.get("sensitive_path_keywords", DEFAULT_SENSITIVE_KEYWORDS)
            ),
            high_risk_actions=frozenset(data.get("high_risk_actions", _DEFAULT_HIGH_RISK)),
            commit_evidence_required=commit_req,
            base_dir=base_dir or p.resolve().parents[1],
            evidence_ledger=evidence_ledger,
        )

    def healthcheck(self) -> bool:
        return True

    def register_hook(
        self,
        name: str,
        points: set[HookPoint] | list[HookPoint] | tuple[HookPoint, ...],
        fn: HookFn,
        *,
        priority: int = 100,
    ) -> None:
        """允许按需扩展自定义生命周期钩子，默认优先级排在硬安全红线（priority < 50）之后。"""
        self.pipeline.register(name, points, fn, priority=priority)

    def _install_default_hooks(self) -> None:
        self.pipeline.register(
            "offline_network_wall",
            (HookPoint.PRE_TOOL_USE, HookPoint.PRE_ROUTE),
            self._hook_offline_network,
            priority=10,
        )
        self.pipeline.register(
            "sensitive_path_wall",
            (HookPoint.PRE_TOOL_USE, HookPoint.PRE_WRITE),
            self._hook_sensitive_and_whitelist_path,
            priority=20,
        )
        self.pipeline.register(
            "work_mode_guard",
            (HookPoint.PRE_TOOL_USE, HookPoint.PRE_WRITE),
            self._hook_work_mode,
            priority=30,
        )
        self.pipeline.register(
            "evidence_and_high_risk_gate",
            (HookPoint.PRE_TOOL_USE, HookPoint.PRE_WRITE, HookPoint.PRE_COMMIT),
            self._hook_evidence_gate,
            priority=40,
        )
        self.pipeline.register(
            "diff_preview_enricher",
            (HookPoint.PRE_WRITE,),
            self._hook_diff_preview,
            priority=45,
        )

    def _hook_offline_network(self, _point: HookPoint, ctx: dict[str, Any]) -> HookVerdict | None:
        offline = ctx.get("offline_only", self.offline_only)
        if not offline:
            return None
        url = ctx.get("url") or ctx.get("endpoint")
        perm = _normalize_permission(ctx)
        if url:
            parsed = urlparse(str(url))
            host = (parsed.hostname or "").lower()
            if host and host not in self.loopback_hosts:
                return HookVerdict(
                    decision=PolicyDecision.DENY,
                    hook_name="offline_network_wall",
                    reason=f"离线模式硬拦截非回环网络请求: {url}",
                )
        elif perm == "NETWORK":
            return HookVerdict(
                decision=PolicyDecision.DENY,
                hook_name="offline_network_wall",
                reason="离线模式物理禁止 NETWORK 权限工具",
            )
        return None

    def _hook_sensitive_and_whitelist_path(
        self, point: HookPoint, ctx: dict[str, Any]
    ) -> HookVerdict | None:
        paths: list[str] = []
        if ctx.get("path"):
            paths.append(str(ctx["path"]))
        for p in ctx.get("paths", []) or []:
            paths.append(str(p))

        override_roots = ctx.get("allowed_paths")
        perm = _normalize_permission(ctx)
        is_mutating = point == HookPoint.PRE_WRITE or perm in _WRITE_PERMISSIONS

        for target in paths:
            sensitive, hit_kw = self.path_guard.is_sensitive(target)
            if sensitive:
                return HookVerdict(
                    decision=PolicyDecision.DENY,
                    hook_name="sensitive_path_wall",
                    reason=f"敏感路径/凭证硬死锁拦截 ({hit_kw}): {target}",
                )
            if is_mutating and not self.path_guard.is_within_allowed(
                target, override_allowed_roots=override_roots
            ):
                return HookVerdict(
                    decision=PolicyDecision.DENY,
                    hook_name="sensitive_path_wall",
                    reason=f"目标路径越出授权工作区白名单（含路径穿越防护）: {target}",
                )
        return None

    def _hook_work_mode(self, point: HookPoint, ctx: dict[str, Any]) -> HookVerdict | None:
        mode = _normalize_mode(ctx.get("work_mode", WorkMode.ASK))
        perm = _normalize_permission(ctx)
        action = str(ctx.get("action", "")).lower()
        mutating = (
            point == HookPoint.PRE_WRITE
            or perm in _WRITE_PERMISSIONS
            or action in self.high_risk_actions
        )

        if mode == WorkMode.ASK:
            if mutating:
                return HookVerdict(
                    decision=PolicyDecision.DENY,
                    hook_name="work_mode_guard",
                    reason=f"Ask 只读模式内核物理禁写/禁执行 (permission={perm}, action={action or point.value})",
                )
            return None

        if mode == WorkMode.PLAN:
            if perm == "EXECUTE":
                return HookVerdict(
                    decision=PolicyDecision.DENY,
                    hook_name="work_mode_guard",
                    reason="Plan 模式禁止直接执行外部命令/代码，请先确认计划后切 Execute",
                )
            if mutating:
                scope_id = str(ctx.get("run_id") or ctx.get("task_id") or "default")
                if not self.evidence.has(scope_id, "plan_confirmed"):
                    diff = self._maybe_build_diff(ctx)
                    return HookVerdict(
                        decision=PolicyDecision.ASK_HUMAN,
                        hook_name="work_mode_guard",
                        reason="Plan 模式写入前必须先展示影响清单与变更预览并获人类确认",
                        missing_evidence=["plan_confirmed"],
                        diff_preview=diff,
                    )
        return None

    def _hook_evidence_gate(self, point: HookPoint, ctx: dict[str, Any]) -> HookVerdict | None:
        scope_id = str(ctx.get("run_id") or ctx.get("task_id") or "default")
        if point == HookPoint.PRE_COMMIT:
            missing = self.evidence.missing(scope_id, self.commit_evidence_required)
            if missing:
                return HookVerdict(
                    decision=PolicyDecision.DENY,
                    hook_name="evidence_and_high_risk_gate",
                    reason=f"证据闸门拦截提交：缺少必需客观凭证 {missing}",
                    missing_evidence=missing,
                )
            return None

        action = str(ctx.get("action", "")).lower()
        if action in self.high_risk_actions and not self.evidence.has(scope_id, "human_approved"):
            diff = self._maybe_build_diff(ctx)
            return HookVerdict(
                decision=PolicyDecision.ASK_HUMAN,
                hook_name="evidence_and_high_risk_gate",
                reason=f"高危动作 '{action}' 需要人工审批凭证 (human_approved)",
                missing_evidence=["human_approved"],
                diff_preview=diff,
            )
        return None

    def _hook_diff_preview(self, _point: HookPoint, ctx: dict[str, Any]) -> HookVerdict | None:
        diff = self._maybe_build_diff(ctx)
        if not diff:
            return None
        return HookVerdict(
            decision=PolicyDecision.ALLOW,
            hook_name="diff_preview_enricher",
            reason="已附带变更 Diff 预览",
            diff_preview=diff,
        )

    @staticmethod
    def _maybe_build_diff(ctx: dict[str, Any]) -> str:
        if "old_content" in ctx and "new_content" in ctx:
            return generate_unified_diff(
                ctx.get("path", "unknown"),
                str(ctx["old_content"]),
                str(ctx["new_content"]),
            )
        return ""

    def evaluate(self, hook_point: HookPoint | str, context: dict[str, Any]) -> HookVerdict:
        return self.pipeline.run(hook_point, context)

    def check(self, hook_point: str, context: dict[str, Any]) -> PolicyDecision:
        """满足 packages.core.interfaces.PolicyHookProtocol 强契约。"""
        return self.evaluate(hook_point, context).decision
