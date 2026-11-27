"""M04 确定性生命周期 Hooks 管线（师从 Anthropic Claude Lifecycle Hooks）."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from packages.core.contracts import PolicyDecision


class HookPoint(str, Enum):
    """6 个标准生命周期拦截点。"""

    PRE_ROUTE = "PreRoute"
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    PRE_WRITE = "PreWrite"
    PRE_COMMIT = "PreCommit"
    ON_COMPACTION = "OnCompaction"


@dataclass
class HookVerdict:
    """结构化钩子判决结果。"""

    decision: PolicyDecision
    hook_name: str
    reason: str = ""
    missing_evidence: list[str] = field(default_factory=list)
    diff_preview: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


HookFn = Callable[[HookPoint, dict[str, Any]], HookVerdict | None]


@dataclass
class RegisteredHook:
    name: str
    points: frozenset[HookPoint]
    fn: HookFn
    priority: int = 100


class HookPipeline:
    """按优先级串联多条确定性钩子，执行严格安全短接（DENY > ASK_HUMAN > ALLOW）。"""

    def __init__(self) -> None:
        self._hooks: list[RegisteredHook] = []

    def register(
        self,
        name: str,
        points: set[HookPoint] | list[HookPoint] | tuple[HookPoint, ...],
        fn: HookFn,
        *,
        priority: int = 100,
    ) -> None:
        self._hooks.append(
            RegisteredHook(
                name=name,
                points=frozenset(points),
                fn=fn,
                priority=priority,
            )
        )
        self._hooks.sort(key=lambda h: h.priority)

    def run(self, point: HookPoint | str, context: dict[str, Any]) -> HookVerdict:
        hp = point if isinstance(point, HookPoint) else HookPoint(point)
        ask_verdict: HookVerdict | None = None
        diff_collected = ""

        for hook in self._hooks:
            if hp not in hook.points:
                continue
            verdict = hook.fn(hp, context)
            if verdict is None:
                continue
            if verdict.diff_preview and not diff_collected:
                diff_collected = verdict.diff_preview
            if verdict.decision == PolicyDecision.DENY:
                if diff_collected and not verdict.diff_preview:
                    verdict.diff_preview = diff_collected
                return verdict
            if verdict.decision == PolicyDecision.ASK_HUMAN and ask_verdict is None:
                ask_verdict = verdict

        if ask_verdict is not None:
            if diff_collected and not ask_verdict.diff_preview:
                ask_verdict.diff_preview = diff_collected
            return ask_verdict

        return HookVerdict(
            decision=PolicyDecision.ALLOW,
            hook_name="pipeline",
            reason="通过全部确定性生命周期钩子检查",
            diff_preview=diff_collected,
        )
