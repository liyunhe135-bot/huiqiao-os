"""M04 路径安全隔离、客观证据闸门与 Unified Diff 变更预览."""

from __future__ import annotations

import difflib
import os
import pathlib
from dataclasses import dataclass, field
from typing import Iterable


DEFAULT_SENSITIVE_KEYWORDS: tuple[str, ...] = (
    ".ssh",
    "id_rsa",
    "id_ed25519",
    ".aws",
    ".gnupg",
    ".env",
    "credentials",
    "chrome/user data",
    "edge/user data",
    "c:/windows",
    "c:/program files",
    "/etc/passwd",
    "/etc/shadow",
    "/system/library",
)


def _normalize_path_str(raw: str | pathlib.Path, *, base_dir: pathlib.Path | None = None) -> str:
    """展开 ~ 与相对路径（解析 .. 防止路径穿越），统一转为小写 POSIX 风格字符串比对。"""
    p = pathlib.Path(os.path.expanduser(str(raw)))
    if not p.is_absolute() and base_dir is not None:
        p = base_dir / p
    # resolve(strict=False) 在路径尚不存在时同样会消除 '..' 与符号片段
    resolved = p.resolve(strict=False)
    return resolved.as_posix().lower()


class PathGuard:
    """确定性路径安全守卫：防路径穿越 + 敏感凭证死锁 + 工作区白名单。"""

    def __init__(
        self,
        *,
        allowed_roots: Iterable[str | pathlib.Path] = (),
        sensitive_keywords: Iterable[str] = DEFAULT_SENSITIVE_KEYWORDS,
        base_dir: pathlib.Path | None = None,
    ) -> None:
        self.base_dir = base_dir.resolve() if base_dir else pathlib.Path.cwd().resolve()
        self.allowed_roots = tuple(
            _normalize_path_str(r, base_dir=self.base_dir).rstrip("/")
            for r in allowed_roots
        )
        self.sensitive_keywords = tuple(k.replace("\\", "/").lower() for k in sensitive_keywords)

    def is_sensitive(self, target_path: str | pathlib.Path) -> tuple[bool, str]:
        raw_norm = str(target_path).replace("\\", "/").lower()
        resolved_norm = _normalize_path_str(target_path, base_dir=self.base_dir)
        for kw in self.sensitive_keywords:
            if kw in raw_norm or kw in resolved_norm:
                return True, kw
        return False, ""

    def is_within_allowed(
        self,
        target_path: str | pathlib.Path,
        *,
        override_allowed_roots: Iterable[str | pathlib.Path] | None = None,
    ) -> bool:
        roots = (
            tuple(
                _normalize_path_str(r, base_dir=self.base_dir).rstrip("/")
                for r in override_allowed_roots
            )
            if override_allowed_roots is not None
            else self.allowed_roots
        )
        if not roots:
            return True
        resolved = _normalize_path_str(target_path, base_dir=self.base_dir).rstrip("/")
        for root in roots:
            if resolved == root or resolved.startswith(root + "/"):
                return True
        return False


@dataclass
class EvidenceLedger:
    """客观证据簿：仅由工具或人类审批钩子签发，防模型口头伪造通过。"""

    grants: dict[str, set[str]] = field(default_factory=dict)

    def grant(self, scope_id: str, evidence_name: str) -> None:
        self.grants.setdefault(scope_id, set()).add(evidence_name)

    def revoke(self, scope_id: str, evidence_name: str) -> None:
        if scope_id in self.grants:
            self.grants[scope_id].discard(evidence_name)

    def has(self, scope_id: str, evidence_name: str) -> bool:
        return evidence_name in self.grants.get(scope_id, set())

    def missing(self, scope_id: str, required: Iterable[str]) -> list[str]:
        present = self.grants.get(scope_id, set())
        return [item for item in required if item not in present]


def generate_unified_diff(
    file_path: str | pathlib.Path,
    old_content: str,
    new_content: str,
    *,
    max_lines: int = 80,
) -> str:
    """生成人类可读的 Unified Diff 变更预览，供 Plan / HITL 审批展示。"""
    name = str(file_path)
    diff_lines = list(
        difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
            lineterm="",
        )
    )
    if not diff_lines:
        return "(无文本差异)"
    if len(diff_lines) > max_lines:
        kept = diff_lines[:max_lines]
        kept.append(f"... (已截断其余 {len(diff_lines) - max_lines} 行差异)")
        return "\n".join(kept)
    return "\n".join(diff_lines)
