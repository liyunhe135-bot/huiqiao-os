"""M08 (B07) 沙箱静态 AST 门禁、环境变量脱敏与工作区路径安全校验."""

from __future__ import annotations

import ast
import pathlib
import re
from typing import Iterable

from packages.governance.evidence import DEFAULT_SENSITIVE_KEYWORDS, PathGuard

T1_ALLOWED_IMPORTS: frozenset[str] = frozenset(
    {
        "base64",
        "bisect",
        "collections",
        "csv",
        "datetime",
        "decimal",
        "fractions",
        "functools",
        "hashlib",
        "heapq",
        "itertools",
        "json",
        "math",
        "re",
        "statistics",
        "string",
        "textwrap",
    }
)

T1_FORBIDDEN_CALLS: frozenset[str] = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "getattr",
        "globals",
        "help",
        "input",
        "locals",
        "memoryview",
        "open",
        "setattr",
        "type",
        "vars",
    }
)

SECRET_ENV_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(api[_-]?key|secret|token|password|passwd|credential|private[_-]?key|cookie|auth)", re.I),
    re.compile(r"^(aws|gcp|azure|openai|anthropic|gemini|github|gitlab|hf|hugging)_", re.I),
)

_SENSITIVE_EXTRA_KEYWORDS: tuple[str, ...] = DEFAULT_SENSITIVE_KEYWORDS + (
    "/etc/hosts",
    "/proc/",
    "/root/",
    "system32",
    "ntds.dit",
)


def validate_workspace_path(
    workspace_dir: str | pathlib.Path | None,
    *,
    allowed_roots: Iterable[str | pathlib.Path] = (),
) -> tuple[bool, str | None, pathlib.Path | None]:
    """校验沙箱工作区路径：禁敏感宿主目录、禁穿越越界、统一解析真实路径。"""
    if workspace_dir is None:
        return True, None, None

    raw = str(workspace_dir).strip()
    if not raw:
        return True, None, None

    guard = PathGuard(
        allowed_roots=allowed_roots,
        sensitive_keywords=DEFAULT_SENSITIVE_KEYWORDS,
    )
    is_sens, kw = guard.is_sensitive(raw)
    if is_sens:
        return False, f"SENSITIVE_WORKSPACE_BLOCKED:{kw}", None

    resolved = pathlib.Path(raw).expanduser().resolve(strict=False)
    is_sens_res, kw_res = guard.is_sensitive(resolved)
    if is_sens_res:
        return False, f"SENSITIVE_WORKSPACE_BLOCKED:{kw_res}", None

    # 拒绝把整个系统根目录（/ 或 C:\）挂载为工作区
    if resolved == resolved.parent:
        return False, "ROOT_DIRECTORY_MOUNT_FORBIDDEN", None

    if allowed_roots and not guard.is_within_allowed(resolved):
        return False, "WORKSPACE_OUTSIDE_ALLOWED_ROOTS", None

    return True, None, resolved


def sanitize_user_env(env_vars: dict[str, str] | None) -> dict[str, str]:
    """仅保留显式传入且不含敏感凭证命名的安全环境变量，绝不继承宿主 os.environ。"""
    clean: dict[str, str] = {}
    if not env_vars:
        return clean
    for key, value in env_vars.items():
        k = str(key).strip()
        if not k or "\x00" in k or "\n" in k:
            continue
        if any(pat.search(k) for pat in SECRET_ENV_PATTERNS):
            continue
        v = str(value)
        if "\x00" in v:
            continue
        clean[k] = v
    return clean


def analyze_t1_python_ast(code: str) -> list[str]:
    """T1 零文件/零网络纯计算静态 AST 强校验。返回违规项列表（空表示通过）。"""
    violations: list[str] = []
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        return [f"SYNTAX_ERROR:{exc.msg} (line {exc.lineno})"]

    for node in ast.walk(tree):
        # 1. 禁止所有 Import / ImportFrom 超出纯计算白名单
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_mod = alias.name.split(".")[0]
                if root_mod not in T1_ALLOWED_IMPORTS:
                    violations.append(f"T1_FORBIDDEN_IMPORT:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                violations.append("T1_RELATIVE_IMPORT_FORBIDDEN")
            elif node.module:
                root_mod = node.module.split(".")[0]
                if root_mod not in T1_ALLOWED_IMPORTS:
                    violations.append(f"T1_FORBIDDEN_IMPORT:{node.module}")
            else:
                violations.append("T1_UNKNOWN_IMPORT_FORBIDDEN")

        # 2. 彻底封死所有双下划线属性逃逸（__class__ / __mro__ / __subclasses__ / __globals__ 等）
        #    以及 C 层可绕过 AST 访问属性的 str.format / format_map
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") or node.attr.endswith("__") or node.attr.startswith("_"):
                violations.append(f"T1_DUNDER_OR_PRIVATE_ATTR_FORBIDDEN:{node.attr}")
            elif node.attr in ("format", "format_map"):
                violations.append(f"T1_FORMAT_ATTR_ESCAPE_FORBIDDEN:{node.attr}")

        # 3. 封死双下划线标识符访问与危险内置函数名
        elif isinstance(node, ast.Name):
            if node.id.startswith("__") and node.id.endswith("__"):
                violations.append(f"T1_DUNDER_NAME_FORBIDDEN:{node.id}")
            elif node.id in T1_FORBIDDEN_CALLS:
                violations.append(f"T1_FORBIDDEN_BUILTIN:{node.id}")

        # 4. 禁止在 T1 内定义或篡改私有/双下划线函数或类属性
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("_"):
                violations.append(f"T1_PRIVATE_DEF_FORBIDDEN:{node.name}")

        # 5. 禁止 global / nonlocal 破坏隔离作用域
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            violations.append("T1_SCOPE_ESCAPE_FORBIDDEN")

        # 6. 禁止调用黑名单（兜底检查）
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in T1_FORBIDDEN_CALLS:
                violations.append(f"T1_FORBIDDEN_CALL:{node.func.id}")

    # 去重保序
    return list(dict.fromkeys(violations))
