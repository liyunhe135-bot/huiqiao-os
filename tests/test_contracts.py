"""M00 契约单测：适配正式契约（ExecutionChannel / SkillStatus / CapabilityCheck）。

注意：本文件随 2026-11-27 正式契约升级而更新；C00 双闸门由契约自身校验器保证。
"""

import json

import pytest
from pydantic import ValidationError

from packages.core.contracts import (
    ExecutionChannel,
    InteractionMode,
    RouteDecision,
    SkillManifest,
    SkillStatus,
    StepOutput,
    TaskEnvelope,
    Verifiability,
)


@pytest.mark.contract
def test_task_envelope_roundtrip() -> None:
    env = TaskEnvelope(
        task_id="tsk_001",
        raw_input="整理这份 PDF",
        input_type="file",
    )
    data = json.loads(env.model_dump_json())
    restored = TaskEnvelope.model_validate(data)
    assert restored == env
    assert restored.task_id == "tsk_001"


@pytest.mark.contract
def test_task_envelope_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        TaskEnvelope(
            task_id="tsk_002",
            raw_input="x",
            input_type="text",
            unexpected_field="不应允许",
        )


@pytest.mark.contract
def test_route_decision_valid() -> None:
    rd = RouteDecision(
        task_id="tsk_001",
        verifiability=Verifiability.HIGH_VERIFIABLE,
        channel=ExecutionChannel.L2C_CODEACT,
        confidence=0.92,
        rationale="规则命中：数据清洗任务",
        interaction_mode=InteractionMode.COPILOT_EXECUTE,
    )
    assert rd.channel == ExecutionChannel.L2C_CODEACT
    assert "规则命中" in rd.rationale


@pytest.mark.contract
def test_route_decision_honest_defer_allowed() -> None:
    """正式契约允许 HONEST_DEFER（知限谦卑通道）。"""
    rd = RouteDecision(
        task_id="tsk_003",
        verifiability=Verifiability.LOW_VERIFIABLE,
        channel=ExecutionChannel.HONEST_DEFER,
        confidence=0.5,
        rationale="超纲，诚实降级",
    )
    assert rd.channel == ExecutionChannel.HONEST_DEFER


@pytest.mark.contract
def test_skill_manifest_all_statuses() -> None:
    """正式契约用 SkillStatus 枚举，不用自由字符串。"""
    skill = SkillManifest(
        skill_id="genesis-doc-digest",
        name="文档摘要",
        description="本地 PDF/Word/MD 批量解析与精华总结",
        status=SkillStatus.DRAFT,
    )
    assert skill.status == SkillStatus.DRAFT
    assert skill.success_count == 0


@pytest.mark.contract
def test_skill_rejected_by_constitution() -> None:
    skill = SkillManifest(
        skill_id="bad-skill",
        name="违宪技能",
        description="绕过用户知情 auto bulk delete without consent",
        status=SkillStatus.REJECTED_BY_CONSTITUTION,
    )
    assert skill.status == SkillStatus.REJECTED_BY_CONSTITUTION


@pytest.mark.contract
def test_step_output_error_case() -> None:
    out = StepOutput(
        task_id="tsk_004",
        step_id="s1",
        brick_name="gate",
        ok=False,
        error="字数闸门未过",
        elapsed_ms=12,
    )
    assert out.ok is False
    assert out.error == "字数闸门未过"
