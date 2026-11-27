"""离线微型基准集框架（M02）。

三套：微型 BFCL（工具参数/诚实拒调）、微型 RULER（多跳+上下文衰减）、微型代码修复（断言）。
这里只定义结构与样例题；真实跑分需要注入本地模型 transport。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Case:
    case_id: str
    category: str  # bfcl | ruler | codefix
    prompt: str
    ctx_tokens: int = 0
    expected: Any = None
    checker: Callable[[str, Any], bool] | None = field(default=None, compare=False)

    def judge(self, answer: str) -> bool:
        if self.checker is None:
            return False
        return bool(self.checker(answer, self.expected))


class MiniSuite:
    """24 条高区分度题的容器（样例 6 条，结构可扩展到 24）。"""

    def __init__(self, cases: list[Case] | None = None) -> None:
        self.cases = cases or self.default_cases()

    @staticmethod
    def default_cases() -> list[Case]:
        return [
            Case(
                case_id="bfcl_001",
                category="bfcl",
                prompt='输出调用 get_weather 的 JSON，location="杭州"',
                expected="get_weather",
                checker=lambda ans, exp: exp in ans,
            ),
            Case(
                case_id="bfcl_002",
                category="bfcl",
                prompt="用户问今天股价，但没有提供股价工具。应该拒调。",
                expected="拒调",
                checker=lambda ans, exp: exp in ans or "无法" in ans,
            ),
            Case(
                case_id="ruler_4k",
                category="ruler",
                prompt="在多文档中找出标记 X7 的值",
                ctx_tokens=4096,
                expected="X7",
                checker=lambda ans, exp: exp in ans,
            ),
            Case(
                case_id="ruler_16k",
                category="ruler",
                prompt="在长文中找出标记 X7 的值",
                ctx_tokens=16384,
                expected="X7",
                checker=lambda ans, exp: exp in ans,
            ),
            Case(
                case_id="codefix_001",
                category="codefix",
                prompt="修复语法错误并只输出 Python 代码",
                expected="def ",
                checker=lambda ans, exp: exp in ans,
            ),
            Case(
                case_id="codefix_002",
                category="codefix",
                prompt="补全函数使断言通过",
                expected="return",
                checker=lambda ans, exp: exp in ans,
            ),
        ]

    def by_category(self, category: str) -> list[Case]:
        return [c for c in self.cases if c.category == category]
