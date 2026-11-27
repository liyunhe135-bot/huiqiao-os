"""汇桥 OS 全局冻结 Pydantic v2 数据契约（M00 Core · 统一兼容版）.

设计哲学：刚性守契约边界，柔性留创造空间。
- 顶层禁止未知字段（extra="forbid"），确保契约严谨；
- 均预留 `metadata: dict[str, Any]` 与模型自由注释字段，绝不把未来模型的新解法写死；
- 无损兼容结构化与扁平两种构造方式（服务 M00–M03 全模块平滑衔接）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONTRACT_VERSION = "huiqiao/v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class BrickLayer(str, Enum):
    """10 大乐高积木槽位层级 + 第零宪章层。"""

    CONSTITUTION = "constitution"
    INGRESS = "ingress"
    ROUTER = "router"
    ORCHESTRATOR = "orchestrator"
    LLM_GATEWAY = "llm_gateway"
    WORKER = "worker"
    MCP = "mcp"
    SANDBOX = "sandbox"
    MEMORY = "memory"
    SKILL_ENGINE = "skill_engine"
    GOVERNANCE = "governance"


_ROLE_TO_LAYER: dict[str, BrickLayer] = {
    "C00": BrickLayer.CONSTITUTION,
    "B01": BrickLayer.INGRESS,
    "B02": BrickLayer.ROUTER,
    "B03": BrickLayer.ORCHESTRATOR,
    "B04": BrickLayer.LLM_GATEWAY,
    "B05": BrickLayer.WORKER,
    "B06": BrickLayer.MCP,
    "B07": BrickLayer.SANDBOX,
    "B08": BrickLayer.MEMORY,
    "B09": BrickLayer.SKILL_ENGINE,
    "B10": BrickLayer.GOVERNANCE,
}


class WorkMode(str, Enum):
    """面向普通用户的三档顶层心智模式（师从 WorkBuddy）。"""

    ASK = "ask"          # 纯只读问答/增上启发，内核物理禁写任何本地文件
    PLAN = "plan"        # 先输出完整拆解与变更影响清单，确认后再执行
    EXECUTE = "execute"  # 授权工作区内自主执行，高危动作仍过证据闸门


class Verifiability(str, Enum):
    """任务客观可验证性判定。"""

    HIGH_VERIFIABLE = "HIGH_VERIFIABLE"
    LOW_VERIFIABLE = "LOW_VERIFIABLE"
    MIXED = "MIXED"


class ExecutionChannel(str, Enum):
    """二维五通道启发式起步建议（Soft Default，允许安全红线内跨界组合）。"""

    L0_SKILL = "L0_SKILL"
    L1_FLOW = "L1_FLOW"
    L2C_CODEACT = "L2C_CODEACT"
    L2S_SEMANTIC_COCREATE = "L2S_SEMANTIC_COCREATE"
    L3_AGENT_GRAPH = "L3_AGENT_GRAPH"
    HONEST_DEFER = "HONEST_DEFER"


class InteractionMode(str, Enum):
    """C00 交互双态：协作代劳 vs 启发增上（授人以渔）。"""

    COPILOT_EXECUTE = "COPILOT_EXECUTE"
    UPLIFT_MENTOR = "UPLIFT_MENTOR"


class SandboxTier(str, Enum):
    NONE = "NONE"
    T1_WASM = "T1_WASM"
    T2_OS_RESTRICTED = "T2_OS_RESTRICTED"
    T3_ISOLATED_VM = "T3_ISOLATED_VM"


class SkillStatus(str, Enum):
    CAPTURED = "CAPTURED"
    DRAFT = "DRAFT"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    PENDING_REVIEW = "PENDING_REVIEW"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    REJECTED_BY_CONSTITUTION = "REJECTED_BY_CONSTITUTION"
    ARCHIVED = "ARCHIVED"


class PolicyDecision(str, Enum):
    ALLOW = "ALLOW"
    ASK_HUMAN = "ASK_HUMAN"
    DENY = "DENY"


class BaseContract(BaseModel):
    """所有契约基类：顶层严禁未知字段，内部通过 metadata 保留柔性扩展位。"""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    contract_version: str = Field(default=CONTRACT_VERSION)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskInput(BaseModel):
    text: str = Field(..., min_length=1, description="用户原始自然语言输入或事件载荷")
    attachments: list[str] = Field(default_factory=list, description="本地文件或目录路径列表")
    expected_output_format: str | None = Field(default=None)


class TaskConstraints(BaseModel):
    offline_only: bool = Field(default=True, description="默认 100% 本地离线，严禁外联")
    work_mode: WorkMode = Field(default=WorkMode.ASK, description="默认安全只读起步")
    max_steps: int = Field(default=10, ge=1, le=50)
    timeout_sec: int = Field(default=300, ge=5, le=7200)
    allowed_paths: list[str] = Field(default_factory=list)


class TaskEnvelope(BaseContract):
    """B01 统一任务接入信封（兼容 TaskInput 结构化与 raw_input 扁平写法）。"""

    task_id: str = Field(default_factory=lambda: new_id("tsk"))
    source: str = Field(default="cli", description="cli | webui | cron | file_watcher | api")
    workspace_scope: str = Field(default="default")
    created_at: datetime = Field(default_factory=utc_now)
    input: TaskInput | None = Field(default=None)
    raw_input: str | None = Field(default=None)
    input_type: str = Field(default="text")
    constraints: TaskConstraints = Field(default_factory=TaskConstraints)

    @model_validator(mode="before")
    @classmethod
    def _sync_input_and_raw(cls, data: Any) -> Any:
        if isinstance(data, dict):
            has_input = data.get("input") is not None
            has_raw = data.get("raw_input") is not None
            if not has_input and has_raw:
                data = {**data, "input": {"text": data["raw_input"]}}
            elif has_input and not has_raw:
                inp = data["input"]
                txt = inp.text if isinstance(inp, TaskInput) else (inp.get("text") if isinstance(inp, dict) else None)
                if txt is not None:
                    data = {**data, "raw_input": txt}
        return data

    @model_validator(mode="after")
    def _require_input(self) -> TaskEnvelope:
        if self.input is None and not self.raw_input:
            raise ValueError("TaskEnvelope 必须提供 input 或 raw_input")
        return self


class CapabilityCheck(BaseModel):
    required_tier: str = Field(default="ANY")
    host_profile_tier: str = Field(default="UNPROFILED")
    within_comfort_zone: bool = Field(default=True)
    effective_ctx_budget: int = Field(default=8192, ge=1024)
    advisory_note: str = Field(default="", description="软性风险提示，不僵化封杀模型创造力")


class UpliftAuditResult(BaseContract):
    """C00 增上四问宪法审查结果（用于 B02 路由校验与 B09 自演化一票否决门）。"""

    passed: bool
    preserves_human_agency: bool = True
    no_harm_or_lockin: bool = True
    enables_uplift_and_accessibility: bool = True
    transparent_and_reversible: bool = True
    rationale: str = ""
    improvement_suggestions: list[str] = Field(default_factory=list)


class RouteDecision(BaseContract):
    """B02 二维五通道启发式路由决策。"""

    task_id: str
    verifiability: Verifiability
    channel: ExecutionChannel
    interaction_mode: InteractionMode = InteractionMode.COPILOT_EXECUTE
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    allow_cross_channel_freedom: bool = Field(
        default=True,
        description="柔性原则：允许模型在安全底线内自主跨界借用其他通道工具",
    )
    matched_skills: list[str] = Field(default_factory=list)
    selected_flow: str | None = None
    primary_model_role: str = Field(default="coder")
    sandbox_tier: SandboxTier = SandboxTier.NONE
    capability_check: CapabilityCheck = Field(default_factory=CapabilityCheck)
    constitution_audit: UpliftAuditResult = Field(
        default_factory=lambda: UpliftAuditResult(passed=True, rationale="默认合规")
    )
    rationale: str = ""


class StepInput(BaseContract):
    """B03 -> B05 单步执行输入契约。"""

    run_id: str = Field(default_factory=lambda: new_id("run"))
    step_id: str = Field(default_factory=lambda: new_id("stp"))
    task_id: str
    goal: str
    work_mode: WorkMode = WorkMode.ASK
    interaction_mode: InteractionMode = InteractionMode.COPILOT_EXECUTE
    context_messages: list[dict[str, Any]] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    effective_ctx_budget: int = Field(default=8192, ge=1024)
    steering_hint: str | None = Field(default=None, description="用户中途改向指令")


class StepOutput(BaseContract):
    """B05 -> B03 单步执行输出契约（兼容 ok 与 success 双命名）。"""

    run_id: str = Field(default_factory=lambda: new_id("run"))
    task_id: str | None = None
    step_id: str
    brick_name: str | None = None
    success: bool = True
    ok: bool = True
    summary: str = ""
    artifacts: list[str] = Field(default_factory=list, description="本步产出的本地文件路径")
    model_notes: str = Field(default="", description="模型自由反思、原理说明或下一步建议")
    tokens_used: int = Field(default=0, ge=0)
    elapsed_ms: int = Field(default=0, ge=0)
    error: str | None = None
    needs_human_approval: bool = False

    @model_validator(mode="before")
    @classmethod
    def _sync_ok_success(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if "ok" in d and "success" not in d:
                d["success"] = d["ok"]
            elif "success" in d and "ok" not in d:
                d["ok"] = d["success"]
            return d
        return data


class ModelBenchmarkMetric(BaseModel):
    model_config = ConfigDict(extra="allow")

    artifact: str = ""
    quantization: str = "unknown"
    bfcl_mini_pass: float = Field(default=0.0, ge=0.0, le=1.0)
    abstain_accuracy: float = Field(default=0.0, ge=0.0, le=1.0)
    codeact_sandbox_pass: float = Field(default=0.0, ge=0.0, le=1.0)
    max_stable_turns: int = Field(default=3, ge=1)
    safe_effective_ctx: int = Field(default=8192, ge=1024)
    tps: float = Field(default=0.0, ge=0.0)
    peak_vram_mb: int = Field(default=0, ge=0)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class CapabilityProfile(BaseContract):
    """B10 装机离线科学能力摸底档案（兼容 M00 结构化与 M02 Profiler 产出）。"""

    profiled_at: datetime = Field(default_factory=utc_now)
    host_os: str = ""
    ram_gb: float = Field(default=0.0, ge=0.0)
    vram_gb: float = Field(default=0.0, ge=0.0)
    hardware_tier: str = Field(default="Standard")
    host_hardware: dict[str, Any] = Field(default_factory=dict)
    models: dict[str, ModelBenchmarkMetric | dict[str, Any]] = Field(default_factory=dict)
    recommended_channels: list[ExecutionChannel] = Field(
        default_factory=lambda: [
            ExecutionChannel.L0_SKILL,
            ExecutionChannel.L1_FLOW,
            ExecutionChannel.L2S_SEMANTIC_COCREATE,
        ]
    )
    enabled_channels: list[ExecutionChannel] = Field(default_factory=list)
    safe_effective_ctx: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _sync_hardware_and_channels(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            hw = d.get("host_hardware") or {}
            if not d.get("host_os") and isinstance(hw, dict) and hw.get("os"):
                d["host_os"] = str(hw["os"])
            if not hw and d.get("host_os"):
                d["host_hardware"] = {"os": d["host_os"]}
            if d.get("enabled_channels") and not d.get("recommended_channels"):
                d["recommended_channels"] = d["enabled_channels"]
            elif d.get("recommended_channels") and not d.get("enabled_channels"):
                d["enabled_channels"] = d["recommended_channels"]
            return d
        return data


class BrickManifest(BaseContract):
    """任意乐高积木的标准自描述清单（兼容 slots 模式与 name/impl 扁平模式）。"""

    brick_id: str = Field(..., min_length=2)
    name: str = Field(default="")
    role: str = Field(default="")
    layer: BrickLayer = BrickLayer.INGRESS
    version: str = Field(default="0.1.0", min_length=1)
    entrypoint: str = Field(..., description="格式: module.path:ClassName")
    impl: str = Field(default="")
    capabilities: list[str] = Field(default_factory=list)
    healthcheck: str = Field(default="healthcheck")
    fallback_brick: str | None = None
    fallback_impl: str | None = None
    enabled: bool = True
    note: str = ""
    config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if "impl" in d and "entrypoint" not in d:
                d["entrypoint"] = d["impl"]
            elif "entrypoint" in d and not d.get("impl"):
                d["impl"] = d["entrypoint"]
            if "name" in d and "brick_id" not in d:
                d["brick_id"] = d["name"]
            elif "brick_id" in d and not d.get("name"):
                d["name"] = d["brick_id"]
            if "layer" not in d and d.get("role") in _ROLE_TO_LAYER:
                d["layer"] = _ROLE_TO_LAYER[d["role"]]
            return d
        return data

    @field_validator("entrypoint")
    @classmethod
    def _validate_entrypoint(cls, value: str) -> str:
        if ":" not in value or value.startswith(":") or value.endswith(":"):
            raise ValueError("entrypoint 必须符合 'module.path:ClassName' 格式")
        return value


class SkillManifest(BaseContract):
    """B09 标准技能包 manifest.yaml 契约。"""

    skill_id: str = Field(..., min_length=2)
    name: str
    version: str = "0.1.0"
    description: str = Field(..., max_length=280, description="渐进式加载极简摘要，防上下文膨胀")
    status: SkillStatus = SkillStatus.DRAFT
    verifiability: Verifiability = Verifiability.HIGH_VERIFIABLE
    required_permissions: list[str] = Field(default_factory=list)
    portable_lite_ready: bool = Field(default=False, description="是否已产出低配电脑普惠版")
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)


class EventRecord(BaseContract):
    """全链路仅追加事件账本记录（支持回放、观测与离线轨迹评测）。"""

    event_id: str = Field(default_factory=lambda: new_id("evt"))
    run_id: str
    task_id: str
    timestamp: datetime = Field(default_factory=utc_now)
    brick_layer: BrickLayer
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
