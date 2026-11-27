"""M11 (B09) 防坍塌双闸门核心：闸门一（独立 M08 沙箱客观回归单测）+ 闸门二（C00 增上四问一票否决）."""

from __future__ import annotations

import ast
import re
import tempfile
import time
import pathlib
from typing import Callable

import yaml

from packages.core.constitution import evaluate_uplift_audit
from packages.core.contracts import SandboxTier, SkillManifest, UpliftAuditResult
from packages.evolution.models import ObjectiveGateReport
from packages.sandbox import SandboxLimits, SandboxManager, SandboxRequest

_SKILL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,60}$")

# 普惠离线技能 handler.py 静态安全黑名单（严禁在自演化技能中偷渡外网/Shell/FFI/裸 eval 后门）
_FORBIDDEN_SKILL_IMPORTS: frozenset[str] = frozenset(
    {
        "socket",
        "ssl",
        "urllib",
        "http",
        "ftplib",
        "smtplib",
        "requests",
        "httpx",
        "subprocess",
        "ctypes",
        "cffi",
        "pty",
        "webbrowser",
        "winreg",
    }
)
_FORBIDDEN_SKILL_CALLS: frozenset[str] = frozenset({"eval", "exec", "compile", "__import__"})
_FORBIDDEN_SKILL_ATTRS: frozenset[str] = frozenset({"system", "popen", "rmtree", "fork", "startfile"})

# C00 增上四问确定性红线词库（任何一项命中即触发一票否决；避免误伤“反人矿/拒绝人矿化”等正向宣导）
_A1_AGENCY_VIOLATIONS: tuple[str, ...] = (
    "绕过用户",
    "隐瞒用户",
    "暗中执行",
    "诱导沉迷",
    "成瘾机制",
    "当成人矿",
    "变成人矿",
    "视作人矿",
    "压榨人矿",
    "沦为人矿",
    "强制锁死",
    "bypass_consent",
    "hide_from_user",
    "dark_pattern",
)
_A2_A4_HARM_VIOLATIONS: tuple[str, ...] = (
    "窃取密码",
    "窃取凭证",
    "隐私外传",
    "勒索加密",
    "木马后门",
    "静默删除",
    "exfiltrate",
    "keylogger",
    "ransomware",
    "steal_token",
    "vendor_lockin",
)
_OBFUSCATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"base64\.b64decode\s*\(.*?\).*?(exec|eval)", re.DOTALL | re.I),
    re.compile(r"codecs\.decode\s*\(.*?rot_?13", re.DOTALL | re.I),
)


def inspect_handler_static_security(handler_code: str) -> list[str]:
    """对自演化候选 handler.py 执行确定性 AST 静态安全检查，返回违规列表。"""
    issues: list[str] = []
    try:
        tree = ast.parse(handler_code, mode="exec")
    except SyntaxError as exc:
        return [f"HANDLER_SYNTAX_ERROR:{exc.msg} (line {exc.lineno})"]

    has_execute_fn = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "execute":
            has_execute_fn = True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                root_mod = alias.name.split(".")[0]
                if root_mod in _FORBIDDEN_SKILL_IMPORTS:
                    issues.append(f"FORBIDDEN_IMPORT:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_mod = node.module.split(".")[0]
                if root_mod in _FORBIDDEN_SKILL_IMPORTS:
                    issues.append(f"FORBIDDEN_IMPORT:{node.module}")
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _FORBIDDEN_SKILL_CALLS:
                issues.append(f"FORBIDDEN_CALL:{node.func.id}")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in _FORBIDDEN_SKILL_ATTRS:
                issues.append(f"FORBIDDEN_ATTR_CALL:{node.func.attr}")

    if not has_execute_fn:
        issues.append("MISSING_EXECUTE_ENTRYPOINT:handler.py must define def execute(envelope, state)")

    return list(dict.fromkeys(issues))


def run_objective_sandbox_gate(
    *,
    manifest_yaml: str,
    skill_markdown: str,
    handler_code: str,
    smoke_test_code: str,
    sandbox: SandboxManager | None = None,
    timeout_sec: float = 12.0,
) -> ObjectiveGateReport:
    """闸门一：契约校验 + 静态安全扫描 + 独立 M08 离线沙箱（T2）实跑冒烟单测。"""
    started = time.perf_counter()
    issues: list[str] = []
    schema_valid = False

    # 1. Manifest 契约强校验
    try:
        raw_manifest = yaml.safe_load(manifest_yaml) or {}
        manifest = SkillManifest.model_validate(raw_manifest)
        if not _SKILL_ID_RE.match(manifest.skill_id):
            issues.append(f"INVALID_SKILL_ID_SLUG:{manifest.skill_id}")
        else:
            schema_valid = True
    except Exception as exc:
        issues.append(f"MANIFEST_SCHEMA_INVALID:{exc}")

    # 2. SKILL.md 人类可读说明校验
    if len((skill_markdown or "").strip()) < 30:
        issues.append("SKILL_MD_TOO_SHORT:必须提供人类可读的用途、步骤与边界说明(>=30字)")

    # 3. handler.py AST 静态安全检查
    sec_issues = inspect_handler_static_security(handler_code)
    static_ok = len(sec_issues) == 0
    issues.extend(sec_issues)

    # 4. smoke_test_code 语法预检
    try:
        ast.parse(smoke_test_code, mode="exec")
    except SyntaxError as exc:
        issues.append(f"SMOKE_TEST_SYNTAX_ERROR:{exc.msg} (line {exc.lineno})")

    if issues:
        return ObjectiveGateReport(
            passed=False,
            sandbox_tier_used=SandboxTier.T2_OS_RESTRICTED,
            exit_code=126,
            stderr="; ".join(issues),
            elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
            schema_valid=schema_valid,
            static_security_ok=static_ok,
            issues=issues,
        )

    # 5. 在真实 M08 T2_OS_RESTRICTED 离线沙箱中独立运行 handler.py + tests_smoke.py
    mgr = sandbox or SandboxManager(offline_only=True)
    with tempfile.TemporaryDirectory(prefix="hq_m11_gate1_") as tmpdir:
        ws = pathlib.Path(tmpdir).resolve()
        (ws / "handler.py").write_text(handler_code, encoding="utf-8")
        (ws / "tests_smoke.py").write_text(smoke_test_code, encoding="utf-8")

        harness = (
            "import importlib.util, pathlib, sys, types\n"
            "# 在完全隔离的 T2 沙箱内提供极简纯内存契约类型桩（不暴露任何宿主文件系统）\n"
            "_p = types.ModuleType('packages')\n"
            "_pc = types.ModuleType('packages.core')\n"
            "_pcc = types.ModuleType('packages.core.contracts')\n"
            "for _sym in ('TaskEnvelope', 'TaskInput', 'TaskConstraints', 'WorkMode', 'SkillManifest', 'StepInput', 'StepOutput'):\n"
            "    setattr(_pcc, _sym, type(_sym, (types.SimpleNamespace,), {}))\n"
            "_p.core = _pc; _pc.contracts = _pcc\n"
            "sys.modules['packages'] = _p; sys.modules['packages.core'] = _pc; sys.modules['packages.core.contracts'] = _pcc\n"
            "spec = importlib.util.spec_from_file_location('candidate_handler', pathlib.Path('handler.py'))\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "assert callable(getattr(mod, 'execute', None)), 'handler.py 缺少 execute'\n"
            "# 基础契约烟雾调用（模拟离线无重依赖环境）\n"
            "dummy_env = types.SimpleNamespace(\n"
            "    raw_input='测试输入样例',\n"
            "    input=types.SimpleNamespace(text='测试输入样例', attachments=[]),\n"
            "    constraints=types.SimpleNamespace(work_mode='ask', offline_only=True),\n"
            "    metadata={},\n"
            ")\n"
            "base_out = mod.execute(dummy_env, {})\n"
            "assert isinstance(base_out, dict), 'execute 必须返回 dict'\n"
            "assert 'summary' in base_out and isinstance(base_out['summary'], str), '返回 dict 必须含字符串 summary'\n"
            "# 运行技能自带独立客观测试用例\n"
            "test_ns = {'__name__': '__main__', 'handler': mod, 'execute': mod.execute, 'types': types}\n"
            "exec(compile(pathlib.Path('tests_smoke.py').read_text(encoding='utf-8'), 'tests_smoke.py', 'exec'), test_ns)\n"
            "print('GATE1_OBJECTIVE_PASS')\n"
        )
        res = mgr.run(
            SandboxRequest(
                code=harness,
                language="python",
                tier=SandboxTier.T2_OS_RESTRICTED,
                workspace_dir=str(ws),
                limits=SandboxLimits(
                    timeout_sec=timeout_sec,
                    max_memory_mb=256,
                    allow_network=False,
                    read_only_workspace=False,
                ),
                work_mode="execute",
            )
        )

    passed = bool(res.ok and "GATE1_OBJECTIVE_PASS" in res.stdout and not res.blocked and not res.timed_out)
    run_issues: list[str] = []
    if not passed:
        run_issues.append(res.blocked_reason or res.killed_reason or f"SANDBOX_EXIT_{res.exit_code}")

    return ObjectiveGateReport(
        passed=passed,
        sandbox_tier_used=res.tier_used,
        exit_code=res.exit_code,
        stdout=res.stdout[:2000],
        stderr=res.stderr[:2000],
        elapsed_ms=round((time.perf_counter() - started) * 1000.0, 2),
        schema_valid=schema_valid,
        static_security_ok=static_ok,
        issues=run_issues,
    )


ExtraAuditFn = Callable[[dict[str, str]], dict[str, bool] | None]


def run_constitution_uplift_gate(
    *,
    name: str,
    description: str,
    manifest_yaml: str,
    skill_markdown: str,
    handler_code: str,
    portable_lite_ready: bool = True,
    extra_auditor_fn: ExtraAuditFn | None = None,
) -> UpliftAuditResult:
    """闸门二：C00 众生和谐增上四问一票否决审查（确定性红线 + 可选模型复核）。"""
    combined_lower = "\n".join(
        [name, description, manifest_yaml, skill_markdown, handler_code]
    ).lower()

    reasons: list[str] = []
    suggestions: list[str] = []

    # 1. A1 人类主体性与反人矿检查
    preserves_human_agency = True
    for kw in _A1_AGENCY_VIOLATIONS:
        if kw.lower() in combined_lower:
            preserves_human_agency = False
            reasons.append(f"触发 A1 主体性红线词 '{kw}'")
            break

    # 2. A2/A4 非对立、无伤害、无外传/黑盒锁死检查
    no_harm_or_lockin = True
    for kw in _A2_A4_HARM_VIOLATIONS:
        if kw.lower() in combined_lower:
            no_harm_or_lockin = False
            reasons.append(f"触发 A2/A4 无伤害与非锁死红线词 '{kw}'")
            break
    sec_issues = inspect_handler_static_security(handler_code)
    if any(i.startswith(("FORBIDDEN_IMPORT:", "FORBIDDEN_ATTR_CALL:", "FORBIDDEN_CALL:")) for i in sec_issues):
        no_harm_or_lockin = False
        reasons.append(f"代码含越权联网/破坏性调用: {sec_issues[0]}")

    # 3. A3 强扶弱与普惠可教学性检查
    enables_uplift = True
    md_stripped = (skill_markdown or "").strip()
    if len(md_stripped) < 30:
        enables_uplift = False
        reasons.append("缺少可供普通用户理解与学习的 SKILL.md 说明")
    if not portable_lite_ready:
        suggestions.append("建议精简重依赖以支持低配 8GB/CPU 设备普惠复用（portable_lite_ready=true）")

    # 4. 透明可审阅与可逆底线检查
    transparent_and_reversible = True
    for pat in _OBFUSCATION_PATTERNS:
        if pat.search(handler_code):
            transparent_and_reversible = False
            reasons.append("检测到混淆/隐藏执行载荷，违背开源透明底线")
            break
    if "os.remove" in handler_code or "os.unlink" in handler_code:
        transparent_and_reversible = False
        reasons.append("技能代码含不可逆文件删除调用（os.remove/unlink），违背可逆安全底线")

    # 可选叠加额外模型定性审查（只允许更严格，严禁覆盖确定性否决！）
    if extra_auditor_fn is not None:
        extra = extra_auditor_fn(
            {
                "name": name,
                "description": description,
                "skill_markdown": skill_markdown,
                "handler_code": handler_code,
            }
        )
        if isinstance(extra, dict):
            preserves_human_agency = preserves_human_agency and bool(extra.get("preserves_human_agency", True))
            no_harm_or_lockin = no_harm_or_lockin and bool(extra.get("no_harm_or_lockin", True))
            enables_uplift = enables_uplift and bool(extra.get("enables_uplift_and_accessibility", True))
            transparent_and_reversible = transparent_and_reversible and bool(
                extra.get("transparent_and_reversible", True)
            )

    return evaluate_uplift_audit(
        preserves_human_agency=preserves_human_agency,
        no_harm_or_lockin=no_harm_or_lockin,
        enables_uplift_and_accessibility=enables_uplift,
        transparent_and_reversible=transparent_and_reversible,
        rationale="；".join(reasons) if reasons else "已通过 C00 增上四问与透明可逆审查",
        improvement_suggestions=suggestions,
    )
