"""INT-4 汇桥 OS v1.0.0 正式发版终极验收测试套件：五维评测 + 版本一致性 + 离线便携打包防泄密校验."""

from __future__ import annotations

import hashlib
import json
import pathlib
import tomllib
import zipfile

from fastapi.testclient import TestClient

from evals.run_int4_eval import render_markdown_report, run_all_five_dimensions
from packages.gateway import HuiQiaoService, create_app
from scripts.build_portable_bundle import build_portable_bundle

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_v1_0_0_version_alignment_across_system(tmp_path: pathlib.Path) -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == "1.0.0"

    svc = HuiQiaoService(repo_root=REPO_ROOT, db_path=tmp_path / "v1_state.db")
    health = svc.healthcheck()
    assert health["ok"] is True
    assert health["version"] == "1.0.0"

    client = TestClient(create_app(svc))
    openapi = client.get("/api/openapi.json").json()
    assert openapi["info"]["version"] == "1.0.0"

    webui_html = (REPO_ROOT / "apps" / "webui" / "index.html").read_text(encoding="utf-8")
    assert "v1.0.0" in webui_html


def test_int4_all_five_dimensions_pass_and_report_renders() -> None:
    summary = run_all_five_dimensions()
    assert summary["release_version"] == "1.0.0"
    assert summary["all_passed"] is True, summary
    assert summary["passed_dimensions"] == "5/5"

    by_name = {d["dimension"]: d for d in summary["dimensions"]}
    assert by_name["D1_OFFLINE_FULLSTACK_E2E"]["pass_rate"] == 1.0
    assert by_name["D2_ROUTING_AND_WAL_TRAJECTORY"]["routing_accuracy"] >= 0.90
    assert by_name["D2_ROUTING_AND_WAL_TRAJECTORY"]["false_codeact_on_humanistic"] == 0
    assert by_name["D3_SECURITY_REDTEAM_CONTAINMENT"]["containment_rate"] == 1.0
    assert by_name["D4_VRAM_AFFINITY_AND_CONTEXT_RESILIENCE"]["switch_reduction_ratio"] >= 0.50
    assert by_name["D4_VRAM_AFFINITY_AND_CONTEXT_RESILIENCE"]["kv_prefix_cache_locked"] is True
    assert by_name["D4_VRAM_AFFINITY_AND_CONTEXT_RESILIENCE"]["c00_constitution_intact"] is True
    assert by_name["D5_C00_UPLIFT_AND_LITE_ACCESSIBILITY"]["portable_genesis_skills_verified"] == "5/5"

    md = render_markdown_report(summary)
    assert "PASS（准予正式发布 v1.0.0）" in md
    assert "C00" in md


def test_portable_release_bundle_builder_integrity_and_zero_leak(tmp_path: pathlib.Path) -> None:
    bundle_zip = tmp_path / "huiqiao-os-v1.0.0-portable.zip"
    info = build_portable_bundle(bundle_zip, include_portable_skills=True)
    assert bundle_zip.exists()
    assert info["version"] == "1.0.0"
    assert len(info["portable_skill_packs"]) == 5

    with zipfile.ZipFile(bundle_zip, "r") as zf:
        names = set(zf.namelist())
        assert "huiqiao-os/RELEASE_MANIFEST.json" in names
        assert "huiqiao-os/USER_GUIDE.md" in names
        assert "huiqiao-os/README.md" in names
        assert "huiqiao-os/workspace/CONSTITUTION.md" in names
        assert "huiqiao-os/scripts/start_huiqiao.ps1" in names
        assert "huiqiao-os/scripts/start_huiqiao.sh" in names

        # 严禁将任何个人记忆、SQLite 数据库或字节码打入便携发行包
        assert not any(n.endswith((".db", ".pyc", "MEMORY.md")) for n in names)

        manifest = json.loads(zf.read("huiqiao-os/RELEASE_MANIFEST.json").decode("utf-8"))
        assert manifest["version"] == "1.0.0"
        assert manifest["offline_only_default"] is True

        # 抽检压缩包内文件 SHA-256 与清单完全一致
        for rel_check in ("README.md", "USER_GUIDE.md", "workspace/CONSTITUTION.md"):
            actual = hashlib.sha256(zf.read(f"huiqiao-os/{rel_check}")).hexdigest()
            assert actual == manifest["sha256"][rel_check]


def test_startup_scripts_and_user_guide_completeness() -> None:
    guide = (REPO_ROOT / "USER_GUIDE.md").read_text(encoding="utf-8")
    assert "127.0.0.1:8765" in guide
    assert "Ask" in guide and "Plan" in guide and "Execute" in guide
    assert ".hqskill.zip" in guide

    ps1 = (REPO_ROOT / "scripts" / "start_huiqiao.ps1").read_text(encoding="utf-8")
    sh = (REPO_ROOT / "scripts" / "start_huiqiao.sh").read_text(encoding="utf-8")
    assert "127.0.0.1" in ps1
    assert "127.0.0.1" in sh
