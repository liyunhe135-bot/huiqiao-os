"""汇桥 OS 三大持久中枢（Skill 规划管理库 · 经验防坑库 · 不断档上下文跟踪器）.

解决三大核心工程与使用痛点：
  1. Skill 规划管理库（workspace/SKILL_PLAN_HUB.md）：
     统一纳管「规划池 (PLANNED) -> 候选种子 (SEED) -> 双闸门待审草稿 (PENDING_REVIEW) -> 已上线技能 (ACTIVE)」，
     支持新建技能规划、一键从规划孵化通过双闸门测试上线、导出 .hqskill.zip 与回滚；
  2. 经验防坑库（workspace/EXPERIENCE_VAULT.md）：
     结构化沉淀踩坑原因与防复发铁律，每次用户「纠偏」自动入库，并在每次编码/SFDP/问答推理前
     自动按相关性挂载 <经验防坑护栏>（省 Token 精炼注入，命中次数可追踪）；
  3. 不断档上下文跟踪器（workspace/ACTIVE_CONTEXT.md + .huiqiao/hub_state.json）：
     跨轮次、跨刷新、跨重启保持项目会话不断档；自动绑定上一轮生成的应用代码产物（如 index.html）与规格书，
     后续输入「继续加上计时器/搜索」时自动继承上下文增量演进，超长对话自动滚动摘要不爆显存。
"""

from __future__ import annotations

import json
import pathlib
from typing import TYPE_CHECKING, Any

from packages.core.contracts import new_id, utc_now
from packages.memory.models import SkillSeedCandidate

if TYPE_CHECKING:
    from packages.evolution.engine import SelfEvolutionEngine
    from packages.gateway.skills_loader import SkillRegistry
    from packages.memory.feedback import FeedbackLoopService
    from packages.memory.store import FileFirstMemoryStore
    from packages.orchestrator.store import RunStore

_INCREMENTAL_HINTS = (
    "继续",
    "加上",
    "增加",
    "再加",
    "修改",
    "改成",
    "优化",
    "完善",
    "补充",
    "调整",
    "刚才",
    "上面",
    "这个小程序",
    "升级",
    "修复",
)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _default_experiences() -> list[dict[str, Any]]:
    now = _now_iso()
    return [
        {
            "exp_id": "exp_anti_drift_sfdp",
            "title": "规格先行与独立沙箱 AC 核验（防交付偏移）",
            "category": "防偏移",
            "pitfall": "摘要漏斗丢掉交互设计步骤或仅靠单测 Mock 假绿灯，导致交付与 PRD 预期脱节。",
            "rule": "复杂构建先对齐规格与验收项(AC)，代码必须在隔离沙箱真实运行落盘，严禁口头宣称完成。",
            "auto_inject": True,
            "hit_count": 0,
            "created_at": now,
        },
        {
            "exp_id": "exp_offline_single_html",
            "title": "本地小程序零外部 CDN 与 localStorage 持久化",
            "category": "本地编码",
            "pitfall": "引用外部 CDN 导致断网白屏，或未做本地存储导致刷新页面打卡数据清零。",
            "rule": "构建本地网页小程序必须输出单文件内联 HTML5+CSS3+原生JS，状态一律存入 localStorage，严禁任何 http/https 外链。",
            "auto_inject": True,
            "hit_count": 0,
            "created_at": now,
        },
        {
            "exp_id": "exp_incremental_preserve",
            "title": "多轮跟进增量演进（严禁丢弃已有功能）",
            "category": "上下文连续",
            "pitfall": "第二轮追加需求时推倒重写，把上一轮已做好的打卡、章节或样式丢掉。",
            "rule": "若上下文中附带了上一版代码产物，必须在其基础上保留全部原有功能并增量添加新特性。",
            "auto_inject": True,
            "hit_count": 0,
            "created_at": now,
        },
        {
            "exp_id": "exp_public_plain_terms",
            "title": "面向公众默认白话零门槛 + 专业术语可切换注释",
            "category": "UI与语境",
            "pitfall": "直接堆砌佛学或内部架构专业名词，导致大众用户看不懂按钮功能。",
            "rule": "界面默认采用直观大众白话；若涉及佛学/传统文化专有词，必须附带白话解释或语境切换按钮。",
            "auto_inject": True,
            "hit_count": 0,
            "created_at": now,
        },
        {
            "exp_id": "exp_win_utf8_io",
            "title": "Windows 本地读写强制 UTF-8 防乱码",
            "category": "沙箱编码",
            "pitfall": "Windows 默认 GBK 编码导致读写中文文本或 Emoji 抛出 UnicodeEncodeError。",
            "rule": "所有 Python 文件读写显式传入 encoding='utf-8'，JSON 跨进程输出确保 UTF-8 兼容。",
            "auto_inject": True,
            "hit_count": 0,
            "created_at": now,
        },
    ]


def _default_skill_plans() -> list[dict[str, Any]]:
    now = _now_iso()
    return [
        {
            "plan_id": "plan_spaced_recite",
            "title": "经典背诵间隔复习规划师",
            "category": "学习精进",
            "priority": "P0",
            "triggers": ["背诵复习计划", "俱舍复习", "艾宾浩斯排期"],
            "goal": "输入经典品目与每日可用时长，自动生成 1/2/4/7/15 天间隔背诵复习表与打卡清单。",
            "status": "PLANNED",
            "linked_skill_id": None,
            "created_at": now,
        },
        {
            "plan_id": "plan_prd_ac_auditor",
            "title": "PRD 需求防偏移核对器",
            "category": "研发治理",
            "priority": "P0",
            "triggers": ["核对PRD偏移", "需求验收清单", "检查交付缺口"],
            "goal": "对照原始需求要点逐条核查功能闭环、边界条件与未实现缺口，防止省流量摘要漏项。",
            "status": "PLANNED",
            "linked_skill_id": None,
            "created_at": now,
        },
        {
            "plan_id": "plan_bilingual_glossary",
            "title": "专业术语白话双语转换器",
            "category": "公众传达",
            "priority": "P1",
            "triggers": ["术语转白话", "佛学白话对照", "通俗解释"],
            "goal": "将佛学、中医或技术专有名词自动转换为面向公众零门槛的大众白话对照说明。",
            "status": "PLANNED",
            "linked_skill_id": None,
            "created_at": now,
        },
    ]


class TrinityContinuityHub:
    """统一管理 Skill 规划管理库、经验防坑库与不断档会话上下文。"""

    def __init__(
        self,
        *,
        workspace_dir: pathlib.Path,
        memory: FileFirstMemoryStore,
        feedback: FeedbackLoopService,
        evolution: SelfEvolutionEngine,
        skills: SkillRegistry,
        run_store: RunStore,
    ) -> None:
        self.workspace_dir = workspace_dir.resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir = self.workspace_dir / ".huiqiao"
        self.meta_dir.mkdir(parents=True, exist_ok=True)

        self.state_path = self.meta_dir / "hub_state.json"
        self.skill_plan_md_path = self.workspace_dir / "SKILL_PLAN_HUB.md"
        self.experience_md_path = self.workspace_dir / "EXPERIENCE_VAULT.md"
        self.active_context_md_path = self.workspace_dir / "ACTIVE_CONTEXT.md"

        self.memory = memory
        self.feedback = feedback
        self.evolution = evolution
        self.skills = skills
        self.run_store = run_store

        self._state = self._load_or_init_state()
        self._bootstrap_session_from_recent_runs()
        self._flush_all_markdown()

    def _load_or_init_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data.setdefault("experiences", _default_experiences())
                    data.setdefault("skill_plans", _default_skill_plans())
                    data.setdefault("sessions", [])
                    data.setdefault("active_session_id", "")
                    return data
            except Exception:
                pass
        default_sid = new_id("ses")
        initial_session = {
            "session_id": default_sid,
            "title": "默认连续工作流会话",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "rolling_summary": "",
            "pinned_run_id": None,
            "pinned_artifact_path": None,
            "pinned_preview_url": None,
            "active_spec_id": None,
            "turns": [],
        }
        state = {
            "experiences": _default_experiences(),
            "skill_plans": _default_skill_plans(),
            "sessions": [initial_session],
            "active_session_id": default_sid,
        }
        self._save_json(state)
        return state

    def _save_json(self, state: dict[str, Any] | None = None) -> None:
        target = state if state is not None else self._state
        self.state_path.write_text(
            json.dumps(target, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def _bootstrap_session_from_recent_runs(self) -> None:
        """重启或首次升级时，自动挂载最近一次真实运行产物，确保之前构建的小程序上下文绝不断档！"""
        active = self.get_active_session()
        if active["turns"] or active.get("pinned_run_id"):
            return
        recent = self.run_store.list_runs(limit=5)
        if not recent:
            return
        for r in recent:
            if r.get("status") != "COMPLETED":
                continue
            detail = self.run_store.get_run(r["run_id"])
            if not detail:
                continue
            st = detail.get("state") or {}
            goal = str((st.get("_envelope") or {}).get("raw_input") or st.get("goal") or "").strip()
            if not goal:
                continue
            out = st.get("structured_step") or {}
            summary = str(out.get("summary") or st.get("summary") or "已完成任务执行").strip()
            arts = self.run_store.list_artifacts(r["run_id"])
            html_art = next((a for a in arts if str(a.get("name", "")).lower().endswith(".html")), None)
            chosen_art = html_art or (arts[0] if arts else None)
            preview_url = (
                f"/preview/{r['run_id']}/{chosen_art['name']}"
                if chosen_art and str(chosen_art.get("name", "")).lower().endswith(".html")
                else None
            )
            active["title"] = goal[:22] + ("…" if len(goal) > 22 else "")
            active["pinned_run_id"] = r["run_id"]
            art_fp = (chosen_art.get("file_path") or chosen_art.get("path")) if chosen_art else None
            active["pinned_artifact_path"] = art_fp
            active["pinned_preview_url"] = preview_url
            active["active_spec_id"] = st.get("spec_id")
            active["turns"].append(
                {
                    "turn_no": 1,
                    "run_id": r["run_id"],
                    "goal": goal,
                    "summary": summary[:320],
                    "artifact_path": art_fp,
                    "preview_url": preview_url,
                    "timestamp": r.get("updated_at") or _now_iso(),
                }
            )
            active["updated_at"] = _now_iso()
            self._save_json()
            break

    # =========================================================================
    # 1. 经验防坑库（Experience Vault）
    # =========================================================================
    def list_experiences(self, category: str | None = None) -> list[dict[str, Any]]:
        items = list(self._state.get("experiences", []))
        if category:
            items = [x for x in items if x.get("category") == category]
        return items

    def add_experience(
        self,
        *,
        title: str,
        pitfall: str,
        rule: str,
        category: str = "用户纠偏",
        auto_inject: bool = True,
        sync_to_memory: bool = True,
    ) -> dict[str, Any]:
        entry = {
            "exp_id": new_id("exp"),
            "title": title.strip(),
            "category": category.strip() or "通用经验",
            "pitfall": pitfall.strip() or "历史实践中发现的易错点",
            "rule": rule.strip(),
            "auto_inject": bool(auto_inject),
            "hit_count": 0,
            "created_at": _now_iso(),
        }
        self._state.setdefault("experiences", []).insert(0, entry)
        if sync_to_memory:
            self.memory.commit(
                {
                    "content": f"[{entry['category']}·{entry['title']}] 防坑铁律：{entry['rule']}（原坑：{entry['pitfall']}）",
                    "layer": "anti_pattern",
                    "topic_key": f"exp.{entry['exp_id']}",
                    "tags": ["experience_vault", entry["category"]],
                    "source": "experience_vault",
                }
            )
        self._save_json()
        self._write_experience_markdown()
        return entry

    def toggle_experience(self, exp_id: str, auto_inject: bool) -> dict[str, Any]:
        for item in self._state.get("experiences", []):
            if item["exp_id"] == exp_id:
                item["auto_inject"] = bool(auto_inject)
                self._save_json()
                self._write_experience_markdown()
                return item
        raise KeyError(f"未找到经验条目: {exp_id}")

    def delete_experience(self, exp_id: str) -> dict[str, Any]:
        before = len(self._state.get("experiences", []))
        self._state["experiences"] = [
            x for x in self._state.get("experiences", []) if x["exp_id"] != exp_id
        ]
        if len(self._state["experiences"]) == before:
            raise KeyError(f"未找到经验条目: {exp_id}")
        self._save_json()
        self._write_experience_markdown()
        return {"deleted": exp_id}

    def match_and_format_guardrails(self, goal: str, *, max_items: int = 4) -> tuple[str, list[str]]:
        """按当前任务意图精准筛选防坑经验，生成极省流量的推理护栏块并累计命中次数。"""
        lowered = (goal or "").lower()
        scored: list[tuple[int, dict[str, Any]]] = []
        for item in self._state.get("experiences", []):
            if not item.get("auto_inject", True):
                continue
            score = 1
            if item.get("category") == "用户纠偏":
                score += 4  # 用户亲自纠偏的铁律最高优！
            if any(k in lowered for k in ("小程序", "网页", "打卡", "html", "界面", "应用")) and item.get("category") in ("本地编码", "UI与语境"):
                score += 3
            if any(k in lowered for k in _INCREMENTAL_HINTS) and item.get("category") == "上下文连续":
                score += 5
            for kw in (item.get("title", ""), item.get("rule", "")):
                if any(tok in lowered for tok in ("俱舍", "背诵", "编码", "脚本", "公众", "佛")):
                    if any(tok in kw for tok in ("编码", "小程序", "白话", "增量")):
                        score += 1
            scored.append((score, item))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        chosen = [item for _, item in scored[:max_items]]
        if not chosen:
            return "", []

        matched_titles: list[str] = []
        lines = ["[汇桥经验防坑库护栏（历史踩坑铁律，本次执行必须严格遵守）]:"]
        for idx, item in enumerate(chosen, 1):
            item["hit_count"] = int(item.get("hit_count", 0)) + 1
            matched_titles.append(item["title"])
            lines.append(f"{idx}. 【{item['category']}】{item['rule']}")

        # 同时召回 M10 记忆库中用户手动写入的相关偏好（最多 2 条，省 Token）
        recalled = self.memory.recall(goal, top_k=2) if goal.strip() else []
        for mem in recalled:
            content = str(mem.get("content", "")).strip()
            if content and not content.startswith("["):
                lines.append(f"- 【用户本地记忆偏好】{content[:140]}")

        self._save_json()
        return "\n".join(lines), matched_titles

    # =========================================================================
    # 2. Skill 规划管理库（Skill Planning & Lifecycle Hub）
    # =========================================================================
    def get_skill_hub_overview(self) -> dict[str, Any]:
        plans = list(self._state.get("skill_plans", []))
        seeds = [s.model_dump(mode="json") for s in self.feedback.list_skill_seeds()]
        drafts = [d.model_dump(mode="json") for d in self.evolution.list_drafts()]
        active = [m.model_dump(mode="json") for m in self.skills.list_manifests()]
        return {
            "counts": {
                "planned": len([p for p in plans if p.get("status") == "PLANNED"]),
                "seeds": len(seeds),
                "drafts": len([d for d in drafts if d.get("status") == "PENDING_REVIEW"]),
                "active": len(active),
            },
            "plans": plans,
            "seeds": seeds,
            "drafts": drafts,
            "active_skills": active,
            "roadmap_markdown_path": str(self.skill_plan_md_path),
        }

    def add_skill_plan(
        self,
        *,
        title: str,
        goal: str,
        category: str = "自定义规划",
        priority: str = "P1",
        triggers: list[str] | None = None,
    ) -> dict[str, Any]:
        clean_triggers = [t.strip() for t in (triggers or []) if t.strip()] or [title.strip()[:16]]
        plan = {
            "plan_id": new_id("plan"),
            "title": title.strip(),
            "category": category.strip() or "自定义规划",
            "priority": priority.strip().upper() if priority.strip().upper() in ("P0", "P1", "P2") else "P1",
            "triggers": clean_triggers,
            "goal": goal.strip(),
            "status": "PLANNED",
            "linked_skill_id": None,
            "created_at": _now_iso(),
        }
        self._state.setdefault("skill_plans", []).insert(0, plan)
        self._save_json()
        self._write_skill_plan_markdown()
        return plan

    def incubate_skill_plan(self, plan_id: str, *, auto_activate: bool = False) -> dict[str, Any]:
        """一键将『规划池』中的技能蓝图合成为候选草稿并跑通 M11 双闸门（沙箱单测 + C00 宪章审查）！"""
        target = next((p for p in self._state.get("skill_plans", []) if p["plan_id"] == plan_id), None)
        if target is None:
            raise KeyError(f"未找到技能规划项: {plan_id}")

        seed = SkillSeedCandidate(
            seed_id=new_id("seed"),
            source_run_id=f"roadmap_{plan_id}",
            title=target["title"],
            user_goal=target["goal"],
            summary=f"触发词：{', '.join(target.get('triggers', []))}。规划目标：{target['goal']}",
            human_note="由 Skill 规划管理库一键启动孵化",
        )
        draft = self.evolution.draft_from_seed(seed)
        draft = self.evolution.verify_draft(draft.draft_id)
        if auto_activate and draft.status.value == "PENDING_REVIEW":
            draft = self.evolution.activate_draft(
                draft.draft_id,
                approved=True,
                reviewer="human_hub",
                review_note="由 Skill 规划管理库一键孵化并确认上线",
            )
            target["status"] = "ACTIVE"
        else:
            target["status"] = draft.status.value
        target["linked_skill_id"] = draft.skill_id
        target["draft_id"] = draft.draft_id
        self._save_json()
        self._write_skill_plan_markdown()
        return {
            "plan": target,
            "draft": draft.model_dump(mode="json"),
        }

    def delete_skill_plan(self, plan_id: str) -> dict[str, Any]:
        before = len(self._state.get("skill_plans", []))
        self._state["skill_plans"] = [
            p for p in self._state.get("skill_plans", []) if p["plan_id"] != plan_id
        ]
        if len(self._state["skill_plans"]) == before:
            raise KeyError(f"未找到技能规划项: {plan_id}")
        self._save_json()
        self._write_skill_plan_markdown()
        return {"deleted": plan_id}

    # =========================================================================
    # 3. 不断档上下文跟踪器（Continuous Context Tracker）
    # =========================================================================
    def list_sessions(self) -> dict[str, Any]:
        return {
            "active_session_id": self._state.get("active_session_id"),
            "active_context_markdown_path": str(self.active_context_md_path),
            "sessions": self._state.get("sessions", []),
        }

    def get_active_session(self) -> dict[str, Any]:
        sid = self._state.get("active_session_id")
        for s in self._state.get("sessions", []):
            if s["session_id"] == sid:
                return s
        if self._state.get("sessions"):
            self._state["active_session_id"] = self._state["sessions"][0]["session_id"]
            return self._state["sessions"][0]
        created = self.create_session("默认连续工作流会话")
        return created

    def create_session(self, title: str = "新项目连续会话") -> dict[str, Any]:
        ses = {
            "session_id": new_id("ses"),
            "title": title.strip() or "新项目连续会话",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "rolling_summary": "",
            "pinned_run_id": None,
            "pinned_artifact_path": None,
            "pinned_preview_url": None,
            "active_spec_id": None,
            "turns": [],
        }
        self._state.setdefault("sessions", []).insert(0, ses)
        self._state["active_session_id"] = ses["session_id"]
        self._save_json()
        self._write_active_context_markdown()
        return ses

    def switch_session(self, session_id: str) -> dict[str, Any]:
        for s in self._state.get("sessions", []):
            if s["session_id"] == session_id:
                self._state["active_session_id"] = session_id
                self._save_json()
                self._write_active_context_markdown()
                return s
        raise KeyError(f"未找到上下文会话: {session_id}")

    def prepare_continuous_context(
        self,
        goal: str,
        *,
        session_id: str | None = None,
        follow_context: bool = True,
    ) -> dict[str, Any]:
        """组装『不断档上下文 + 经验防坑护栏』，确保多轮跟进修改绝不断片、绝不重犯老错。"""
        ses = (
            self.switch_session(session_id)
            if session_id
            else self.get_active_session()
        )
        guardrail_block, matched_exp_titles = self.match_and_format_guardrails(goal)

        context_messages: list[dict[str, str]] = []
        prior_code_snippet = ""
        attached_prev_artifact = False

        if follow_context:
            if ses.get("rolling_summary"):
                context_messages.append(
                    {
                        "role": "user",
                        "content": f"[早期会话滚动摘要（自动防断档）]:\n{ses['rolling_summary']}",
                    }
                )
                context_messages.append(
                    {
                        "role": "assistant",
                        "content": "明白，我已完整继承此前轮次的项目背景与关键决策。",
                    }
                )
            # 保留最近 3 轮对话，既不断档又极省 Token
            for t in ses.get("turns", [])[-3:]:
                context_messages.append({"role": "user", "content": str(t.get("goal", ""))})
                context_messages.append({"role": "assistant", "content": str(t.get("summary", ""))})

            # 若当前会话已有上一版代码文件（如 index.html），且用户在跟进修改/迭代，自动挂载上一版源码供增量修改！
            art_path_str = ses.get("pinned_artifact_path")
            is_follow_up = any(h in goal for h in _INCREMENTAL_HINTS) or (
                bool(art_path_str) and len(ses.get("turns", [])) >= 1 and len(goal) <= 120
            )
            if art_path_str and is_follow_up:
                p = pathlib.Path(str(art_path_str))
                if p.is_file() and p.suffix.lower() in {".html", ".py", ".js", ".css", ".md"}:
                    try:
                        raw_code = p.read_text(encoding="utf-8", errors="ignore")
                        if raw_code.strip():
                            clipped = raw_code[:7000]
                            prior_code_snippet = (
                                f"\n\n[当前会话上一版已落盘产物 `{p.name}`（请在此基础上增量演进，严禁丢弃已有功能）]:\n"
                                f"```{p.suffix.lstrip('.') or 'text'}\n{clipped}\n```"
                            )
                            attached_prev_artifact = True
                    except Exception:
                        pass

        parts = [goal.strip()]
        if prior_code_snippet:
            parts.append(prior_code_snippet)
        if guardrail_block:
            parts.append(f"\n{guardrail_block}")

        augmented_goal = "\n".join(parts)
        return {
            "session_id": ses["session_id"],
            "session_title": ses["title"],
            "turn_index": len(ses.get("turns", [])) + 1,
            "context_messages": context_messages,
            "augmented_goal": augmented_goal,
            "guardrail_block": guardrail_block,
            "matched_experiences": matched_exp_titles,
            "attached_prev_artifact": attached_prev_artifact,
            "pinned_preview_url": ses.get("pinned_preview_url"),
        }

    def record_turn_completion(
        self,
        *,
        session_id: str | None,
        run_id: str,
        raw_goal: str,
        summary: str,
        artifacts: list[dict[str, Any]] | None = None,
        spec_id: str | None = None,
    ) -> dict[str, Any]:
        """每次任务或 SFDP 构建完成后自动追加到会话链，超过 6 轮自动压缩滚动摘要，永不断档！"""
        ses = (
            self.switch_session(session_id)
            if session_id
            else self.get_active_session()
        )
        arts = artifacts or []
        html_art = next((a for a in arts if str(a.get("name", "")).lower().endswith(".html")), None)
        code_art = html_art or next(
            (a for a in arts if str(a.get("name", "")).lower().endswith((".py", ".md"))),
            arts[0] if arts else None,
        )
        preview_url = (
            f"/preview/{run_id}/{html_art['name']}"
            if html_art
            else ses.get("pinned_preview_url")
        )
        if html_art:
            ses["pinned_artifact_path"] = html_art.get("file_path") or html_art.get("path")
            ses["pinned_preview_url"] = preview_url
        elif code_art and not ses.get("pinned_artifact_path"):
            ses["pinned_artifact_path"] = code_art.get("file_path") or code_art.get("path")

        ses["pinned_run_id"] = run_id
        if spec_id:
            ses["active_spec_id"] = spec_id

        if len(ses.get("turns", [])) == 0 and ses.get("title") in ("默认连续工作流会话", "新项目连续会话"):
            ses["title"] = raw_goal.strip()[:22] + ("…" if len(raw_goal.strip()) > 22 else "")

        prev_turns = ses.get("turns", [])
        last_no = int(prev_turns[-1]["turn_no"]) if prev_turns else int(ses.get("total_turns", 0))
        turn_no = last_no + 1
        ses["total_turns"] = turn_no
        ses.setdefault("turns", []).append(
            {
                "turn_no": turn_no,
                "run_id": run_id,
                "goal": raw_goal.strip(),
                "summary": (summary or "").strip()[:360],
                "artifact_path": (code_art.get("file_path") or code_art.get("path")) if code_art else None,
                "preview_url": preview_url if html_art else None,
                "timestamp": _now_iso(),
            }
        )

        # 双触发轻量防断档滚动压缩：超过 6 轮时将最早轮次浓缩进 rolling_summary，既不断档又省 Token
        if len(ses["turns"]) > 6:
            overflow = ses["turns"][:-4]
            ses["turns"] = ses["turns"][-4:]
            digest_lines = [
                f"- 第{t['turn_no']}轮：{t['goal'][:50]} -> {t['summary'][:70]}"
                for t in overflow
            ]
            prev = (ses.get("rolling_summary") or "").strip()
            merged = (f"{prev}\n" + "\n".join(digest_lines)).strip()
            ses["rolling_summary"] = merged[-1200:]

        ses["updated_at"] = _now_iso()
        self._save_json()
        self._write_active_context_markdown()
        return ses

    # =========================================================================
    # File-First 人类可读 Markdown 实时镜像落盘
    # =========================================================================
    def _flush_all_markdown(self) -> None:
        self._write_skill_plan_markdown()
        self._write_experience_markdown()
        self._write_active_context_markdown()

    def _write_skill_plan_markdown(self) -> None:
        lines = [
            "# 🧩 汇桥 OS · Skill 规划管理库 (SKILL_PLAN_HUB.md)",
            "",
            "> 本文件为人类可读真相源镜像，汇桥工作台实时双向维护「规划池 -> 种子 -> 双闸门待审 -> 已启用技能」。",
            "",
            "## 一、当前规划蓝图池 (Roadmap & Planned Skills)",
        ]
        for p in self._state.get("skill_plans", []):
            lines.append(
                f"- **[{p.get('priority', 'P1')} | {p.get('status', 'PLANNED')}] {p['title']}** (`{p['plan_id']}`) "
                f"— 分类：{p.get('category', '')} ｜ 触发词：`{', '.join(p.get('triggers', []))}` ｜ 目标：{p.get('goal', '')}"
            )
        lines.extend(["", "## 二、已启用活跃技能 (Active Skills)"])
        for m in self.skills.list_manifests():
            lines.append(f"- **{m.name}** (`{m.skill_id}` v{m.version}) — {m.description}")
        self.skill_plan_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_experience_markdown(self) -> None:
        lines = [
            "# 📚 汇桥 OS · 经验防坑库 (EXPERIENCE_VAULT.md)",
            "",
            "> 每次编码、规格设计与问答推理前自动匹配挂载，确保历史踩过的坑绝不重犯。",
            "",
        ]
        for e in self._state.get("experiences", []):
            flag = "✅自动挂载" if e.get("auto_inject", True) else "⏸️已暂停"
            lines.append(
                f"### [{e['category']}] {e['title']} (`{e['exp_id']}` · {flag} · 累计护航 {e.get('hit_count', 0)} 次)\n"
                f"- **历史踩坑**：{e['pitfall']}\n"
                f"- **防复发铁律**：{e['rule']}\n"
            )
        self.experience_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_active_context_markdown(self) -> None:
        ses = self.get_active_session()
        lines = [
            "# 🔗 汇桥 OS · 当前不断档会话上下文 (ACTIVE_CONTEXT.md)",
            "",
            f"- **活跃会话**：{ses['title']} (`{ses['session_id']}`)",
            f"- **最近更新**：{ses.get('updated_at', '')}",
            f"- **当前绑定运行**：`{ses.get('pinned_run_id') or '暂无'}`",
            f"- **当前绑定代码产物**：`{ses.get('pinned_artifact_path') or '暂无'}`",
            f"- **当前绑定预览链接**：`{ses.get('pinned_preview_url') or '暂无'}`",
            "",
        ]
        if ses.get("rolling_summary"):
            lines.extend(["## 早期轮次浓缩摘要", ses["rolling_summary"], ""])
        lines.append("## 最近连续对话与构建轨迹")
        if not ses.get("turns"):
            lines.append("- （新会话就绪，首次输入需求后自动建立连续跟踪链）")
        else:
            for t in ses.get("turns", []):
                lines.append(
                    f"- **第 {t['turn_no']} 轮** (`{t['run_id']}`)：{t['goal']}\n"
                    f"  - 结果摘要：{t['summary'][:180]}"
                )
        self.active_context_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
