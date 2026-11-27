"""M04 安全治理验收单测：18+ 条越权拦截、三档模式硬锁、路径穿越、证据闸门与 <5ms 性能校验."""

from __future__ import annotations

import pathlib
import time

import pytest

from packages.core import (
    BrickLayer,
    BrickManifest,
    BrickRegistry,
    PolicyDecision,
    PolicyHookProtocol,
    WorkMode,
)
from packages.governance import (
    EvidenceLedger,
    GovernanceGuard,
    HookPoint,
    HookVerdict,
    generate_unified_diff,
)
from packages.mcp_bus.permissions import Permission, ToolSpec

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _make_guard(tmp_path: pathlib.Path) -> GovernanceGuard:
    ws = tmp_path / "workspace"
    ws.mkdir(exist_ok=True)
    return GovernanceGuard(
        offline_only=True,
        allowed_roots=(ws,),
        base_dir=tmp_path,
    )


# === 1. WorkBuddy Ask / Plan / Execute 三档模式硬锁 ===
def test_ask_mode_allows_read_only(tmp_path: pathlib.Path) -> None:
    guard = _make_guard(tmp_path)
    tool = ToolSpec(name="fs_read", description="读文件", permission=Permission.READ)
    verdict = guard.evaluate(
        HookPoint.PRE_TOOL_USE,
        {"work_mode": WorkMode.ASK, "tool": tool, "path": str(tmp_path / "workspace" / "a.md")},
    )
    assert verdict.decision == PolicyDecision.ALLOW


def test_ask_mode_physically_denies_write_tool(tmp_path: pathlib.Path) -> None:
    guard = _make_guard(tmp_path)
    tool = ToolSpec(name="fs_write", description="写文件", permission=Permission.WRITE)
    verdict = guard.evaluate(
        HookPoint.PRE_TOOL_USE,
        {"work_mode": WorkMode.ASK, "tool": tool, "path": str(tmp_path / "workspace" / "a.md")},
    )
    assert verdict.decision == PolicyDecision.DENY
    assert "Ask" in verdict.reason


def test_ask_mode_physically_denies_execute_tool(tmp_path: pathlib.Path) -> None:
    guard = _make_guard(tmp_path)
    tool = ToolSpec(name="shell_run", description="跑命令", permission=Permission.EXECUTE)
    verdict = guard.evaluate(
        HookPoint.PRE_TOOL_USE,
        {"work_mode": "ask", "tool": tool},
    )
    assert verdict.decision == PolicyDecision.DENY


def test_ask_mode_denies_pre_write_even_if_permission_omitted(tmp_path: pathlib.Path) -> None:
    guard = _make_guard(tmp_path)
    verdict = guard.evaluate(
        HookPoint.PRE_WRITE,
        {"work_mode": WorkMode.ASK, "path": str(tmp_path / "workspace" / "note.md")},
    )
    assert verdict.decision == PolicyDecision.DENY


def test_plan_mode_requires_human_confirmation_with_diff_for_write(tmp_path: pathlib.Path) -> None:
    guard = _make_guard(tmp_path)
    target = str(tmp_path / "workspace" / "plan.md")
    verdict = guard.evaluate(
        HookPoint.PRE_WRITE,
        {
            "run_id": "run_plan",
            "work_mode": WorkMode.PLAN,
            "path": target,
            "old_content": "v1\n",
            "new_content": "v2\n",
        },
    )
    assert verdict.decision == PolicyDecision.ASK_HUMAN
    assert "plan_confirmed" in verdict.missing_evidence
    assert "-v1" in verdict.diff_preview and "+v2" in verdict.diff_preview

    # 人类确认计划后放行
    guard.evidence.grant("run_plan", "plan_confirmed")
    v2 = guard.evaluate(
        HookPoint.PRE_WRITE,
        {"run_id": "run_plan", "work_mode": WorkMode.PLAN, "path": target},
    )
    assert v2.decision == PolicyDecision.ALLOW


def test_plan_mode_denies_execute(tmp_path: pathlib.Path) -> None:
    guard = _make_guard(tmp_path)
    tool = ToolSpec(name="run_py", description="执行脚本", permission=Permission.EXECUTE)
    verdict = guard.evaluate(HookPoint.PRE_TOOL_USE, {"work_mode": WorkMode.PLAN, "tool": tool})
    assert verdict.decision == PolicyDecision.DENY


def test_execute_mode_allows_write_inside_workspace(tmp_path: pathlib.Path) -> None:
    guard = _make_guard(tmp_path)
    target = str(tmp_path / "workspace" / "ok.txt")
    verdict = guard.evaluate(
        HookPoint.PRE_WRITE,
        {
            "work_mode": WorkMode.EXECUTE,
            "path": target,
            "old_content": "hello",
            "new_content": "world",
        },
    )
    assert verdict.decision == PolicyDecision.ALLOW
    assert "+world" in verdict.diff_preview


# === 2. 路径越界、路径穿越与敏感凭证死锁（即使 Execute 模式也 100% DENY） ===
def test_execute_mode_denies_outside_whitelist(tmp_path: pathlib.Path) -> None:
    guard = _make_guard(tmp_path)
    outside = str(tmp_path / "other_folder" / "secret.txt")
    verdict = guard.evaluate(
        HookPoint.PRE_WRITE,
        {"work_mode": WorkMode.EXECUTE, "path": outside},
    )
    assert verdict.decision == PolicyDecision.DENY
    assert "白名单" in verdict.reason


def test_path_traversal_escape_blocked(tmp_path: pathlib.Path) -> None:
    guard = _make_guard(tmp_path)
    traversal = str(tmp_path / "workspace" / ".." / ".." / "evil.txt")
    verdict = guard.evaluate(
        HookPoint.PRE_WRITE,
        {"work_mode": WorkMode.EXECUTE, "path": traversal},
    )
    assert verdict.decision == PolicyDecision.DENY


@pytest.mark.parametrize(
    "bad_path",
    [
        "~/.ssh/id_rsa",
        "C:\\Users\\demo_user\\.ssh\\id_ed25519",
        "C:\\Windows\\System32\\drivers\\etc\\hosts",
        "workspace/.env",
        "C:\\Users\\demo_user\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Cookies",
    ],
)
def test_sensitive_paths_always_denied_even_for_read(
    tmp_path: pathlib.Path, bad_path: str
) -> None:
    guard = _make_guard(tmp_path)
    verdict = guard.evaluate(
        HookPoint.PRE_TOOL_USE,
        {"work_mode": WorkMode.EXECUTE, "permission": "READ", "path": bad_path},
    )
    assert verdict.decision == PolicyDecision.DENY
    assert "敏感路径" in verdict.reason


# === 3. 100% 离线网络硬拦截 ===
def test_offline_blocks_external_url_and_allows_loopback(tmp_path: pathlib.Path) -> None:
    guard = _make_guard(tmp_path)
    ext = guard.evaluate(
        HookPoint.PRE_TOOL_USE,
        {"work_mode": WorkMode.EXECUTE, "url": "https://evil.example.com/exfil"},
    )
    assert ext.decision == PolicyDecision.DENY

    local = guard.evaluate(
        HookPoint.PRE_TOOL_USE,
        {"work_mode": WorkMode.EXECUTE, "url": "http://127.0.0.1:11434/api/tags"},
    )
    assert local.decision == PolicyDecision.ALLOW


def test_offline_blocks_network_permission_tool(tmp_path: pathlib.Path) -> None:
    guard = _make_guard(tmp_path)
    verdict = guard.evaluate(
        HookPoint.PRE_TOOL_USE,
        {"work_mode": WorkMode.EXECUTE, "permission": "NETWORK"},
    )
    assert verdict.decision == PolicyDecision.DENY


# === 4. Claude Evidence Gate 与高危动作审批 ===
def test_pre_commit_evidence_gate_requires_test_passed(tmp_path: pathlib.Path) -> None:
    guard = _make_guard(tmp_path)
    denied = guard.evaluate(HookPoint.PRE_COMMIT, {"run_id": "run_c1"})
    assert denied.decision == PolicyDecision.DENY
    assert "test_passed" in denied.missing_evidence

    guard.evidence.grant("run_c1", "test_passed")
    allowed = guard.evaluate(HookPoint.PRE_COMMIT, {"run_id": "run_c1"})
    assert allowed.decision == PolicyDecision.ALLOW


def test_high_risk_delete_requires_human_approval(tmp_path: pathlib.Path) -> None:
    guard = _make_guard(tmp_path)
    target = str(tmp_path / "workspace" / "old.txt")
    ask = guard.evaluate(
        HookPoint.PRE_WRITE,
        {"run_id": "run_del", "work_mode": WorkMode.EXECUTE, "action": "delete", "path": target},
    )
    assert ask.decision == PolicyDecision.ASK_HUMAN
    assert "human_approved" in ask.missing_evidence

    guard.evidence.grant("run_del", "human_approved")
    ok = guard.evaluate(
        HookPoint.PRE_WRITE,
        {"run_id": "run_del", "work_mode": WorkMode.EXECUTE, "action": "delete", "path": target},
    )
    assert ok.decision == PolicyDecision.ALLOW


# === 5. 自定义 Hook 优先级短接、YAML 配置、Registry 热插拔与 <5ms 性能 ===
def test_custom_hook_deny_overrides_ask(tmp_path: pathlib.Path) -> None:
    guard = _make_guard(tmp_path)
    guard.register_hook(
        "custom_blocker",
        (HookPoint.PRE_WRITE,),
        lambda _p, _c: HookVerdict(PolicyDecision.DENY, "custom_blocker", "自定义硬阻断"),
        priority=60,
    )
    verdict = guard.evaluate(
        HookPoint.PRE_WRITE,
        {
            "run_id": "r_ov",
            "work_mode": WorkMode.PLAN,
            "path": str(tmp_path / "workspace" / "x.md"),
        },
    )
    assert verdict.decision == PolicyDecision.DENY
    assert verdict.hook_name == "custom_blocker"


def test_load_from_project_policies_yaml_and_registry_protocol() -> None:
    guard = GovernanceGuard.from_yaml(PROJECT_ROOT / "config" / "policies.yaml")
    assert isinstance(guard, PolicyHookProtocol)
    assert guard.check("PreToolUse", {"work_mode": "ask", "permission": "WRITE"}) == PolicyDecision.DENY

    reg = BrickRegistry()
    reg.register_manifest(
        "m04-guard",
        BrickManifest(
            brick_id="b10-governance-guard",
            layer=BrickLayer.GOVERNANCE,
            version="1.0.0",
            entrypoint="packages.governance.guard:GovernanceGuard",
        ),
        set_active=True,
    )
    resolved = reg.resolve(BrickLayer.GOVERNANCE)
    assert resolved.check("PreCommit", {"run_id": "no_tests"}) == PolicyDecision.DENY


def test_unified_diff_and_evidence_ledger_helpers() -> None:
    diff = generate_unified_diff("demo.py", "a = 1\n", "a = 2\n")
    assert "-a = 1" in diff and "+a = 2" in diff
    assert generate_unified_diff("demo.py", "same", "same") == "(无文本差异)"

    ledger = EvidenceLedger()
    ledger.grant("s1", "test_passed")
    assert ledger.has("s1", "test_passed")
    ledger.revoke("s1", "test_passed")
    assert not ledger.has("s1", "test_passed")


def test_hook_check_latency_under_5ms(tmp_path: pathlib.Path) -> None:
    guard = _make_guard(tmp_path)
    ctx = {
        "work_mode": WorkMode.EXECUTE,
        "permission": "WRITE",
        "path": str(tmp_path / "workspace" / "fast.txt"),
    }
    iterations = 200
    t0 = time.perf_counter()
    for _ in range(iterations):
        assert guard.check("PreWrite", ctx) == PolicyDecision.ALLOW
    avg_ms = (time.perf_counter() - t0) * 1000 / iterations
    assert avg_ms < 5.0
