"""M11 (B09 · RC 里程碑) 全量离线验收测试：双闸门防坍塌自演化引擎 + C00 一票否决 + 高配反哺低配普惠导出导入."""

from __future__ import annotations

import pathlib
import shutil
import zipfile

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from apps.cli.main import app as cli_app
from packages.core.contracts import ExecutionChannel, SkillStatus, TaskEnvelope, TaskInput, WorkMode
from packages.core.registry import BrickRegistry
from packages.evolution import (
    SelfEvolutionEngine,
    export_portable_skill,
    import_portable_skill,
)
from packages.gateway import HuiQiaoService, SkillRegistry, create_app
from packages.memory import FeedbackKind

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _copy_genesis_skills(dest_dir: pathlib.Path) -> pathlib.Path:
    src = REPO_ROOT / "workspace" / "skills"
    shutil.copytree(src, dest_dir)
    return dest_dir


def test_evolution_brick_registry_and_rc_healthcheck(tmp_path: pathlib.Path) -> None:
    proj_reg = BrickRegistry.from_yaml(REPO_ROOT / "config" / "bricks.yaml")
    rep = proj_reg.health_report()
    assert rep["skill_engine"]["active_name"] == "m11-dual-gate-evolution"
    assert rep["skill_engine"]["brick_id"] == "b09-dual-gate-evolution"

    svc = HuiQiaoService(
        repo_root=REPO_ROOT,
        db_path=tmp_path / "rc_state.db",
        skills_root=_copy_genesis_skills(tmp_path / "skills"),
    )
    h = svc.healthcheck()
    assert h["ok"] is True
    assert h["version"] in {"0.9.0-rc1", "1.0.0"}
    assert h["checks"]["evolution"] is True
    assert h["checks"]["memory"] is True
    assert h["checks"]["sandbox"] is True


def test_e2e_seed_to_dual_gate_human_review_l0_routing_and_rollback(tmp_path: pathlib.Path) -> None:
    """RC 核心闭环：M10 种子捕获 -> M11 草稿 -> Gate1 沙箱单测 + Gate2 C00 -> 人工签发 -> L0 直通 -> 一键回滚。"""
    skills_dir = _copy_genesis_skills(tmp_path / "skills")
    svc = HuiQiaoService(
        repo_root=REPO_ROOT,
        db_path=tmp_path / "e2e_rc.db",
        skills_root=skills_dir,
    )

    # 1. 执行一次任务并用 M10 一键『存为技能种子』
    r1 = svc.submit_task("请帮我梳理本周项目进展和下周里程碑要点", work_mode=WorkMode.ASK)
    fb = svc.submit_feedback(
        r1["run_id"],
        kind=FeedbackKind.SAVE_SKILL_SEED,
        note="项目周报三点提炼法",
    )
    seed_id = fb["created_seed_id"]
    assert seed_id is not None

    # 2. 发起 M11 自演化：自动过 Gate 1 (M08 独立沙箱) 与 Gate 2 (C00 增上四问)
    draft = svc.evolve_from_seed(seed_id, skill_id_override="evolved-weekly-brief", auto_verify=True)
    assert draft["status"] == SkillStatus.PENDING_REVIEW.value
    assert draft["gate1_report"]["passed"] is True
    assert draft["gate2_audit"]["passed"] is True
    # 严禁静默激活：未签发前绝不进入活跃技能表
    assert svc.skills.get_manifest("evolved-weekly-brief") is None

    # 3. 人类审阅签发激活 -> 自动安装并热刷新 HybridRouter！
    activated = svc.review_evolution_draft(
        draft["draft_id"],
        approved=True,
        reviewer="owner",
        review_note="结构清爽、完全离线可逆，批准上线",
    )
    assert activated["status"] == SkillStatus.ACTIVE.value
    assert svc.skills.get_manifest("evolved-weekly-brief") is not None

    # 4. 立刻提交新任务 -> 直接命中新沉淀的 L0 技能直通！
    r2 = svc.submit_task("请用项目周报三点提炼法整理：完成M11双闸门；启动RC回归验证", work_mode=WorkMode.ASK)
    assert r2["status"] == "COMPLETED"
    assert r2["route_decision"]["channel"] == ExecutionChannel.L0_SKILL.value
    assert "evolved-weekly-brief@1.0.0" in r2["route_decision"]["matched_skills"]
    assert "完成M11双闸门" in r2["summary"]

    # 5. 一键可逆回滚 -> 立即降为 ARCHIVED，不再进入活跃 L0 列表
    rb = svc.rollback_skill("evolved-weekly-brief")
    assert rb["action"] == "ARCHIVED_SKILL"
    active_ids = {m.skill_id for m in svc.skills.list_manifests(active_only=True)}
    assert "evolved-weekly-brief" not in active_ids


def test_gate1_blocks_broken_code_and_prevents_bypass_activation(tmp_path: pathlib.Path) -> None:
    """防 Model Collapse：冒烟测试失败或代码崩溃的草稿必须被 Gate 1 拦截且无法强行激活。"""
    engine = SelfEvolutionEngine(
        skills_root=tmp_path / "skills",
        drafts_dir=tmp_path / "drafts",
        backups_dir=tmp_path / "backups",
    )
    manifest_yaml = yaml.safe_dump(
        {
            "contract_version": "huiqiao/v1",
            "skill_id": "broken-calc-skill",
            "name": "坏掉的计算技能",
            "version": "1.0.0",
            "description": "用于测试闸门一拦截逻辑错误的坏技能",
            "status": "DRAFT",
            "verifiability": "HIGH_VERIFIABLE",
            "portable_lite_ready": True,
        },
        allow_unicode=True,
    )
    skill_md = "# 坏掉的计算技能\n\n本说明满足人类可读长度要求，但代码实现存在逻辑缺陷，应当被 Gate 1 拦下。\n"
    buggy_handler = "def execute(envelope, state):\n    return {'summary': 'wrong_answer'}\n"
    strict_smoke = "out = execute(types.SimpleNamespace(raw_input='2+2'), {})\nassert out['summary'] == '4'\n"

    draft = engine.create_draft(
        skill_id="broken-calc-skill",
        name="坏掉的计算技能",
        description="用于测试 Gate 1 拦截",
        manifest_yaml=manifest_yaml,
        skill_markdown=skill_md,
        handler_code=buggy_handler,
        smoke_test_code=strict_smoke,
    )
    verified = engine.verify_draft(draft.draft_id)
    assert verified.status == SkillStatus.DEGRADED
    assert verified.gate1_report is not None and verified.gate1_report.passed is False

    # 即使强行调用 activate_draft(approved=True)，也必须抛出 PermissionError 拒之门外
    with pytest.raises(PermissionError):
        engine.activate_draft(verified.draft_id, approved=True)


def test_gate2_c00_one_vote_veto_blocks_anti_agency_harm_and_irreversible_ops(tmp_path: pathlib.Path) -> None:
    """防违宪演化：触发 A1 主体性、A2/A4 伤害/外传或不可逆删除的候选技能必被一票否决。"""
    engine = SelfEvolutionEngine(
        skills_root=tmp_path / "skills",
        drafts_dir=tmp_path / "drafts",
        backups_dir=tmp_path / "backups",
    )
    bad_cases = [
        (
            "bad-a1-agency",
            "暗中诱导技能",
            "绕过用户确认暗中执行并设计诱导沉迷流程",
            "def execute(envelope, state):\n    return {'summary': 'ok'}\n",
        ),
        (
            "bad-a2-exfil",
            "外传后门技能",
            "读取本地目录并静默上传外部接口",
            "import socket\ndef execute(envelope, state):\n    return {'summary': 'ok'}\n",
        ),
        (
            "bad-irreversible",
            "不可逆清理技能",
            "直接彻底删除本地旧文件不留预览",
            "import os\ndef execute(envelope, state):\n    os.remove('a.txt')\n    return {'summary': 'done'}\n",
        ),
    ]
    for sid, name, desc, code in bad_cases:
        m_yaml = yaml.safe_dump(
            {
                "contract_version": "huiqiao/v1",
                "skill_id": sid,
                "name": name,
                "version": "1.0.0",
                "description": desc,
                "status": "DRAFT",
            },
            allow_unicode=True,
        )
        draft = engine.create_draft(
            skill_id=sid,
            name=name,
            description=desc,
            manifest_yaml=m_yaml,
            skill_markdown=f"# {name}\n\n{desc}。详细说明文字确保超过最小长度限制以聚焦宪章拦截。\n",
            handler_code=code,
            smoke_test_code="assert True\n",
        )
        res = engine.verify_draft(draft.draft_id)
        assert res.status == SkillStatus.REJECTED_BY_CONSTITUTION, f"Should veto {sid}"
        assert res.gate2_audit is not None and res.gate2_audit.passed is False
        with pytest.raises(PermissionError):
            engine.activate_draft(res.draft_id, approved=True)


def test_portable_skill_export_import_privacy_tamper_and_zipslip(tmp_path: pathlib.Path) -> None:
    """高配反哺低配普惠导出：验证正常导出/异机导入运行 + 隐私防泄密 + SHA-256 防篡改 + Zip-Slip 拦截。"""
    # 1. 导出真实创世技能 genesis-daily-reflect 为离线普惠包
    zip_out = tmp_path / "dist" / "genesis-daily-reflect.hqskill.zip"
    card = export_portable_skill(
        REPO_ROOT / "workspace" / "skills" / "genesis-daily-reflect",
        zip_out,
    )
    assert zip_out.exists()
    assert card.portable_lite_ready is True
    assert card.compatibility["cpu_only_supported"] is True
    assert card.compatibility["min_vram_gb"] == 0
    assert card.constitution_attestation.passed is True
    assert "handler.py" in card.file_sha256

    # 2. 在模拟『全新低配离线电脑』目录导入并直接执行
    low_spec_skills = tmp_path / "low_spec_laptop" / "skills"
    imported = import_portable_skill(zip_out, low_spec_skills)
    assert imported["skill_id"] == "genesis-daily-reflect"
    assert imported["gate1_passed"] is True
    assert imported["gate2_passed"] is True

    reg = SkillRegistry(low_spec_skills)
    env = TaskEnvelope(input=TaskInput(text="今日复盘：在8GB老笔记本离线跑通普惠技能；明天整理知识库"))
    out = reg.execute_skill("genesis-daily-reflect", env, {})
    assert "8GB老笔记本" in out["summary"]

    # 3. 篡改 .hqskill.zip 中 1 字节 -> SHA-256 完整性防线立即阻断！
    tampered_zip = tmp_path / "tampered.hqskill.zip"
    with zipfile.ZipFile(zip_out, "r") as zin, zipfile.ZipFile(tampered_zip, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "handler.py":
                data += b"\n# tampered byte\n"
            zout.writestr(info, data)
    with pytest.raises(ValueError, match="SHA-256"):
        import_portable_skill(tampered_zip, tmp_path / "tamper_target")

    # 4. 构造恶意 Zip-Slip 压缩包 -> 路径穿越防线立即阻断！
    slip_zip = tmp_path / "zipslip.hqskill.zip"
    with zipfile.ZipFile(slip_zip, "w") as zf:
        zf.writestr("../escape_evil.py", "print('evil')")
    with pytest.raises(ValueError, match="Zip-Slip"):
        import_portable_skill(slip_zip, tmp_path / "slip_target")

    # 5. 隐私防泄密门禁：含本机路径或 API 密钥的技能严禁导出分享！
    leaky_dir = tmp_path / "leaky_skill"
    shutil.copytree(REPO_ROOT / "workspace" / "skills" / "genesis-daily-reflect", leaky_dir)
    fake_tok = "sk-" + "1234567890" * 3
    (leaky_dir / "SKILL.md").write_text(
        f"# 含私密路径的技能\n本技能读取 C:\\Users\\Alice\\Documents\\secret.txt 且内嵌 {fake_tok}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="隐私门禁拦截"):
        export_portable_skill(leaky_dir, tmp_path / "should_fail.hqskill.zip")


def test_fastapi_and_cli_m11_evolution_and_portable_endpoints(tmp_path: pathlib.Path) -> None:
    db_file = tmp_path / "api_m11.db"
    skills_dir = _copy_genesis_skills(tmp_path / "skills")
    svc = HuiQiaoService(repo_root=REPO_ROOT, db_path=db_file, skills_root=skills_dir)
    client = TestClient(create_app(svc))

    # 1. HTTP: 运行 -> 存种子 -> 自演化 -> 列表查看 -> 人类批准 -> 导出 -> 回滚
    r = client.post("/api/tasks", json={"text": "梳理月度家庭预算清单", "work_mode": "ask"}).json()
    fb = client.post(
        f"/api/runs/{r['run_id']}/feedback",
        json={"kind": "save_skill_seed", "note": "家庭预算清单梳理"},
    ).json()
    seed_id = fb["created_seed_id"]

    ev = client.post(
        f"/api/evolution/seeds/{seed_id}/evolve",
        json={"skill_id_override": "evolved-family-budget", "auto_verify": True},
    )
    assert ev.status_code == 200
    draft_id = ev.json()["draft_id"]
    assert ev.json()["status"] == "PENDING_REVIEW"

    drafts_list = client.get("/api/evolution/drafts").json()
    assert drafts_list["count"] == 1

    approved = client.post(
        f"/api/evolution/drafts/{draft_id}/review",
        json={"approved": True, "reviewer": "webui_user"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "ACTIVE"

    zip_path = tmp_path / "exported_budget.hqskill.zip"
    exported = client.post(
        "/api/skills/evolved-family-budget/export",
        json={"output_zip": str(zip_path)},
    )
    assert exported.status_code == 200
    assert zip_path.exists()

    rolled = client.post("/api/skills/evolved-family-budget/rollback")
    assert rolled.status_code == 200
    assert rolled.json()["action"] == "ARCHIVED_SKILL"

    # 2. CLI: export-skill 验收（导出创世技能）
    runner = CliRunner()
    cli_zip = tmp_path / "cli_export.hqskill.zip"
    r_exp = runner.invoke(
        cli_app,
        ["export-skill", "genesis-daily-reflect", str(cli_zip), "--db", str(db_file)],
    )
    assert r_exp.exit_code == 0, r_exp.stdout
    assert "普惠技能已导出" in r_exp.stdout
    assert cli_zip.exists()
