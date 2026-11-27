"""Tool Search 延迟工具加载器（师从 Claude defer_loading）。

核心：初始只向模型注入一个极轻的 tool_search 元工具，
命中后再展开具体工具 schema。保护前缀缓存、避免工具区撑爆窗口。

DoD：挂载 30 个工具时，初始系统工具区 < 500 tokens。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .permissions import ToolSpec


@dataclass(frozen=True)
class ToolBundle:
    """注入给模型的工具区快照。"""

    tools: tuple[dict[str, Any], ...]
    estimated_tokens: int


class ToolSearch:
    def __init__(self, tools: Iterable[ToolSpec]) -> None:
        self._tools = {t.name: t for t in tools}

    @staticmethod
    def _meta_tool() -> dict[str, Any]:
        # 极简元工具：只有名字和一行说明
        return {
            "name": "tool_search",
            "description": "按关键词查找可用工具",
            "input_schema": {"query": "string"},
        }

    def initial_bundle(self) -> ToolBundle:
        """初始只给元工具，不给任何具体 schema。"""
        meta = self._meta_tool()
        tokens = len(str(meta)) // 4 + 8
        return ToolBundle(tools=(meta,), estimated_tokens=tokens)

    def search(self, query: str, top_k: int = 3) -> list[ToolSpec]:
        """关键词匹配：名字/tags/描述命中，按命中数排序。"""
        q = query.lower()
        scored: list[tuple[int, ToolSpec]] = []
        for tool in self._tools.values():
            hay = f"{tool.name} {' '.join(tool.tags)} {tool.description}".lower()
            score = sum(1 for word in q.split() if word in hay)
            if score:
                scored.append((score, tool))
        scored.sort(key=lambda x: (-x[0], x[1].name))
        return [t for _, t in scored[:top_k]]

    def expand(self, names: list[str]) -> ToolBundle:
        """把命中的工具展开成完整 schema 注入。"""
        expanded = [self._tools[n] for n in names if n in self._tools]
        tools = tuple(
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in expanded
        )
        tokens = sum(t.estimated_tokens() for t in expanded)
        return ToolBundle(tools=tools, estimated_tokens=tokens)

    def handle(self, query: str, top_k: int = 3) -> ToolBundle:
        """一次调用：搜索 + 展开。"""
        hits = self.search(query, top_k)
        return self.expand([t.name for t in hits])
