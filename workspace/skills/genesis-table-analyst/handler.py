"""创世种子技能 3：本地 CSV/TSV 表格清洗审计与精确统计（纯标准库零外部依赖）."""

from __future__ import annotations

import csv
import io
import pathlib
import statistics
from collections import Counter
from typing import Any

from packages.core.contracts import TaskEnvelope


def _try_float(val: str) -> float | None:
    cleaned = val.strip().replace(",", "").lstrip("¥$￥")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def execute(envelope: TaskEnvelope, state: dict[str, Any]) -> dict[str, Any]:
    attachments = list(envelope.input.attachments) if envelope.input else []
    csv_text = ""
    source_label = "内联 CSV 数据"

    if attachments:
        p = pathlib.Path(attachments[0])
        if not p.exists() or not p.is_file():
            return {
                "summary": f"未找到表格文件：`{p}`",
                "row_count": 0,
                "model_notes": "请检查本地 CSV/TSV 文件路径是否正确。",
            }
        csv_text = p.read_text(encoding="utf-8-sig", errors="replace")
        source_label = str(p)
    else:
        raw = (envelope.raw_input or (envelope.input.text if envelope.input else "")).strip()
        if "," in raw or "\t" in raw:
            csv_text = raw

    if not csv_text.strip():
        return {
            "summary": "请附带一个本地 `.csv`/`.tsv` 文件路径，或直接在输入中粘贴逗号分隔表格内容。",
            "row_count": 0,
            "model_notes": "未检测到可解析表格载荷。",
        }

    delimiter = "\t" if ("\t" in csv_text.splitlines()[0] and "," not in csv_text.splitlines()[0]) else ","
    reader = csv.reader(io.StringIO(csv_text), delimiter=delimiter)
    rows = [r for r in reader if any(cell.strip() for cell in r)]
    if not rows:
        return {"summary": "表格为空，无有效数据行。", "row_count": 0}

    headers = [h.strip() or f"col_{i+1}" for i, h in enumerate(rows[0])]
    data_rows = rows[1:]
    row_count = len(data_rows)
    seen_rows: set[tuple[str, ...]] = set()
    duplicate_rows = 0
    cleaned_rows: list[list[str]] = [headers]

    missing_by_col: dict[str, int] = {h: 0 for h in headers}
    numeric_vals: dict[str, list[float]] = {h: [] for h in headers}
    cat_vals: dict[str, Counter[str]] = {h: Counter() for h in headers}

    for r in data_rows:
        padded = [(r[i].strip() if i < len(r) else "") for i in range(len(headers))]
        sig = tuple(padded)
        if sig in seen_rows:
            duplicate_rows += 1
        else:
            seen_rows.add(sig)
            cleaned_rows.append(padded)

        for idx, h in enumerate(headers):
            cell = padded[idx]
            if cell == "" or cell.lower() in {"na", "n/a", "null", "none", "-"}:
                missing_by_col[h] += 1
                continue
            num = _try_float(cell)
            if num is not None:
                numeric_vals[h].append(num)
            else:
                cat_vals[h][cell] += 1

    lines = [
        "# 本地表格清洗与统计报告",
        f"- **数据源**：`{source_label}`",
        f"- **总数据行数**：{row_count} 行 | **字段数**：{len(headers)} 列（`{', '.join(headers)}`）",
        f"- **重复行检测**：发现 {duplicate_rows} 行完全重复记录（去重后净余 {len(cleaned_rows) - 1} 行）",
        "",
        "## 字段质量与统计明细",
    ]

    stats_dict: dict[str, dict[str, Any]] = {}
    for h in headers:
        miss = missing_by_col[h]
        nums = numeric_vals[h]
        if nums and len(nums) >= max(1, (row_count - miss) // 2):
            col_stat = {
                "type": "numeric",
                "count": len(nums),
                "missing": miss,
                "sum": round(sum(nums), 4),
                "mean": round(statistics.mean(nums), 4),
                "median": round(statistics.median(nums), 4),
                "min": round(min(nums), 4),
                "max": round(max(nums), 4),
            }
            stats_dict[h] = col_stat
            lines.append(
                f"- **`{h}`**（数值列，有效 {len(nums)}，缺失 {miss}）："
                f"总和 = `{col_stat['sum']}` | 均值 = `{col_stat['mean']}` | "
                f"中位数 = `{col_stat['median']}` | 范围 `[{col_stat['min']}, {col_stat['max']}]`"
            )
        else:
            top3 = ", ".join(f"{k}({v})" for k, v in cat_vals[h].most_common(3)) or "无有效值"
            stats_dict[h] = {"type": "categorical", "missing": miss, "top": dict(cat_vals[h].most_common(3))}
            lines.append(f"- **`{h}`**（分类/文本列，缺失 {miss}）：高频分布 {top3}")

    out_buf = io.StringIO()
    csv.writer(out_buf, lineterminator="\n").writerows(cleaned_rows)
    report_md = "\n".join(lines)

    return {
        "summary": report_md,
        "row_count": row_count,
        "deduped_row_count": len(cleaned_rows) - 1,
        "duplicate_rows": duplicate_rows,
        "columns": headers,
        "column_stats": stats_dict,
        "artifact_name": "cleaned_table.csv",
        "artifact_content": out_buf.getvalue(),
        "model_notes": "由 Python 标准库确定性引擎计算完成，去重清洗副本已保存为运行产物。",
    }
