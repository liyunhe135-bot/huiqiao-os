"""M05 持久化编排引擎验收单测：WAL、ADK 五原语、YAML 流、HITL、中途改向、部分产物保留与真实子进程强杀续跑."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from packages.core.contracts import WorkMode
from packages.governance import GovernanceGuard
from packages.orchestrator import (
    FlowContext,
    GraphRouter,
    InterruptSignal,
    LoopFlow,
    OrchestratorEngine,
    ParallelFlow,
    SequentialFlow,
    SqliteStateStore,
    TaskNode,
    load_yaml_flow,
)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _make_engine(tmp_path: pathlib.Path, *, guard: GovernanceGuard | None = None) -> OrchestratorEngine:
    store = SqliteStateStore(tmp_path / "data" / "state.db", artifacts_root=tmp_path / "runs")
    return OrchestratorEngine(store, guard=guard)


# === 1. SQLite WAL 模式与基础健康检查 ===
def test_sqlite_wal_mode_and_healthcheck(tmp_path: pathlib.Path) -> None:
    eng = _make_engine(tmp_path)
    assert eng.store.journal_mode() == "wal"
    assert eng.healthcheck() is True


# === 2. ADK 五原语：Sequential + Parallel(亲和串行/并发) + Loop + GraphRouter ===
def test_sequential_and_parallel_and_loop_nested(tmp_path: pathlib.Path) -> None:
    eng = _make_engine(tmp_path)
    log: list[str] = []

    def step_init(ctx: FlowContext) -> dict:
        log.append("init")
        return {"score": 0, "items": []}

    def branch_a(ctx: FlowContext) -> dict:
        log.append("branch_a")
        return {"a_val": 10}

    def branch_b(ctx: FlowContext) -> dict:
        log.append("branch_b")
        return {"b_val": 20}

    def refine(ctx: FlowContext) -> dict:
        cur = int(ctx.state.get("score", 0)) + 1
        log.append(f"refine_{cur}")
        return {"score": cur}

    flow = SequentialFlow(
        node_id="main_seq",
        steps=[
            TaskNode("init", step_init),
            ParallelFlow(
                node_id="fanout",
                branches=[TaskNode("ba", branch_a), TaskNode("bb", branch_b)],
                max_concurrency=2,
            ),
            LoopFlow(
                node_id="critic_loop",
                body=TaskNode("refine", refine),
                exit_condition=lambda st, _i: st.get("score", 0) >= 3,
                max_iterations=5,
            ),
        ],
    )

    result = eng.run(flow, task_id="tsk_adk")
    assert result["status"] == "COMPLETED"
    assert result["state"]["a_val"] == 10
    assert result["state"]["b_val"] == 20
    assert result["state"]["score"] == 3
    assert "init" in log and "refine_3" in log


def test_graph_router_dynamic_routing_and_step_limit_fuse(tmp_path: pathlib.Path) -> None:
    eng = _make_engine(tmp_path)

    def plan_node(ctx: FlowContext) -> dict:
        return {"tries": ctx.state.get("tries", 0) + 1}

    def fix_node(ctx: FlowContext) -> dict:
        return {"fixed": True}

    graph = GraphRouter(
        node_id="dynamic_graph",
        nodes={"plan": TaskNode("plan", plan_node), "fix": TaskNode("fix", fix_node)},
        entry_node="plan",
        router=lambda st: "fix" if st.get("tries", 0) < 2 and not st.get("fixed") else None,
        max_hops=5,
    )
    res = eng.run(graph, task_id="tsk_graph")
    assert res["status"] == "COMPLETED"
    assert res["state"]["fixed"] is True

    # 死循环应触发硬熔断
    infinite_graph = GraphRouter(
        node_id="inf_graph",
        nodes={"loop_self": TaskNode("loop_self", lambda _c: {"tick": 1})},
        entry_node="loop_self",
        router=lambda _st: "loop_self",
        max_hops=3,
    )
    fused = eng.run(infinite_graph, task_id="tsk_inf")
    assert fused["status"] == "FAILED"
    assert "熔断" in (fused["error"] or "")


# === 3. 声明式 YAML Flow 加载与执行 ===
def test_declarative_yaml_flow_loader(tmp_path: pathlib.Path) -> None:
    yaml_file = tmp_path / "demo_flow.yaml"
    yaml_file.write_text(
        """
id: yaml_demo
type: sequential
steps:
  - id: load_doc
    type: task
    handler: load_doc
  - id: polish_loop
    type: loop
    max_iterations: 4
    exit_condition: quality_ok
    body:
      id: polish
      type: task
      handler: polish
""",
        encoding="utf-8",
    )

    flow = load_yaml_flow(
        yaml_file,
        handlers={
            "load_doc": lambda ctx: {"doc": "raw", "quality": 0},
            "polish": lambda ctx: {"quality": ctx.state["quality"] + 1},
        },
        conditions={"quality_ok": lambda st, _i: st.get("quality", 0) >= 2},
    )
    eng = _make_engine(tmp_path)
    res = eng.run(flow, task_id="tsk_yaml")
    assert res["status"] == "COMPLETED"
    assert res["state"]["quality"] == 2


# === 4. HITL 挂起与恢复（联动 M04 GovernanceGuard + 节点主动 InterruptSignal） ===
def test_hitl_pause_and_resume_with_m04_governance(tmp_path: pathlib.Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    guard = GovernanceGuard(offline_only=True, allowed_roots=(ws,), base_dir=tmp_path)
    eng = _make_engine(tmp_path, guard=guard)

    executed: list[str] = []

    def step1(ctx: FlowContext) -> dict:
        executed.append("step1")
        return {
            "target_file": str(ws / "old.txt"),
            "old_content": "old line\n",
            "new_content": "new line\n",
        }

    def step2_delete(ctx: FlowContext) -> dict:
        executed.append("step2_delete")
        return {"deleted": True}

    flow = SequentialFlow(
        node_id="hitl_flow",
        steps=[
            TaskNode("s1", step1, permission="READ"),
            TaskNode("s2", step2_delete, permission="WRITE", action="delete", target_path_key="target_file"),
        ],
    )

    # 首次执行：s1 完成，s2 因高危 delete 触发 M04 ASK_HUMAN 自动挂起
    paused = eng.run(flow, task_id="tsk_hitl", run_id="run_hitl_01", work_mode=WorkMode.EXECUTE)
    assert paused["status"] == "PAUSED_FOR_HUMAN"
    assert executed == ["step1"]
    assert "human_approved" in paused["pending_interrupt"]["missing_evidence"]
    assert "-old line" in paused["pending_interrupt"]["diff_preview"]

    # 人类批准恢复：s1 跳过不重复执行，s2 获得凭证顺利完成
    resumed = eng.resume(flow, "run_hitl_01", approved=True, work_mode=WorkMode.EXECUTE)
    assert resumed["status"] == "COMPLETED"
    assert resumed["state"]["deleted"] is True
    assert executed == ["step1", "step2_delete"]


def test_hitl_rejection_cancels_cleanly(tmp_path: pathlib.Path) -> None:
    eng = _make_engine(tmp_path)

    def ask_node(ctx: FlowContext) -> dict:
        if not ctx.approval_payload:
            raise InterruptSignal(node_id="ask_node", reason="请确认最终发布文案")
        return {"published": True}

    flow = TaskNode("ask_node", ask_node)
    paused = eng.run(flow, task_id="tsk_rej", run_id="run_rej")
    assert paused["status"] == "PAUSED_FOR_HUMAN"

    cancelled = eng.resume(flow, "run_rej", approved=False)
    assert cancelled["status"] == "CANCELLED_BY_HUMAN"


def test_governance_deny_blocks_ask_mode_write(tmp_path: pathlib.Path) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    guard = GovernanceGuard(offline_only=True, allowed_roots=(ws,), base_dir=tmp_path)
    eng = _make_engine(tmp_path, guard=guard)

    flow = TaskNode("bad_write", lambda _c: {"wrote": True}, permission="WRITE")
    res = eng.run(flow, task_id="tsk_deny", work_mode=WorkMode.ASK)
    assert res["status"] == "FAILED"
    assert "安全守卫拦截" in (res["error"] or "")


# === 5. 流式事件订阅、中途改向 steer() 与部分产物保留 ===
def test_streaming_events_and_mid_flight_steering(tmp_path: pathlib.Path) -> None:
    eng = _make_engine(tmp_path)
    seen_hints: list[str] = []

    def step1(ctx: FlowContext) -> dict:
        return {"step1": "done"}

    def step2(ctx: FlowContext) -> dict:
        seen_hints.extend(ctx.steering_hints)
        return {"step2": "steered" if ctx.steering_hints else "normal"}

    flow = SequentialFlow("steer_seq", [TaskNode("s1", step1), TaskNode("s2", step2)])

    event_types: list[str] = []
    for evt in eng.stream_run(flow, task_id="tsk_steer", run_id="run_steer"):
        event_types.append(evt["event_type"])
        # 在 s1 刚完成瞬间动态注入中途改向指令！
        if evt["event_type"] == "node_completed" and evt["node_id"] == "steer_seq/s1":
            eng.steer("run_steer", "输出改为更简洁的要点列表")

    assert "steering_applied" in event_types
    assert seen_hints == ["输出改为更简洁的要点列表"]
    snap = eng.store.get_run("run_steer")
    assert snap is not None and snap["state"]["step2"] == "steered"


def test_partial_artifact_preservation_on_mid_failure(tmp_path: pathlib.Path) -> None:
    eng = _make_engine(tmp_path)

    def s1(ctx: FlowContext) -> dict:
        ctx.save_artifact("stage1_summary.md", "# 第一阶段已完成摘要\n重要数据保留")
        return {"s1": True}

    def s2(ctx: FlowContext) -> dict:
        ctx.save_artifact("stage2_table.csv", "col1,col2\n1,2\n")
        return {"s2": True}

    def s3_boom(ctx: FlowContext) -> dict:
        raise RuntimeError("模拟第 3 步模型超时崩溃")

    flow = SequentialFlow("partial_seq", [TaskNode("s1", s1), TaskNode("s2", s2), TaskNode("s3", s3_boom)])
    res = eng.run(flow, task_id="tsk_partial", run_id="run_partial")
    assert res["status"] == "FAILED"

    arts = eng.store.list_artifacts("run_partial")
    assert len(arts) == 2
    assert {a["name"] for a in arts} == {"stage1_summary.md", "stage2_table.csv"}
    for a in arts:
        assert pathlib.Path(a["file_path"]).exists()


# === 6. 真实子进程强杀（Hard Crash）后重启 100% 无重复副作用续跑测试 ===
def test_real_subprocess_crash_and_exact_resume(tmp_path: pathlib.Path) -> None:
    db_path = tmp_path / "crash_state.db"
    side_effect_log = tmp_path / "side_effects.log"
    worker_script = tmp_path / "crash_worker.py"

    worker_script.write_text(
        f"""
import os, sys, pathlib
sys.path.insert(0, {str(PROJECT_ROOT)!r})
from packages.orchestrator import OrchestratorEngine, SequentialFlow, SqliteStateStore, TaskNode

mode = sys.argv[1]
log_file = pathlib.Path({str(side_effect_log)!r})
store = SqliteStateStore({str(db_path)!r}, artifacts_root={str(tmp_path / 'runs')!r})
eng = OrchestratorEngine(store)

def make_step(name):
    def _fn(ctx):
        with log_file.open("a", encoding="utf-8") as f:
            f.write(name + "\\n")
        if name == "step3" and mode == "crash":
            os._exit(137)  # 模拟 kill -9 进程硬崩溃，无任何 Python cleanup
        return {{name: "ok"}}
    return _fn

flow = SequentialFlow(
    "five_step_flow",
    [TaskNode(f"step{{i}}", make_step(f"step{{i}}")) for i in range(1, 6)],
)

if mode == "crash":
    eng.run(flow, task_id="tsk_crash", run_id="run_crash_01")
else:
    res = eng.resume(flow, "run_crash_01")
    assert res["status"] == "COMPLETED", res
""",
        encoding="utf-8",
    )

    # 第 1 次启动：执行 step1、step2 后在 step3 进程硬崩溃（退出码 137）
    p1 = subprocess.run([sys.executable, str(worker_script), "crash"], capture_output=True, text=True)
    assert p1.returncode == 137

    # 第 2 次重启：从 Checkpoint 无损续跑，step1 与 step2 绝不重复执行
    p2 = subprocess.run([sys.executable, str(worker_script), "resume"], capture_output=True, text=True)
    assert p2.returncode == 0, p2.stderr

    lines = side_effect_log.read_text(encoding="utf-8").splitlines()
    # step1、step2 严格只执行 1 次；step3 因上次中途强杀未落盘 Checkpoint，重启后补完，随后 step4、step5 依次完成
    assert lines.count("step1") == 1
    assert lines.count("step2") == 1
    assert lines.count("step4") == 1
    assert lines.count("step5") == 1
    assert lines[-3:] == ["step3", "step4", "step5"]
