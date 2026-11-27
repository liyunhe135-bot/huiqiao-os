"""M10 (B08) 全量离线验收测试：File-First 分层记忆 + 中英 FTS5/向量混合双时态检索 + 手改 Markdown 同步 + 1 秒 4 键反馈闭环."""

from __future__ import annotations

import os
import pathlib
import re
import time

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from apps.cli.main import app as cli_app
from packages.core.contracts import BrickLayer, SkillStatus, WorkMode
from packages.core.interfaces import MemoryStoreProtocol
from packages.core.registry import BrickRegistry
from packages.gateway import HuiQiaoService, create_app
from packages.memory import (
    FeedbackKind,
    FileFirstMemoryStore,
    MemoryLayer,
    MemoryRecord,
    MemoryStatus,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_memory_protocol_and_brick_registry_resolution(tmp_path: pathlib.Path) -> None:
    proj_reg = BrickRegistry.from_yaml(REPO_ROOT / "config" / "bricks.yaml")
    rep = proj_reg.health_report()
    assert rep["memory"]["active_name"] == "m10-file-first-memory"
    assert rep["memory"]["brick_id"] == "b08-file-first-memory"

    cfg = tmp_path / "mem_bricks.yaml"
    ws_posix = (tmp_path / "ws").as_posix()
    cfg.write_text(
        f"""
schema_version: "huiqiao/v1"
slots:
  memory:
    active: "m10-file-first-memory"
    bricks:
      m10-file-first-memory:
        brick_id: "b08-file-first-memory"
        layer: "memory"
        version: "1.0.0"
        contract_version: "huiqiao/v1"
        entrypoint: "packages.memory.store:FileFirstMemoryStore"
        enabled: true
        config:
          workspace_dir: "{ws_posix}"
""",
        encoding="utf-8",
    )
    reg = BrickRegistry.from_yaml(cfg)
    store = reg.resolve(BrickLayer.MEMORY)
    assert isinstance(store, FileFirstMemoryStore)
    assert isinstance(store, MemoryStoreProtocol)
    assert store.healthcheck() is True


def test_bilingual_hybrid_recall_fts5_and_vector(tmp_path: pathlib.Path) -> None:
    store = FileFirstMemoryStore(tmp_path)
    store.commit({"content": "用户偏好每周五下午生成三点式精简周报", "layer": "core", "tags": ["weekly"]})
    store.commit({"content": "持久化层统一使用 SQLite WAL 模式防止断电损坏", "layer": "core", "tags": ["arch"]})
    store.commit({"content": "严禁在业务代码中使用吞掉错误的裸 except pass", "layer": "anti_pattern"})

    t0 = time.perf_counter()
    hits_cn = store.recall("周五周报格式", top_k=2)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    assert elapsed_ms < 200.0
    assert len(hits_cn) >= 1
    assert "三点式精简周报" in hits_cn[0]["content"]

    hits_en = store.recall("SQLite WAL 持久化", top_k=2)
    assert len(hits_en) >= 1
    assert "SQLite WAL" in hits_en[0]["content"]


def test_bi_temporal_preference_supersede_and_history_audit(tmp_path: pathlib.Path) -> None:
    store = FileFirstMemoryStore(tmp_path)
    old_rec = store.commit_record(
        MemoryRecord(
            content="汇报偏好：两千字详尽长文",
            topic_key="report_style",
            layer=MemoryLayer.CORE,
        )
    )
    new_rec = store.commit_record(
        MemoryRecord(
            content="汇报偏好：先给三行核心结论再附表格",
            topic_key="report_style",
            layer=MemoryLayer.CORE,
        )
    )

    # 1. 默认活跃召回仅返回最新认知，不产生旧偏好干扰
    active_hits = store.recall("汇报偏好", top_k=5)
    assert len(active_hits) == 1
    assert active_hits[0]["memory_id"] == new_rec.memory_id
    assert "三行核心结论" in active_hits[0]["content"]

    # 2. MEMORY.md 仅保留最新 ACTIVE 条目
    md_text = store.memory_md_path.read_text(encoding="utf-8")
    assert "三行核心结论" in md_text
    assert "两千字详尽长文" not in md_text

    # 3. 开启 include_history=True 可完整追溯双时态更替链
    history_hits = store.recall("汇报偏好", top_k=5, include_history=True)
    by_id = {h["memory_id"]: h for h in history_hits}
    assert old_rec.memory_id in by_id
    assert by_id[old_rec.memory_id]["status"] == MemoryStatus.SUPERSEDED.value
    assert by_id[old_rec.memory_id]["superseded_by"] == new_rec.memory_id
    assert by_id[old_rec.memory_id]["invalidated_at"] is not None
    assert by_id[old_rec.memory_id]["valid_until"] is not None


def test_file_first_human_markdown_edit_two_way_sync_and_forget(tmp_path: pathlib.Path) -> None:
    store = FileFirstMemoryStore(tmp_path)
    id_keep = store.commit({"content": "代码注释保持精炼中文", "layer": "core"})
    id_delete = store.commit({"content": "待删除的临时旧规则", "layer": "core"})

    # 模拟人类直接用记事本修改 MEMORY.md：修改 id_keep、删掉 id_delete、手写新增一行无 ID 条目
    md_original = store.memory_md_path.read_text(encoding="utf-8")
    assert id_delete in md_original

    edited_lines: list[str] = []
    for ln in md_original.splitlines():
        if id_delete in ln:
            continue  # 人类手工删除该行
        if id_keep in ln:
            edited_lines.append(f"- [{id_keep}] (core:comment_lang) 代码关键契约处写清中文注释")
        else:
            edited_lines.append(ln)
        if "长期偏好与核心认知" in ln:
            edited_lines.append("- (core:analogy) 解释复杂架构时优先打乐高积木比方")

    store.memory_md_path.write_text("\n".join(edited_lines) + "\n", encoding="utf-8")
    # 确保文件系统 mtime 推进（防止极快写入在同一纳秒内）
    st = store.memory_md_path.stat()
    os.utime(store.memory_md_path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))

    # 无需手动调用 sync，直接 recall 自动检测 mtime 变化并完成双向同步！
    analogy_hits = store.recall("乐高积木比方", top_k=3)
    assert len(analogy_hits) >= 1
    assert "乐高积木比方" in analogy_hits[0]["content"]

    all_with_inactive = {m["memory_id"]: m for m in store.list_memories(include_inactive=True)}
    assert all_with_inactive[id_keep]["content"] == "代码关键契约处写清中文注释"
    assert all_with_inactive[id_delete]["status"] == MemoryStatus.FORGOTTEN.value

    # 再测试 API 一键 forget()
    forgotten = store.forget(id_keep)
    assert forgotten["status"] == MemoryStatus.FORGOTTEN.value
    assert id_keep not in store.memory_md_path.read_text(encoding="utf-8")


def test_daily_episodic_markdown_log_append(tmp_path: pathlib.Path) -> None:
    store = FileFirstMemoryStore(tmp_path)
    mem_id = store.commit(
        {
            "content": "完成 M10 双时态记忆引擎自测",
            "layer": "episodic",
            "source": "agent",
            "source_run_id": "run_demo_01",
        }
    )
    daily_files = list(store.daily_dir.glob("*.md"))
    assert len(daily_files) == 1
    daily_text = daily_files[0].read_text(encoding="utf-8")
    assert mem_id in daily_text
    assert "完成 M10 双时态记忆引擎自测" in daily_text


def test_four_key_feedback_loop_recalls_into_next_task_and_captures_seed(tmp_path: pathlib.Path) -> None:
    svc = HuiQiaoService(
        repo_root=REPO_ROOT,
        db_path=tmp_path / "m10_state.db",
    )
    r1 = svc.submit_task("我对独立产品冷启动节奏有些犹豫，请给我启发拆解", work_mode=WorkMode.ASK)
    run_id = r1["run_id"]
    assert r1["status"] == "COMPLETED"

    # 1. 👍 赞 (<200ms)
    fb_praise = svc.submit_feedback(run_id, kind=FeedbackKind.PRAISE, note="追问角度很到位")
    assert fb_praise["elapsed_ms"] < 200.0
    assert fb_praise["created_memory_id"] is not None

    # 2. 👎 踩 (<200ms) -> 写入反模式
    fb_dislike = svc.submit_feedback(run_id, kind=FeedbackKind.DISLIKE, note="不要堆砌空洞行业黑话")
    assert fb_dislike["elapsed_ms"] < 200.0
    assert "不要堆砌空洞行业黑话" in svc.memory.memory_md_path.read_text(encoding="utf-8")

    # 3. ✏️ 纠偏 (<200ms) -> 写入长期偏好，并在下一次任务自动召回生效！
    fb_correct = svc.submit_feedback(
        run_id,
        kind=FeedbackKind.CORRECT,
        note="讨论冷启动产品时优先采用『最小闭环验证』框架",
        topic_key="cold_start_pref",
    )
    assert fb_correct["elapsed_ms"] < 200.0

    r2 = svc.submit_task("再聊聊独立产品冷启动第一步怎么做？", work_mode=WorkMode.ASK)
    assert r2["status"] == "COMPLETED"
    assert "本地透明记忆" in r2["model_notes"]

    # 4. 🌱 存为技能种子 (<200ms) -> 生成 CAPTURED 候选直供 M11！
    fb_seed = svc.submit_feedback(
        run_id,
        kind=FeedbackKind.SAVE_SKILL_SEED,
        note="独立产品冷启动苏格拉底拆解模板",
    )
    assert fb_seed["elapsed_ms"] < 200.0
    assert fb_seed["created_seed_id"] is not None

    seeds = svc.list_skill_seeds()
    assert len(seeds) == 1
    assert seeds[0]["seed_id"] == fb_seed["created_seed_id"]
    assert seeds[0]["status"] == SkillStatus.CAPTURED.value
    assert seeds[0]["source_run_id"] == run_id


def test_fastapi_cli_and_webui_m10_endpoints(tmp_path: pathlib.Path) -> None:
    db_file = tmp_path / "api_m10.db"
    svc = HuiQiaoService(repo_root=REPO_ROOT, db_path=db_file)
    client = TestClient(create_app(svc))

    # 1. HTTP 记忆增查改删
    created = client.post(
        "/api/memory",
        json={"content": "输出表格默认按金额降序排列", "layer": "core", "topic_key": "sort_pref"},
    )
    assert created.status_code == 200
    mem_id = created.json()["memory_id"]

    queried = client.get("/api/memory", params={"q": "金额降序"}).json()
    assert queried["count"] >= 1
    assert queried["memories"][0]["memory_id"] == mem_id

    updated = client.put(
        f"/api/memory/{mem_id}",
        json={"content": "输出表格默认按日期升序排列"},
    )
    assert updated.status_code == 200
    assert "日期升序" in updated.json()["content"]

    # 2. HTTP 运行 + 4 键反馈校验（空纠偏返回 400）
    task_res = client.post(
        "/api/tasks",
        json={"text": "今日复盘：完成M10接口联调；明天推进M11双闸门自演化", "work_mode": "ask"},
    ).json()
    rid = task_res["run_id"]

    bad_correct = client.post(f"/api/runs/{rid}/feedback", json={"kind": "correct", "note": "   "})
    assert bad_correct.status_code == 400

    ok_seed = client.post(
        f"/api/runs/{rid}/feedback",
        json={"kind": "save_skill_seed", "note": "每日结构化复盘模板"},
    )
    assert ok_seed.status_code == 200
    seeds_resp = client.get("/api/skill-seeds").json()
    assert seeds_resp["count"] == 1

    deleted = client.delete(f"/api/memory/{mem_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == MemoryStatus.FORGOTTEN.value

    # 3. Typer CLI memories & feedback 命令验收
    runner = CliRunner()
    r_add = runner.invoke(cli_app, ["memories", "--add", "CLI写入的透明记忆条目", "--db", str(db_file)])
    assert r_add.exit_code == 0
    assert "已写入核心记忆" in r_add.stdout

    r_q = runner.invoke(cli_app, ["memories", "-q", "CLI写入", "--db", str(db_file)])
    assert r_q.exit_code == 0
    assert "CLI写入的透明记忆条目" in r_q.stdout

    r_fb = runner.invoke(cli_app, ["feedback", rid, "praise", "-n", "CLI一键点赞", "--db", str(db_file)])
    assert r_fb.exit_code == 0
    assert "kind=praise" in r_fb.stdout

    # 4. WebUI 保持 100% 离线零外部 CDN，且已包含 4 键反馈与记忆同步控件
    html = (REPO_ROOT / "apps" / "webui" / "index.html").read_text(encoding="utf-8")
    external_refs = re.findall(r"""(?:src|href)\s*=\s*["']https?://""", html, flags=re.IGNORECASE)
    assert external_refs == []
    assert "sendFeedback('save_skill_seed')" in html
    assert "loadMemories()" in html
