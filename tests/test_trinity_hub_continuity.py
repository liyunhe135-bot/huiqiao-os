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


def test_lossless_high_density_condensation_and_behavioral_gates(tmp_path: pathlib.Path) -> None:
    from packages.hub.manager import condense_code_losslessly, extract_immutable_invariants
    from packages.workers.codeact import CodeActWorker

    # 1. 验证超长 HTML (>18KB) 无损脱水：绝不切掉底部 <script> 与 localStorage 契约！
    huge_css = "/* comment */ .box {   padding: 10px;   margin: 10px; }\n" * 450
    tail_script = "<script>function saveProgress(){ localStorage.setItem('jushe_v2','ok'); }</script>"
    big_html = f"<!doctype html><html><head><style>{huge_css}</style></head><body><div id='app'></div>{tail_script}</body></html>"
    assert len(big_html) > 18000
    condensed, contract_hdr = condense_code_losslessly(big_html, ".html", soft_limit=16000)
    assert "function saveProgress()" in condensed
    assert "jushe_v2" in contract_hdr
    assert "saveProgress" in contract_hdr

    # 2. 验证必保逐字原文与分项条款无损提取
    invs = extract_immutable_invariants(
        "开发背诵器：1. 内置归敬颂：「诸一切种诸冥灭，拔众生出生死泥」不得改动；2. 支持遮字默背。"
    )
    assert any("诸一切种诸冥灭，拔众生出生死泥" in x for x in invs)
    assert any("2. 支持遮字默背" in x for x in invs)

    # 3. 验证 CodeAct 沙箱拒绝『悬空 onclick 未定义函数』伪造交付，并在第 2 轮自愈通过！
    calls = {"n": 0}

    def self_healing_model(messages: list[dict[str, str]]) -> str:
        calls["n"] += 1
        last = messages[-1]["content"]
        if calls["n"] == 1:
            # 故意制造常见低质伪造：按钮绑定了 checkInNow()，但 <script> 里写错了函数名！
            return "```html\n<!doctype html><html><body><button onclick=\"checkInNow()\">打卡</button><script>function typoCheckIn(){}</script></body></html>\n```"
        if "未定义的函数" in last:
            return "```html\n<!doctype html><html><body><button onclick=\"checkInNow()\">打卡</button><script>function checkInNow(){ localStorage.setItem('ok','1'); }</script></body></html>\n```"
        return '{"action": "finish", "summary": "已通过行为级闭环自愈交付"}'

    worker = CodeActWorker(
        infer_fn=self_healing_model,
        workspace_dir=tmp_path / "ca_ws",
    )
    from packages.core.contracts import StepInput, WorkMode

    out = worker.run(StepInput(run_id="r_qa", task_id="t_qa", goal="构建打卡器", work_mode=WorkMode.EXECUTE))
    assert out.success is True
    assert calls["n"] == 2  # 第1轮被沙箱断言拦截 -> 第2轮修复通过并零冗余直达交付！

    # 4. 验证 SFDP 必保逐字原文 AC-04 拦截漏字并在第 2 轮自动收敛补齐！
    svc = HuiQiaoService(
        db_path=tmp_path / "hq2.db",
        skills_root=tmp_path / "ws_skills2",
        memory_dir=tmp_path / "mem_ws2",
        auto_ollama=False,
    )
    goal_with_quote = "构建俱舍小程序，内置原文：「诸一切种诸冥灭，拔众生出生死泥」不得改动"
    clar = svc.sfdp_clarify_and_draft(goal_with_quote)
    tid = clar["task_id"]
    ac_ids = [a["ac_id"] for a in clar["spec"]["ac_list"]]
    assert "AC-04" in ac_ids

    round_tracker = {"r": 0}

    def sfdp_model(messages: list[dict[str, str]]) -> str:
        last = messages[-1]["content"]
        if "HTML_APP_VERIFIED" in last or "exit_code=0" in last:
            return '{"action": "finish", "summary": "本轮构建完成"}'
        round_tracker["r"] += 1
        if round_tracker["r"] == 1:
            # 第 1 轮故意漏掉必保原文 -> 触发 SFDP AC-04 只读收敛重跑！
            return "```html\n<!doctype html><html><body><button onclick=\"go()\">背诵</button><script>function go(){ localStorage.setItem('a', localStorage.getItem('a')||'1'); }</script></body></html>\n```"
        return "```html\n<!doctype html><html><body><p>诸一切种诸冥灭，拔众生出生死泥</p><button onclick=\"go()\">背诵</button><script>function go(){ localStorage.setItem('a', localStorage.getItem('a')||'1'); }</script></body></html>\n```"

    svc._codeact_infer_fn = sfdp_model
    built = svc.sfdp_build_from_spec(tid, goal=goal_with_quote)
    assert built["status"] == "COMPLETED"
    assert round_tracker["r"] == 2
    assert "AC-04" in built["delivery"]["self_check"]

    # 5. 验证预置技能规划『经典背诵间隔复习规划师』一键孵化产出真实艾宾浩斯排期表！
    inc = svc.incubate_skill_plan("plan_spaced_recite", auto_activate=True)
    skill_id = inc["draft"]["skill_id"]
    res_recite = svc.submit_task("第一品界品颂；第二品根品颂", skill_id=skill_id)
    assert "+1天" in res_recite["summary"] and "+15天" in res_recite["summary"]
