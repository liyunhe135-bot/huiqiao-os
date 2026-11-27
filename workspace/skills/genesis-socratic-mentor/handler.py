"""创世种子技能 5：基于 C00 宪章的苏格拉底启发式难题拆解导师（UPLIFT_MENTOR）."""

from __future__ import annotations

from typing import Any

from packages.core.contracts import InteractionMode, StepInput, TaskEnvelope
from packages.workers.semantic import SemanticCoCreatorWorker


def execute(envelope: TaskEnvelope, state: dict[str, Any]) -> dict[str, Any]:
    question = (envelope.raw_input or (envelope.input.text if envelope.input else "")).strip()
    infer_fn = state.get("_semantic_infer_fn")

    if callable(infer_fn):
        worker = SemanticCoCreatorWorker(infer_fn=infer_fn)
        out = worker.run(
            StepInput(
                task_id=envelope.task_id,
                goal=question,
                work_mode=envelope.constraints.work_mode,
                interaction_mode=InteractionMode.UPLIFT_MENTOR,
            )
        )
        reply = out.summary
    else:
        reply = "\n".join(
            [
                "# 启发式难题拆解与多维权衡",
                f"- **核心议题**：{question}",
                "",
                "## 1. 本质问题剥离",
                "- 表面看是「选哪条路」的纠结，底层往往是 **短期确定性收益** 与 **长期能力复利 / 可逆试错空间** 之间的优先级排序。",
                "",
                "## 2. 双视角利弊对照",
                "| 维度 | 路径 A：稳健渐进（先小步闭环验真） | 路径 B：集中突破（重兵投入新方向） |",
                "| :--- | :--- | :--- |",
                "| 核心优势 | 试错成本极低、现金流/心力平稳、随时可逆 | 上限空间更大、避免温水煮青蛙 |",
                "| 潜在代价 | 突破速度较慢，需防止陷入琐碎维护 | 对资源储备与抗压容错率要求高 |",
                "",
                "## 3. 可迁移底层原理（杠铃策略 + 最小可逆实验）",
                "- 在重大不确定决策前，把 **90% 基本盘守在绝对安全线内**，先拿 **10% 时间/精力做一个 1–2 周内能看到真实反馈的最小实验**，用客观反馈代替空想内耗。",
                "",
                "## 4. 交还主导权的苏格拉底追问",
                "1. 如果最坏情况发生，哪一个选项的后果是你完全可承受、可逆转的？",
                "2. 不必等条件 100% 成熟，未来 7 天内你能花不到 4 小时做出的「最小试水动作」是什么？",
            ]
        )

    return {
        "summary": reply,
        "interaction_mode": InteractionMode.UPLIFT_MENTOR.value,
        "artifact_name": "socratic_mentor_notes.md",
        "artifact_content": reply,
        "model_notes": "已按 C00 授人以渔原则提供结构化思辨框架，最终取舍权完全归于你本人。",
    }
