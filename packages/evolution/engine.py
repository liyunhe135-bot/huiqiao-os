"""M11 (B09) 双闸门防坍塌自演化总控引擎（SelfEvolutionEngine）.

完整防坍塌闭环：
  1. 承接 M10 1 秒反馈捕获的 SkillSeedCandidate (CAPTURED) -> 合成可读可测候选技能草稿 (DRAFT)；
  2. verify_draft() 顺序运行 Gate 1（M08 独立离线沙箱单测）+ Gate 2（C00 增上四问一票否决）；
     - 任一闸门不通过绝不可升入活跃库（Gate 2 不通过永久打标 REJECTED_BY_CONSTITUTION，Gate 1 不通过打标 DEGRADED）；
     - 双闸门全绿进入 PENDING_REVIEW（绝不背着用户静默激活！）；
  3. activate_draft(approved=True) 经人类确认后才写入 workspace/skills/<skill_id>/、热刷新 SkillRegistry 并留存一键回滚快照；
  4. rollback_skill(skill_id) 支持随时一键回滚（C00 A1 透明可逆）；
  5. export_skill() / import_skill() 实现高配沉淀反哺低配 8GB/CPU 设备的普惠共享。
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
from typing import TYPE_CHECKING, Any, Callable

import yaml

from packages.core.contracts import SkillStatus, Verifiability, utc_now
from packages.evolution.gates import (
    ExtraAuditFn,
    run_constitution_uplift_gate,
    run_objective_sandbox_gate,
)
from packages.evolution.models import EvolutionDraft, PortableSkillCard
from packages.evolution.portable import export_portable_skill, import_portable_skill
from packages.memory.models import SkillSeedCandidate
from packages.sandbox import SandboxManager

if TYPE_CHECKING:
    from packages.gateway.skills_loader import SkillRegistry

SynthesizerFn = Callable[[SkillSeedCandidate], dict[str, str]]


def _slugify_skill_id(seed: SkillSeedCandidate) -> str:
    raw = re.sub(r"[^a-z0-9]+", "-", (seed.title or "").lower()).strip("-")
    if len(raw) >= 3:
        return f"evolved-{raw[:36]}".rstrip("-")
    suffix = re.sub(r"[^a-z0-9]+", "", seed.seed_id.lower())[-8:] or "custom01"
    return f"evolved-skill-{suffix}"


def _extract_triggers(seed: SkillSeedCandidate) -> list[str]:
    candidates: list[str] = []
    for text in (seed.title, seed.human_note, seed.user_goal):
        clean = (text or "").strip()
        if clean and len(clean) >= 2:
            # 抽取短关键词或首句片段供 HybridRouter 精准命中
            frag = re.split(r"[，。；;：:\n]", clean)[0].strip()[:24]
            if frag and frag not in candidates:
                candidates.append(frag)
    return candidates or [seed.title[:20] or "自演化技能"]


def _default_synthesize_from_seed(seed: SkillSeedCandidate) -> dict[str, str]:
    """零云端依赖确定性技能合成器：将人类标记的高价值运行轨迹蒸馏为标准纯 Python 离线普惠技能。"""
    skill_id = _slugify_skill_id(seed)
    triggers = _extract_triggers(seed)
    title = seed.title.strip() or f"沉淀技能 {skill_id}"
    desc = (
        f"由运行 {seed.source_run_id} 沉淀并通过双闸门验收的离线普惠技能：{title}。"
        "遵循 C00 众生和谐增上宪章，透明可读、零重依赖、可一键回滚。"
    )

    manifest_dict = {
        "contract_version": "huiqiao/v1",
        "skill_id": skill_id,
        "name": title,
        "version": "1.0.0",
        "description": desc,
        "status": "DRAFT",
        "verifiability": Verifiability.MIXED.value,
        "required_permissions": ["READ"],
        "portable_lite_ready": True,
        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}},
        "output_schema": {"type": "object", "properties": {"summary": {"type": "string"}}},
        "metadata": {
            "category": "evolved",
            "source_seed_id": seed.seed_id,
            "source_run_id": seed.source_run_id,
            "triggers": triggers,
        },
    }
    manifest_yaml = yaml.safe_dump(manifest_dict, allow_unicode=True, sort_keys=False)

    skill_md = (
        f"# {title} (`{skill_id}`)\n\n"
        f"> **来源种子**：`{seed.seed_id}`（运行 `{seed.source_run_id}`）  \n"
        f"> **普惠适配**：纯 Python 标准库实现，支持 4GB–8GB RAM / 无 GPU 设备 100% 离线运行。\n\n"
        "## 一、适用场景与触发词\n"
        f"- 原始需求：{seed.user_goal}\n"
        f"- 建议触发词：{', '.join(triggers)}\n\n"
        "## 二、执行步骤（透明可审阅）\n"
        "1. 读取用户当前输入文本，按要点切分并保留原始语义；\n"
        "2. 结合沉淀的最佳结构模板输出清晰行动清单与复盘建议；\n"
        "3. 全程纯只读计算，不修改任何本地业务文件，随时支持一键回滚或归档。\n"
    )

    template_ref = (seed.summary or seed.user_goal or title).replace('"""', "'''")[:400]
    combined_intent = f"{title} {seed.user_goal} {seed.summary}".lower()
    if any(k in combined_intent for k in ("背诵", "复习", "俱舍", "艾宾浩斯", "记忆排期")):
        archetype = "spaced_recite"
    elif any(k in combined_intent for k in ("prd", "偏移", "验收", "核对", "缺口")):
        archetype = "prd_auditor"
    elif any(k in combined_intent for k in ("白话", "术语", "双语", "通俗", "佛学")):
        archetype = "bilingual_glossary"
    else:
        archetype = "action_matrix"

    handler_code = (
        '"""由汇桥 OS M11 自演化引擎沉淀的高纯度离线普惠技能（纯 Python 标准库，零外部依赖）."""\n\n'
        "from __future__ import annotations\n\n"
        "from datetime import date, timedelta\n"
        "import re\n"
        "from typing import Any\n\n"
        f"SKILL_TITLE = {title!r}\n"
        f"ARCHETYPE = {archetype!r}\n"
        f"REFERENCE_PATTERN = {template_ref!r}\n\n"
        "_GLOSSARY = {\n"
        "    '阿赖耶识': '本地持久核心记忆库（支持透明查看、编辑与遗忘）',\n"
        "    '般若': '清醒洞察本质的分析智慧 / 智能路由中枢',\n"
        "    '止观': '专注安住与如实观察 / 纯只读深度分析模式',\n"
        "    '四摄回向': '1秒轻量反馈闭环（赞/踩/纠偏/沉淀新技能）',\n"
        "    '随眠': '潜伏未察觉的惯性烦恼与认知盲区',\n"
        "    '有漏/无漏': '仍会引发纠结损耗的状态 / 清净通达不再内耗的状态',\n"
        "    '界品': '剖析认知要素分类与因果构成的底层基础篇',\n"
        "}\n\n\n"
        "def execute(envelope: Any, state: dict[str, Any]) -> dict[str, Any]:\n"
        "    raw = getattr(envelope, 'raw_input', None)\n"
        "    if not raw and getattr(envelope, 'input', None) is not None:\n"
        "        raw = getattr(envelope.input, 'text', '')\n"
        "    text = str(raw or '').strip()\n"
        "    segments = [s.strip() for s in re.split(r'[\\n；;。]+', text) if s.strip()]\n"
        "    items = segments if segments else [SKILL_TITLE]\n\n"
        "    if ARCHETYPE == 'spaced_recite':\n"
        "        today = date.today()\n"
        "        intervals = [0, 1, 2, 4, 7, 15, 30]\n"
        "        rows = ['| 序号 | 学习/背诵条目 | 首学日 | +1天 | +2天 | +4天 | +7天 | +15天 | +30天 |',\n"
        "                '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']\n"
        "        for idx, it in enumerate(items[:10], 1):\n"
        "            start = today + timedelta(days=idx - 1)\n"
        "            dates = [(start + timedelta(days=d)).strftime('%m-%d') for d in intervals]\n"
        "            rows.append(f'| {idx} | {it} | ' + ' | '.join(dates) + ' |')\n"
        "        body = '\\n'.join(rows) + '\\n\\n- **执行心法**：遮字默背优先于反复顺读，卡壳处用单字提示触发主动检索。'\n"
        "    elif ARCHETYPE == 'prd_auditor':\n"
        "        rows = ['| 条款编号 | 原始需求/规格锚点 | 客观验收检查项 (AC) | 防偏移红线 |',\n"
        "                '| --- | --- | --- | --- |']\n"
        "        for idx, it in enumerate(items[:12], 1):\n"
        "            rows.append(f'| REQ-{idx:02d} | {it} | 沙箱实跑可观察断言通过 | 严禁口头宣称或硬截断丢项 |')\n"
        "        body = '\\n'.join(rows)\n"
        "    elif ARCHETYPE == 'bilingual_glossary':\n"
        "        rows = ['| 原始文本/专有名词 | 大众零门槛白话解释 |',\n"
        "                '| --- | --- |']\n"
        "        matched_any = False\n"
        "        for term, plain in _GLOSSARY.items():\n"
        "            if term in text:\n"
        "                rows.append(f'| **{term}** | {plain} |')\n"
        "                matched_any = True\n"
        "        if not matched_any:\n"
        "            for it in items[:8]:\n"
        "                rows.append(f'| {it} | 核心功能直译：用一句话说明『点它能帮普通用户解决什么具体问题』 |')\n"
        "        body = '\\n'.join(rows)\n"
        "    else:\n"
        "        rows = ['| 优先级 | 关键行动项 | 可验证完成标准 (DoD) |',\n"
        "                '| --- | --- | --- |']\n"
        "        for idx, it in enumerate(items[:10], 1):\n"
        "            prio = 'P0' if idx <= 2 else 'P1'\n"
        "            rows.append(f'| `{prio}` | {it} | 产出可核查文件或明确结论 |')\n"
        "        body = '\\n'.join(rows)\n\n"
        "    summary = f'### {SKILL_TITLE}\\n\\n{body}\\n\\n> **参考规格**：{REFERENCE_PATTERN[:200]}'\n"
        "    return {\n"
        "        'summary': summary,\n"
        "        'model_notes': f'本结果由双闸门验真普惠技能 ({ARCHETYPE}) 离线确定性生成，零外网、零失真。',\n"
        "        'artifact_name': 'evolved_skill_output.md',\n"
        "        'artifact_content': summary,\n"
        "    }\n"
    )

    smoke_test_code = (
        "import types\n"
        "env = types.SimpleNamespace(\n"
        "    raw_input='第一项核对预算与阿赖耶识边界；第二项明确本周交付节奏',\n"
        "    input=types.SimpleNamespace(text='第一项核对预算与阿赖耶识边界；第二项明确本周交付节奏', attachments=[]),\n"
        "    constraints=types.SimpleNamespace(work_mode='ask', offline_only=True),\n"
        "    metadata={},\n"
        ")\n"
        "res = execute(env, {})\n"
        "assert isinstance(res, dict)\n"
        "assert '|' in res['summary'] and len(res['summary']) >= 60\n"
        "assert res.get('artifact_name') == 'evolved_skill_output.md'\n"
    )

    return {
        "skill_id": skill_id,
        "name": title,
        "version": "1.0.0",
        "description": desc,
        "manifest_yaml": manifest_yaml,
        "skill_markdown": skill_md,
        "handler_code": handler_code,
        "smoke_test_code": smoke_test_code,
    }


class SelfEvolutionEngine:
    """B09 双闸门防坍塌自演化引擎（高配沉淀 + 客观沙箱验真 + C00 一票否决 + 人工签发 + 普惠导出）。"""

    def __init__(
        self,
        *,
        skills_root: pathlib.Path | str | None = None,
        drafts_dir: pathlib.Path | str | None = None,
        backups_dir: pathlib.Path | str | None = None,
        sandbox: SandboxManager | None = None,
        skill_registry: SkillRegistry | None = None,
        synthesizer_fn: SynthesizerFn | None = None,
        extra_auditor_fn: ExtraAuditFn | None = None,
    ) -> None:
        default_ws = pathlib.Path(__file__).resolve().parents[2] / "workspace"
        self.skills_root = (
            pathlib.Path(skills_root).resolve() if skills_root is not None else (default_ws / "skills").resolve()
        )
        self.drafts_dir = (
            pathlib.Path(drafts_dir).resolve()
            if drafts_dir is not None
            else (default_ws / ".huiqiao" / "evolution_drafts").resolve()
        )
        self.backups_dir = (
            pathlib.Path(backups_dir).resolve()
            if backups_dir is not None
            else (default_ws / ".huiqiao" / "skill_backups").resolve()
        )
        self.skills_root.mkdir(parents=True, exist_ok=True)
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

        self.sandbox = sandbox or SandboxManager(offline_only=True)
        self.skill_registry = skill_registry
        self._synthesizer_fn = synthesizer_fn or _default_synthesize_from_seed
        self._extra_auditor_fn = extra_auditor_fn

    def healthcheck(self) -> bool:
        return self.sandbox.healthcheck() and self.drafts_dir.exists()

    def _draft_path(self, draft_id: str) -> pathlib.Path:
        return self.drafts_dir / f"{draft_id}.json"

    def _save_draft(self, draft: EvolutionDraft) -> EvolutionDraft:
        updated = draft.model_copy(update={"updated_at": utc_now()})
        self._draft_path(updated.draft_id).write_text(
            json.dumps(updated.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return updated

    def get_draft(self, draft_id: str) -> EvolutionDraft:
        p = self._draft_path(draft_id)
        if not p.exists():
            raise KeyError(f"未找到自演化草稿: {draft_id}")
        return EvolutionDraft.model_validate_json(p.read_text(encoding="utf-8"))

    def list_drafts(self) -> list[EvolutionDraft]:
        items: list[EvolutionDraft] = []
        for p in sorted(self.drafts_dir.glob("draft_*.json")):
            try:
                items.append(EvolutionDraft.model_validate_json(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        items.sort(key=lambda d: d.updated_at, reverse=True)
        return items

    def draft_from_seed(
        self,
        seed: SkillSeedCandidate,
        *,
        skill_id_override: str | None = None,
    ) -> EvolutionDraft:
        """从 M10 捕获的 SkillSeedCandidate 生成结构化 DRAFT 候选技能。"""
        synth = self._synthesizer_fn(seed)
        skill_id = skill_id_override or synth["skill_id"]
        manifest_yaml = synth["manifest_yaml"]
        if skill_id_override:
            raw_m = yaml.safe_load(manifest_yaml) or {}
            raw_m["skill_id"] = skill_id_override
            manifest_yaml = yaml.safe_dump(raw_m, allow_unicode=True, sort_keys=False)

        draft = EvolutionDraft(
            source_seed_id=seed.seed_id,
            skill_id=skill_id,
            name=synth["name"],
            version=synth.get("version", "1.0.0"),
            description=synth["description"],
            status=SkillStatus.DRAFT,
            manifest_yaml=manifest_yaml,
            skill_markdown=synth["skill_markdown"],
            handler_code=synth["handler_code"],
            smoke_test_code=synth["smoke_test_code"],
            portable_lite_ready=True,
        )
        return self._save_draft(draft)

    def create_draft(
        self,
        *,
        skill_id: str,
        name: str,
        description: str,
        manifest_yaml: str,
        skill_markdown: str,
        handler_code: str,
        smoke_test_code: str,
        version: str = "1.0.0",
        portable_lite_ready: bool = True,
        source_seed_id: str | None = None,
    ) -> EvolutionDraft:
        draft = EvolutionDraft(
            source_seed_id=source_seed_id,
            skill_id=skill_id,
            name=name,
            version=version,
            description=description,
            status=SkillStatus.DRAFT,
            manifest_yaml=manifest_yaml,
            skill_markdown=skill_markdown,
            handler_code=handler_code,
            smoke_test_code=smoke_test_code,
            portable_lite_ready=portable_lite_ready,
        )
        return self._save_draft(draft)

    def verify_draft(self, draft_id: str) -> EvolutionDraft:
        """执行防坍塌双闸门：先 Gate 2 C00 增上四问一票否决，再 Gate 1 独立 M08 离线沙箱客观验证。"""
        draft = self.get_draft(draft_id)
        draft = self._save_draft(draft.model_copy(update={"status": SkillStatus.VERIFYING}))

        # 闸门二：C00 增上四问一票否决（违宪内容甚至不必浪费沙箱算力，直接永久否决！）
        gate2 = run_constitution_uplift_gate(
            name=draft.name,
            description=draft.description,
            manifest_yaml=draft.manifest_yaml,
            skill_markdown=draft.skill_markdown,
            handler_code=draft.handler_code,
            portable_lite_ready=draft.portable_lite_ready,
            extra_auditor_fn=self._extra_auditor_fn,
        )
        if not gate2.passed:
            return self._save_draft(
                draft.model_copy(
                    update={
                        "gate2_audit": gate2,
                        "status": SkillStatus.REJECTED_BY_CONSTITUTION,
                        "review_note": f"被闸门二 C00 宪章一票否决：{gate2.rationale}",
                    }
                )
            )

        # 闸门一：独立 M08 T2 离线沙箱客观冒烟单测
        gate1 = run_objective_sandbox_gate(
            manifest_yaml=draft.manifest_yaml,
            skill_markdown=draft.skill_markdown,
            handler_code=draft.handler_code,
            smoke_test_code=draft.smoke_test_code,
            sandbox=self.sandbox,
        )
        if not gate1.passed:
            return self._save_draft(
                draft.model_copy(
                    update={
                        "gate1_report": gate1,
                        "gate2_audit": gate2,
                        "status": SkillStatus.DEGRADED,
                        "review_note": f"未通过闸门一独立沙箱客观验证：{gate1.stderr or gate1.issues}",
                    }
                )
            )

        # 双闸门全部通过 -> 进入 PENDING_REVIEW 等待人类透明审阅与签发（绝不背着人静默上线！）
        return self._save_draft(
            draft.model_copy(
                update={
                    "gate1_report": gate1,
                    "gate2_audit": gate2,
                    "status": SkillStatus.PENDING_REVIEW,
                    "review_note": "双闸门（M08 沙箱客观单测 + C00 增上四问）全部通过，等待人类确认签发。",
                }
            )
        )

    def activate_draft(
        self,
        draft_id: str,
        *,
        approved: bool = True,
        reviewer: str = "human",
        review_note: str = "",
    ) -> EvolutionDraft:
        """人类审阅签发：只有双闸门全绿的草稿才允许批准安装为 ACTIVE 技能；驳回则安全归档。"""
        draft = self.get_draft(draft_id)

        if not approved:
            return self._save_draft(
                draft.model_copy(
                    update={
                        "status": SkillStatus.ARCHIVED,
                        "reviewer": reviewer,
                        "review_note": review_note or "人类审阅未批准，已安全归档。",
                    }
                )
            )

        # 硬红线：严禁绕过双闸门强行激活任何草稿
        if draft.status == SkillStatus.REJECTED_BY_CONSTITUTION or (
            draft.gate2_audit is not None and not draft.gate2_audit.passed
        ):
            raise PermissionError(
                f"禁止激活被 C00 宪章否决的草稿 ({draft_id})：{draft.review_note}"
            )
        if (
            draft.gate1_report is None
            or not draft.gate1_report.passed
            or draft.gate2_audit is None
            or not draft.gate2_audit.passed
        ):
            raise PermissionError(
                f"草稿 ({draft_id}) 尚未同时通过双闸门（Gate 1 客观单测 + Gate 2 C00 审查），严禁激活。"
            )

        # 写入 workspace/skills/<skill_id>/ 前若已有同名旧版，自动留存一键回滚快照
        target_dir = self.skills_root / draft.skill_id
        backup_dir = self.backups_dir / draft.skill_id
        if target_dir.exists():
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            shutil.copytree(target_dir, backup_dir)

        target_dir.mkdir(parents=True, exist_ok=True)
        raw_manifest = yaml.safe_load(draft.manifest_yaml) or {}
        raw_manifest["status"] = SkillStatus.ACTIVE.value
        active_manifest_yaml = yaml.safe_dump(raw_manifest, allow_unicode=True, sort_keys=False)

        (target_dir / "manifest.yaml").write_text(active_manifest_yaml, encoding="utf-8")
        (target_dir / "SKILL.md").write_text(draft.skill_markdown, encoding="utf-8")
        (target_dir / "handler.py").write_text(draft.handler_code, encoding="utf-8")
        (target_dir / "tests_smoke.py").write_text(draft.smoke_test_code, encoding="utf-8")

        if self.skill_registry is not None:
            self.skill_registry.reload()

        return self._save_draft(
            draft.model_copy(
                update={
                    "manifest_yaml": active_manifest_yaml,
                    "status": SkillStatus.ACTIVE,
                    "reviewer": reviewer,
                    "review_note": review_note or f"已由 {reviewer} 审阅签发并激活上线。",
                }
            )
        )

    def rollback_skill(self, skill_id: str) -> dict[str, Any]:
        """一键可逆回滚（C00 A1）：若有历史备份则恢复旧版，否则将当前激活技能安全降为 ARCHIVED。"""
        target_dir = self.skills_root / skill_id
        if not target_dir.exists():
            raise KeyError(f"未找到已安装技能目录: {skill_id}")

        backup_dir = self.backups_dir / skill_id
        action: str
        if backup_dir.exists():
            shutil.rmtree(target_dir)
            shutil.copytree(backup_dir, target_dir)
            shutil.rmtree(backup_dir)
            action = "RESTORED_PREVIOUS_VERSION"
        else:
            manifest_path = target_dir / "manifest.yaml"
            raw_m = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            raw_m["status"] = SkillStatus.ARCHIVED.value
            manifest_path.write_text(
                yaml.safe_dump(raw_m, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            action = "ARCHIVED_SKILL"

        if self.skill_registry is not None:
            self.skill_registry.reload()

        return {"skill_id": skill_id, "action": action}

    def export_skill(self, skill_id: str, output_zip: pathlib.Path | str) -> PortableSkillCard:
        skill_dir = self.skills_root / skill_id
        return export_portable_skill(skill_dir, output_zip, sandbox=self.sandbox)

    def import_skill(
        self,
        zip_path: pathlib.Path | str,
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        info = import_portable_skill(
            zip_path,
            self.skills_root,
            sandbox=self.sandbox,
            require_dual_gate=True,
            overwrite=overwrite,
        )
        if self.skill_registry is not None:
            self.skill_registry.reload()
        return info
