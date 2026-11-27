"""创世种子技能 4：每日复盘与明日 1–3 件核心要事梳理（护持节奏、反焦虑内卷）."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from packages.core.contracts import TaskEnvelope

_BLOCKER_WORDS = ("卡住", "问题", "报错", "难点", "延迟", "没做完", "不足", "教训", "坑", "瓶颈", "困惑")
_NEXT_WORDS = ("明天", "明日", "下一步", "计划", "待办", "准备", "接下来", "todo")


def execute(envelope: TaskEnvelope, state: dict[str, Any]) -> dict[str, Any]:
    raw = (envelope.raw_input or (envelope.input.text if envelope.input else "")).strip()
    fragments = [
        s.strip(" -*•\t")
        for s in re.split(r"[\n；;。！？!?]+", raw)
        if s.strip(" -*•\t")
    ]

    wins: list[str] = []
    learnings: list[str] = []
    next_actions: list[str] = []

    for frag in fragments:
        low = frag.lower()
        if any(w in low for w in _NEXT_WORDS):
            next_actions.append(frag)
        elif any(w in low for w in _BLOCKER_WORDS):
            learnings.append(frag)
        else:
            wins.append(frag)

    if not wins and fragments:
        wins.append(fragments[0])
    if not learnings:
        learnings.append("今日整体推进平稳，注意保持专注块连续、避免多任务频繁切换。")
    if not next_actions:
        next_actions = [
            "优先推进当前最关键的 1 个闭环交付节点",
            "留出 15 分钟整理过程笔记与验证结果",
        ]

    top_three = next_actions[:3]
    later_pool = next_actions[3:]
    today_str = date.today().isoformat()

    lines = [
        f"# 每日复盘与节奏梳理（{today_str}）",
        "",
        "## 一、今日已完成与进展亮点",
        *[f"- {w}" for w in wins[:5]],
        "",
        "## 二、卡点觉察与可复用经验",
        *[f"- {l}" for l in learnings[:4]],
        "",
        "## 三、明日聚焦核心要事（严格收敛 ≤ 3 件）",
        *[f"{idx}. {act}" for idx, act in enumerate(top_three, start=1)],
    ]
    if later_pool:
        lines.extend(
            [
                "",
                "## 四、安心缓办池（暂不挤占明日主精力）",
                *[f"- {item}" for item in later_pool],
            ]
        )
    lines.extend(
        [
            "",
            "> **增上温言**：先稳住最重要的 1 件事做透，其余顺势而为，留白也是生产力的一部分。",
        ]
    )

    report = "\n".join(lines)
    return {
        "summary": report,
        "wins_count": len(wins),
        "focus_actions": top_three,
        "artifact_name": f"daily_reflection_{today_str}.md",
        "artifact_content": report,
        "model_notes": "已按 C00 反内卷增上原则将明日待办收敛在 3 件以内，守护可持续心力。",
    }
