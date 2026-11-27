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
    assert len(res["laws"]) == 7

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
            "text": "构建一个《俱舍诵疏》遮字默背本地小程序，内置原文：「诸一切种诸冥灭，拔众生出生死泥」不得改动，localStorage 离线保存，界面默认大众白话。",
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
