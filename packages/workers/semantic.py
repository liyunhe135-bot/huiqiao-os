"""M06 B05 L2-S 语义共生执行内核（SemanticCoCreatorWorker · 实现 WorkerProtocol）.

定位：专治 CodeAct 失效区（开放人文、战略权衡、学习辅导、深度写作、情感沟通）。
核心机制：
- 头部固定注入 C00 宪章极简前缀（保护本地 KV 前缀缓存）；
- 双态自适应：UPLIFT_MENTOR（授人以渔：拆解 + 多视角权衡 + 原理 + 启发提问）vs COPILOT_EXECUTE；
- 柔性支持可选只读事实查证回调，且自动吸纳中途改向 steering_hint 并剥离 <think> 块。
"""

from __future__ import annotations

import time
from typing import Any, Callable

from packages.core.constitution import LoadedConstitution, load_constitution
from packages.core.contracts import InteractionMode, StepInput, StepOutput
from packages.llm_gateway.thinking import strip_think_blocks

InferFn = Callable[[list[dict[str, str]]], str]
FactLookupFn = Callable[[str], str]

_MENTOR_DIRECTIVE = (
    "【当前交互姿态：UPLIFT_MENTOR（启发增上态）】\n"
    "请以真诚平实的同行导师视角回应，结构包含：\n"
    "1) 问题本质拆解；2) 至少两个视角/方案的利弊权衡；"
    "3) 背后可迁移的核心原理或方法；4) 1-2 个帮助对方进一步澄清自身判断的关键问题。\n"
    "严禁替用户做唯一黑盒替身决策，请把主体权与选择权清晰交还给人。"
)

_COPILOT_DIRECTIVE = (
    "【当前交互姿态：COPILOT_EXECUTE（协作代劳态）】\n"
    "直接、清晰地交付高质量结果，并在末尾附极简推理依据或可微调要点，便于用户透明把控。"
)


def _default_offline_semantic_fallback(messages: list[dict[str, str]]) -> str:
    """无本地模型注入时的确定性降级响应（保障完全离线单测与冷启动可运行）。"""
    user_msg = messages[-1]["content"] if messages else ""
    return (
        f"【本质拆解】收到目标：{user_msg}\n"
        "【多视角权衡】路径 A（保守渐进，先小步验真） vs 路径 B（直接聚焦核心瓶颈推进）。\n"
        "【可迁移原理】复杂开放问题先界定不可破底线与最小可验证假设，再由你主导最终取舍。\n"
        "【启发提问】这件事里你最不能妥协的 1 条底线是什么？"
    )


class SemanticCoCreatorWorker:
    """L2-S 语义共生与启发共创 Worker。"""

    def __init__(
        self,
        *,
        infer_fn: InferFn | None = None,
        fact_lookup_fn: FactLookupFn | None = None,
        constitution: LoadedConstitution | None = None,
    ) -> None:
        self._infer_fn = infer_fn or _default_offline_semantic_fallback
        self._fact_lookup_fn = fact_lookup_fn
        self._constitution = constitution or load_constitution()

    def healthcheck(self) -> bool:
        return bool(self._constitution.as_system_prefix())

    def build_messages(self, step: StepInput) -> list[dict[str, str]]:
        """构造前缀稳定的消息列表（C00 宪章置顶保护 KV 缓存，动态改向放末尾）。"""
        mode_guide = (
            _MENTOR_DIRECTIVE
            if step.interaction_mode == InteractionMode.UPLIFT_MENTOR
            else _COPILOT_DIRECTIVE
        )
        system_content = f"{self._constitution.as_system_prefix()}\n\n{mode_guide}"
        messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]

        for msg in step.context_messages:
            role = str(msg.get("role", "user"))
            content = str(msg.get("content", ""))
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})

        user_parts = [step.goal]
        if self._fact_lookup_fn is not None and step.metadata.get("fact_query"):
            fact = self._fact_lookup_fn(str(step.metadata["fact_query"]))
            if fact:
                user_parts.append(f"\n[只读事实查证参考]\n{fact}")
        if step.steering_hint:
            user_parts.append(f"\n[用户中途改向指令 - 请立即遵循]\n{step.steering_hint}")

        messages.append({"role": "user", "content": "\n".join(user_parts)})
        return messages

    def run(self, step: StepInput) -> StepOutput:
        t0 = time.perf_counter()
        messages = self.build_messages(step)
        try:
            raw_reply = self._infer_fn(messages)
            clean_reply = strip_think_blocks(raw_reply)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            note = (
                "已按 UPLIFT_MENTOR 模式提供原理拆解与启发提问，最终判断权归用户。"
                if step.interaction_mode == InteractionMode.UPLIFT_MENTOR
                else "已按 COPILOT_EXECUTE 模式完成交付并附透明依据。"
            )
            return StepOutput(
                run_id=step.run_id,
                task_id=step.task_id,
                step_id=step.step_id,
                brick_name="semantic_cocreator",
                success=True,
                summary=clean_reply,
                model_notes=note,
                elapsed_ms=elapsed_ms,
                metadata={"system_prefix_has_c00": True, "messages_count": len(messages)},
            )
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            return StepOutput(
                run_id=step.run_id,
                task_id=step.task_id,
                step_id=step.step_id,
                brick_name="semantic_cocreator",
                success=False,
                summary="",
                error=str(exc),
                elapsed_ms=elapsed_ms,
            )
