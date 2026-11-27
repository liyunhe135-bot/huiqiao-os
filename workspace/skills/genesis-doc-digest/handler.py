"""创世种子技能 1：本地多格式文档精华提炼（联动 M03 DocIngest，100% 离线只读）."""

from __future__ import annotations

import pathlib
import re
from typing import Any

from packages.core.contracts import TaskEnvelope
from packages.doc_ingest.ingest import DocIngest


def _extract_highlights(markdown_text: str, max_bullets: int = 6) -> tuple[list[str], list[str]]:
    headings: list[str] = []
    key_lines: list[str] = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            headings.append(re.sub(r"^#+\s*", "", line))
        elif len(line) >= 8 and not line.startswith("| ---") and not line.startswith("```"):
            cleaned = re.sub(r"^[-*•\d.)\s]+", "", line).strip()
            if cleaned and cleaned not in key_lines:
                key_lines.append(cleaned[:140])
    return headings[:6], key_lines[:max_bullets]


def execute(envelope: TaskEnvelope, state: dict[str, Any]) -> dict[str, Any]:
    attachments = list(envelope.input.attachments) if envelope.input else []
    raw_text = (envelope.raw_input or (envelope.input.text if envelope.input else "")).strip()
    ingestor = DocIngest()

    sections: list[str] = ["# 本地文档精华提炼报告"]
    parsed_sources: list[str] = []
    total_chars = 0

    for item in attachments:
        p = pathlib.Path(item)
        if not p.exists() or not p.is_file():
            sections.append(f"\n## [未找到文件] `{p.name}`\n- 路径不存在或不可读：`{p}`")
            continue
        res = ingestor.ingest(p)
        parsed_sources.append(str(p))
        total_chars += len(res.markdown)
        headings, highlights = _extract_highlights(res.markdown)
        sections.append(f"\n## 来源：`{p.name}`")
        sections.append(f"- **路径**：`{p}`（解析器：`{res.metadata.get('parser', 'Auto')}`，字符数：{len(res.markdown)}）")
        if headings:
            sections.append(f"- **章节脉络**：{' / '.join(headings)}")
        if res.tables:
            for tbl in res.tables:
                sections.append(f"- **内含数据表**：{tbl.to_markdown().lstrip('- ')}")
        if highlights:
            sections.append("- **核心要点提炼**：")
            for hl in highlights:
                sections.append(f"  - {hl}")

    if not attachments:
        total_chars = len(raw_text)
        headings, highlights = _extract_highlights(raw_text)
        sections.append("\n## 来源：内联输入文本")
        sections.append(f"- **字符数**：{total_chars}")
        if headings:
            sections.append(f"- **结构脉络**：{' / '.join(headings)}")
        if highlights:
            sections.append("- **核心要点提炼**：")
            for hl in highlights:
                sections.append(f"  - {hl}")

    summary_md = "\n".join(sections)
    return {
        "summary": summary_md,
        "doc_count": len(parsed_sources) or (1 if raw_text else 0),
        "total_chars": total_chars,
        "sources": parsed_sources,
        "artifact_name": "doc_digest_report.md",
        "artifact_content": summary_md,
        "model_notes": "已通过 M03 DocIngest 在本地离线完成只读提炼，所有要点均可回溯至原文件。",
    }
