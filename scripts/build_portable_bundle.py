"""汇桥 OS (HuiQiao OS) v1.0.0 离线便携发行包构建器（零隐私残留 + SHA-256 完整性清单 + 内置普惠技能包）."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import Any

# 允许直接通过 `python scripts/build_portable_bundle.py` 运行
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.evolution.portable import export_portable_skill  # noqa: E402

RELEASE_VERSION = "1.0.0"

_INCLUDE_DIRS = ("apps", "packages", "evals", "scripts", "config")
_INCLUDE_ROOT_FILES = ("README.md", "USER_GUIDE.md", "LICENSE", "pyproject.toml", "AGENTS.md")
_SKIP_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".vendor", "dev-meta", ".huiqiao"}
_SKIP_SUFFIXES = {".pyc", ".pyo", ".db", ".db-wal", ".db-shm", ".sqlite", ".log", ".lock"}

_HYGIENE_PATTERNS = (
    ("windows_user_path", re.compile(r"[A-Za-z]:\\Users\\[^\\]+", re.I)),
    ("secret_token", re.compile(r"sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,}")),
)


def _should_skip(path: pathlib.Path) -> bool:
    if any(part in _SKIP_DIR_NAMES for part in path.parts):
        return True
    if path.suffix.lower() in _SKIP_SUFFIXES:
        return True
    return False


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_portable_bundle(
    output_zip: pathlib.Path | str | None = None,
    *,
    include_portable_skills: bool = True,
) -> dict[str, Any]:
    """构建干净、免云端、零个人状态残留的离线便携发行包，并返回构建清单摘要。"""
    out_path = (
        pathlib.Path(output_zip).resolve()
        if output_zip is not None
        else (REPO_ROOT / "dist" / f"huiqiao-os-v{RELEASE_VERSION}-portable.zip").resolve()
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    entries: dict[str, bytes] = {}

    # 1. 收集根目录核心说明与工程配置
    for fname in _INCLUDE_ROOT_FILES:
        fp = REPO_ROOT / fname
        if fp.is_file():
            entries[fname] = fp.read_bytes()

    # 2. 收集核心代码目录
    for dname in _INCLUDE_DIRS:
        dpath = REPO_ROOT / dname
        if not dpath.is_dir():
            continue
        for fp in sorted(dpath.rglob("*")):
            if not fp.is_file() or _should_skip(fp.relative_to(REPO_ROOT)):
                continue
            rel = fp.relative_to(REPO_ROOT).as_posix()
            entries[rel] = fp.read_bytes()

    # 3. 收集纯净工作区底座（仅含 C00 宪章与创世种子技能，绝不打包个人 MEMORY.md 或运行数据库！）
    const_fp = REPO_ROOT / "workspace" / "CONSTITUTION.md"
    if const_fp.is_file():
        entries["workspace/CONSTITUTION.md"] = const_fp.read_bytes()

    skills_dir = REPO_ROOT / "workspace" / "skills"
    if skills_dir.is_dir():
        for fp in sorted(skills_dir.rglob("*")):
            if not fp.is_file() or _should_skip(fp.relative_to(REPO_ROOT)):
                continue
            rel = fp.relative_to(REPO_ROOT).as_posix()
            entries[rel] = fp.read_bytes()

    # 4. 可选将 5 个创世技能预打包为可独立分发给低配电脑的 .hqskill.zip
    exported_skill_packs: list[str] = []
    if include_portable_skills and skills_dir.is_dir():
        with tempfile.TemporaryDirectory(prefix="hq_bundle_skills_") as td:
            tp = pathlib.Path(td)
            for manifest_fp in sorted(skills_dir.glob("genesis-*/manifest.yaml")):
                sdir = manifest_fp.parent
                zname = f"{sdir.name}.hqskill.zip"
                zfile = tp / zname
                export_portable_skill(sdir, zfile, require_sandbox_verify=False)
                arc_rel = f"portable_skills/{zname}"
                entries[arc_rel] = zfile.read_bytes()
                exported_skill_packs.append(arc_rel)

    # 5. 全包文本文件隐私防泄密强制扫描
    for rel, raw in entries.items():
        if rel.endswith(".zip"):
            continue
        text = raw.decode("utf-8", errors="ignore")
        for label, pat in _HYGIENE_PATTERNS:
            if pat.search(text):
                raise ValueError(f"打包隐私门禁阻断 ({label}): {rel}")

    checksums = {rel: _sha256(raw) for rel, raw in sorted(entries.items())}
    manifest = {
        "name": "huiqiao-os",
        "version": RELEASE_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "offline_only_default": True,
        "zero_external_cdn": True,
        "file_count": len(entries),
        "portable_skill_packs": exported_skill_packs,
        "sha256": checksums,
    }

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, raw in sorted(entries.items()):
            zf.writestr(f"huiqiao-os/{rel}", raw)
        zf.writestr(
            "huiqiao-os/RELEASE_MANIFEST.json",
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )

    return {
        "zip_path": str(out_path),
        "version": RELEASE_VERSION,
        "file_count": len(entries),
        "portable_skill_packs": exported_skill_packs,
        "size_bytes": out_path.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="构建汇桥 OS v1.0.0 离线便携发行包")
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="自定义输出 zip 路径（默认 dist/huiqiao-os-v1.0.0-portable.zip）",
    )
    args = parser.parse_args()
    info = build_portable_bundle(args.output or None)
    print(
        f"[打包成功] {info['zip_path']} | 版本=v{info['version']} | "
        f"文件数={info['file_count']} | 大小={info['size_bytes'] // 1024} KB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
