"""DocIngest 统一入口：调试/真实数据隔离 + 表结构摘要 + 来源标注。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packages.core.errors import HuiQiaoError

from .parsers import ParserRegistry


class DebugDataIsolation(HuiQiaoError):
    code = "HQ303"


@dataclass
class TableSummary:
    name: str
    columns: list[str]
    row_count: int

    def to_markdown(self) -> str:
        return f"- {self.name}: {self.row_count} 行，列 {', '.join(self.columns)}"


@dataclass
class IngestResult:
    source: str
    markdown: str
    tables: list[TableSummary] = field(default_factory=list)
    is_debug: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_context(self) -> str:
        head = f"[来源: {self.source}]"
        if self.is_debug:
            head += " [调试数据，非生产]"
        table_text = "\n".join(t.to_markdown() for t in self.tables)
        return f"{head}\n\n{self.markdown}" + (f"\n\n表结构:\n{table_text}" if table_text else "")


class DocIngest:
    def __init__(self, registry: ParserRegistry | None = None, *, allow_debug: bool = True) -> None:
        self.registry = registry or ParserRegistry.default()
        self.allow_debug = allow_debug

    def ingest(
        self,
        path: str | Path,
        *,
        is_debug: bool = False,
        max_lines: int = 2000,
        base_dir: str | Path | None = None,
    ) -> IngestResult:
        """调试数据必须显式标记；base_dir 限制可读范围。"""
        if is_debug and not self.allow_debug:
            raise DebugDataIsolation("当前实例不允许调试数据")

        p = Path(path)
        if base_dir:
            root = Path(base_dir).resolve()
            if root not in p.resolve().parents and p.resolve() != root:
                raise DebugDataIsolation(f"路径越出 base_dir: {p}")

        parser = self.registry.get(p)
        if parser is None:
            raise HuiQiaoError(f"不支持的格式: {p.suffix}")

        md = parser.parse(p, max_lines=max_lines)
        tables = self._summarize_csv(p) if p.suffix.lower() == ".csv" else []
        return IngestResult(
            source=str(p),
            markdown=md,
            tables=tables,
            is_debug=is_debug,
            metadata={"lines_limit": max_lines, "parser": type(parser).__name__},
        )

    @staticmethod
    def _summarize_csv(path: Path) -> list[TableSummary]:
        import csv

        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                return []
            count = sum(1 for _ in reader)
        return [TableSummary(name=path.stem, columns=header, row_count=count)]
