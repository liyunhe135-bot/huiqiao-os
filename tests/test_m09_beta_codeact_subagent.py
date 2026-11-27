"""M09 B05（Beta 里程碑）全量离线验收测试：上下文四件套 + CodeAct 沙箱自愈闭环 + 逻辑隔离/物理亲和 Subagent."""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

import pytest

from packages.core.contracts import (
    ExecutionChannel,
    SandboxTier,
    StepInput,
    StepOutput,
    WorkMode,
)
from packages.core.interfaces import WorkerProtocol
from packages.gateway import HuiQiaoService
from packages.governance import GovernanceGuard
from packages.sandbox import SandboxManager
from packages.workers import (
    C00_REINJECT_MARKER,
    COMPACT_SUMMARY_MARKER,
    AffinitySubagentPool,
    CodeActWorker,
    CompactionPolicy,
    ContextManager,
    SubagentSpec,
    clamp_work_mode,
    estimate_messages_tokens,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


# =====================================================================
# 一、上下文四件套（清理 / 双触发压缩 / 摘要化 / C00 宪章重注 + KV 前缀锁）
# =====================================================================


def test_context_prune_strips_think_and_bulky_observations() -> None:
    cm = ContextManager(
        policy=CompactionPolicy(
            safe_effective_ctx=16384,
            max_raw_messages=30,
            keep_recent_messages=2,
            prune_observation_chars=200,
            prune_keep_head=60,
            prune_keep_tail=40,
        )
    )
    sys_msg = cm.build_system_message("测试系统指令")
    messages = [
        sys_msg,
        {"role": "user", "content": "请分析日志"},
        {"role": "assistant", "content": "<think>大量内部草稿推理" + "x" * 300 + "</think>最终简洁答复"},
        {"role": "user", "content": "[Observation: sandbox]\n" + "LOG_LINE_" * 80},
        {"role": "assistant", "content": "最近一轮回复"},
        {"role": "user", "content": "当前最新追问"},
    ]

    out = cm.prune_observations(messages)
    assert "<think>" not in out[2]["content"]
    assert "最终简洁答复" in out[2]["content"]
    assert "[Pruned historical output:" in out[3]["content"]
    assert len(out[3]["content"]) < len(messages[3]["content"])
    # 最近 2 条原样保留，绝不误伤排错现场
    assert out[-2]["content"] == "最近一轮回复"
    assert out[-1]["content"] == "当前最新追问"
    assert cm.telemetry.prune_count >= 2
    assert cm.telemetry.pruned_chars > 500


def test_context_dual_trigger_token_and_turn_compaction_with_c00_reinject() -> None:
    # A) Token 占比触发器 + KV 前缀缓存锁 + C00 强重注
    cm_tok = ContextManager(
        policy=CompactionPolicy(
            safe_effective_ctx=800,
            compact_ratio=0.70,
            max_raw_messages=50,
            keep_recent_messages=4,
            prune_observation_chars=2000,
        )
    )
    sys_msg = cm_tok.build_system_message("角色：离线本地编程专家")
    orig_prefix_hash = hashlib.sha256(sys_msg["content"].encode("utf-8")).hexdigest()

    msgs: list[dict[str, str]] = [sys_msg]
    for i in range(10):
        msgs.append({"role": "user", "content": f"第{i}步需求：处理本地报表数据并核对营收字段 " + "数据" * 40})
        msgs.append({"role": "assistant", "content": f"第{i}步执行完成，生成 part_{i}.json " + "校验" * 40})

    before_toks = estimate_messages_tokens(msgs)
    compacted = cm_tok.prepare(msgs)
    after_toks = estimate_messages_tokens(compacted)

    assert cm_tok.telemetry.compaction_count == 1
    assert str(cm_tok.telemetry.last_trigger_reason).startswith("TOKEN_RATIO_TRIGGER:")
    assert after_toks < before_toks
    # KV Prefix Cache 锁：messages[0] 必须逐字节纹丝不动！
    assert hashlib.sha256(compacted[0]["content"].encode("utf-8")).hexdigest() == orig_prefix_hash
    # 摘要块与 C00 宪章重注锚点必须同时存在
    assert COMPACT_SUMMARY_MARKER in compacted[1]["content"]
    assert C00_REINJECT_MARKER in compacted[1]["content"]
    assert cm_tok.verify_constitution_intact(compacted) is True

    # B) 消息轮次上限触发器（即使总 Token 远低于预算上限）
    cm_turn = ContextManager(
        policy=CompactionPolicy(
            safe_effective_ctx=32768,
            compact_ratio=0.90,
            max_raw_messages=10,
            keep_recent_messages=4,
        )
    )
    turn_msgs: list[dict[str, str]] = [cm_turn.build_system_message("短轮次压测")]
    for i in range(6):
        turn_msgs.append({"role": "user", "content": f"短问 {i} [中途改向]: 保留中文表头"})
        turn_msgs.append({"role": "assistant", "content": f"短答 {i}"})

    compacted_turn = cm_turn.prepare(turn_msgs)
    assert cm_turn.telemetry.compaction_count == 1
    assert str(cm_turn.telemetry.last_trigger_reason).startswith("MESSAGE_COUNT_TRIGGER:")
    assert "保留中文表头" in compacted_turn[1]["content"]
    assert cm_turn.verify_constitution_intact(compacted_turn) is True


def test_context_custom_summarizer_callback() -> None:
    seen_middle: list[int] = []

    def custom_summarizer(middle: list[dict[str, str]]) -> str:
        seen_middle.append(len(middle))
        return "已完成 CSV 清洗与字段归一化，待生成汇总图。"

    cm = ContextManager(
        policy=CompactionPolicy(safe_effective_ctx=16384, max_raw_messages=6, keep_recent_messages=2),
        summarizer_fn=custom_summarizer,
    )
    msgs = [cm.build_system_message("摘要回调测试")]
    for i in range(4):
        msgs.append({"role": "user", "content": f"u{i}"})
        msgs.append({"role": "assistant", "content": f"a{i}"})

    out = cm.prepare(msgs)
    assert seen_middle == [6]
    assert "CSV 清洗与字段归一化" in out[1]["content"]
    assert cm.verify_constitution_intact(out) is True


# =====================================================================
# 二、CodeActWorker 联动 M08 安全沙箱自愈闭环与证据闸门测试
# =====================================================================


def test_codeact_self_heal_and_objective_verify_real_sandbox(tmp_path: pathlib.Path) -> None:
    """首轮代码故意写错 -> 沙箱客观报错回灌 -> 二轮自动修复并写文件 -> 客观校验脚本通过 -> 交付成功。"""
    guard = GovernanceGuard(offline_only=True, allowed_roots=(tmp_path,))
    sandbox = SandboxManager(offline_only=True, allowed_roots=(tmp_path,), governance_guard=guard)

    call_idx = {"n": 0}
    observed_prompts: list[str] = []

    def scripted_model(messages: list[dict[str, str]]) -> str:
        call_idx["n"] += 1
        observed_prompts.append(messages[-1]["content"])
        if call_idx["n"] == 1:
            # 模拟带 <think> 的本地模型直接输出有 Bug 的 Markdown Python 代码块
            return (
                "<think>先尝试计算平均值，但忘记处理分母</think>\n"
                "```python\n"
                "nums = [10, 20, 30]\n"
                "avg = sum(nums) / 0\n"
                "print(avg)\n"
                "```"
            )
        if call_idx["n"] == 2:
            # 收到 ZeroDivisionError 反馈后自愈修复，并输出合法产物文件
            return json.dumps(
                {
                    "action": "run_code",
                    "code": (
                        "import json, pathlib\n"
                        "nums = [10, 20, 30]\n"
                        "avg = sum(nums) / len(nums)\n"
                        "pathlib.Path('metrics.json').write_text(json.dumps({'avg': avg}), encoding='utf-8')\n"
                        "print('FIXED_AVG:', avg)\n"
                    ),
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "action": "finish",
                "summary": "已修复除零异常并产出经过客观校验的 metrics.json（avg=20.0）。",
                "notes": "通过 len(nums) 替代硬编码 0，并已过只读断言校验。",
            },
            ensure_ascii=False,
        )

    verifier = (
        "import json, pathlib\n"
        "data = json.loads(pathlib.Path('metrics.json').read_text(encoding='utf-8'))\n"
        "assert data['avg'] == 20.0, f'unexpected: {data}'\n"
        "print('VERIFIER_OK')\n"
    )
    worker = CodeActWorker(
        infer_fn=scripted_model,
        sandbox=sandbox,
        sandbox_tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=tmp_path,
        guard=guard,
        verifier_code=verifier,
        max_turns=6,
    )
    assert isinstance(worker, WorkerProtocol)
    assert worker.healthcheck() is True

    step = StepInput(
        task_id="tsk_self_heal",
        goal="计算 [10, 20, 30] 均值并写入 metrics.json",
        work_mode=WorkMode.EXECUTE,
    )
    out = worker.run(step)

    assert out.success is True, out.error
    assert "ZeroDivisionError" in observed_prompts[1]
    assert "VERIFIER_OK" in observed_prompts[2]
    assert out.metadata["verified"] is True
    assert out.metadata["sandbox_runs"] == 3  # 1次失败 + 1次修复 + 1次客观校验
    assert any(p.endswith("metrics.json") for p in out.artifacts)
    assert guard.evidence.has(step.run_id, "test_passed") is True
    assert json.loads((tmp_path / "metrics.json").read_text(encoding="utf-8")) == {"avg": 20.0}


def test_codeact_evidence_gate_rejects_verbal_finish_without_execution(tmp_path: pathlib.Path) -> None:
    """Claude Evidence Gate：禁止模型未经沙箱执行便口头虚报完成。"""
    step_n = {"n": 0}
    last_user_msgs: list[str] = []

    def lazy_then_honest_model(messages: list[dict[str, str]]) -> str:
        step_n["n"] += 1
        last_user_msgs.append(messages[-1]["content"])
        if step_n["n"] == 1:
            # 试图偷懒直接口头宣布完成
            return json.dumps({"action": "finish", "summary": "我心算完了，答案是 42。"}, ensure_ascii=False)
        if step_n["n"] == 2:
            # 被 Evidence Gate 驳回后，乖乖在沙箱真实执行
            return json.dumps({"action": "run_code", "code": "print(6 * 7)"}, ensure_ascii=False)
        return json.dumps({"action": "finish", "summary": "经沙箱实测 6*7=42。"}, ensure_ascii=False)

    worker = CodeActWorker(
        infer_fn=lazy_then_honest_model,
        sandbox_tier=SandboxTier.T1_WASM,
        workspace_dir=tmp_path,
        require_objective_verify=True,
    )
    out = worker.run(StepInput(task_id="tsk_gate", goal="计算 6*7", work_mode=WorkMode.EXECUTE))
    assert out.success is True
    assert "Evidence Gate 拒绝" in last_user_msgs[1]
    assert out.metadata["sandbox_runs"] == 1
    assert out.metadata["verified"] is True


def test_codeact_three_round_same_error_stop_loss_preserves_artifacts(tmp_path: pathlib.Path) -> None:
    """3 轮同错止损铁律：连续 3 次遇到相同报错自动止损，同时保留前面已落盘的部分产物。"""
    turn = {"n": 0}

    def stuck_model(_messages: list[dict[str, str]]) -> str:
        turn["n"] += 1
        # 每轮代码微调（避开重复代码哈希拦截），但先留草稿再抛出相同 ValueError
        return json.dumps(
            {
                "action": "run_code",
                "code": (
                    f"import pathlib\n"
                    f"pathlib.Path('partial_draft.txt').write_text('attempt={turn['n']}', encoding='utf-8')\n"
                    f"raise ValueError('MISSING_REQUIRED_COLUMN_ID')\n"
                ),
            },
            ensure_ascii=False,
        )

    worker = CodeActWorker(
        infer_fn=stuck_model,
        sandbox_tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=tmp_path,
        max_turns=8,
        max_consecutive_same_error=3,
    )
    out = worker.run(StepInput(task_id="tsk_stop", goal="解析缺失字段的表格", work_mode=WorkMode.EXECUTE))

    assert out.success is False
    assert out.error is not None and out.error.startswith("SAME_ERROR_STOP_LOSS:")
    assert out.metadata["turns"] == 3
    assert any(p.endswith("partial_draft.txt") for p in out.artifacts)
    assert (tmp_path / "partial_draft.txt").exists()


def test_codeact_security_boundaries_ask_mode_escape_and_none_forbidden(tmp_path: pathlib.Path) -> None:
    # 1. 严禁构造 SandboxTier.NONE 的 CodeActWorker
    with pytest.raises(ValueError):
        CodeActWorker(infer_fn=lambda _: "{}", sandbox_tier=SandboxTier.NONE)

    # 2. Ask 只读模式下 GovernanceGuard 硬拦截 T2 执行
    guard = GovernanceGuard(offline_only=True, allowed_roots=(tmp_path,))
    w_ask = CodeActWorker(
        infer_fn=lambda _: json.dumps({"action": "run_code", "code": "print(1)"}),
        sandbox=SandboxManager(offline_only=True, allowed_roots=(tmp_path,), governance_guard=guard),
        sandbox_tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=tmp_path,
        guard=guard,
    )
    res_ask = w_ask.run(StepInput(task_id="tsk_ask", goal="写文件", work_mode=WorkMode.ASK))
    assert res_ask.success is False
    assert "治理守卫拦截" in (res_ask.error or "")

    # 3. 恶意模型连续企图联网/Shell逃逸 -> 被 M08 沙箱双连拦并安全熔断
    n = {"i": 0}

    def malicious_model(_msgs: list[dict[str, str]]) -> str:
        n["i"] += 1
        if n["i"] == 1:
            return json.dumps({"action": "run_code", "code": "import socket; socket.socket().connect(('1.1.1.1', 80))"})
        return json.dumps({"action": "run_code", "code": "import subprocess; subprocess.run(['echo', 'pwn'])"})

    w_mal = CodeActWorker(
        infer_fn=malicious_model,
        sandbox_tier=SandboxTier.T2_OS_RESTRICTED,
        workspace_dir=tmp_path,
        max_security_blocks=2,
    )
    res_mal = w_mal.run(StepInput(task_id="tsk_mal", goal="执行脚本", work_mode=WorkMode.EXECUTE))
    assert res_mal.success is False
    assert str(res_mal.error).startswith("SANDBOX_SECURITY_ABORT:")


def test_codeact_long_loop_triggers_compaction_and_preserves_c00(tmp_path: pathlib.Path) -> None:
    """长多轮 CodeAct 触发上下文压缩后，C00 宪章必须依然完整在场。"""
    cm = ContextManager(
        policy=CompactionPolicy(
            safe_effective_ctx=1024,
            compact_ratio=0.65,
            max_raw_messages=6,
            keep_recent_messages=2,
            prune_observation_chars=300,
        )
    )
    turn = {"n": 0}

    def chatty_model(_msgs: list[dict[str, str]]) -> str:
        turn["n"] += 1
        if turn["n"] <= 4:
            return json.dumps(
                {
                    "action": "run_code",
                    "code": f"print('STEP_{turn['n']}_' + 'DETAIL_' * 120)",
                }
            )
        return json.dumps({"action": "finish", "summary": "多轮长输出处理完毕。"}, ensure_ascii=False)

    worker = CodeActWorker(
        infer_fn=chatty_model,
        sandbox_tier=SandboxTier.T1_WASM,
        context_manager=cm,
        max_turns=6,
    )
    out = worker.run(
        StepInput(
            task_id="tsk_long",
            goal="连续多轮汇总长日志",
            work_mode=WorkMode.EXECUTE,
            effective_ctx_budget=1024,
        )
    )
    assert out.success is True
    assert out.metadata["compactions"] >= 1
    assert out.metadata["constitution_intact"] is True


# =====================================================================
# 三、逻辑隔离 / 物理显存亲和 Subagent 调度池测试
# =====================================================================


def test_subagent_vram_affinity_reduces_switches_and_prioritizes_resident() -> None:
    """6 路混排多模型子代理：亲和调度优先跑已驻留显存模型组，大幅减少冷换模次数。"""
    executed_log: list[tuple[str, str]] = []

    class _RecordingWorker:
        def __init__(self, spec: SubagentSpec) -> None:
            self.spec = spec

        def healthcheck(self) -> bool:
            return True

        def run(self, step: StepInput) -> StepOutput:
            executed_log.append((self.spec.subagent_id, self.spec.model))
            return StepOutput(
                run_id=step.run_id,
                task_id=step.task_id,
                step_id=step.step_id,
                success=True,
                summary=f"done:{self.spec.role}",
            )

    # 模拟 RTX 4070 12GB 当前显存已驻留 qwen3-14b
    pool = AffinitySubagentPool(
        worker_factory=lambda spec, _ctx: _RecordingWorker(spec),
        resident_model="qwen3-14b",
        vram_budget_gb=12.0,
    )
    specs = [
        SubagentSpec(subagent_id="s1", role="router_a", model="qwen3-4b", goal="分类 A"),
        SubagentSpec(subagent_id="s2", role="coder_a", model="qwen3-14b", goal="写代码 A"),
        SubagentSpec(subagent_id="s3", role="router_b", model="qwen3-4b", goal="分类 B"),
        SubagentSpec(subagent_id="s4", role="coder_b", model="qwen3-14b", goal="写代码 B"),
        SubagentSpec(subagent_id="s5", role="deep_arch", model="qwen3-32b", goal="深度评审"),
        SubagentSpec(subagent_id="s6", role="router_c", model="qwen3-4b", goal="分类 C"),
    ]

    report = pool.run_batch(specs, parent_work_mode=WorkMode.EXECUTE)
    assert report.all_succeeded is True
    assert report.naive_model_switches == 6  # 朴素顺序每次都切模（连首项也要切离 14b）
    assert report.optimized_model_switches == 2  # 驻留 14b 先跑(0次) -> 4b 批(1次) -> 32b(2次)
    assert report.switches_saved == 4
    # 前两个执行的必须是已驻留显存的 qwen3-14b 组
    assert report.executed_models[:2] == ["qwen3-14b", "qwen3-14b"]
    assert report.executed_models[2:5] == ["qwen3-4b", "qwen3-4b", "qwen3-4b"]
    assert report.executed_models[5] == "qwen3-32b"
    assert report.resident_model_after == "qwen3-32b"


def test_subagent_logical_context_isolation_and_mode_non_escalation() -> None:
    """验证兄弟子代理间上下文物理零污染，且子代理严禁突破父任务 WorkMode 越权升级。"""
    seen_steps: dict[str, StepInput] = {}

    class _InspectWorker:
        def __init__(self, spec: SubagentSpec, ctx: ContextManager) -> None:
            self.spec = spec
            self.ctx = ctx

        def healthcheck(self) -> bool:
            return True

        def run(self, step: StepInput) -> StepOutput:
            seen_steps[self.spec.subagent_id] = step
            msgs = self.ctx.prepare(
                [
                    self.ctx.build_system_message(f"子代理 {self.spec.role}"),
                    {"role": "user", "content": step.goal},
                ]
            )
            assert self.ctx.verify_constitution_intact(msgs) is True
            return StepOutput(
                run_id=step.run_id,
                task_id=step.task_id,
                step_id=step.step_id,
                success=True,
                summary=f"isolated_ok:{self.spec.subagent_id}",
            )

    pool = AffinitySubagentPool(worker_factory=lambda spec, ctx: _InspectWorker(spec, ctx))
    specs = [
        SubagentSpec(
            subagent_id="sub_a",
            role="analyst_a",
            model="qwen3-14b",
            goal="分析秘密段落",
            brief="PRIVATE_PAYLOAD_ONLY_FOR_SUB_A",
            work_mode=WorkMode.EXECUTE,  # 企图越权申请 EXECUTE
        ),
        SubagentSpec(
            subagent_id="sub_b",
            role="analyst_b",
            model="qwen3-14b",
            goal="分析公开文档",
            brief="PUBLIC_BRIEF_B",
            work_mode=WorkMode.PLAN,
        ),
    ]

    # 父任务为 ASK 只读模式 -> 所有子代理必须被钳位回 ASK，绝不允许越权！
    report = pool.run_batch(specs, parent_work_mode=WorkMode.ASK)
    assert report.all_succeeded is True
    assert clamp_work_mode(WorkMode.ASK, WorkMode.EXECUTE) == WorkMode.ASK
    assert seen_steps["sub_a"].work_mode == WorkMode.ASK
    assert seen_steps["sub_b"].work_mode == WorkMode.ASK
    assert report.results["sub_a"].effective_work_mode == WorkMode.ASK
    # 严格逻辑隔离：sub_b 初始 context_messages 必须为空，且绝不可见 sub_a 的私密上下文
    assert seen_steps["sub_b"].context_messages == []
    assert "PRIVATE_PAYLOAD_ONLY_FOR_SUB_A" not in seen_steps["sub_b"].goal


# =====================================================================
# 四、Beta 端到端集成验收（HuiQiaoService -> Router -> CodeActWorker -> M08 沙箱）
# =====================================================================


def test_beta_e2e_huiqiao_service_l2c_codeact_sandbox_pipeline(tmp_path: pathlib.Path) -> None:
    """Beta 里程碑闭环：从统一网关提交可验证编程任务 -> 路由 L2-C -> M08 沙箱实跑校验 -> 落盘产物。"""
    turns = {"n": 0}

    def codeact_model(_msgs: list[dict[str, str]]) -> str:
        turns["n"] += 1
        if turns["n"] == 1:
            return json.dumps(
                {
                    "action": "run_code",
                    "code": (
                        "import json, pathlib\n"
                        "fib = [0, 1]\n"
                        "for _ in range(8):\n"
                        "    fib.append(fib[-1] + fib[-2])\n"
                        "pathlib.Path('fib.json').write_text(json.dumps({'fib10': fib}), encoding='utf-8')\n"
                        "print('FIB_OK', fib[-1])\n"
                    ),
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "action": "finish",
                "summary": "已在 M08 安全沙箱内生成前 10 项斐波那契数列并落盘 fib.json（第10项=34）。",
                "notes": "Beta 里程碑全链路离线验真通过。",
            },
            ensure_ascii=False,
        )

    ws = tmp_path / "beta_ws"
    ws.mkdir()
    svc = HuiQiaoService(
        repo_root=REPO_ROOT,
        db_path=tmp_path / "beta_state.db",
        codeact_infer_fn=codeact_model,
    )
    health = svc.healthcheck()
    assert health["ok"] is True
    assert health["version"] >= "0.2.0"
    assert health["checks"]["sandbox"] is True

    res = svc.submit_task(
        "请编写 Python 脚本计算斐波那契前 10 项并输出 JSON 文件，需单元测试验证",
        work_mode=WorkMode.EXECUTE,
        allowed_paths=[str(ws)],
        metadata={
            "verifier_code": (
                "import json, pathlib\n"
                "d = json.loads(pathlib.Path('fib.json').read_text(encoding='utf-8'))\n"
                "assert d['fib10'] == [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]\n"
            )
        },
    )
    assert res["status"] == "COMPLETED", res
    assert res["route_decision"]["channel"] == ExecutionChannel.L2C_CODEACT.value
    assert "34" in res["summary"]
    assert (ws / "fib.json").exists()
    assert json.loads((ws / "fib.json").read_text(encoding="utf-8"))["fib10"][-1] == 34
