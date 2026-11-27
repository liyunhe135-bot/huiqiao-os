"""M06 B05 轻量工具循环执行内核（ReActWorker · 实现 WorkerProtocol）.

联动三块已有积木：
- M01 strip_think_blocks：流式剥离 <think> 块，防止推理文本污染 JSON 指令解析；
- M03 ToolSearch：初始只挂极轻 tool_search 元工具，按需延迟展开工具 schema；
- M04 GovernanceGuard：每次工具调用前过确定性安全守卫（DENY 硬拦截 / ASK_HUMAN 交回审批）。
内置防烧 Token 护栏：重复动作死循环检测 + 最大步数硬止损。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

from packages.core.constitution import LoadedConstitution, load_constitution
from packages.core.contracts import PolicyDecision, StepInput, StepOutput
from packages.governance import GovernanceGuard, HookPoint
from packages.llm_gateway.thinking import strip_think_blocks
from packages.mcp_bus.permissions import ToolSpec
from packages.mcp_bus.tool_search import ToolSearch

InferFn = Callable[[list[dict[str, str]]], str]
ToolExecutorFn = Callable[[str, dict[str, Any]], Any]

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", flags=re.DOTALL)


def _parse_action_json(raw_text: str) -> dict[str, Any]:
    cleaned = strip_think_blocks(raw_text)
    match = _JSON_FENCE_RE.search(cleaned)
    candidate = match.group(1) if match else cleaned
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = candidate[start : end + 1]
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("ReAct 动作输出必须为 JSON 对象")
    return data


class ReActWorker:
    """基于延迟 ToolSearch 与确定性安全守卫的轻量 ReAct 工具执行内核。"""

    def __init__(
        self,
        *,
        infer_fn: InferFn,
        tools: list[ToolSpec] | None = None,
        tool_executor: ToolExecutorFn | None = None,
        guard: GovernanceGuard | None = None,
        constitution: LoadedConstitution | None = None,
        max_turns: int = 6,
    ) -> None:
        self._infer_fn = infer_fn
        self._tool_specs: dict[str, ToolSpec] = {t.name: t for t in (tools or [])}
        self._tool_search = ToolSearch(self._tool_specs.values())
        self._tool_executor = tool_executor
        self._guard = guard
        self._constitution = constitution or load_constitution()
        self.max_turns = max_turns

    def healthcheck(self) -> bool:
        return True

    def run(self, step: StepInput) -> StepOutput:
        t0 = time.perf_counter()
        init_bundle = self._tool_search.initial_bundle()
        system_prompt = (
            f"{self._constitution.as_system_prefix()}\n\n"
            "你运行在 ReAct 工具循环中，每轮请输出严格 JSON：\n"
            '- 查找工具: {"action": "tool_search", "query": "关键词"}\n'
            '- 调用工具: {"action": "tool_call", "tool": "工具名", "params": {...}}\n'
            '- 完成交付: {"action": "finish", "summary": "最终结果", "notes": "可选说明"}\n'
            f"初始可用元工具: {json.dumps(list(init_bundle.tools), ensure_ascii=False)}"
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            *[
                {"role": str(m["role"]), "content": str(m.get("content", ""))}
                for m in (step.context_messages or [])
                if isinstance(m, dict) and m.get("role") in ("user", "assistant")
            ],
            {
                "role": "user",
                "content": (
                    f"{step.goal}\n[中途改向]: {step.steering_hint}"
                    if step.steering_hint
                    else step.goal
                ),
            },
        ]

        last_call_sig: str | None = None
        trace: list[dict[str, Any]] = []

        for turn in range(1, self.max_turns + 1):
            raw = self._infer_fn(messages)
            try:
                cmd = _parse_action_json(raw)
            except Exception as exc:  # noqa: BLE001
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": f"[格式修正提示] 无法解析 JSON 动作 ({exc})，请仅输出合法 JSON 对象。",
                    }
                )
                continue

            action = str(cmd.get("action", "")).lower()

            if action == "finish":
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                return StepOutput(
                    run_id=step.run_id,
                    task_id=step.task_id,
                    step_id=step.step_id,
                    brick_name="react_worker",
                    success=True,
                    summary=str(cmd.get("summary", "")),
                    model_notes=str(cmd.get("notes", "")),
                    elapsed_ms=elapsed_ms,
                    metadata={"turns": turn, "trace": trace},
                )

            if action == "tool_search":
                query = str(cmd.get("query", ""))
                bundle = self._tool_search.handle(query)
                obs = {
                    "matched_tools": list(bundle.tools),
                    "estimated_tokens": bundle.estimated_tokens,
                }
                trace.append({"turn": turn, "action": "tool_search", "query": query})
                messages.append({"role": "assistant", "content": json.dumps(cmd, ensure_ascii=False)})
                messages.append(
                    {"role": "user", "content": f"[Observation: tool_search]\n{json.dumps(obs, ensure_ascii=False)}"}
                )
                continue

            if action == "tool_call":
                tool_name = str(cmd.get("tool", ""))
                params = cmd.get("params") if isinstance(cmd.get("params"), dict) else {}
                sig = f"{tool_name}:{json.dumps(params, sort_keys=True, ensure_ascii=False)}"
                if sig == last_call_sig:
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                    return StepOutput(
                        run_id=step.run_id,
                        task_id=step.task_id,
                        step_id=step.step_id,
                        brick_name="react_worker",
                        success=False,
                        summary="",
                        error=f"检测到连续重复工具调用死循环 ({tool_name})，已触发防烧 Token 熔断",
                        elapsed_ms=elapsed_ms,
                        metadata={"turns": turn, "trace": trace},
                    )
                last_call_sig = sig

                spec = self._tool_specs.get(tool_name)
                if spec is None:
                    messages.append({"role": "assistant", "content": json.dumps(cmd, ensure_ascii=False)})
                    messages.append(
                        {"role": "user", "content": f"[Observation: error] 未找到工具 '{tool_name}'，请先调用 tool_search。"}
                    )
                    continue

                # 过 M04 确定性生命周期守卫
                if self._guard is not None:
                    hook_point = (
                        HookPoint.PRE_WRITE
                        if spec.permission.value in {"WRITE", "DELETE"}
                        else HookPoint.PRE_TOOL_USE
                    )
                    guard_ctx: dict[str, Any] = {
                        "run_id": step.run_id,
                        "task_id": step.task_id,
                        "work_mode": step.work_mode,
                        "tool": spec,
                        "permission": spec.permission.value,
                        "action": str(params.get("action", "")),
                    }
                    if "path" in params:
                        guard_ctx["path"] = params["path"]
                    if "url" in params:
                        guard_ctx["url"] = params["url"]
                    if "old_content" in params and "new_content" in params:
                        guard_ctx["old_content"] = params["old_content"]
                        guard_ctx["new_content"] = params["new_content"]

                    verdict = self._guard.evaluate(hook_point, guard_ctx)
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                    if verdict.decision == PolicyDecision.DENY:
                        return StepOutput(
                            run_id=step.run_id,
                            task_id=step.task_id,
                            step_id=step.step_id,
                            brick_name="react_worker",
                            success=False,
                            summary="",
                            error=f"工具 {tool_name} 被安全守卫拦截: {verdict.reason}",
                            elapsed_ms=elapsed_ms,
                            metadata={"turns": turn, "trace": trace},
                        )
                    if verdict.decision == PolicyDecision.ASK_HUMAN:
                        return StepOutput(
                            run_id=step.run_id,
                            task_id=step.task_id,
                            step_id=step.step_id,
                            brick_name="react_worker",
                            success=False,
                            summary=f"等待人工审批: {verdict.reason}",
                            model_notes=verdict.diff_preview,
                            needs_human_approval=True,
                            elapsed_ms=elapsed_ms,
                            metadata={
                                "turns": turn,
                                "missing_evidence": verdict.missing_evidence,
                                "trace": trace,
                            },
                        )

                if self._tool_executor is None:
                    result_payload: Any = {"ok": True, "tool": tool_name, "params": params}
                else:
                    result_payload = self._tool_executor(tool_name, params)

                trace.append({"turn": turn, "action": "tool_call", "tool": tool_name})
                messages.append({"role": "assistant", "content": json.dumps(cmd, ensure_ascii=False)})
                messages.append(
                    {
                        "role": "user",
                        "content": f"[Observation: {tool_name}]\n{json.dumps(result_payload, ensure_ascii=False)}",
                    }
                )
                continue

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return StepOutput(
            run_id=step.run_id,
            task_id=step.task_id,
            step_id=step.step_id,
            brick_name="react_worker",
            success=False,
            summary="",
            error=f"超过最大 ReAct 轮次上限 ({self.max_turns})，已安全止损",
            elapsed_ms=elapsed_ms,
            metadata={"turns": self.max_turns, "trace": trace},
        )
