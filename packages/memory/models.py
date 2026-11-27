"""M10 (B08) 分层本地记忆引擎与 1 秒 4 键反馈闭环数据契约."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import Field

from packages.core.contracts import BaseContract, SkillStatus, new_id, utc_now


class MemoryLayer(str, Enum):
    """三层本地透明记忆分层。"""

    CORE = "core"                # 长期核心偏好/事实（双向同步 workspace/MEMORY.md）
    EPISODIC = "episodic"        # 每日情景流水日志（追加落盘 workspace/memory/YYYY-MM-DD.md）
    ANTI_PATTERN = "anti_pattern"  # 踩坑与反模式警示（优先提示路由与 Worker 避坑）


class MemoryStatus(str, Enum):
    """双时态记忆生命周期状态。"""

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"  # 被后续纠偏或新事实替代（保留审计链，默认不召回）
    FORGOTTEN = "FORGOTTEN"    # 人类主动删除/遗忘


class FeedbackKind(str, Enum):
    """1 秒 4 键极简人类反馈类型。"""

    PRAISE = "praise"                    # 👍 赞：正向强化成功经验
    DISLIKE = "dislike"                  # 👎 踩：沉淀反模式避坑记录
    CORRECT = "correct"                  # ✏️ 纠偏：写入长期偏好并双时态覆盖旧认知
    SAVE_SKILL_SEED = "save_skill_seed"  # 🌱 存为技能种子：导出 CAPTURED 种子直供 M11


class MemoryRecord(BaseContract):
    """双时态（Transaction Time + Valid Time）透明记忆条目。"""

    memory_id: str = Field(default_factory=lambda: new_id("mem"))
    scope: str = Field(default="default")
    layer: MemoryLayer = Field(default=MemoryLayer.CORE)
    status: MemoryStatus = Field(default=MemoryStatus.ACTIVE)
    content: str = Field(..., min_length=1)
    topic_key: str | None = Field(
        default=None,
        description="可选主题键（如 report_style），同 scope+topic_key 提交新认知时自动双时态替代旧条目",
    )
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    source: str = Field(default="system", description="来源：human_edit / feedback_correct / agent / episodic")
    source_run_id: str | None = Field(default=None)
    superseded_by: str | None = Field(default=None)
    # 双时态时间轴：系统入库时间轴 (recorded_at / invalidated_at) + 现实生效时间轴 (valid_from / valid_until)
    recorded_at: datetime = Field(default_factory=utc_now)
    invalidated_at: datetime | None = Field(default=None)
    valid_from: datetime = Field(default_factory=utc_now)
    valid_until: datetime | None = Field(default=None)


class FeedbackEvent(BaseContract):
    """单次 1 秒人类反馈事件记录。"""

    feedback_id: str = Field(default_factory=lambda: new_id("fbk"))
    run_id: str = Field(..., min_length=1)
    kind: FeedbackKind
    note: str = Field(default="")
    topic_key: str | None = Field(default=None)
    scope: str = Field(default="default")
    created_memory_id: str | None = Field(default=None)
    created_seed_id: str | None = Field(default=None)
    elapsed_ms: float = Field(default=0.0, ge=0.0)
    created_at: datetime = Field(default_factory=utc_now)


class SkillSeedCandidate(BaseContract):
    """由『存为技能种子』一键捕获的待演化候选包（status=CAPTURED，直供 M11 双闸门自演化）。"""

    seed_id: str = Field(default_factory=lambda: new_id("seed"))
    source_run_id: str
    title: str
    user_goal: str
    channel: str = Field(default="UNKNOWN")
    summary: str = Field(default="")
    human_note: str = Field(default="")
    artifact_paths: list[str] = Field(default_factory=list)
    status: SkillStatus = Field(default=SkillStatus.CAPTURED)
    created_at: datetime = Field(default_factory=utc_now)
    extra: dict[str, Any] = Field(default_factory=dict)
