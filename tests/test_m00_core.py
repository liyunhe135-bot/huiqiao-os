"""M00 验收单元测试：C00 宪章、Pydantic 核心契约、协议接口与 BrickRegistry 热插拔."""

from __future__ import annotations

import pathlib
from typing import Any

import pytest
from pydantic import ValidationError

from packages.core import (
    CONTRACT_VERSION,
    BrickLayer,
    BrickManifest,
    BrickRegistry,
    BrickRegistryError,
    CapabilityProfile,
    ConstitutionError,
    ErrorCode,
    EventRecord,
    ExecutionChannel,
    InteractionMode,
    ModelBenchmarkMetric,
    RouteDecision,
    SandboxTier,
    SkillManifest,
    SkillStatus,
    StepInput,
    StepOutput,
    TaskEnvelope,
    TaskInput,
    Verifiability,
    WorkMode,
    evaluate_uplift_audit,
    load_constitution,
)

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


# --- 模拟可热插拔的 LLM Gateway 乐高积木（MockA <-> MockB 零改业务代码） ---
class MockGatewayA:
    def __init__(self, tag: str = "A") -> None:
        self.tag = tag

    def healthcheck(self) -> bool:
        return True

    def complete(
        self,
        *,
        role: str,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any] | None = None,
        thinking_mode: str = "off",
        affinity_key: str | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        return {"provider": f"mock-{self.tag}", "role": role, "content": "ok-A"}


class MockGatewayB(MockGatewayA):
    def __init__(self, tag: str = "B") -> None:
        super().__init__(tag=tag)

    def complete(
        self,
        *,
        role: str,
        messages: list[dict[str, Any]],
        json_schema: dict[str, Any] | None = None,
        thinking_mode: str = "off",
        affinity_key: str | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        return {"provider": f"mock-{self.tag}", "role": role, "content": "ok-B"}


class UnhealthyGateway(MockGatewayA):
    def healthcheck(self) -> bool:
        return False


class BrokenProtocolBrick:
    """只实现了 healthcheck 但未实现 complete()，应被协议校验拦截。"""

    def healthcheck(self) -> bool:
        return True


def _business_call_llm(registry: BrickRegistry) -> str:
    """模拟上层业务代码：只依赖契约协议，完全不知道底层是 A 还是 B。"""
    gw = registry.resolve(BrickLayer.LLM_GATEWAY)
    resp = gw.complete(role="fast_router", messages=[{"role": "user", "content": "hi"}])
    return resp["provider"]


# === 1. C00 宪章加载与增上四问测试 ===
def test_load_default_constitution_and_compact_digest() -> None:
    loaded = load_constitution()
    assert loaded.path == PROJECT_ROOT / "workspace" / "CONSTITUTION.md"
    assert loaded.axiom_markers_present == ("A1", "A2", "A3", "A4", "A5")
    digest = loaded.as_system_prefix()
    assert "助众生和谐增上" in digest
    assert "人矿" in digest
    assert len(digest) < 500  # 保证压缩重注极简，不造成 Token 膨胀


def test_constitution_missing_raises(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ConstitutionError) as exc_info:
        load_constitution(tmp_path / "NON_EXISTENT.md")
    assert exc_info.value.code == ErrorCode.CONSTITUTION_MISSING


def test_constitution_incomplete_axioms_raises(tmp_path: pathlib.Path) -> None:
    bad_file = tmp_path / "CONSTITUTION.md"
    bad_file.write_text("# 缺公理测试\n仅包含 A1 A2", encoding="utf-8")
    with pytest.raises(ConstitutionError) as exc_info:
        load_constitution(bad_file)
    assert exc_info.value.code == ErrorCode.CONSTITUTION_REJECTED


def test_uplift_audit_veto_mechanics() -> None:
    ok = evaluate_uplift_audit(
        preserves_human_agency=True,
        no_harm_or_lockin=True,
        enables_uplift_and_accessibility=True,
        transparent_and_reversible=True,
    )
    assert ok.passed is True

    vetoed = evaluate_uplift_audit(
        preserves_human_agency=False,
        no_harm_or_lockin=True,
        enables_uplift_and_accessibility=True,
        transparent_and_reversible=True,
        rationale="试图隐藏执行步骤以提速",
    )
    assert vetoed.passed is False
    assert "A1" in vetoed.rationale


# === 2. 核心 Pydantic 契约强校验 + 柔性扩展测试 ===
def test_contracts_roundtrip_and_flexible_metadata() -> None:
    env = TaskEnvelope(
        input=TaskInput(text="整理本地报销目录"),
        metadata={"creative_hint": "model_can_mix_tools"},
    )
    assert env.constraints.offline_only is True
    assert env.constraints.work_mode == WorkMode.ASK
    assert env.metadata["creative_hint"] == "model_can_mix_tools"
    assert TaskEnvelope.model_validate_json(env.model_dump_json()).task_id == env.task_id

    decision = RouteDecision(
        task_id=env.task_id,
        verifiability=Verifiability.LOW_VERIFIABLE,
        channel=ExecutionChannel.L2S_SEMANTIC_COCREATE,
        interaction_mode=InteractionMode.UPLIFT_MENTOR,
        sandbox_tier=SandboxTier.NONE,
    )
    assert decision.allow_cross_channel_freedom is True

    step_in = StepInput(run_id="run_1", task_id=env.task_id, goal="启发式拆解")
    step_out = StepOutput(
        run_id="run_1",
        step_id=step_in.step_id,
        success=True,
        summary="完成拆解",
        model_notes="已提供原理说明，方便用户自主微调",
    )
    assert step_out.model_notes != ""

    profile = CapabilityProfile(
        host_os="Windows 10",
        ram_gb=64.0,
        vram_gb=12.0,
        models={
            "coder": ModelBenchmarkMetric(
                artifact="qwen3-14b-q6_k.gguf",
                bfcl_mini_pass=0.92,
                safe_effective_ctx=16384,
            )
        },
    )
    assert profile.models["coder"].safe_effective_ctx == 16384

    skill = SkillManifest(
        skill_id="genesis-doc-digest",
        name="本地文档精华总结",
        description="离线解析本地 PDF/Word/Markdown 并输出结构化摘要",
        status=SkillStatus.ACTIVE,
        portable_lite_ready=True,
    )
    assert skill.contract_version == CONTRACT_VERSION

    evt = EventRecord(
        run_id="run_1",
        task_id=env.task_id,
        brick_layer=BrickLayer.ROUTER,
        event_type="route_decided",
        payload={"channel": decision.channel.value},
    )
    assert evt.event_id.startswith("evt_")


def test_contract_rejects_invalid_entrypoint_and_empty_input() -> None:
    with pytest.raises(ValidationError):
        TaskInput(text="")

    with pytest.raises(ValidationError):
        BrickManifest(
            brick_id="bad-entry",
            layer=BrickLayer.LLM_GATEWAY,
            version="0.1.0",
            entrypoint="missing_colon_entrypoint",
        )


# === 3. BrickRegistry 配置加载、热插拔、自动降级与体检报告测试 ===
def test_registry_loads_project_bricks_yaml_and_reports_health() -> None:
    reg = BrickRegistry.from_yaml(PROJECT_ROOT / "config" / "bricks.yaml")
    report = reg.health_report()
    assert "llm_gateway" in report
    assert "sandbox" in report
    assert "memory" in report
    assert report["llm_gateway"]["status"] == "standby"


def test_registry_hot_swap_mock_a_to_b_without_touching_business_code(
    tmp_path: pathlib.Path,
) -> None:
    cfg = tmp_path / "bricks.yaml"
    cfg.write_text(
        """
schema_version: "huiqiao/v1"
slots:
  llm_gateway:
    active: "gw-a"
    bricks:
      gw-a:
        brick_id: "b04-mock-a"
        layer: "llm_gateway"
        version: "1.0.0"
        contract_version: "huiqiao/v1"
        entrypoint: "tests.test_m00_core:MockGatewayA"
        config: { tag: "Alpha" }
      gw-b:
        brick_id: "b04-mock-b"
        layer: "llm_gateway"
        version: "1.0.0"
        contract_version: "huiqiao/v1"
        entrypoint: "tests.test_m00_core:MockGatewayB"
        config: { tag: "Beta" }
""",
        encoding="utf-8",
    )
    reg = BrickRegistry.from_yaml(cfg)
    assert _business_call_llm(reg) == "mock-Alpha"

    # 仅做热替换，完全不改 _business_call_llm 业务函数
    reg.hot_swap(BrickLayer.LLM_GATEWAY, "gw-b")
    assert _business_call_llm(reg) == "mock-Beta"
    assert reg.health_report()["llm_gateway"]["status"] == "healthy"


def test_registry_automatic_fallback_on_unhealthy_brick() -> None:
    reg = BrickRegistry()
    reg.register_manifest(
        "primary-bad",
        BrickManifest(
            brick_id="b04-bad",
            layer=BrickLayer.LLM_GATEWAY,
            version="1.0.0",
            entrypoint="tests.test_m00_core:UnhealthyGateway",
            fallback_brick="backup-good",
        ),
        set_active=True,
    )
    reg.register_manifest(
        "backup-good",
        BrickManifest(
            brick_id="b04-backup",
            layer=BrickLayer.LLM_GATEWAY,
            version="1.0.0",
            entrypoint="tests.test_m00_core:MockGatewayB",
            config={"tag": "Fallback"},
        ),
    )
    assert _business_call_llm(reg) == "mock-Fallback"
    report = reg.health_report()
    assert report["llm_gateway"]["used_fallback"] is True
    assert report["llm_gateway"]["status"] == "fallback_healthy"


def test_registry_rejects_protocol_and_version_mismatch() -> None:
    reg = BrickRegistry()
    with pytest.raises(BrickRegistryError) as ver_err:
        reg.register_manifest(
            "wrong-ver",
            BrickManifest(
                brick_id="b04-old",
                layer=BrickLayer.LLM_GATEWAY,
                version="0.1.0",
                contract_version="huiqiao/v0",
                entrypoint="tests.test_m00_core:MockGatewayA",
            ),
        )
    assert ver_err.value.code == ErrorCode.BRICK_CONTRACT_MISMATCH

    reg.register_manifest(
        "broken-proto",
        BrickManifest(
            brick_id="b04-broken",
            layer=BrickLayer.LLM_GATEWAY,
            version="1.0.0",
            entrypoint="tests.test_m00_core:BrokenProtocolBrick",
        ),
        set_active=True,
    )
    with pytest.raises(BrickRegistryError) as proto_err:
        reg.resolve(BrickLayer.LLM_GATEWAY)
    assert proto_err.value.code == ErrorCode.CONTRACT_VIOLATION
