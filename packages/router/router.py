"""M06 B02 二维五通道柔硬结合路由器（HybridRouter · 实现 RouterProtocol）.

设计原则：
- 先查 C00 方向底线（拒绝明显伤害/窃密/操控意图）；
- 再走 L0 已验证技能快速匹配（零/极低推理开销）；
- 核心按「可验证性 x 结构化复杂度 x 赋能姿态」分流，低可验证开放人文任务 0% 误塞 CodeAct；
- 结合本机 CapabilityProfile 做 A5 知限谦卑检查：严重超纲时诚实止步并给出拆小步建议，
  但默认保持 allow_cross_channel_freedom=True，不以死板规则束缚模型创造力。
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable

from packages.core.constitution import evaluate_uplift_audit
from packages.core.contracts import (
    CapabilityCheck,
    CapabilityProfile,
    ExecutionChannel,
    InteractionMode,
    RouteDecision,
    SandboxTier,
    SkillManifest,
    SkillStatus,
    TaskEnvelope,
    Verifiability,
)

ClassifierFn = Callable[[TaskEnvelope, list[SkillManifest]], dict[str, Any] | None]

_HARMFUL_KEYWORDS = (
    "窃取密码",
    "盗取凭证",
    "绕过用户知情",
    "偷偷删除",
    "恶意攻击",
    "木马",
    "勒索",
    "诈骗话术",
    "steal credentials",
    "bypass consent",
    "exfiltrate",
)

# 高可验证（结构化计算、文件批处理、脚本自动化、代码单测）信号词
_HIGH_VERIFIABLE_HINTS = (
    "csv",
    "excel",
    "xlsx",
    "json",
    "pdf",
    "sql",
    "sqlite",
    "python",
    "脚本",
    "统计",
    "汇总",
    "提取",
    "批量",
    "重命名",
    "格式转换",
    "清洗",
    "计算",
    "单测",
    "pytest",
    "bug",
    "修复代码",
    "解析",
    "发票",
    "表格",
    "对账",
    "生成图表",
    "代码",
    "编程",
    "编码",
    "小程序",
    "网页",
    "前端",
    "html",
    "小工具",
    "本地应用",
    "计算器",
    "打卡器",
)

# 复杂跨文件/长程工程信号词（倾向 L3）
_L3_COMPLEX_HINTS = (
    "重构整个",
    "跨仓库",
    "多文件重构",
    "架构迁移",
    "完整系统",
    "全仓库排查",
    "端到端搭建",
    "多源深度研究并写代码",
)

# 固定多步流程信号词（倾向 L1）
_L1_FLOW_HINTS = (
    "每天定时",
    "每周定时",
    "流水线",
    "依次执行",
    "扫描并归档",
    "先摘要再归档",
    "固定模板",
)

# 低可验证开放人文/决策/创意/学习信号词（必须走 L2-S，绝不误塞 CodeAct）
_LOW_VERIFIABLE_HINTS = (
    "人生",
    "困惑",
    "焦虑",
    "情绪",
    "权衡",
    "战略",
    "怎么选",
    "职业规划",
    "哲学",
    "伦理",
    "价值观",
    "写一篇散文",
    "写一首诗",
    "润色演讲",
    "沟通话术",
    "怎么安慰",
    "创意灵感",
    "品牌故事",
    "商业模式思考",
    "学习计划",
    "帮我理解",
    "教我",
    "启发",
    "为什么",
    "怎么看",
)

# 触发启发增上态（UPLIFT_MENTOR）的意图信号
_UPLIFT_HINTS = (
    "教我",
    "帮我理解",
    "讲讲原理",
    "学习",
    "怎么选",
    "权衡",
    "职业规划",
    "战略",
    "困惑",
    "启发",
    "思考",
    "复盘",
    "为什么",
    "指导",
)


def _extract_tokens(text: str) -> set[str]:
    lower = text.lower()
    latin = set(re.findall(r"[a-z0-9_+-]{2,}", lower))
    cjk_chunks = re.findall(r"[\u4e00-\u9fff]{2,}", lower)
    cjk_grams: set[str] = set()
    for chunk in cjk_chunks:
        cjk_grams.add(chunk)
        for i in range(len(chunk) - 1):
            cjk_grams.add(chunk[i : i + 2])
    return latin | cjk_grams


class HybridRouter:
    """三阶柔硬结合路由器：C00 预检 -> L0 技能直通 -> 二维通道判定 + CapabilityProfile 边界自检。"""

    def __init__(
        self,
        *,
        skills: Iterable[SkillManifest] = (),
        classifier_fn: ClassifierFn | None = None,
        l0_match_threshold: float = 0.5,
    ) -> None:
        self._skills: list[SkillManifest] = list(skills)
        self._classifier_fn = classifier_fn
        self.l0_match_threshold = l0_match_threshold

    def healthcheck(self) -> bool:
        return True

    def register_skill(self, skill: SkillManifest) -> None:
        self._skills = [s for s in self._skills if s.skill_id != skill.skill_id]
        self._skills.append(skill)

    def _match_l0_skill(self, text: str) -> tuple[SkillManifest | None, float]:
        active_skills = [s for s in self._skills if s.status == SkillStatus.ACTIVE]
        if not active_skills:
            return None, 0.0

        text_lower = text.lower()
        q_tokens = _extract_tokens(text)
        best_skill: SkillManifest | None = None
        best_score = 0.0

        for skill in active_skills:
            # 精确命中 skill_id、技能名或 metadata.triggers 触发短语直接高置信度直通
            if skill.skill_id.lower() in text_lower or skill.name.lower() in text_lower:
                return skill, 0.96
            triggers = skill.metadata.get("triggers", []) if isinstance(skill.metadata, dict) else []
            if any(str(t).lower() in text_lower for t in triggers if t):
                return skill, 0.93
            s_tokens = _extract_tokens(f"{skill.name} {skill.description}")
            if not s_tokens or not q_tokens:
                continue
            overlap = len(q_tokens & s_tokens)
            denom = min(len(q_tokens), len(s_tokens))
            score = overlap / max(denom, 1)
            if score > best_score:
                best_score = score
                best_skill = skill

        if best_skill is not None and best_score >= self.l0_match_threshold:
            return best_skill, min(0.95, round(0.65 + best_score * 0.3, 3))
        return None, 0.0

    def route(
        self,
        envelope: TaskEnvelope,
        profile: CapabilityProfile | None = None,
    ) -> RouteDecision:
        text = (envelope.raw_input or (envelope.input.text if envelope.input else "")).strip()
        text_lower = text.lower()

        # 0. C00 价值底线预检
        for bad in _HARMFUL_KEYWORDS:
            if bad in text_lower:
                audit = evaluate_uplift_audit(
                    preserves_human_agency=False,
                    no_harm_or_lockin=False,
                    enables_uplift_and_accessibility=False,
                    transparent_and_reversible=False,
                    rationale=f"检测到违背 C00 众生增上底线的有害意图信号: '{bad}'",
                )
                return RouteDecision(
                    task_id=envelope.task_id,
                    verifiability=Verifiability.LOW_VERIFIABLE,
                    channel=ExecutionChannel.HONEST_DEFER,
                    interaction_mode=InteractionMode.UPLIFT_MENTOR,
                    confidence=0.98,
                    allow_cross_channel_freedom=False,
                    primary_model_role="semantic",
                    sandbox_tier=SandboxTier.NONE,
                    constitution_audit=audit,
                    rationale=audit.rationale,
                )

        # 1. L0 已验证技能直通检查
        matched_skill, skill_conf = self._match_l0_skill(text)
        if matched_skill is not None:
            return RouteDecision(
                task_id=envelope.task_id,
                verifiability=matched_skill.verifiability,
                channel=ExecutionChannel.L0_SKILL,
                interaction_mode=InteractionMode.COPILOT_EXECUTE,
                confidence=skill_conf,
                matched_skills=[f"{matched_skill.skill_id}@{matched_skill.version}"],
                primary_model_role="fast_router",
                sandbox_tier=SandboxTier.T2_OS_RESTRICTED
                if matched_skill.verifiability == Verifiability.HIGH_VERIFIABLE
                else SandboxTier.NONE,
                capability_check=self._build_capability_check(ExecutionChannel.L0_SKILL, profile),
                rationale=f"命中已验证活跃技能 {matched_skill.skill_id}，走 L0 低开销直通",
            )

        # 2. 若注入了轻量本地小模型分类器，优先采用其结构化建议（同时保留底线兜底）
        verifiability, channel, interaction, rationale = self._classify_two_dim(
            envelope, text, text_lower
        )

        # 3. 结合本机 CapabilityProfile 做 A5 知限谦卑检查
        cap_check = self._build_capability_check(channel, profile)
        if not cap_check.within_comfort_zone and channel == ExecutionChannel.L3_AGENT_GRAPH:
            channel = ExecutionChannel.HONEST_DEFER
            interaction = InteractionMode.UPLIFT_MENTOR
            rationale = (
                f"{rationale}；但本机实测能力档案暂未达到 L3 长程探索稳健线，"
                "按 C00 A5 知限谦卑原则主动诚实提示并建议拆小步人机协同推进"
            )

        sandbox = SandboxTier.NONE
        role = "semantic"
        if channel == ExecutionChannel.L2C_CODEACT:
            sandbox = SandboxTier.T2_OS_RESTRICTED
            role = "coder"
        elif channel == ExecutionChannel.L3_AGENT_GRAPH:
            sandbox = SandboxTier.T3_ISOLATED_VM
            role = "reasoner"
        elif channel == ExecutionChannel.L1_FLOW:
            sandbox = SandboxTier.T1_WASM
            role = "fast_router"

        return RouteDecision(
            task_id=envelope.task_id,
            verifiability=verifiability,
            channel=channel,
            interaction_mode=interaction,
            confidence=0.88,
            allow_cross_channel_freedom=True,
            primary_model_role=role,
            sandbox_tier=sandbox,
            capability_check=cap_check,
            rationale=rationale,
        )

    def _classify_two_dim(
        self,
        envelope: TaskEnvelope,
        text: str,
        text_lower: str,
    ) -> tuple[Verifiability, ExecutionChannel, InteractionMode, str]:
        if self._classifier_fn is not None:
            custom = self._classifier_fn(envelope, self._skills)
            if isinstance(custom, dict) and "channel" in custom and "verifiability" in custom:
                v = Verifiability(custom["verifiability"])
                ch = ExecutionChannel(custom["channel"])
                # 硬守护：绝不允许将明确低可验证人文任务误塞进 CodeAct
                if v == Verifiability.LOW_VERIFIABLE and ch == ExecutionChannel.L2C_CODEACT:
                    ch = ExecutionChannel.L2S_SEMANTIC_COCREATE
                im = InteractionMode(
                    custom.get(
                        "interaction_mode",
                        InteractionMode.UPLIFT_MENTOR.value
                        if ch == ExecutionChannel.L2S_SEMANTIC_COCREATE
                        else InteractionMode.COPILOT_EXECUTE.value,
                    )
                )
                return v, ch, im, str(custom.get("rationale", "由轻量分类器判定"))

        high_score = sum(1 for k in _HIGH_VERIFIABLE_HINTS if k in text_lower)
        low_score = sum(1 for k in _LOW_VERIFIABLE_HINTS if k in text_lower)
        l3_score = sum(1 for k in _L3_COMPLEX_HINTS if k in text_lower)
        l1_score = sum(1 for k in _L1_FLOW_HINTS if k in text_lower)
        uplift_hit = any(k in text_lower for k in _UPLIFT_HINTS)

        has_attachments = bool(envelope.input and envelope.input.attachments)
        if has_attachments and high_score > 0:
            high_score += 1

        # 优先识别低可验证开放人文/战略/情感/教学任务 -> 强制走 L2-S，0% 误塞 CodeAct
        if low_score > 0 and low_score >= high_score and l3_score == 0:
            mode = InteractionMode.UPLIFT_MENTOR if (uplift_hit or low_score >= 1) else InteractionMode.COPILOT_EXECUTE
            return (
                Verifiability.LOW_VERIFIABLE,
                ExecutionChannel.L2S_SEMANTIC_COCREATE,
                mode,
                "判定为低可验证开放语义/决策/人文任务，走 L2-S 语义共生通道并保留人类主导权",
            )

        if l3_score > 0:
            return (
                Verifiability.HIGH_VERIFIABLE if high_score >= low_score else Verifiability.MIXED,
                ExecutionChannel.L3_AGENT_GRAPH,
                InteractionMode.UPLIFT_MENTOR if uplift_hit else InteractionMode.COPILOT_EXECUTE,
                "判定为跨文件/长程复杂工程任务，建议走 L3 状态图分步协作",
            )

        if l1_score > 0 and high_score >= 1:
            return (
                Verifiability.HIGH_VERIFIABLE,
                ExecutionChannel.L1_FLOW,
                InteractionMode.COPILOT_EXECUTE,
                "判定为多步常规结构化流程，走 L1 确定性工作流",
            )

        if high_score >= 1:
            return (
                Verifiability.HIGH_VERIFIABLE,
                ExecutionChannel.L2C_CODEACT,
                InteractionMode.UPLIFT_MENTOR if uplift_hit else InteractionMode.COPILOT_EXECUTE,
                "判定为高可验证数据处理/脚本任务，建议走 L2-C CodeAct 沙箱执行",
            )

        # 默认保守落回 L2-S 语义共生（宁可先透明对话澄清，绝不瞎写代码）
        return (
            Verifiability.LOW_VERIFIABLE,
            ExecutionChannel.L2S_SEMANTIC_COCREATE,
            InteractionMode.UPLIFT_MENTOR,
            "任务开放度较高或意图尚需澄清，默认走 L2-S 语义共生通道透明共创",
        )

    @staticmethod
    def _build_capability_check(
        channel: ExecutionChannel,
        profile: CapabilityProfile | None,
    ) -> CapabilityCheck:
        if profile is None:
            return CapabilityCheck(
                required_tier=channel.value,
                host_profile_tier="UNPROFILED",
                within_comfort_zone=True,
                effective_ctx_budget=8192,
                advisory_note="尚未运行本机能力摸底，暂按保守有效上下文 8K 运行",
            )

        enabled = set(profile.enabled_channels or profile.recommended_channels)
        ctx_values = list(profile.safe_effective_ctx.values()) if profile.safe_effective_ctx else []
        if not ctx_values:
            for m in profile.models.values():
                if hasattr(m, "safe_effective_ctx"):
                    ctx_values.append(int(m.safe_effective_ctx))
        ctx_budget = max(ctx_values) if ctx_values else 8192

        in_zone = True
        note = ""
        if channel == ExecutionChannel.L3_AGENT_GRAPH and ExecutionChannel.L3_AGENT_GRAPH not in enabled:
            in_zone = False
            note = "当前本机模型未进入 L3 稳健区，建议拆分为 ≤3 步的人机协同子任务推进"
        elif channel == ExecutionChannel.L2C_CODEACT and ExecutionChannel.L2C_CODEACT not in enabled:
            in_zone = False
            note = "当前本机模型实测 CodeAct 偏弱，建议转为受限脚本模板 + 人工预览确认（不硬封杀）"

        return CapabilityCheck(
            required_tier=channel.value,
            host_profile_tier=profile.hardware_tier,
            within_comfort_zone=in_zone,
            effective_ctx_budget=ctx_budget,
            advisory_note=note,
        )
