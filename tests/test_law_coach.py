"""汇桥 OS 七律架构教练（LawCoachEngine · 85% 确定性规则 0 显存秒诊 + 15% 可选 AI + 可分享报告）端到端测试."""

from __future__ import annotations

import pathlib

from fastapi.testclient import TestClient

from packages.gateway.api import create_app
from packages.gateway.service import HuiQiaoService


def test_coach_deterministic_seven_laws_oversized_and_jargon_and_destructive(tmp_path: pathlib.Path) -> None:
    svc = HuiQiaoService(
        db_path=tmp_path / "hq.db",
        skills_root=tmp_path / "ws_skills",
        memory_dir=tmp_path / "mem_ws",
        auto_ollama=False,
    )
    # 故意构造一个典型的“航空母舰 + 模糊词 + 未解释佛学词 + 高危删除”客户原始需求
    messy_input = (
        "帮我弄一个好看点、高端大气的阿赖耶识和俱舍大平台，要有账号登录、微信支付、企业后台管理大屏、"
        "AI客服知识库小程序，并且直接删除覆盖我本地旧文件。"
    )
    res = svc.analyze_with_coach(messy_input, work_mode="execute", use_ai=False)
    assert res["engine_mode"] == "deterministic_rules_only"
    assert len(res["laws"]) == 8

    by_id = {lw["law_id"]: lw for lw in res["laws"]}
    # L2 必须抓住航空母舰风险并给出 V0.1 钢丝切片
    assert by_id["L2"]["status"] == "RISK"
    assert res["comparison"]["lego_slice"]["is_oversized"] is True
    assert len(res["comparison"]["lego_slice"]["later_bricks"]) >= 2
    # L3 必须抓住模糊形容词（好看点/高端）
    assert by_id["L3"]["status"] in ("WARN", "RISK")
    # L6 必须抓住未加白话解释的专有名词（阿赖耶识/俱舍）
    assert by_id["L6"]["status"] == "WARN"
    # L7 必须在 execute 模式下抓住“删除/覆盖”高危动作红牌告警
    assert by_id["L7"]["status"] == "RISK"
    # L8 必须抓住缺失定性 Non-Goals / 定量指标 / 数据契约
    assert by_id["L8"]["status"] in ("WARN", "RISK")
    assert "四维沟通契约补齐" in res["comparison"]["optimized_prompt"]
    # 必须自动生成高纯度优化版对比文案与分享 Markdown
    assert "V0.1 最小乐高闭环目标" in res["comparison"]["optimized_prompt"]
    assert "原始输入 vs 教练高纯度优化版" in res["share_markdown"]


def test_coach_optional_15pct_local_ai_and_share_html_preview_api(tmp_path: pathlib.Path) -> None:
    def mock_ai(messages: list[dict[str, str]]) -> str:
        return "1. 杠杆点：先攻单日遮字默背复利；2. 隐形坑：手机端遮字点按区过小；3. 下一积木：艾宾浩斯复习提醒。"

    svc = HuiQiaoService(
        db_path=tmp_path / "hq2.db",
        skills_root=tmp_path / "ws_skills2",
        memory_dir=tmp_path / "mem_ws2",
        semantic_infer_fn=mock_ai,
        auto_ollama=False,
    )
    client = TestClient(create_app(svc))

    # 1. 默认纯代码规则模式（不触发 AI）
    r_rule = client.post(
        "/api/coach/analyze",
        json={
            "text": "面向新手公众构建一个《俱舍诵疏》遮字默背本地小程序，核心闭环<=2次点击，内置原文：「诸一切种诸冥灭，拔众生出生死泥」不得改动，localStorage 离线保存，不做云端登录，界面默认大众白话。",
            "work_mode": "plan",
            "use_ai": False,
        },
    )
    assert r_rule.status_code == 200
    d_rule = r_rule.json()
    assert d_rule["engine_mode"] == "deterministic_rules_only"
    assert d_rule["overall_score"] >= 90
    assert any("AC-04" in a for a in d_rule["comparison"]["auto_assertions"])
    assert d_rule["ai_deep_advice"] == ""

    # 2. 按需开启 15% 本机 AI 点睛 + 一键生成可分享独立 HTML 报告页
    r_share = client.post(
        "/api/coach/share",
        json={
            "text": "构建一个《俱舍诵疏》遮字默背本地小程序，离线保存进度。",
            "work_mode": "plan",
            "use_ai": True,
        },
    )
    assert r_share.status_code == 200
    body = r_share.json()
    assert body["analysis"]["engine_mode"] == "rules_85_plus_local_ai_15"
    assert "杠杆点" in body["analysis"]["ai_deep_advice"]
    preview_url = body["share"]["preview_url"]
    assert preview_url.startswith("/preview/coach/coh_")

    # 3. 预览接口可安全打开且零外部 CDN，并拦截路径穿越
    page = client.get(preview_url)
    assert page.status_code == 200
    assert "汇桥 OS · 七律架构教练诊断对比报告" in page.text
    assert "http://" not in page.text and "https://" not in page.text

    bad = client.get("/preview/coach/..%2Fsecret.html")
    assert bad.status_code in (400, 404)


def test_sfdp_adaptive_quick_vs_deep_dual_view_prd_and_storage_key_contract(tmp_path: pathlib.Path) -> None:
    svc = HuiQiaoService(
        db_path=tmp_path / "hq3.db",
        skills_root=tmp_path / "ws_skills3",
        memory_dir=tmp_path / "mem_ws3",
        auto_ollama=False,
    )
    # 1. 简单微工具默认触发极速 3 问 + 双视角 PRD（视角 A 对外大白话 + 视角 B 对内代码契约）
    q_res = svc.sfdp_clarify_and_draft("做一个本地打卡小程序", depth="auto")
    assert q_res["depth"] == "quick"
    assert len(q_res["clarify_qa"]) == 3
    assert "视角 A · 对外大白话 PRD" in q_res["spec"]["spec_md"]
    assert "Non-Goals" in q_res["spec"]["spec_md"]
    assert "视角 B · 对内严谨代码契约" in q_res["spec"]["plan_md"]

    # 2. 复杂多域需求或显式 depth='deep' 触发深度专家 5 关拷问
    d_res = svc.sfdp_clarify_and_draft("做一个带账号登录和报表导出的本地小程序", depth="auto")
    assert d_res["depth"] == "deep"
    assert len(d_res["clarify_qa"]) == 5

    # 3. 显式签死 localStorage['jushe_contract_v9'] 键名 -> 自动追加 AC-05 并在沙箱强制机检！
    k_goal = "做一个本地背诵打卡小程序，使用 localStorage['jushe_contract_v9'] 存储数据"
    k_clar = svc.sfdp_clarify_and_draft(k_goal, depth="quick")
    ac_ids = [a["ac_id"] for a in k_clar["spec"]["ac_list"]]
    assert "AC-05" in ac_ids

    rounds = {"n": 0}

    def contract_model(_msgs: list[dict[str, str]]) -> str:
        rounds["n"] += 1
        if rounds["n"] == 1:
            # 第 1 轮故意写错存储键名 -> 被 AC-05 拦截打回！
            return (
                "```html\n<!doctype html><html><head><meta charset='utf-8'><title>俱舍打卡测试</title></head>"
                "<body><h1>本地背诵打卡器</h1><p>完全离线保存进度记录，零外部依赖。</p>"
                "<button onclick=\"ok()\">打卡+1</button>"
                "<script>function ok(){ const v=localStorage.getItem('wrong_key')||'0'; localStorage.setItem('wrong_key', v); }</script>"
                "</body></html>\n```"
            )
        return (
            "```html\n<!doctype html><html><head><meta charset='utf-8'><title>俱舍打卡测试</title></head>"
            "<body><h1>本地背诵打卡器</h1><p>完全离线保存进度记录，零外部依赖。</p>"
            "<button onclick=\"ok()\">打卡+1</button>"
            "<script>function ok(){ const v=localStorage.getItem('jushe_contract_v9')||'0'; localStorage.setItem('jushe_contract_v9', v); }</script>"
            "</body></html>\n```"
        )

    svc._codeact_infer_fn = contract_model
    built = svc.sfdp_build_from_spec(k_clar["task_id"], goal=k_goal)
    assert built["status"] == "COMPLETED"
    assert rounds["n"] == 2
    assert "AC-05" in built["delivery"]["self_check"]
