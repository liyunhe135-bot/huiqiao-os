#!/usr/bin/env python3
"""
汇桥 OS（HuiQiao OS）· 管电脑零 Token 管家脚本（forge_guard.py）
纯 Python 标准库实现，零额外依赖，严格仅访问本机回环地址。

核心子命令：
  python forge/scripts/forge_guard.py preflight          # 极简本机硬件/显存/Ollama/工具链体检（<=25行）
  python forge/scripts/forge_guard.py test [pytest参数]  # 本地跑测试并将冗长日志脱水为<=35行诊断卡
  python forge/scripts/forge_guard.py brief M00          # 生成某块积木的模型切换建议 + 新会话最小开场指令
  python forge/scripts/forge_guard.py digest <文件路径>  # 大日志/大文本本地脱水摘要后再喂云端模型
"""

from __future__ import annotations

import ctypes
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "forge" / "logs"

BRICK_SPECS: dict[str, dict[str, str]] = {
    "M00": {
        "name": "宪章核心、契约总线与工程底座",
        "brain": "Gemini 4 Neon (Extra High) [备选: Claude Opus 5.5]",
        "coder": "Gemini 4 Hydrogen (Medium) / flash 子代理 (补单测)",
        "est_quota": "周额度 ~3–4%",
        "read_files": "forge/BRICK_CONTEXT_CARD.md, forge/PROGRESS_LEDGER.md",
        "dod": "CONSTITUTION.md 落盘 + Pydantic 核心契约 + BrickRegistry 热插拔单测 100% 通过",
    },
    "M01": {
        "name": "本地模型网关、显存亲和与思考剥离",
        "brain": "Gemini 4 Neon (Extra High) [备选: Claude Sonnet 5.5]",
        "coder": "Gemini 4 Carbon (Medium) (写 Adapter 与单测)",
        "est_quota": "周额度 ~5–6%",
        "read_files": "forge/BRICK_CONTEXT_CARD.md, forge/PROGRESS_LEDGER.md, packages/core/",
        "dod": "改配置无痛切换 Ollama/llama-server + 亲和队列降换模>=60% + <think>流式剥离 + 断网强拦截",
    },
    "M02": {
        "name": "装机离线科学能力摸底器 (Capability Profiler)",
        "brain": "无需重脑力（异常时再升级）",
        "coder": "Gemini 4 Carbon (Medium) + Hydrogen (报告模板)",
        "est_quota": "周额度 ~3–4%",
        "read_files": "forge/BRICK_CONTEXT_CARD.md, forge/PROGRESS_LEDGER.md, packages/llm_gateway/",
        "dod": "100% 离线 5–10 分钟跑通 24 题微型基准并产出 config/capability_profile.json",
    },
    "M03": {
        "name": "核心 MCP 总线与本地全格式文档解析 (DocIngest)",
        "brain": "按需抽检接口",
        "coder": "Gemini 4 Carbon (Medium) [错峰: Claude Sonnet 5.5] + flash 补单测",
        "est_quota": "周额度 ~3–4%",
        "read_files": "forge/BRICK_CONTEXT_CARD.md, forge/PROGRESS_LEDGER.md, packages/core/",
        "dod": "Tool Search 延迟加载 (<500 tokens) + 离线解析真实 PDF/Word/Excel 通过测试",
    },
    "M04": {
        "name": "确定性生命周期 Hooks 与 Ask/Plan/Execute 三档守卫",
        "brain": "Claude Opus 5.5 (边界抽检)",
        "coder": "Claude Sonnet 5.5 (Medium) [错峰第二池]",
        "est_quota": "Claude 周额度 ~3%",
        "read_files": "forge/BRICK_CONTEXT_CARD.md, forge/PROGRESS_LEDGER.md, packages/mcp_bus/",
        "dod": "15 条越权与 Ask 物理禁写拦截率 100%，单次校验 <5ms",
    },
    "M05": {
        "name": "持久化 ADK 五原语编排与流式状态机",
        "brain": "Gemini 4 Neon (Extra High) [备选: Claude Opus 5.5]",
        "coder": "Gemini 4 Carbon (Medium) (辅助单测)",
        "est_quota": "周额度 ~5–6%",
        "read_files": "forge/BRICK_CONTEXT_CARD.md, forge/PROGRESS_LEDGER.md, packages/governance/",
        "dod": "ADK 五原语 + SQLite WAL 强杀续跑 100% + HITL 挂起恢复 + 中途改向与部分产物保留",
    },
    "M06": {
        "name": "柔硬结合路由与语义共生执行内核 (L2-S)",
        "brain": "按需抽检路由提示",
        "coder": "Claude Sonnet 5.5 / Gemini 4 Carbon (Medium)",
        "est_quota": "周额度 ~4%",
        "read_files": "forge/BRICK_CONTEXT_CARD.md, forge/PROGRESS_LEDGER.md, packages/orchestrator/",
        "dod": "20 题混合路由准确率>=90%、低可验证任务 0 误塞 CodeAct、代劳/增上双态正常切换",
    },
    "M07": {
        "name": "统一网关、CLI/WebUI 与 5 个创世种子技能 (Alpha MVP)",
        "brain": "Alpha 里程碑总验收",
        "coder": "Gemini 4 Carbon (Medium) + Hydrogen (轻量单页 UI/样式/种子Skill)",
        "est_quota": "周额度 ~4–5%",
        "read_files": "forge/BRICK_CONTEXT_CARD.md, forge/PROGRESS_LEDGER.md",
        "dod": "完全断网端到端跑通 5 个创世种子技能，Alpha MVP 可日常自用",
    },
    "M08": {
        "name": "分级本地安全沙箱 (WASM / OS 原生 / MicroVM-Docker)",
        "brain": "Claude Opus 5.5 / Gemini 4 Neon (Extra High)",
        "coder": "Gemini 4 Carbon (Medium) (适配器与攻击用例脚本)",
        "est_quota": "周额度 ~5–6%",
        "read_files": "forge/BRICK_CONTEXT_CARD.md, forge/PROGRESS_LEDGER.md, packages/governance/",
        "dod": "热切 T2/T3 沙箱 + 15 条逃逸/外泄/内存炸弹攻击拦截率 100%",
    },
    "M09": {
        "name": "CodeAct 执行器、上下文四件套与逻辑隔离/物理亲和 Subagent",
        "brain": "Gemini 4 Neon (Extra High) [备选: Claude Opus 5.5]",
        "coder": "Gemini 4 Carbon (Medium) (测试与基准脚本)",
        "est_quota": "周额度 ~6–7%",
        "read_files": "forge/BRICK_CONTEXT_CARD.md, forge/PROGRESS_LEDGER.md, packages/sandbox/",
        "dod": "批处理提速>=40% + 25 轮长对话压缩后 100% 重注 CONSTITUTION.md/MEMORY.md + Subagent 零换模",
    },
    "M10": {
        "name": "分层本地记忆引擎与 1 秒低摩擦反馈闭环",
        "brain": "冲突策略抽检",
        "coder": "Gemini 4 Carbon (Medium) / Claude Sonnet 5.5",
        "est_quota": "周额度 ~3–4%",
        "read_files": "forge/BRICK_CONTEXT_CARD.md, forge/PROGRESS_LEDGER.md, packages/gateway/",
        "dod": "File-First + FTS5/sqlite-vec 双时态冲突覆盖通过 + 1 秒 4 键反馈生效 + 拷贝目录无损重建",
    },
    "M11": {
        "name": "双闸门防坍塌自演化引擎与普惠技能导出",
        "brain": "Gemini 4 Neon (Extra High) + Claude Opus 5.5 交叉红队审计",
        "coder": "Gemini 4 Carbon (Medium) (导出与打包脚本)",
        "est_quota": "周额度 ~5–6%",
        "read_files": "forge/BRICK_CONTEXT_CARD.md, forge/PROGRESS_LEDGER.md, packages/memory/",
        "dod": "L2-C->双闸门验真->L0 复用跑通 + 10 条伪造脚本与违宪诱导拦截率 100%",
    },
    "INT-4": {
        "name": "五维整体测试、离线打包与 v1.0 正式上线",
        "brain": "Gemini 4 Neon / Claude Opus 5.5 异常根因与上线把关",
        "coder": "Gemini 4 Carbon (Medium) 写回归与打包脚本",
        "est_quota": "周额度 ~3–4%",
        "read_files": "forge/BRICK_CONTEXT_CARD.md, forge/PROGRESS_LEDGER.md, docs/05_乐高式研发执行与测试上线总计划.md",
        "dod": "断网 E2E + 轨迹评测 + 安全红队 + 显存压测 + 真人盲测全绿 + 离线安装包 SHA256 发布",
    },
}


def _get_ram_gb() -> str:
    if platform.system() == "Windows":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(stat)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            total = stat.ullTotalPhys / (1024**3)
            avail = stat.ullAvailPhys / (1024**3)
            return f"{total:.1f} GB (可用 {avail:.1f} GB)"
    return "未知"


def _get_gpu_info() -> str:
    if not shutil.which("nvidia-smi"):
        return "未检测到 nvidia-smi (可能是核显/AMD/Apple Silicon)"
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader"],
            text=True,
            timeout=3,
            stderr=subprocess.DEVNULL,
        ).strip()
        return out.replace("\n", " | ") or "无 GPU 输出"
    except Exception as exc:
        return f"查询失败: {exc}"


def _get_ollama_models() -> list[str]:
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = []
        for item in data.get("models", []):
            name = item.get("name", "?")
            size_gb = item.get("size", 0) / (1024**3)
            models.append(f"{name} ({size_gb:.1f}GB)")
        return models
    except Exception:
        return []


def cmd_preflight() -> int:
    disk = shutil.disk_usage(ROOT)
    tools = ["python", "uv", "git", "pytest", "ruff", "mypy", "ollama", "docker"]
    found = [t for t in tools if shutil.which(t)]
    missing = [t for t in tools if not shutil.which(t)]
    ollama_models = _get_ollama_models()

    print("=== [汇桥 · 管电脑零Token体检卡] ===")
    print(f"项目路径 : {ROOT}")
    print(f"系统/Py  : {platform.system()} {platform.release()} | Python {platform.python_version()}")
    print(f"内存 RAM : {_get_ram_gb()}")
    print(f"显卡 GPU : {_get_gpu_info()}")
    print(f"磁盘剩余 : {disk.free / (1024**3):.1f} GB / {disk.total / (1024**3):.1f} GB")
    print(f"已装工具 : {', '.join(found) if found else '无'}")
    print(f"缺失工具 : {', '.join(missing) if missing else '无'}")
    if ollama_models:
        shown = ollama_models[:8]
        extra = f" ... 共 {len(ollama_models)} 个" if len(ollama_models) > 8 else ""
        print(f"本地Ollama: 运行中 | 模型: {', '.join(shown)}{extra}")
    else:
        print("本地Ollama: 未运行或 127.0.0.1:11434 无响应 (可按需启动或改用 llama-server)")
    print("===================================")
    return 0


def cmd_test(pytest_args: list[str]) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    raw_log = LOG_DIR / "last_test_raw.log"
    cmd = [sys.executable, "-m", "pytest", "--tb=short", "-q", *pytest_args]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    full_out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    raw_log.write_text(full_out, encoding="utf-8")

    if proc.returncode == 0:
        summary = [ln.strip() for ln in full_out.splitlines() if ln.strip()][-2:]
        print("=== [管电脑测试报告: ALL PASS] ===")
        for ln in summary:
            print(ln)
        return 0

    lines = full_out.splitlines()
    condensed: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if (
            s.startswith(("FAILED ", "ERROR ", "ERROR:", "E   ", "___", "=== short test summary"))
            or "AssertionError" in s
            or "Error:" in s
            or "passed" in s
            or "failed" in s
        ):
            condensed.append(ln[:160])

    if not condensed:
        condensed = [ln[:160] for ln in lines if ln.strip()][-15:]

    print("=== [管电脑脱水报错卡 (<=35行, 完整日志见 forge/logs/last_test_raw.log)] ===")
    for ln in condensed[:35]:
        print(ln)
    if len(condensed) > 35:
        print(f"... (已折叠其余 {len(condensed) - 35} 行，严禁直接整篇贴给云端大模型)")
    return proc.returncode


def cmd_brief(brick_id: str) -> int:
    key = brick_id.upper()
    if key not in BRICK_SPECS:
        print(f"未知积木编号: {brick_id}。可选: {', '.join(BRICK_SPECS.keys())}")
        return 1
    spec = BRICK_SPECS[key]
    print(f"=== [汇桥 · {key} 新会话模型切换与极简开场卡] ===")
    print(f"积木名称   : {spec['name']}")
    print(f"管大脑模型 : {spec['brain']}")
    print(f"管编码模型 : {spec['coder']}")
    print(f"预计额度   : {spec['est_quota']}")
    print(f"必读最小集 : {spec['read_files']}")
    print(f"本块 DoD   : {spec['dod']}")
    print("--- [直接复制下面 5 行粘贴到新会话开场] ---")
    print(f"请激活 huiqiao-forge-os 技能，开始施工汇桥 OS 积木 {key}（{spec['name']}）。")
    print(f"1. 仅读取 {spec['read_files']}，严禁整篇通读大 PRD。")
    print("2. 先运行 python forge/scripts/forge_guard.py preflight 确认本机环境。")
    print("3. 先输出本块文件清单、核心接口签名与测试用例清单（<100行），等我确认后再写代码。")
    print("4. 严守 C00 方向与物理安全底线，具体实现鼓励优雅简洁；跑测试统一走 forge_guard.py test。")
    print("==============================================")
    return 0


def cmd_digest(file_path: str, max_lines: int = 35) -> int:
    p = pathlib.Path(file_path)
    if not p.exists():
        print(f"文件不存在: {p}")
        return 1
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) <= max_lines:
        print("\n".join(lines))
        return 0
    head = lines[:8]
    tail = lines[-10:]
    alerts = [
        f"L{idx+1}: {ln[:160]}"
        for idx, ln in enumerate(lines[8:-10], start=8)
        if any(k in ln.lower() for k in ("error", "exception", "traceback", "failed", "warn", "assert"))
    ][: max(1, max_lines - 18)]
    print(f"=== [本地日志脱水摘要: {p.name} (原 {len(lines)} 行 -> 精选 <= {max_lines} 行)] ===")
    print("--- HEAD ---")
    print("\n".join(head))
    if alerts:
        print("--- KEY ERRORS/WARNINGS ---")
        print("\n".join(alerts))
    print("--- TAIL ---")
    print("\n".join(tail))
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    sub = sys.argv[1].lower()
    if sub == "preflight":
        return cmd_preflight()
    if sub == "test":
        return cmd_test(sys.argv[2:])
    if sub == "brief":
        if len(sys.argv) < 3:
            print("用法: python forge/scripts/forge_guard.py brief M00")
            return 1
        return cmd_brief(sys.argv[2])
    if sub == "digest":
        if len(sys.argv) < 3:
            print("用法: python forge/scripts/forge_guard.py digest <文件路径> [最大行数]")
            return 1
        max_l = int(sys.argv[3]) if len(sys.argv) > 3 else 35
        return cmd_digest(sys.argv[2], max_l)
    print(f"未知子命令: {sub}\n{__doc__}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
