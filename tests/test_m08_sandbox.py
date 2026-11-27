"""M08 (B07) 分级本地安全沙箱功能与 16 项红队越权/逃逸/炸弹对抗测试套件.

跨平台确定性保证：
- 在 Windows 10 本地与 GitHub Actions Ubuntu Linux CI 上均 100% 稳定通过；
- 零外网依赖、零 Docker Hub 拉取依赖；
- 严格检验 Fail-Closed（绝不静默降级至宿主裸跑）。
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from typing import Any

import pytest

from packages.core.contracts import BrickLayer, SandboxTier
from packages.core.interfaces import SandboxProtocol
from packages.core.registry import BrickRegistry
from packages.governance.guard import GovernanceGuard
from packages.sandbox import (
    SandboxLimits,
    SandboxManager,
    SandboxRequest,
    SandboxResult,
    T1WasmLightSandbox,
    T2OsRestrictedSandbox,
    T3ContainerSandbox,
)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


class _CustomSwapAdapter:
    """用于验证乐高热插拔替换的自定义测试适配器。"""

    tier: SandboxTier = SandboxTier.T1_WASM
    backend_name: str = "custom-hot-swapped-t1"

    def healthcheck(self) -> bool:
        return True

    def execute_request(self, request: SandboxRequest) -> SandboxResult:
        return SandboxResult(
            ok=True,
            tier_requested=request.tier,
            tier_used=self.tier,
            exit_code=0,
            stdout="SWAPPED_OK",
            backend=self.backend_name,
        )


# =====================================================================
# 一、协议合规、BrickRegistry 装配、热插拔与正常业务功能测试
# =====================================================================


def test_sandbox_protocol_and_brick_registry_resolution(tmp_path: pathlib.Path) -> None:
    # 1. 验证项目 config/bricks.yaml 已登记真实 M08 槽位入口
    proj_reg = BrickRegistry.from_yaml(PROJECT_ROOT / "config" / "bricks.yaml")
    proj_report = proj_reg.health_report()
    assert proj_report["sandbox"]["active_name"] == "m08-tiered-sandbox"
    assert proj_report["sandbox"]["brick_id"] == "b07-tiered-sandbox"

    # 2. 验证启用态 BrickRegistry 动态装配 SandboxManager 并通过 SandboxProtocol 强校验
    cfg = tmp_path / "sandbox_bricks.yaml"
    cfg.write_text(
        """
schema_version: "huiqiao/v1"
slots:
  sandbox:
    active: "m08-tiered-sandbox"
    bricks:
      m08-tiered-sandbox:
        brick_id: "b07-tiered-sandbox"
        layer: "sandbox"
        version: "1.0.0"
        contract_version: "huiqiao/v1"
        entrypoint: "packages.sandbox.manager:SandboxManager"
        enabled: true
""",
        encoding="utf-8",
    )
    reg = BrickRegistry.from_yaml(cfg)
    sandbox = reg.resolve(BrickLayer.SANDBOX)
    assert isinstance(sandbox, SandboxManager)
    assert isinstance(sandbox, SandboxProtocol)
    assert sandbox.healthcheck() is True

    report = reg.health_report()
    assert report["sandbox"]["status"] == "healthy"
    health = sandbox.tier_health()
    assert health[SandboxTier.T1_WASM.value] is True
    assert health[SandboxTier.T2_OS_RESTRICTED.value] is True


def test_t1_legitimate_pure_compute_fast() -> None:
    mgr = SandboxManager()
    code = (
        "import math, json, statistics\n"
        "vals = [10, 20, 30, 40]\n"
        "out = {'mean': statistics.mean(vals), 'pi2': round(math.pi * 2, 4)}\n"
        "print(json.dumps(out))\n"
    )
    res = mgr.execute(code, tier=SandboxTier.T1_WASM, timeout_sec=5)
    assert res["ok"] is True
    assert res["tier_used"] == SandboxTier.T1_WASM.value
    assert res["elapsed_ms"] < 500.0
    parsed = json.loads(res["stdout"])
    assert parsed["mean"] == 25
    assert parsed["pi2"] == 6.2832


def test_t2_legitimate_workspace_file_io_and_artifacts(tmp_path: pathlib.Path) -> None:
    ws = tmp_path / "work"
    ws.mkdir()
    (ws / "input.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    mgr = SandboxManager()
    code = (
        "import json, pathlib\n"
        "lines = pathlib.Path('input.txt').read_text(encoding='utf-8').splitlines()\n"
        "pathlib.Path('summary.json').write_text(json.dumps({'count': len(lines)}), encoding='utf-8')\n"
        "print('ROWS:', len(lines))\n"
    )
    res = mgr.execute(code, tier=SandboxTier.T2_OS_RESTRICTED, workspace_dir=str(ws), timeout_sec=10)
    assert res["ok"] is True, res["stderr"]
    assert "ROWS: 3" in res["stdout"]
    assert "summary.json" in res["artifacts"]
    assert json.loads((ws / "summary.json").read_text(encoding="utf-8")) == {"count": 3}


def test_t3_hardened_command_audit_and_injected_runner(tmp_path: pathlib.Path) -> None:
    ws = tmp_path / "t3_ws"
    ws.mkdir()
    captured: dict[str, Any] = {}

    def fake_runner(
        cmd: list[str], code_bytes: bytes, timeout_sec: float, max_out: int
    ) -> tuple[int, str, str, bool, bool]:
        captured["cmd"] = cmd
        captured["code"] = code_bytes.decode("utf-8")
        return 0, "CONTAINER_OK\n", "", False, False

    t3 = T3ContainerSandbox(
        offline_only=True,
        daemon_probe=lambda: True,
        command_runner=fake_runner,
    )
    mgr = SandboxManager(adapters={SandboxTier.T3_ISOLATED_VM: t3})

    # 1. Dry-run 审计全部安全硬化参数
    dry = mgr.execute(
        "print('hello')",
        tier=SandboxTier.T3_ISOLATED_VM,
        workspace_dir=str(ws),
        dry_run=True,
        read_only_workspace=True,
    )
    assert dry["ok"] is True
    preview = dry["command_preview"]
    assert "--rm" in preview
    assert "--network=none" in preview
    assert "--read-only" in preview
    assert "--cap-drop=ALL" in preview
    assert "--security-opt=no-new-privileges:true" in preview
    assert any(arg.startswith("--pids-limit=") for arg in preview)
    assert any(arg.startswith("--memory=") for arg in preview)
    assert any(arg.startswith("--memory-swap=") for arg in preview)
    assert any(arg.endswith(":/workspace:ro") for arg in preview)

    # 2. 注入 runner 实跑验证
    ran = mgr.execute(
        "print('hello')",
        tier=SandboxTier.T3_ISOLATED_VM,
        workspace_dir=str(ws),
        env_vars={"APP_MODE": "offline", "SECRET_TOKEN": "must_strip"},
    )
    assert ran["ok"] is True
    assert ran["stdout"].strip() == "CONTAINER_OK"
    assert "APP_MODE=offline" in captured["cmd"]
    assert not any("SECRET_TOKEN" in part or "must_strip" in part for part in captured["cmd"])


def test_sandbox_adapter_hot_swap_and_explicit_safe_fallback(tmp_path: pathlib.Path) -> None:
    t3_offline = T3ContainerSandbox(daemon_probe=lambda: False)
    mgr = SandboxManager(adapters={SandboxTier.T3_ISOLATED_VM: t3_offline})

    # 1. 热插拔 T1 引擎
    old = mgr.swap_adapter(SandboxTier.T1_WASM, _CustomSwapAdapter())
    assert isinstance(old, T1WasmLightSandbox)
    swapped_res = mgr.execute("print(1)", tier=SandboxTier.T1_WASM)
    assert swapped_res["ok"] is True
    assert swapped_res["stdout"] == "SWAPPED_OK"
    assert swapped_res["backend"] == "custom-hot-swapped-t1"

    # 2. T3 不可用且无显式降级 -> 必须 Fail-Closed
    denied = mgr.execute("print('should_not_run')", tier=SandboxTier.T3_ISOLATED_VM, workspace_dir=str(tmp_path))
    assert denied["ok"] is False
    assert denied["blocked"] is True
    assert denied["blocked_reason"] == "T3_DAEMON_UNAVAILABLE"

    # 3. T3 不可用但显式指定降级至 NONE -> 依然 Fail-Closed！
    denied_none = mgr.execute(
        "print('should_not_run')",
        tier=SandboxTier.T3_ISOLATED_VM,
        fallback_tier=SandboxTier.NONE,
        workspace_dir=str(tmp_path),
    )
    assert denied_none["ok"] is False
    assert denied_none["blocked"] is True
    assert denied_none["blocked_reason"] == "T3_DAEMON_UNAVAILABLE"

    # 4. T3 不可用但显式指定安全降级至 T2 -> 可控降级并在结果中留下完整审计记录
    fb = mgr.execute(
        "print('SAFE_FALLBACK_T2')",
        tier=SandboxTier.T3_ISOLATED_VM,
        fallback_tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=str(tmp_path),
    )
    assert fb["ok"] is True
    assert fb["tier_requested"] == SandboxTier.T3_ISOLATED_VM.value
    assert fb["tier_used"] == SandboxTier.T2_OS_RESTRICTED.value
    assert fb["metadata"]["fallback_from"] == SandboxTier.T3_ISOLATED_VM.value
    assert "SAFE_FALLBACK_T2" in fb["stdout"]


def test_governance_guard_integration_and_forbid_none_tier(tmp_path: pathlib.Path) -> None:
    guard = GovernanceGuard(offline_only=True, allowed_roots=(tmp_path,))
    mgr = SandboxManager(governance_guard=guard, allowed_roots=(tmp_path,))

    # SandboxTier.NONE 严禁绕过沙箱
    res_none = mgr.execute("print(1)", tier=SandboxTier.NONE, workspace_dir=str(tmp_path))
    assert res_none["ok"] is False
    assert res_none["blocked"] is True
    assert res_none["blocked_reason"] == "UNSANDBOXED_TIER_FORBIDDEN"

    # Ask 模式下 GovernanceGuard 拦截代码执行
    res_ask = mgr.execute("print(1)", tier=SandboxTier.T2_OS_RESTRICTED, workspace_dir=str(tmp_path), work_mode="ask")
    assert res_ask["ok"] is False
    assert res_ask["blocked"] is True
    assert res_ask["blocked_reason"] is not None
    assert res_ask["blocked_reason"].startswith("GOVERNANCE_DENY:")


# =====================================================================
# 二、16 项红队对抗测试（要求 100% 拦截或安全遏制）
# =====================================================================


def test_rt01_outbound_tcp_socket_blocked(tmp_path: pathlib.Path) -> None:
    """RT-01: 阻断外网原始 TCP Socket 直连。"""
    mgr = SandboxManager()
    code = (
        "import socket\n"
        "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "s.settimeout(1)\n"
        "s.connect(('1.1.1.1', 80))\n"
    )
    res = mgr.execute(code, tier=SandboxTier.T2_OS_RESTRICTED, workspace_dir=str(tmp_path))
    assert res["ok"] is False
    assert res["blocked"] is True
    assert "offline network wall" in res["stderr"]


def test_rt02_dns_and_urllib_exfiltration_blocked(tmp_path: pathlib.Path) -> None:
    """RT-02: 阻断 DNS 解析、urllib 外传与离线模式下开启 allow_network 企图。"""
    mgr = SandboxManager(offline_only=True)

    # 1. 企图通过参数打开外网被全局离线墙硬拒绝
    net_req = mgr.execute("print(1)", tier=SandboxTier.T2_OS_RESTRICTED, allow_network=True)
    assert net_req["ok"] is False
    assert net_req["blocked"] is True
    assert net_req["blocked_reason"] == "OFFLINE_NETWORK_BLOCKED"

    # 2. urllib.request 外传被审计钩子阻断
    res_url = mgr.execute(
        "import urllib.request\nurllib.request.urlopen('https://example.com', timeout=1)\n",
        tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=str(tmp_path),
    )
    assert res_url["ok"] is False
    assert res_url["blocked"] is True

    # 3. DNS 解析外泄（socket.getaddrinfo）被阻断
    res_dns = mgr.execute(
        "import socket\nsocket.getaddrinfo('example.com', 80)\n",
        tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=str(tmp_path),
    )
    assert res_dns["ok"] is False
    assert res_dns["blocked"] is True


def test_rt03_sensitive_host_file_read_blocked(tmp_path: pathlib.Path) -> None:
    """RT-03: 阻断读取宿主敏感凭证文件（.env / .ssh / 系统文件）。"""
    ws = tmp_path / "ws"
    ws.mkdir()
    secret_env = tmp_path / ".env"
    secret_env.write_text("DB_PASSWORD=top_secret_value\n", encoding="utf-8")

    mgr = SandboxManager()
    targets = [
        str(secret_env),
        os.path.expanduser("~/.ssh/id_rsa"),
        "/etc/passwd" if os.name == "posix" else r"C:\Windows\win.ini",
    ]
    for target in targets:
        code = f"print(open({target!r}, 'r', encoding='utf-8', errors='ignore').read())\n"
        res = mgr.execute(code, tier=SandboxTier.T2_OS_RESTRICTED, workspace_dir=str(ws))
        assert res["ok"] is False, f"Sensitive read should fail for {target}"
        assert res["blocked"] is True
        assert "top_secret_value" not in res["stdout"]


def test_rt04_path_traversal_escape_blocked(tmp_path: pathlib.Path) -> None:
    """RT-04: 阻断通过 ../ 路径穿越读取或篡改沙箱工作区外的宿主文件。"""
    outside = tmp_path / "host_secret.txt"
    outside.write_text("HOST_ONLY_SECRET_42", encoding="utf-8")
    jail = tmp_path / "jail"
    jail.mkdir()

    mgr = SandboxManager()
    res_read = mgr.execute(
        "print(open('../host_secret.txt', 'r', encoding='utf-8').read())\n",
        tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=str(jail),
    )
    assert res_read["ok"] is False
    assert res_read["blocked"] is True
    assert "HOST_ONLY_SECRET_42" not in res_read["stdout"]

    res_write = mgr.execute(
        "open('../escaped_write.txt', 'w', encoding='utf-8').write('pwned')\n",
        tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=str(jail),
    )
    assert res_write["ok"] is False
    assert res_write["blocked"] is True
    assert not (tmp_path / "escaped_write.txt").exists()


def test_rt05_symlink_escape_creation_and_read_blocked(tmp_path: pathlib.Path) -> None:
    """RT-05: 阻断创建越界符号链接，以及通过预置越界符号链接逃逸读取宿主文件。"""
    outside = tmp_path / "outside.txt"
    outside.write_text("SYMLINK_SECRET_99", encoding="utf-8")
    jail = tmp_path / "jail"
    jail.mkdir()

    mgr = SandboxManager()

    # A: 沙箱内尝试创建指向工作区外的符号链接 -> 审计钩子在系统调用前直接拦截
    res_create = mgr.execute(
        f"import os\nos.symlink({str(outside)!r}, 'escape_link.txt')\n",
        tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=str(jail),
    )
    assert res_create["ok"] is False
    assert res_create["blocked"] is True

    # B: 若宿主支持预置符号链接（Linux/启用开发者模式的 Windows），验证通过 realpath 彻底拦截读取
    pre_link = jail / "pre_escape.txt"
    try:
        os.symlink(outside, pre_link)
    except OSError:
        pre_link = None  # 无符号链接特权的 Windows 环境跳过预置阶段，A 已证明拦截生效

    if pre_link is not None:
        res_follow = mgr.execute(
            "print(open('pre_escape.txt', 'r', encoding='utf-8').read())\n",
            tier=SandboxTier.T2_OS_RESTRICTED,
            workspace_dir=str(jail),
        )
        assert res_follow["ok"] is False
        assert res_follow["blocked"] is True
        assert "SYMLINK_SECRET_99" not in res_follow["stdout"]


def test_rt06_host_env_secret_theft_blocked(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RT-06: 阻断读取宿主环境变量中的私钥/API Key/Token。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-host-secret-must-not-leak")
    monkeypatch.setenv("HUIQIAO_MASTER_SECRET", "master-secret-999")

    mgr = SandboxManager()
    code = "import os, json\nprint(json.dumps(dict(os.environ)))\n"
    res = mgr.execute(
        code,
        tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=str(tmp_path),
        env_vars={"GITHUB_TOKEN": "ghp_must_strip", "SAFE_TASK_TAG": "huiqiao_ok"},
    )
    assert res["ok"] is True
    env_dump = json.loads(res["stdout"])
    assert "OPENAI_API_KEY" not in env_dump
    assert "HUIQIAO_MASTER_SECRET" not in env_dump
    assert "GITHUB_TOKEN" not in env_dump
    assert "sk-host-secret-must-not-leak" not in res["stdout"]
    assert "master-secret-999" not in res["stdout"]
    assert "ghp_must_strip" not in res["stdout"]
    assert env_dump.get("SAFE_TASK_TAG") == "huiqiao_ok"


def test_rt07_subprocess_and_os_system_shell_escape_blocked(tmp_path: pathlib.Path) -> None:
    """RT-07: 阻断 subprocess.run 与 os.system Shell 命令逃逸。"""
    mgr = SandboxManager()

    res_sub = mgr.execute(
        "import subprocess\nsubprocess.run(['echo', 'SHELL_PWNED'], check=False)\n",
        tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=str(tmp_path),
    )
    assert res_sub["ok"] is False
    assert res_sub["blocked"] is True
    assert "SHELL_PWNED" not in res_sub["stdout"]

    res_sys = mgr.execute(
        "import os\nos.system('echo OS_SYSTEM_PWNED')\n",
        tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=str(tmp_path),
    )
    assert res_sys["ok"] is False
    assert res_sys["blocked"] is True
    assert "OS_SYSTEM_PWNED" not in res_sys["stdout"]


def test_rt08_ctypes_ffi_escape_blocked(tmp_path: pathlib.Path) -> None:
    """RT-08: 阻断 ctypes 原生动态库加载与底层内存 FFI 逃逸。"""
    mgr = SandboxManager()
    lib_expr = "ctypes.windll.kernel32" if sys.platform == "win32" else "ctypes.CDLL(None)"
    code = f"import ctypes\nlib = {lib_expr}\nprint(lib)\n"
    res = mgr.execute(code, tier=SandboxTier.T2_OS_RESTRICTED, workspace_dir=str(tmp_path))
    assert res["ok"] is False
    assert res["blocked"] is True
    assert "native FFI" in res["stderr"]


def test_rt09_t1_dunder_introspection_escape_blocked() -> None:
    """RT-09: T1 阻断经典 Python 双下划线对象图逃逸（__class__.__base__.__subclasses__）。"""
    mgr = SandboxManager()
    payloads = [
        "print(().__class__.__base__.__subclasses__())",
        "f = lambda: 1\nprint(f.__globals__)",
        "print((1).__class__.__mro__)",
        "print('{0.__class__.__mro__}'.format(1))",
    ]
    for code in payloads:
        res = mgr.execute(code, tier=SandboxTier.T1_WASM)
        assert res["ok"] is False
        assert res["blocked"] is True
        assert res["blocked_reason"] is not None
        assert "T1_AST_BLOCKED" in res["blocked_reason"]


def test_rt10_t1_eval_exec_import_open_injection_blocked() -> None:
    """RT-10: T1 阻断 eval / exec / __import__ / open / 越权模块导入。"""
    mgr = SandboxManager()
    payloads = [
        "eval('1 + 1')",
        "exec('x = 1')",
        "__import__('os').system('echo hi')",
        "open('secret.txt', 'w')",
        "import os\nprint(os.getcwd())",
        "import subprocess\nprint(subprocess)",
    ]
    for code in payloads:
        res = mgr.execute(code, tier=SandboxTier.T1_WASM)
        assert res["ok"] is False
        assert res["blocked"] is True
        assert "T1_AST_BLOCKED" in str(res["blocked_reason"])


def test_rt11_infinite_cpu_loop_killed_in_t1_and_t2(tmp_path: pathlib.Path) -> None:
    """RT-11: T1 与 T2 均可可靠击杀无限死循环（while True），绝不挂死宿主。"""
    mgr = SandboxManager()

    req_t1 = SandboxRequest(
        code="while True:\n    pass\n",
        tier=SandboxTier.T1_WASM,
        limits=SandboxLimits(timeout_sec=0.4),
    )
    res_t1 = mgr.run(req_t1)
    assert res_t1.ok is False
    assert res_t1.timed_out is True
    assert res_t1.killed_reason == "TIMEOUT"
    assert res_t1.elapsed_ms < 2500.0

    req_t2 = SandboxRequest(
        code="while True:\n    pass\n",
        tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=str(tmp_path),
        limits=SandboxLimits(timeout_sec=1.0),
    )
    res_t2 = mgr.run(req_t2)
    assert res_t2.ok is False
    assert res_t2.timed_out is True
    assert res_t2.exit_code == 124
    assert res_t2.killed_reason == "TIMEOUT"


def test_rt12_fork_and_process_spawn_bomb_blocked(tmp_path: pathlib.Path) -> None:
    """RT-12: 阻断 Fork / 进程派生炸弹（subprocess / multiprocessing 恶意刷进程）。"""
    mgr = SandboxManager()
    code = (
        "import subprocess, sys\n"
        "for _ in range(50):\n"
        "    subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    )
    res = mgr.execute(code, tier=SandboxTier.T2_OS_RESTRICTED, workspace_dir=str(tmp_path), timeout_sec=5)
    assert res["ok"] is False
    assert res["blocked"] is True
    assert "process/shell execution forbidden" in res["stderr"]


def test_rt13_stdout_flood_bomb_truncated_safely(tmp_path: pathlib.Path) -> None:
    """RT-13: T1 与 T2 的输出洪水炸弹（打印百万字节）均被截断在 max_output_bytes 内。"""
    mgr = SandboxManager()

    req_t1 = SandboxRequest(
        code="for _ in range(500):\n    print('A' * 1000)\n",
        tier=SandboxTier.T1_WASM,
        limits=SandboxLimits(timeout_sec=3.0, max_output_bytes=4096),
    )
    res_t1 = mgr.run(req_t1)
    assert res_t1.ok is True
    assert res_t1.output_truncated is True
    assert len(res_t1.stdout.encode("utf-8")) <= 4096

    req_t2 = SandboxRequest(
        code="print('B' * 200_000)\n",
        tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=str(tmp_path),
        limits=SandboxLimits(timeout_sec=5.0, max_output_bytes=4096),
    )
    res_t2 = mgr.run(req_t2)
    assert res_t2.ok is True
    assert res_t2.output_truncated is True
    assert len(res_t2.stdout.encode("utf-8")) <= 4096


def test_rt14_memory_allocation_bomb_contained(tmp_path: pathlib.Path) -> None:
    """RT-14: T1 序列/乘方/字节数组内存炸弹与 T2 进程级大内存分配炸弹均被安全遏制。"""
    mgr = SandboxManager()

    # T1 内存炸弹（bytearray / 字符串乘法 / 超大指数）
    for bomb in (
        "x = bytearray(128 * 1024 * 1024)",
        "x = 'A' * (100 * 1024 * 1024)",
        "x = 9 ** 999999",
    ):
        res_t1 = mgr.run(
            SandboxRequest(
                code=bomb,
                tier=SandboxTier.T1_WASM,
                limits=SandboxLimits(timeout_sec=3.0, max_memory_mb=64),
            )
        )
        assert res_t1.ok is False, f"T1 bomb should fail: {bomb}"
        assert res_t1.blocked is True
        assert res_t1.killed_reason == "MEMORY_LIMIT"

    # T2 进程级内存炸弹（Windows Job Object / POSIX RLIMIT_AS 封顶 128MB，尝试分配 512MB）
    res_t2 = mgr.run(
        SandboxRequest(
            code="buf = bytearray(512 * 1024 * 1024)\nprint(len(buf))\n",
            tier=SandboxTier.T2_OS_RESTRICTED,
            workspace_dir=str(tmp_path),
            limits=SandboxLimits(timeout_sec=8.0, max_memory_mb=128),
        )
    )
    assert res_t2.ok is False
    assert res_t2.exit_code != 0
    assert "536870912" not in res_t2.stdout


def test_rt15_readonly_workspace_and_disk_write_quota_enforced(tmp_path: pathlib.Path) -> None:
    """RT-15: 强制执行只读工作区保护、单次磁盘写入字节配额与最多写入文件数配额。"""
    mgr = SandboxManager()

    # A: 只读工作区禁写
    ro_ws = tmp_path / "ro"
    ro_ws.mkdir()
    res_ro = mgr.execute(
        "open('hack.txt', 'w', encoding='utf-8').write('nope')\n",
        tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=str(ro_ws),
        read_only_workspace=True,
    )
    assert res_ro["ok"] is False
    assert res_ro["blocked"] is True
    assert not (ro_ws / "hack.txt").exists()

    # B: 磁盘写字节配额防写爆（上限 2048 bytes，尝试写 50KB）
    quota_ws = tmp_path / "quota_bytes"
    quota_ws.mkdir()
    res_bytes = mgr.run(
        SandboxRequest(
            code="with open('big.bin', 'wb') as f:\n    f.write(b'X' * 50_000)\n",
            tier=SandboxTier.T2_OS_RESTRICTED,
            workspace_dir=str(quota_ws),
            limits=SandboxLimits(max_write_bytes=2048),
        )
    )
    assert res_bytes.ok is False
    assert res_bytes.blocked is True
    assert "quota exceeded" in res_bytes.stderr

    # B2: 低级 os.open + os.write 同样受磁盘写字节配额限制
    res_os_bytes = mgr.run(
        SandboxRequest(
            code="import os\nfd = os.open('low.bin', os.O_CREAT | os.O_WRONLY)\ntry:\n    os.write(fd, b'Y' * 50_000)\nfinally:\n    os.close(fd)\n",
            tier=SandboxTier.T2_OS_RESTRICTED,
            workspace_dir=str(quota_ws),
            limits=SandboxLimits(max_write_bytes=2048),
        )
    )
    assert res_os_bytes.ok is False
    assert res_os_bytes.blocked is True
    assert "quota exceeded" in res_os_bytes.stderr

    # C: 文件数配额防小文件洪水（上限 3 个文件，尝试写 10 个）
    files_ws = tmp_path / "quota_files"
    files_ws.mkdir()
    res_files = mgr.run(
        SandboxRequest(
            code="for i in range(10):\n    open(f'f_{i}.txt', 'w').write('ok')\n",
            tier=SandboxTier.T2_OS_RESTRICTED,
            workspace_dir=str(files_ws),
            limits=SandboxLimits(max_write_files=3),
        )
    )
    assert res_files.ok is False
    assert res_files.blocked is True
    assert "max write files quota exceeded" in res_files.stderr


def test_rt16_t3_sensitive_mount_and_wasm_fail_closed_audit() -> None:
    """RT-16: 阻断 T3 挂载敏感目录/系统根目录、阻断离线联网与无 WASM 运行时 Fail-Closed。"""
    t3 = T3ContainerSandbox(offline_only=True, daemon_probe=lambda: False)
    mgr = SandboxManager(offline_only=True, adapters={SandboxTier.T3_ISOLATED_VM: t3})

    # 1. 敏感目录挂载（即使 dry_run=True 也必须拦截）
    for bad_mount in (os.path.expanduser("~/.ssh"), "/etc/passwd", "C:/Windows"):
        res_bad = mgr.execute(
            "print(1)",
            tier=SandboxTier.T3_ISOLATED_VM,
            workspace_dir=bad_mount,
            dry_run=True,
        )
        assert res_bad["ok"] is False
        assert res_bad["blocked"] is True
        assert "SENSITIVE_WORKSPACE_BLOCKED" in str(res_bad["blocked_reason"])

    # 2. 禁止挂载整个根目录
    root_dir = "C:\\" if sys.platform == "win32" else "/"
    res_root = mgr.execute(
        "print(1)",
        tier=SandboxTier.T3_ISOLATED_VM,
        workspace_dir=root_dir,
        dry_run=True,
    )
    assert res_root["ok"] is False
    assert res_root["blocked"] is True
    assert res_root["blocked_reason"] == "ROOT_DIRECTORY_MOUNT_FORBIDDEN"

    # 3. T3 离线锁拒网
    res_net = t3.execute_request(
        SandboxRequest(
            code="print(1)",
            tier=SandboxTier.T3_ISOLATED_VM,
            limits=SandboxLimits(allow_network=True),
            dry_run=True,
        )
    )
    assert res_net.ok is False
    assert res_net.blocked is True
    assert res_net.blocked_reason == "OFFLINE_NETWORK_BLOCKED"

    # 4. 本机未装 wasmtime 时，WASM 语言请求必须 Fail-Closed
    t1 = T1WasmLightSandbox()
    if not t1._has_wasmtime:
        res_wasm = mgr.execute("(module)", language="wasm", tier=SandboxTier.T1_WASM)
        assert res_wasm["ok"] is False
        assert res_wasm["blocked"] is True
        assert res_wasm["blocked_reason"] == "WASM_RUNTIME_UNAVAILABLE"
