"""思考预算开关 + <think> 流式剥离。

工程教训（DeepSeek 交错思考）：
- 简单路由/抽取任务开深度思考 → 延迟飙升；
- <think> 块混入 JSON/代码解析 → 解析失败。
所以：按角色定预算，物理剥离思考文本。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ThinkingBudget(str, Enum):
    OFF = "off"
    LOW = "low"
    HIGH = "high"


def budget_for_role(role: str) -> ThinkingBudget:
    """角色默认预算：路由/抽取关思考，规划/代码审查开高。"""
    if role in {"fast_router", "extractor", "embed", "classifier"}:
        return ThinkingBudget.OFF
    if role in {"coder", "summarizer", "semantic"}:
        return ThinkingBudget.LOW
    if role in {"reasoner", "planner", "evaluator"}:
        return ThinkingBudget.HIGH
    return ThinkingBudget.LOW


_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think>", flags=re.DOTALL | re.IGNORECASE)
_THINK_OPEN = re.compile(r"<think\b[^>]*>", flags=re.IGNORECASE)


def strip_think_blocks(text: str) -> str:
    """剥离思考文本，保解析器稳定。

    - 成对的 <think>...</think> 整段删除（含内部思考）。
    - 未闭合的 <think> 表示后续全部是流式思考，直接截断到标签前，
      不能只删标签而把思考内容留进正文（否则污染 JSON/代码解析）。
    """
    cleaned = _THINK_RE.sub("", text)
    open_match = _THINK_OPEN.search(cleaned)
    if open_match:
        cleaned = cleaned[: open_match.start()]
    return cleaned.strip()
