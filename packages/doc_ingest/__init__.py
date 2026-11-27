"""B06-DocIngest 本地全格式文档解析：离线转结构化 Markdown + 表结构摘要。"""

from .parsers import Parser, TextParser, MarkdownParser, CsvParser, ParserRegistry
from .ingest import IngestResult, TableSummary, DocIngest

__all__ = [
    "Parser",
    "TextParser",
    "MarkdownParser",
    "CsvParser",
    "ParserRegistry",
    "IngestResult",
    "TableSummary",
    "DocIngest",
]
