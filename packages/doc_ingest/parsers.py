"""可插拔解析器：内置文本/Markdown/CSV 用标准库；PDF/Word/Excel 留可选依赖。

设计原则：装不起 PyMuPDF/python-docx 的机器也能跑通全链路（用 mock 解析器验证），
不因为缺一个重依赖就卡死 M03。
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Protocol

from packages.core.errors import HuiQiaoError


class Parser(Protocol):
    extensions: tuple[str, ...]

    def parse(self, path: Path, *, max_lines: int = 2000) -> str: ...


class _BaseParser:
    extensions: tuple[str, ...] = ()

    @staticmethod
    def _read_lines(path: Path, encoding: str, max_lines: int) -> str:
        """按行读取，防止大文件一次塞爆上下文。"""
        out: list[str] = []
        with path.open("r", encoding=encoding, errors="replace") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    out.append(f"\n[已截断：超过 {max_lines} 行]")
                    break
                out.append(line.rstrip("\n"))
        return "\n".join(out)


class TextParser(_BaseParser):
    extensions = (".txt", ".log")

    def parse(self, path: Path, *, max_lines: int = 2000) -> str:
        return self._read_lines(path, "utf-8", max_lines)


class MarkdownParser(_BaseParser):
    extensions = (".md", ".markdown")

    def parse(self, path: Path, *, max_lines: int = 2000) -> str:
        return self._read_lines(path, "utf-8", max_lines)


class CsvParser(_BaseParser):
    extensions = (".csv",)

    def parse(self, path: Path, *, max_lines: int = 2000) -> str:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
            reader = csv.reader(f)
            rows: list[str] = []
            for i, row in enumerate(reader):
                if i >= max_lines:
                    rows.append(f"| [已截断：超过 {max_lines} 行] |")
                    break
                if i == 0:
                    rows.append("| " + " | ".join(row) + " |")
                    rows.append("| " + " | ".join("---" for _ in row) + " |")
                else:
                    rows.append("| " + " | ".join(row) + " |")
        return "\n".join(rows)


class MockBinaryParser(_BaseParser):
    """PDF/DOCX/XLSX 的离线替身：不依赖重库，验证流水线用。"""

    extensions = (".pdf", ".docx", ".xlsx", ".xls")

    def parse(self, path: Path, *, max_lines: int = 2000) -> str:
        return f"[MockBinaryParser 解析 {path.name}，真实解析需装可选依赖]"


class ParserRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, Parser] = {}

    def register(self, parser: Parser) -> None:
        for ext in parser.extensions:
            self._parsers[ext.lower()] = parser

    @classmethod
    def default(cls, *, mock_binary: bool = True) -> "ParserRegistry":
        reg = cls()
        reg.register(TextParser())
        reg.register(MarkdownParser())
        reg.register(CsvParser())
        if mock_binary:
            reg.register(MockBinaryParser())
        return reg

    def get(self, path: Path) -> Parser | None:
        return self._parsers.get(path.suffix.lower())
