"""创世种子技能 2：文件夹安全分类与重命名预览（零盲删、默认只出预览 + Unified Diff）."""

from __future__ import annotations

import pathlib
import shutil
from collections import defaultdict
from typing import Any

from packages.core.contracts import TaskEnvelope, WorkMode
from packages.governance.evidence import generate_unified_diff

_CATEGORY_MAP: dict[str, tuple[str, ...]] = {
    "01_文档资料": (".md", ".txt", ".pdf", ".doc", ".docx", ".rtf", ".ppt", ".pptx"),
    "02_表格数据": (".csv", ".tsv", ".xls", ".xlsx", ".json", ".yaml", ".yml", ".sqlite", ".db"),
    "03_图像媒体": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".mp3", ".wav", ".mp4", ".mov"),
    "04_代码脚本": (".py", ".js", ".ts", ".html", ".css", ".ps1", ".sh", ".sql", ".toml"),
    "05_压缩归档": (".zip", ".7z", ".rar", ".tar", ".gz"),
}


def _classify_ext(ext: str) -> str:
    ext_l = ext.lower()
    for folder, exts in _CATEGORY_MAP.items():
        if ext_l in exts:
            return folder
    return "06_其他文件"


def execute(envelope: TaskEnvelope, state: dict[str, Any]) -> dict[str, Any]:
    attachments = list(envelope.input.attachments) if envelope.input else []
    target_dir = pathlib.Path(attachments[0]) if attachments else None
    if target_dir is None or not target_dir.exists() or not target_dir.is_dir():
        return {
            "summary": "请通过附件参数提供一个存在的本地文件夹路径以生成安全分类预览。",
            "file_count": 0,
            "applied": False,
            "model_notes": "未检测到有效目录路径，未做任何磁盘操作。",
        }

    files = sorted([p for p in target_dir.iterdir() if p.is_file()], key=lambda x: x.name.lower())
    grouped: dict[str, list[pathlib.Path]] = defaultdict(list)
    before_lines: list[str] = []
    after_lines: list[str] = []
    move_plan: list[tuple[pathlib.Path, pathlib.Path]] = []

    for f in files:
        cat = _classify_ext(f.suffix)
        grouped[cat].append(f)
        dest = target_dir / cat / f.name
        idx = 1
        while dest.exists() and dest != f:
            dest = target_dir / cat / f"{f.stem}_{idx}{f.suffix}"
            idx += 1
        before_lines.append(f.name)
        after_lines.append(f"{cat}/{dest.name}")
        move_plan.append((f, dest))

    diff_preview = generate_unified_diff(
        str(target_dir / "folder_layout.manifest"),
        "\n".join(before_lines) + ("\n" if before_lines else ""),
        "\n".join(after_lines) + ("\n" if after_lines else ""),
    )

    apply_changes = bool(
        envelope.metadata.get("apply_changes", False) or state.get("apply_changes", False)
    )
    can_apply = apply_changes and envelope.constraints.work_mode == WorkMode.EXECUTE
    moved_count = 0
    if can_apply:
        for src, dst in move_plan:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            moved_count += 1

    mode_banner = (
        f"已安全归档移动 {moved_count} 个文件（0 删除）"
        if can_apply
        else "安全预览模式（未改动任何原文件，0 删除风险）"
    )
    lines = [
        f"# 文件夹安全分类方案（{mode_banner}）",
        f"- **目标目录**：`{target_dir}`",
        f"- **扫描顶层文件数**：{len(files)}",
        "",
        "## 分类汇总",
    ]
    for cat in sorted(grouped.keys()):
        sample_names = ", ".join(f"`{p.name}`" for p in grouped[cat][:5])
        more = f" 等 {len(grouped[cat])} 项" if len(grouped[cat]) > 5 else f"（共 {len(grouped[cat])} 项）"
        lines.append(f"- **{cat}** {more}：{sample_names}")

    if diff_preview:
        lines.extend(["", "## 变更预览（Unified Diff）", f"```diff\n{diff_preview}\n```"])

    report = "\n".join(lines)
    return {
        "summary": report,
        "file_count": len(files),
        "applied": can_apply,
        "moved_count": moved_count,
        "diff_preview": diff_preview,
        "artifact_name": "folder_organization_plan.md",
        "artifact_content": report,
        "model_notes": "遵循 C00 透明可逆原则：默认仅生成分类预览与 Diff，绝不执行任何删除操作。",
    }
