"""汇桥 OS 三大持久中枢（Skill 规划管理库 · 经验防坑库 · 不断档上下文跟踪）端到端测试."""

from __future__ import annotations

import pathlib

from fastapi.testclient import TestClient

from packages.gateway.api import create_app
from packages.gateway.service import HuiQiaoService


def test_skill_planning_hub_add_and_one_click_incubate(tmp_path: pathlib.Path) -> None:
    svc = HuiQiaoService(
        db_path=tmp_path / "hq.db",
        skills_root=tmp_path / "ws_skills",
        memory_dir=tmp_path / "mem_ws",
        auto_ollama=False,
    )
    plan = svc.add_skill_plan(
        title="读书金句卡片器",
        goal="将输入段落提炼为三张结构化复习卡片并附行动要点",
        priority="P0",
        triggers=["金句卡片", "读书卡片"],
    )
    assert plan["status"] == "PLANNED"
    assert (tmp_path / "mem_ws" / "SKILL_PLAN_HUB.md").exists()

    incubated = svc.incubate_skill_plan(plan["plan_id"], auto_activate=True)
    assert incubated["draft"]["status"] == "ACTIVE"
    new_skill_id = incubated["draft"]["skill_id"]
    active_ids = {m.skill_id for m in svc.list_skills()}
    assert new_skill_id in active_ids


def test_experience_vault_guardrail_injection_and_feedback_sync(tmp_path: pathlib.Path) -> None:
    captured_prompts: list[str] = []

    def mock_codeact(messages: list[dict[str, str]]) -> str:
        last = messages[-1]["content"]
        captured_prompts.append(last)
        if "Sandbox Observation" in last or "exit_code=0" in last:
            return '{"action": "finish", "summary": "已完成阅读打卡小程序构建", "notes": "离线可用"}'
        return "```html\n<!doctype html><html><body><button onclick=\"localStorage.setItem('k','1')\">打卡</button><script>console.log(1)</script></body></html>\n```"

    svc = HuiQiaoService(
        db_path=tmp_path / "hq.db",
        skills_root=tmp_path / "ws_skills",
        memory_dir=tmp_path / "mem_ws",
        codeact_infer_fn=mock_codeact,
        auto_ollama=False,
    )
    custom_exp = svc.add_experience_rule(
        title="字号适老化保护",
        pitfall="正文字号过小影响长辈阅读",
        rule="网页正文字号不小于 15px 并保持高对比度。",
        category="UI与语境",
    )
    assert (tmp_path / "mem_ws" / "EXPERIENCE_VAULT.md").exists()

    run1 = svc.submit_task("构建一个本地经典阅读打卡小程序", work_mode="execute")
    assert run1["status"] == "COMPLETED"
    assert any("汇桥经验防坑库护栏" in p for p in captured_prompts)

    # 用户提交『纠偏』反馈后，应自动同步进入经验防坑库
    svc.submit_feedback(run1["run_id"], kind="correct", note="背诵统计必须默认展示连续天数")
    exps_after = svc.get_hub_overview()["experiences"]
    assert any("连续天数" in e["rule"] for e in exps_after)

    # 测试暂停自动挂载
    toggled = svc.toggle_experience_rule(custom_exp["exp_id"], False)
    assert toggled["auto_inject"] is False


def test_continuous_context_follow_up_and_rolling_compaction(tmp_path: pathlib.Path) -> None:
    seen_messages: list[list[dict[str, str]]] = []

    def mock_codeact(messages: list[dict[str, str]]) -> str:
        seen_messages.append([dict(m) for m in messages])
        last = messages[-1]["content"]
        if "Sandbox Observation" in last or "exit_code=0" in last:
            return '{"action": "finish", "summary": "已完成俱舍打卡小程序增量更新", "notes": "已保留原功能"}'
        return (
            "```html\n<!doctype html><html><body><h1>俱舍打卡 v1</h1>"
            "<button onclick=\"localStorage.setItem('c','1')\">+1</button><script>let x=1;</script></body></html>\n```"
        )

    svc = HuiQiaoService(
        db_path=tmp_path / "hq.db",
        skills_root=tmp_path / "ws_skills",
        memory_dir=tmp_path / "mem_ws",
        codeact_infer_fn=mock_codeact,
        auto_ollama=False,
    )
    # 第 1 轮：创建应用
    r1 = svc.submit_task("构建一个俱舍背诵打卡小程序", work_mode="execute")
    assert r1["status"] == "COMPLETED"
    ses = svc.hub.get_active_session()
    assert ses["pinned_preview_url"] is not None
    assert len(ses["turns"]) == 1

    # 第 2 轮：仅说『继续加上 15 分钟倒计时器』（不含"小程序"字样），验证连续路由 + 自动附带上一版 index.html 源码！
    r2 = svc.submit_task("继续加上 15 分钟倒计时器", work_mode="execute")
    assert r2["status"] == "COMPLETED"
    assert r2["route_decision"]["channel"] == "L2C_CODEACT"
    last_call_msgs = seen_messages[-1]
    joined_prompt = "\n".join(m["content"] for m in last_call_msgs)
    assert "俱舍打卡 v1" in joined_prompt  # 证明上一版 index.html 已被自动挂载！
    assert "已继承上一版代码增量演进" in r2["model_notes"]

    # 连续多轮推进超过 6 轮，验证自动滚动浓缩摘要且不断档
    for i in range(3, 9):
        svc.hub.record_turn_completion(
            session_id=ses["session_id"],
            run_id=f"run_extra_{i}",
            raw_goal=f"第{i}轮微调样式与快捷键",
            summary=f"已完成第{i}轮增量更新",
        )
    ses_compacted = svc.hub.get_active_session()
    assert len(ses_compacted["turns"]) == 5
    assert ses_compacted["total_turns"] == 8
    assert "第1轮" in ses_compacted["rolling_summary"]
    assert (tmp_path / "mem_ws" / "ACTIVE_CONTEXT.md").exists()


def test_hub_rest_api_endpoints(tmp_path: pathlib.Path) -> None:
    svc = HuiQiaoService(
        db_path=tmp_path / "hq.db",
        skills_root=tmp_path / "ws_skills",
        memory_dir=tmp_path / "mem_ws",
        auto_ollama=False,
    )
    client = TestClient(create_app(svc))

    ov = client.get("/api/hub/overview")
    assert ov.status_code == 200
    body = ov.json()
    assert "skill_hub" in body and "experiences" in body and "context" in body

    s_new = client.post("/api/hub/sessions", json={"title": "第二测试项目"})
    assert s_new.status_code == 200
    sid = s_new.json()["session_id"]

    s_sw = client.post(f"/api/hub/sessions/{sid}/switch")
    assert s_sw.status_code == 200
    assert s_sw.json()["title"] == "第二测试项目"
