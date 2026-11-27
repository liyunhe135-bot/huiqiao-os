"""M11 (B09) 双闸门防坍塌自演化引擎与普惠便携技能包数据契约."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from packages.core.contracts import (
    BaseContract,
    SandboxTier,
    SkillStatus,
    UpliftAuditResult,
    new_id,
    utc_now,
)


class ObjectiveGateReport(BaseContract):
    """闸门一：独立沙箱客观单测与静态安全验收报告（零 LLM 自评防 Model Collapse）。"""

    passed: bool
    sandbox_tier_used: SandboxTier = Field(default=SandboxTier.T2_OS_RESTRICTED)
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    elapsed_ms: float = Field(default=0.0, ge=0.0)
    schema_valid: bool = False
    static_security_ok: bool = False
    issues: list[str] = Field(default_factory=list)


class EvolutionDraft(BaseContract):
    """自演化技能草稿全生命周期状态记录（CAPTURED -> DRAFT -> VERIFYING -> PENDING_REVIEW -> ACTIVE）。"""

    draft_id: str = Field(default_factory=lambda: new_id("draft"))
    source_seed_id: str | None = None
    skill_id: str = Field(..., min_length=3)
    name: str = Field(..., min_length=1)
    version: str = Field(default="0.1.0")
    description: str = Field(..., min_length=1)
    status: SkillStatus = Field(default=SkillStatus.DRAFT)
    manifest_yaml: str = Field(..., min_length=1)
    skill_markdown: str = Field(..., min_length=1)
    handler_code: str = Field(..., min_length=1)
    smoke_test_code: str = Field(..., min_length=1)
    portable_lite_ready: bool = True
    gate1_report: ObjectiveGateReport | None = None
    gate2_audit: UpliftAuditResult | None = None
    review_note: str = ""
    reviewer: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class PortableSkillCard(BaseContract):
    """高配反哺低配普惠技能包（.hqskill.zip）完整性与低配兼容性名片。"""

    format_version: str = Field(default="hqskill/v1")
    skill_id: str
    name: str
    version: str
    description: str
    portable_lite_ready: bool = True
    compatibility: dict[str, Any] = Field(
        default_factory=lambda: {
            "min_ram_gb": 4,
            "min_vram_gb": 0,
            "cpu_only_supported": True,
            "offline_only": True,
            "requires_cloud_api": False,
            "recommended_lite_model": "qwen3-4b-q4_k_m (optional)",
        }
    )
    constitution_attestation: UpliftAuditResult
    file_sha256: dict[str, str] = Field(default_factory=dict)
    exported_at: datetime = Field(default_factory=utc_now)
