"""M05 对标 Google ADK 的五块可嵌套标准乐高编排原语（primitives.py）.

五原语：
  1. TaskNode (LlmNode / 确定性节点统一抽象)
  2. SequentialFlow (顺序流水线)
  3. ParallelFlow (逻辑扇出并行，物理支持单机 max_concurrency=1 显存亲和节流)
  4. LoopFlow (Writer <-> Critic / Code <-> Test 有界循环)
  5. GraphRouter (柔性动态状态图，由模型或路由函数决定下一跳，支持硬步数止损)
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any, Callable


class InterruptSignal(Exception):
    """HITL 人工审批挂起信号：由节点或安全钩子抛出，引擎自动落盘断点并暂停。"""

    def __init__(
        self,
        *,
        node_id: str,
        reason: str,
        diff_preview: str = "",
        missing_evidence: list[str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(reason)
        self.node_id = node_id
        self.reason = reason
        self.diff_preview = diff_preview
        self.missing_evidence = missing_evidence or []
        self.payload = payload or {}


class StepLimitExceeded(RuntimeError):
    """防死循环硬熔断异常（守住单机算力与预算底线）。"""


@dataclass
class FlowContext:
    """传递给每个执行节点的轻量上下文对象。"""

    run_id: str
    task_id: str
    state: dict[str, Any]
    steering_hints: list[str] = field(default_factory=list)
    approval_payload: dict[str, Any] | None = None
    _save_artifact_fn: Callable[[str, str | bytes], pathlib.Path] | None = None

    def save_artifact(self, name: str, content: str | bytes) -> pathlib.Path:
        if self._save_artifact_fn is None:
            raise RuntimeError("当前 FlowContext 未绑定持久化产物保存器")
        return self._save_artifact_fn(name, content)


NodeFn = Callable[[FlowContext], dict[str, Any] | None]
RouterFn = Callable[[dict[str, Any]], str | None]
ExitCondFn = Callable[[dict[str, Any], int], bool]


@dataclass
class TaskNode:
    """原语 1：原子任务节点（可包装大模型 LlmNode 或纯确定性 Python/MCP 节点）。"""

    node_id: str
    fn: NodeFn
    permission: str = "READ"
    action: str = ""
    target_path_key: str | None = None
    description: str = ""


@dataclass
class SequentialFlow:
    """原语 2：顺序流水线（子项可任意嵌套 5 种原语）。"""

    node_id: str
    steps: list[FlowPrimitive]


@dataclass
class ParallelFlow:
    """原语 3：逻辑扇出并行（默认 max_concurrency=1 适配单卡防显存乒乓，Pro 档可调高）。"""

    node_id: str
    branches: list[FlowPrimitive]
    max_concurrency: int = 1


@dataclass
class LoopFlow:
    """原语 4：有界循环（例如 Writer <-> Critic 或 Code <-> Test，防无限死循环）。"""

    node_id: str
    body: FlowPrimitive
    exit_condition: ExitCondFn
    max_iterations: int = 5


@dataclass
class GraphRouter:
    """原语 5：柔性动态有环状态图（router_fn 可由模型自由决策下一跳，仅受 max_hops 硬止损）。"""

    node_id: str
    nodes: dict[str, FlowPrimitive]
    entry_node: str
    router: RouterFn
    max_hops: int = 12


FlowPrimitive = TaskNode | SequentialFlow | ParallelFlow | LoopFlow | GraphRouter
