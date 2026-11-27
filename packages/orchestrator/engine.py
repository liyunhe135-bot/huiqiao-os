"""M05 流式持久化编排引擎（OrchestratorEngine）与声明式 YAML Flow 加载器.

核心能力：
- 驱动 ADK 五大原语及其任意嵌套；
- 每个原子节点完成后立即落盘 SQLite WAL Checkpoint，进程强杀重启精确从断点续跑，零重复副作用；
- 与 M04 GovernanceGuard 联动：遇到 ASK_HUMAN 自动触发 HITL interrupt() 挂起并保留 Diff 预览，
  人工批准后经 resume() 签发凭证无缝继续；遇到 DENY 立即拦截；
- 实时流式推送进度事件，支持运行中途 steer() 动态改向，异常/超时后已完成产物 100% 留存。
"""

from __future__ import annotations

import pathlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Iterator

import yaml

from packages.core.contracts import PolicyDecision, WorkMode, new_id
from packages.core.errors import ErrorCode, HuiQiaoError
from packages.governance import GovernanceGuard, HookPoint
from packages.orchestrator.primitives import (
    ExitCondFn,
    FlowContext,
    FlowPrimitive,
    GraphRouter,
    InterruptSignal,
    LoopFlow,
    NodeFn,
    ParallelFlow,
    SequentialFlow,
    StepLimitExceeded,
    TaskNode,
)
from packages.orchestrator.store import SqliteStateStore


@dataclass
class _RunTracker:
    run_id: str
    task_id: str
    work_mode: WorkMode
    state: dict[str, Any]
    completed_nodes: list[str]
    completed_set: set[str]
    step_count: int
    max_total_steps: int
    approval_payload: dict[str, Any] | None = None


class OrchestratorEngine:
    """持久化 ADK 五原语流式编排引擎。"""

    def __init__(
        self,
        store: SqliteStateStore,
        *,
        guard: GovernanceGuard | None = None,
        max_total_steps: int = 30,
    ) -> None:
        self.store = store
        self.guard = guard
        self.max_total_steps = max_total_steps

    def healthcheck(self) -> bool:
        return self.store.journal_mode() == "wal"

    def steer(self, run_id: str, hint: str) -> None:
        """中途改向：向运行中或挂起中的任务注入新指引，下一执行节点自动收到。"""
        self.store.add_steering_hint(run_id, hint)

    def stream_run(
        self,
        flow: FlowPrimitive,
        *,
        task_id: str,
        initial_state: dict[str, Any] | None = None,
        run_id: str | None = None,
        work_mode: WorkMode = WorkMode.EXECUTE,
        approval_payload: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """以流式生成器驱动流程，实时 yield 结构化进度事件。"""
        rid = run_id or new_id("run")
        existing = self.store.get_run(rid)

        if existing is None:
            state = dict(initial_state or {})
            self.store.create_run(
                run_id=rid,
                task_id=task_id,
                flow_name=flow.node_id,
                initial_state=state,
            )
            completed: list[str] = []
            step_count = 0
            yield self.store.append_event(
                run_id=rid,
                task_id=task_id,
                event_type="run_started",
                payload={"flow_name": flow.node_id, "work_mode": work_mode.value},
            )
        else:
            state = dict(existing["state"])
            completed = list(existing["completed_nodes"])
            step_count = int(existing["step_count"])
            yield self.store.append_event(
                run_id=rid,
                task_id=existing["task_id"],
                event_type="run_resumed",
                payload={
                    "flow_name": flow.node_id,
                    "completed_count": len(completed),
                    "step_count": step_count,
                },
            )
            task_id = existing["task_id"]

        tracker = _RunTracker(
            run_id=rid,
            task_id=task_id,
            work_mode=work_mode,
            state=state,
            completed_nodes=completed,
            completed_set=set(completed),
            step_count=step_count,
            max_total_steps=self.max_total_steps,
            approval_payload=approval_payload,
        )

        try:
            yield from self._exec_primitive(flow, scope="", tracker=tracker)
            self.store.save_checkpoint(
                run_id=rid,
                node_id=flow.node_id,
                step_index=tracker.step_count,
                state=tracker.state,
                completed_nodes=tracker.completed_nodes,
                status="COMPLETED",
            )
            yield self.store.append_event(
                run_id=rid,
                task_id=task_id,
                event_type="run_completed",
                payload={"step_count": tracker.step_count, "state_keys": sorted(tracker.state.keys())},
            )
        except InterruptSignal as sig:
            interrupt_info = {
                "node_id": sig.node_id,
                "reason": sig.reason,
                "diff_preview": sig.diff_preview,
                "missing_evidence": sig.missing_evidence,
                "payload": sig.payload,
            }
            self.store.save_checkpoint(
                run_id=rid,
                node_id=sig.node_id,
                step_index=tracker.step_count,
                state=tracker.state,
                completed_nodes=tracker.completed_nodes,
                status="PAUSED_FOR_HUMAN",
                pending_interrupt=interrupt_info,
            )
            yield self.store.append_event(
                run_id=rid,
                task_id=task_id,
                event_type="run_paused_hitl",
                node_id=sig.node_id,
                payload=interrupt_info,
            )
        except Exception as exc:  # noqa: BLE001
            self.store.save_checkpoint(
                run_id=rid,
                node_id=flow.node_id,
                step_index=tracker.step_count,
                state=tracker.state,
                completed_nodes=tracker.completed_nodes,
                status="FAILED",
                error=str(exc),
            )
            yield self.store.append_event(
                run_id=rid,
                task_id=task_id,
                event_type="run_failed",
                payload={
                    "error": str(exc),
                    "preserved_artifacts": len(self.store.list_artifacts(rid)),
                },
            )

    def run(
        self,
        flow: FlowPrimitive,
        *,
        task_id: str,
        initial_state: dict[str, Any] | None = None,
        run_id: str | None = None,
        work_mode: WorkMode = WorkMode.EXECUTE,
    ) -> dict[str, Any]:
        """同步便捷入口：消费完整事件流并返回最终持久化运行快照。"""
        events = list(
            self.stream_run(
                flow,
                task_id=task_id,
                initial_state=initial_state,
                run_id=run_id,
                work_mode=work_mode,
            )
        )
        rid = run_id or events[0]["run_id"]
        snapshot = self.store.get_run(rid)
        assert snapshot is not None
        snapshot["events"] = events
        return snapshot

    def resume(
        self,
        flow: FlowPrimitive,
        run_id: str,
        *,
        approved: bool = True,
        approval_payload: dict[str, Any] | None = None,
        grant_evidence: list[str] | None = None,
        work_mode: WorkMode = WorkMode.EXECUTE,
    ) -> dict[str, Any]:
        """从崩溃断点或 HITL 挂起点无缝恢复执行。"""
        record = self.store.get_run(run_id)
        if record is None:
            raise KeyError(f"无法恢复，未找到 run_id: {run_id}")

        if not approved:
            self.store.save_checkpoint(
                run_id=run_id,
                node_id=(record["pending_interrupt"] or {}).get("node_id", flow.node_id),
                step_index=int(record["step_count"]),
                state=record["state"],
                completed_nodes=record["completed_nodes"],
                status="CANCELLED_BY_HUMAN",
                pending_interrupt=None,
                error="用户驳回人工审批请求",
            )
            self.store.append_event(
                run_id=run_id,
                task_id=record["task_id"],
                event_type="run_cancelled_by_human",
                payload={"approval_payload": approval_payload or {}},
            )
            snap = self.store.get_run(run_id)
            assert snap is not None
            return snap

        # 若为 HITL 批准恢复，自动向 GovernanceGuard 签发对应的缺失凭证
        if self.guard is not None:
            pending = record.get("pending_interrupt") or {}
            to_grant = list(grant_evidence or pending.get("missing_evidence", []))
            for ev in to_grant:
                self.guard.evidence.grant(run_id, ev)

        events = list(
            self.stream_run(
                flow,
                task_id=record["task_id"],
                run_id=run_id,
                work_mode=work_mode,
                approval_payload=approval_payload,
            )
        )
        snap = self.store.get_run(run_id)
        assert snap is not None
        snap["events"] = events
        return snap

    def _exec_primitive(
        self,
        node: FlowPrimitive,
        *,
        scope: str,
        tracker: _RunTracker,
    ) -> Iterator[dict[str, Any]]:
        full_id = f"{scope}/{node.node_id}" if scope else node.node_id

        if isinstance(node, TaskNode):
            yield from self._exec_task_node(node, full_id=full_id, tracker=tracker)
            return

        if isinstance(node, SequentialFlow):
            for child in node.steps:
                yield from self._exec_primitive(child, scope=full_id, tracker=tracker)
            return

        if isinstance(node, ParallelFlow):
            yield from self._exec_parallel(node, full_id=full_id, tracker=tracker)
            return

        if isinstance(node, LoopFlow):
            for idx in range(node.max_iterations):
                iter_scope = f"{full_id}[{idx}]"
                yield from self._exec_primitive(node.body, scope=iter_scope, tracker=tracker)
                if node.exit_condition(tracker.state, idx + 1):
                    yield self.store.append_event(
                        run_id=tracker.run_id,
                        task_id=tracker.task_id,
                        event_type="loop_exited",
                        node_id=full_id,
                        payload={"iterations": idx + 1},
                    )
                    return
            yield self.store.append_event(
                run_id=tracker.run_id,
                task_id=tracker.task_id,
                event_type="loop_max_reached",
                node_id=full_id,
                payload={"max_iterations": node.max_iterations},
            )
            return

        if isinstance(node, GraphRouter):
            current = node.entry_node
            for hop in range(node.max_hops):
                if current not in node.nodes:
                    raise KeyError(f"GraphRouter '{node.node_id}' 找不到节点 '{current}'")
                hop_scope = f"{full_id}@hop{hop}"
                yield from self._exec_primitive(
                    node.nodes[current], scope=hop_scope, tracker=tracker
                )
                nxt = node.router(tracker.state)
                yield self.store.append_event(
                    run_id=tracker.run_id,
                    task_id=tracker.task_id,
                    event_type="graph_routed",
                    node_id=f"{hop_scope}/{current}",
                    payload={"from": current, "to": nxt},
                )
                if nxt is None:
                    return
                current = nxt
            raise StepLimitExceeded(
                f"GraphRouter '{node.node_id}' 超过最大跳转上限 {node.max_hops}，触发防死循环熔断"
            )

    def _exec_parallel(
        self,
        node: ParallelFlow,
        *,
        full_id: str,
        tracker: _RunTracker,
    ) -> Iterator[dict[str, Any]]:
        # 默认 max_concurrency=1：单机单卡亲和串行，避免显存乒乓；>1 时开启受控线程池并发
        if node.max_concurrency <= 1:
            for idx, branch in enumerate(node.branches):
                yield from self._exec_primitive(
                    branch, scope=f"{full_id}#b{idx}", tracker=tracker
                )
            return

        # 仅当全部分支为独立 TaskNode 时并发执行并按分支顺序确定性合流
        if all(isinstance(b, TaskNode) for b in node.branches):
            pending_branches: list[tuple[int, TaskNode, str]] = []
            for idx, b in enumerate(node.branches):
                assert isinstance(b, TaskNode)
                bid = f"{full_id}#b{idx}/{b.node_id}"
                if bid in tracker.completed_set:
                    yield self.store.append_event(
                        run_id=tracker.run_id,
                        task_id=tracker.task_id,
                        event_type="node_skipped_from_checkpoint",
                        node_id=bid,
                        payload={"reason": "already_completed"},
                    )
                else:
                    pending_branches.append((idx, b, bid))

            if not pending_branches:
                return

            # 并发前先过安全钩子
            for _idx, b, bid in pending_branches:
                self._enforce_governance(b, full_id=bid, tracker=tracker)

            def _run_branch(b_node: TaskNode, bid: str) -> dict[str, Any]:
                ctx = FlowContext(
                    run_id=tracker.run_id,
                    task_id=tracker.task_id,
                    state=dict(tracker.state),
                    steering_hints=[],
                    approval_payload=tracker.approval_payload,
                    _save_artifact_fn=lambda name, content: self.store.save_artifact(
                        run_id=tracker.run_id, node_id=bid, name=name, content=content
                    ),
                )
                return b_node.fn(ctx) or {}

            with ThreadPoolExecutor(max_workers=node.max_concurrency) as pool:
                futures = [(bid, pool.submit(_run_branch, b, bid)) for _i, b, bid in pending_branches]
                for bid, fut in futures:
                    delta = fut.result()
                    tracker.state.update(delta)
                    tracker.step_count += 1
                    tracker.completed_nodes.append(bid)
                    tracker.completed_set.add(bid)
                    self.store.save_checkpoint(
                        run_id=tracker.run_id,
                        node_id=bid,
                        step_index=tracker.step_count,
                        state=tracker.state,
                        completed_nodes=tracker.completed_nodes,
                        status="RUNNING",
                    )
                    yield self.store.append_event(
                        run_id=tracker.run_id,
                        task_id=tracker.task_id,
                        event_type="node_completed",
                        node_id=bid,
                        payload={"updated_keys": sorted(delta.keys()), "parallel": True},
                    )
            return

        # 嵌套复杂子流安全退化为确定性分步执行
        for idx, branch in enumerate(node.branches):
            yield from self._exec_primitive(branch, scope=f"{full_id}#b{idx}", tracker=tracker)

    def _enforce_governance(
        self,
        node: TaskNode,
        *,
        full_id: str,
        tracker: _RunTracker,
    ) -> None:
        if self.guard is None:
            return
        hook_point = (
            HookPoint.PRE_WRITE
            if node.permission.upper() in {"WRITE", "DELETE"}
            else HookPoint.PRE_TOOL_USE
        )
        ctx: dict[str, Any] = {
            "run_id": tracker.run_id,
            "task_id": tracker.task_id,
            "work_mode": tracker.work_mode,
            "permission": node.permission,
            "action": node.action,
        }
        if node.target_path_key and node.target_path_key in tracker.state:
            ctx["path"] = tracker.state[node.target_path_key]
        if "allowed_paths" in tracker.state and tracker.state["allowed_paths"]:
            ctx["allowed_paths"] = tracker.state["allowed_paths"]
        if "old_content" in tracker.state and "new_content" in tracker.state:
            ctx["old_content"] = tracker.state["old_content"]
            ctx["new_content"] = tracker.state["new_content"]

        verdict = self.guard.evaluate(hook_point, ctx)
        if verdict.decision == PolicyDecision.DENY:
            raise HuiQiaoError(
                ErrorCode.POLICY_DENIED,
                f"节点 {full_id} 被安全守卫拦截: {verdict.reason}",
                {"node_id": full_id, "hook": verdict.hook_name},
            )
        if verdict.decision == PolicyDecision.ASK_HUMAN:
            raise InterruptSignal(
                node_id=full_id,
                reason=verdict.reason,
                diff_preview=verdict.diff_preview,
                missing_evidence=verdict.missing_evidence,
            )

    def _exec_task_node(
        self,
        node: TaskNode,
        *,
        full_id: str,
        tracker: _RunTracker,
    ) -> Iterator[dict[str, Any]]:
        if full_id in tracker.completed_set:
            yield self.store.append_event(
                run_id=tracker.run_id,
                task_id=tracker.task_id,
                event_type="node_skipped_from_checkpoint",
                node_id=full_id,
                payload={"reason": "already_completed"},
            )
            return

        if tracker.step_count >= tracker.max_total_steps:
            raise StepLimitExceeded(
                f"运行 {tracker.run_id} 超过最大总步数限制 {tracker.max_total_steps}，触发硬熔断"
            )

        # 吸纳用户中途改向指令
        hints = self.store.consume_steering_hints(tracker.run_id)
        if hints:
            history = list(tracker.state.get("_steering_hints", []))
            history.extend(hints)
            tracker.state["_steering_hints"] = history
            yield self.store.append_event(
                run_id=tracker.run_id,
                task_id=tracker.task_id,
                event_type="steering_applied",
                node_id=full_id,
                payload={"hints": hints},
            )

        # 过 M04 确定性生命周期安全守卫
        self._enforce_governance(node, full_id=full_id, tracker=tracker)

        yield self.store.append_event(
            run_id=tracker.run_id,
            task_id=tracker.task_id,
            event_type="node_started",
            node_id=full_id,
            payload={"permission": node.permission, "action": node.action},
        )

        ctx = FlowContext(
            run_id=tracker.run_id,
            task_id=tracker.task_id,
            state=tracker.state,
            steering_hints=hints,
            approval_payload=tracker.approval_payload,
            _save_artifact_fn=lambda name, content: self.store.save_artifact(
                run_id=tracker.run_id, node_id=full_id, name=name, content=content
            ),
        )
        delta = node.fn(ctx)
        if isinstance(delta, dict):
            tracker.state.update(delta)

        tracker.step_count += 1
        tracker.completed_nodes.append(full_id)
        tracker.completed_set.add(full_id)
        self.store.save_checkpoint(
            run_id=tracker.run_id,
            node_id=full_id,
            step_index=tracker.step_count,
            state=tracker.state,
            completed_nodes=tracker.completed_nodes,
            status="RUNNING",
        )
        yield self.store.append_event(
            run_id=tracker.run_id,
            task_id=tracker.task_id,
            event_type="node_completed",
            node_id=full_id,
            payload={"step_count": tracker.step_count},
        )


def load_yaml_flow(
    yaml_source: pathlib.Path | str,
    *,
    handlers: dict[str, NodeFn],
    conditions: dict[str, ExitCondFn] | None = None,
) -> FlowPrimitive:
    """将声明式 YAML 工作流文件/字符串装配为可执行的 ADK 嵌套乐高树。"""
    p = pathlib.Path(yaml_source)
    raw_text = p.read_text(encoding="utf-8") if p.exists() else str(yaml_source)
    spec = yaml.safe_load(raw_text)
    if not isinstance(spec, dict):
        raise ValueError("YAML Flow 顶层必须为字典对象")
    return _build_from_spec(spec, handlers=handlers, conditions=conditions or {})


def _build_from_spec(
    spec: dict[str, Any],
    *,
    handlers: dict[str, NodeFn],
    conditions: dict[str, ExitCondFn],
) -> FlowPrimitive:
    kind = str(spec.get("type", "task")).lower()
    node_id = str(spec["id"])

    if kind == "task":
        handler_name = str(spec["handler"])
        if handler_name not in handlers:
            raise KeyError(f"YAML Flow 找不到 handler: {handler_name}")
        return TaskNode(
            node_id=node_id,
            fn=handlers[handler_name],
            permission=str(spec.get("permission", "READ")),
            action=str(spec.get("action", "")),
            target_path_key=spec.get("target_path_key"),
            description=str(spec.get("description", "")),
        )

    if kind == "sequential":
        steps = [
            _build_from_spec(item, handlers=handlers, conditions=conditions)
            for item in spec.get("steps", [])
        ]
        return SequentialFlow(node_id=node_id, steps=steps)

    if kind == "parallel":
        branches = [
            _build_from_spec(item, handlers=handlers, conditions=conditions)
            for item in spec.get("branches", [])
        ]
        return ParallelFlow(
            node_id=node_id,
            branches=branches,
            max_concurrency=int(spec.get("max_concurrency", 1)),
        )

    if kind == "loop":
        body = _build_from_spec(spec["body"], handlers=handlers, conditions=conditions)
        cond_name = str(spec["exit_condition"])
        if cond_name not in conditions:
            raise KeyError(f"YAML Flow 找不到 exit_condition: {cond_name}")
        return LoopFlow(
            node_id=node_id,
            body=body,
            exit_condition=conditions[cond_name],
            max_iterations=int(spec.get("max_iterations", 5)),
        )

    raise ValueError(f"不支持的 YAML Flow 节点类型: {kind}")
