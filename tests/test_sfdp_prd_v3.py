"""PRD v3.0 §5–§10 铸泽 SFDP（规格先行设计与五件套交付）全量验收测试."""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from packages.gateway import HuiQiaoService, create_app
from packages.orchestrator import ChuZeSfdpEngine, SqliteStateStore, validate_delivery_five_pieces

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_sfdp_clarify_gate_and_spec_freeze_anti_drift_lock(tmp_path: pathlib.Path) -> None:
    """验收 ① & 风险矩阵防规格漂移：澄清门 <=5 问写入 spec，冻结后篡改 AC 必抛 PermissionError。"""
    store = SqliteStateStore(tmp_path / "sfdp.db", artifacts_root=tmp_path / "runs")
    engine = ChuZeSfdpEngine(store)

    clarified = engine.generate_clarify_questions("构建一个本地禅修计时与每日功课打卡小程序")
    tid = clarified["task_id"]
    assert 1 <= len(clarified["clarify_qa"]) <= 5
    assert clarified["spec"]["frozen"] is False
    assert len(clarified["spec"]["ac_list"]) >= 3

    # 超过 5 个澄清问题被硬拒绝
    with pytest.raises(ValueError):
        store.save_clarify_qa(tid, [{"question": f"q{i}", "answer": "a"} for i in range(6)])

    # 冻结规格
    frozen = engine.build_spec_workshop(tid, "构建禅修打卡小程序", freeze=True)
    assert frozen["frozen"] is True

    # 企图在冻结后偷改 AC 条款使测试“永远通过” -> 被防漂移死锁 100% 拦截！
    with pytest.raises(PermissionError, match="防漂移死锁"):
        store.append_spec(
            spec_id="spc_tamper",
            task_id=tid,
            spec_md=frozen["spec_md"],
            plan_md=frozen["plan_md"],
            tasks=frozen["tasks"],
            ac_list=[{"ac_id": "AC-FAKE", "title": "假通过"}],
            frozen=True,
        )


def test_sfdp_converge_appends_remediation_task_and_delivers_five_pieces(tmp_path: pathlib.Path) -> None:
    """验收 ② & ③：首轮输出缺 localStorage 未过 AC -> converge 只追加修复任务不改 AC -> 二轮收敛产出齐全五件套。"""
    store = SqliteStateStore(tmp_path / "conv.db", artifacts_root=tmp_path / "runs")
    engine = ChuZeSfdpEngine(store)
    info = engine.generate_clarify_questions("构建一个背诵俱舍诵疏打卡小程序")
    tid = info["task_id"]
    orig_ac = info["spec"]["ac_list"]

    round_n = {"n": 0}

    def two_stage_model(_msgs: list[dict[str, str]]) -> str:
        round_n["n"] += 1
        # 第 1 轮构建（round_n=1,2）故意漏写 localStorage，触发 AC-03 失败
        if round_n["n"] == 1:
            return (
                "```html\n"
                "<!DOCTYPE html><html><body>" + ("<p>俱舍诵疏静态页</p>" * 12) + "<script>function f(){}</script></body></html>\n"
                "```"
            )
        if round_n["n"] == 2:
            return '{"action": "finish", "summary": "首轮草稿"}'
        # 第 2 轮收敛（收到未通过 AC 反馈后补齐按钮 onclick 与 localStorage）
        if round_n["n"] == 3:
            return (
                "```html\n"
                "<!DOCTYPE html><html><body><h1>俱舍诵疏打卡</h1>"
                "<button onclick=\"save()\">打卡+1</button>"
                "<script>function save(){ localStorage.setItem('k','1'); }</script>"
                + ("<!-- pad -->" * 20)
                + "</body></html>\n"
                "```"
            )
        return '{"action": "finish", "summary": "已补齐 localStorage 与打卡按钮并通过全部 AC。"}'

    out = engine.build_and_converge(tid, goal="构建一个背诵俱舍诵疏打卡小程序", infer_fn=two_stage_model)
    assert out["status"] == "COMPLETED"
    assert out["delivery"]["status"] == "converged"
    # 验证 AC 未被篡改，且 tasks 列表以追加方式记录了收敛补齐子任务
    assert out["spec"]["ac_list"] == orig_ac
    assert len(out["spec"]["tasks"]) >= 3
    assert "收敛补齐缺口" in out["spec"]["tasks"][-1]["title"]
    # 验证五件套物理文件与 B10 证据印章齐全
    assert len(out["delivery"]["artifact_refs"]) >= 1
    assert "B10_EVIDENCE_SEAL:" in out["delivery"]["self_check"]


def test_b10_delivery_gate_blocks_missing_piece_and_forged_self_check(tmp_path: pathlib.Path) -> None:
    """验收 ④：交付包缺件或模型伪造自检报告（无客观沙箱印章） -> 拦截率 100%。"""
    f = tmp_path / "index.html"
    f.write_text("<html></html>", encoding="utf-8")

    # 1. 缺变更清单
    ok_missing, reasons_missing = validate_delivery_five_pieces(
        artifact_refs=[str(f)],
        change_list="",
        log_ref="# 沙箱执行日志足够长度记录内容",
        self_check="# 自检报告 B10_EVIDENCE_SEAL:abc123",
        acceptance_protocol="# 验收与回滚协议足够长度说明内容",
        objective_evidence_token="B10_EVIDENCE_SEAL:abc123",
    )
    assert ok_missing is False
    assert any("变更清单" in r for r in reasons_missing)

    # 2. 五件套字数够但伪造自检（无客观 B10 证据印章）
    ok_forged, reasons_forged = validate_delivery_five_pieces(
        artifact_refs=[str(f)],
        change_list="# 变更清单 index.html 100 bytes",
        log_ref="# 沙箱执行日志 exit_code=0",
        self_check="# 我自己口头宣布全部 AC 都通过啦！",
        acceptance_protocol="# 验收协议：打开浏览器查看即可回滚",
        objective_evidence_token=None,
    )
    assert ok_forged is False
    assert any("ANTI_FORGERY_BLOCKED" in r for r in reasons_forged)


def test_fastapi_sfdp_design_to_run_endpoints(tmp_path: pathlib.Path) -> None:
    svc = HuiQiaoService(repo_root=REPO_ROOT, db_path=tmp_path / "api_sfdp.db")
    client = TestClient(create_app(svc))

    c_res = client.post("/api/sfdp/clarify", json={"goal": "构建一个本地阅读笔记打卡网页小程序"})
    assert c_res.status_code == 200
    tid = c_res.json()["task_id"]
    qa = c_res.json()["clarify_qa"]
    qa[0]["answer"] = "黑金禅意单文件 HTML 应用，含章节进度条"

    b_res = client.post(
        "/api/sfdp/build",
        json={"task_id": tid, "goal": "构建一个本地阅读笔记打卡网页小程序", "qa_items": qa},
    )
    assert b_res.status_code == 200
    run_data = b_res.json()
    assert run_data["status"] == "COMPLETED"
    assert run_data["delivery"]["status"] == "converged"
    assert any(a["name"] == "index.html" for a in run_data["artifacts"])
