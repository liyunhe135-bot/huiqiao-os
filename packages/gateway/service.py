"""M07 B01 统一网关与 Alpha MVP 总装配服务（HuiQiaoService · 串联 M00–M06 全部积木）."""

from __future__ import annotations

import pathlib
from typing import Any, Callable, Iterator

from packages.core.constitution import LoadedConstitution, load_constitution
from packages.core.contracts import (
    CapabilityProfile,
    ExecutionChannel,
    InteractionMode,
    RouteDecision,
    SandboxTier,
    SkillManifest,
    StepInput,
    TaskConstraints,
    TaskEnvelope,
    TaskInput,
    Verifiability,
    WorkMode,
    new_id,
)
from packages.evolution import SelfEvolutionEngine
from packages.gateway.skills_loader import SkillRegistry
from packages.governance import GovernanceGuard
from packages.hub import TrinityContinuityHub
from packages.llm_gateway.ollama_live import (
    list_ollama_models,
    make_ollama_infer_fn,
    pick_best_local_model,
)
from packages.memory import FeedbackKind, FeedbackLoopService, FileFirstMemoryStore
from packages.orchestrator import (
    ChuZeSfdpEngine,
    FlowContext,
    FlowPrimitive,
    OrchestratorEngine,
    SequentialFlow,
    SqliteStateStore,
    TaskNode,
)
from packages.router import HybridRouter
from packages.sandbox import SandboxManager
from packages.workers import CodeActWorker, ReActWorker, SemanticCoCreatorWorker

InferFn = Callable[[list[dict[str, str]]], str]


class HuiQiaoService:
    """汇桥 OS 本地一体化运行内核（CLI / FastAPI / WebSocket 共享同一确定性底座）。"""

    def __init__(
        self,
        *,
        repo_root: pathlib.Path | str | None = None,
        db_path: pathlib.Path | str | None = None,
        skills_root: pathlib.Path | str | None = None,
        memory_dir: pathlib.Path | str | None = None,
        semantic_infer_fn: InferFn | None = None,
        react_infer_fn: InferFn | None = None,
        codeact_infer_fn: InferFn | None = None,
        auto_ollama: bool | None = None,
        sandbox: SandboxManager | None = None,
        capability_profile: CapabilityProfile | None = None,
    ) -> None:
        self.repo_root = (
            pathlib.Path(repo_root).resolve()
            if repo_root is not None
            else pathlib.Path(__file__).resolve().parents[2]
        )
        self.workspace_dir = self.repo_root / "workspace"
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        self.constitution: LoadedConstitution = load_constitution(
            self.workspace_dir / "CONSTITUTION.md"
        )
        self.skills = SkillRegistry(skills_root or (self.workspace_dir / "skills"))

        policies_yaml = self.repo_root / "config" / "policies.yaml"
        if policies_yaml.exists():
            self.guard = GovernanceGuard.from_yaml(policies_yaml, base_dir=self.repo_root)
        else:
            self.guard = GovernanceGuard(
                offline_only=True,
                allowed_roots=(self.workspace_dir,),
                base_dir=self.repo_root,
            )

        resolved_db = (
            pathlib.Path(db_path)
            if db_path is not None
            else self.workspace_dir / ".huiqiao" / "state.db"
        )
        self.store = SqliteStateStore(
            resolved_db,
            artifacts_root=resolved_db.parent / "runs",
        )
        self.engine = OrchestratorEngine(self.store, guard=self.guard)
        self.router = HybridRouter(skills=self.skills.list_manifests(active_only=True))
        # 生产环境（db_path=None）或显式开启 auto_ollama 时，自动探活本机 127.0.0.1:11434 Ollama 模型
        enable_auto_ollama = (
            auto_ollama
            if auto_ollama is not None
            else (
                db_path is None
                and semantic_infer_fn is None
                and react_infer_fn is None
                and codeact_infer_fn is None
            )
        )
        self._auto_ollama_enabled = enable_auto_ollama
        self.available_local_models: list[dict[str, Any]] = (
            list_ollama_models() if enable_auto_ollama else []
        )
        self.active_local_model: str | None = (
            pick_best_local_model(self.available_local_models) if enable_auto_ollama else None
        )
        ollama_fn: InferFn | None = (
            make_ollama_infer_fn(lambda: self.active_local_model)
            if self.active_local_model
            else None
        )

        self._semantic_infer_fn = semantic_infer_fn or ollama_fn
        self._react_infer_fn = react_infer_fn or ollama_fn
        self._codeact_infer_fn = codeact_infer_fn or ollama_fn
        self.semantic_worker = SemanticCoCreatorWorker(
            infer_fn=self._semantic_infer_fn,
            constitution=self.constitution,
        )
        self.sandbox = sandbox or SandboxManager(
            offline_only=self.guard.offline_only,
            governance_guard=self.guard,
        )
        self.sfdp = ChuZeSfdpEngine(
            self.store,
            sandbox=self.sandbox,
            guard=self.guard,
            constitution=self.constitution,
        )
        resolved_mem_dir = (
            pathlib.Path(memory_dir).resolve()
            if memory_dir is not None
            else (self.workspace_dir if db_path is None else resolved_db.parent.resolve())
        )
        self.memory = FileFirstMemoryStore(
            resolved_mem_dir,
            db_path=resolved_mem_dir / ".huiqiao" / "memory.db",
        )
        self.feedback = FeedbackLoopService(self.memory)
        self.evolution = SelfEvolutionEngine(
            skills_root=self.skills.skills_root,
            drafts_dir=resolved_mem_dir / ".huiqiao" / "evolution_drafts",
            backups_dir=resolved_mem_dir / ".huiqiao" / "skill_backups",
            sandbox=self.sandbox,
            skill_registry=self.skills,
        )
        self.hub = TrinityContinuityHub(
            workspace_dir=resolved_mem_dir,
            memory=self.memory,
            feedback=self.feedback,
            evolution=self.evolution,
            skills=self.skills,
            run_store=self.store,
        )
        self.capability_profile = capability_profile

    def healthcheck(self) -> dict[str, Any]:
        active_skills = self.skills.list_manifests(active_only=True)
        checks = {
            "constitution": bool(self.constitution.sha256),
            "router": self.router.healthcheck(),
            "governance": self.guard.healthcheck(),
            "orchestrator_wal": self.engine.healthcheck(),
            "semantic_worker": self.semantic_worker.healthcheck(),
            "sandbox": self.sandbox.healthcheck(),
            "memory": self.memory.healthcheck(),
            "evolution": self.evolution.healthcheck(),
            "genesis_skills_ready": len(active_skills) >= 5,
        }
        return {
            "ok": all(checks.values()),
            "version": "1.0.0",
            "offline_only": self.guard.offline_only,
            "constitution_version": self.constitution.version,
            "constitution_sha256": self.constitution.sha256[:16],
            "active_skills_count": len(active_skills),
            "active_local_model": self.active_local_model,
            "checks": checks,
        }

    def list_skills(self) -> list[SkillManifest]:
        return self.skills.list_manifests()

    def get_skill_detail(self, skill_id: str) -> dict[str, Any]:
        manifest = self.skills.get_manifest(skill_id)
        if manifest is None:
            raise KeyError(f"未找到技能: {skill_id}")
        return {
            "manifest": manifest.model_dump(mode="json"),
            "skill_markdown": self.skills.read_skill_markdown(skill_id),
        }

    def accept(self, raw_payload: dict[str, Any], source: str = "api") -> TaskEnvelope:
        """满足 IngressGatewayProtocol：将外部请求标准化为 TaskEnvelope。"""
        text = str(raw_payload.get("text") or raw_payload.get("raw_input") or "").strip()
        attachments = [str(p) for p in (raw_payload.get("attachments") or []) if str(p).strip()]
        allowed_paths = [str(p) for p in (raw_payload.get("allowed_paths") or []) if str(p).strip()]
        mode_raw = raw_payload.get("work_mode", WorkMode.ASK)
        work_mode = mode_raw if isinstance(mode_raw, WorkMode) else WorkMode(str(mode_raw).lower())

        return TaskEnvelope(
            source=source,
            input=TaskInput(
                text=text,
                attachments=attachments,
                expected_output_format=raw_payload.get("expected_output_format"),
            ),
            constraints=TaskConstraints(
                offline_only=bool(raw_payload.get("offline_only", True)),
                work_mode=work_mode,
                allowed_paths=allowed_paths,
            ),
            metadata=dict(raw_payload.get("metadata") or {}),
        )

    def _resolve_route(self, envelope: TaskEnvelope, explicit_skill_id: str | None = None) -> RouteDecision:
        # 无论是否显式指定 skill_id，先经 HybridRouter 做 C00 有害意图预检
        decision = self.router.route(envelope, self.capability_profile)
        if not decision.constitution_audit.passed:
            return decision

        if explicit_skill_id:
            manifest = self.skills.get_manifest(explicit_skill_id)
            if manifest is None:
                raise KeyError(f"指定的技能不存在: {explicit_skill_id}")
            im = (
                InteractionMode.UPLIFT_MENTOR
                if manifest.verifiability == Verifiability.LOW_VERIFIABLE
                else InteractionMode.COPILOT_EXECUTE
            )
            return RouteDecision(
                task_id=envelope.task_id,
                verifiability=manifest.verifiability,
                channel=ExecutionChannel.L0_SKILL,
                interaction_mode=im,
                confidence=0.99,
                matched_skills=[f"{manifest.skill_id}@{manifest.version}"],
                primary_model_role="fast_router",
                rationale=f"用户显式指定执行创世/工作区技能 {manifest.skill_id}",
            )

        # 不断档上下文连续路由：若当前会话已绑定上一轮生成的应用代码文件(.html/.py)，且用户在追加修改，直通 L2-C CodeAct 增量演进！
        meta = envelope.metadata or {}
        if bool(meta.get("follow_context", True)) and not (envelope.input and envelope.input.attachments):
            ses = self.hub.get_active_session()
            pinned_art = str(ses.get("pinned_artifact_path") or "").lower()
            raw_txt = envelope.raw_input or ""
            if pinned_art.endswith((".html", ".py")) and any(
                kw in raw_txt for kw in ("继续", "加上", "增加", "再加", "修改", "改成", "优化", "完善", "补充", "调整", "修复")
            ):
                return RouteDecision(
                    task_id=envelope.task_id,
                    verifiability=Verifiability.HIGH_VERIFIABLE,
                    channel=ExecutionChannel.L2C_CODEACT,
                    interaction_mode=InteractionMode.COPILOT_EXECUTE,
                    sandbox_tier=SandboxTier.T2_OS_RESTRICTED,
                    confidence=0.95,
                    primary_model_role="coder_planner",
                    rationale="检测到当前连续会话已绑定代码产物且用户发起跟进修改，自动延续 L2-C 沙箱增量迭代",
                )
        return decision

    def _build_flow(self, envelope: TaskEnvelope, decision: RouteDecision) -> FlowPrimitive:
        meta = envelope.metadata or {}
        apply_changes = bool(meta.get("apply_changes", False))
        custom_action = str(meta.get("action", ""))
        requested_perm = str(meta.get("permission", "")).upper()

        # 1. L0 技能直通执行节点
        if decision.channel == ExecutionChannel.L0_SKILL and decision.matched_skills:
            skill_id = decision.matched_skills[0].split("@")[0]
            manifest = self.skills.get_manifest(skill_id)
            req_perms = {p.upper() for p in (manifest.required_permissions if manifest else [])}
            perm = "WRITE" if (apply_changes or "WRITE" in req_perms or requested_perm == "WRITE") else "READ"

            def _run_l0(ctx: FlowContext) -> dict[str, Any]:
                call_state = dict(ctx.state)
                if self._semantic_infer_fn is not None:
                    call_state["_semantic_infer_fn"] = self._semantic_infer_fn
                result = self.skills.execute_skill(skill_id, envelope, call_state)
                art_paths: list[str] = []
                if result.get("artifact_name") and result.get("artifact_content") is not None:
                    saved = ctx.save_artifact(
                        str(result["artifact_name"]),
                        result["artifact_content"],
                    )
                    art_paths.append(str(saved))
                return {
                    "summary": result.get("summary", ""),
                    "model_notes": result.get("model_notes", ""),
                    "diff_preview": result.get("diff_preview", ""),
                    "skill_id": skill_id,
                    "skill_output": {
                        k: v
                        for k, v in result.items()
                        if k not in {"artifact_content"}
                    },
                    "artifact_paths": art_paths,
                }

            return SequentialFlow(
                node_id=f"flow_l0_{skill_id}",
                steps=[
                    TaskNode(
                        node_id=f"skill_{skill_id}",
                        fn=_run_l0,
                        permission=perm,
                        action=custom_action,
                        target_path_key="target_path" if "target_path" in self._initial_paths(envelope) else None,
                        description=f"执行技能 {skill_id}",
                    )
                ],
            )

        # 2. L2-S 语义共生与启发共创通道
        if decision.channel == ExecutionChannel.L2S_SEMANTIC_COCREATE:
            perm = (
                requested_perm
                if requested_perm in {"READ", "WRITE", "DELETE", "EXECUTE"}
                else ("WRITE" if (apply_changes or meta.get("new_content") is not None) else "READ")
            )

            def _run_l2s(ctx: FlowContext) -> dict[str, Any]:
                follow_ctx = bool(meta.get("follow_context", True))
                ses_id = str(meta.get("session_id") or "") or None
                ctx_pack = self.hub.prepare_continuous_context(
                    envelope.raw_input or "",
                    session_id=ses_id,
                    follow_context=follow_ctx,
                )
                recalled = self.memory.recall(envelope.raw_input or "", top_k=3)
                mem_hint = ""
                if recalled:
                    mem_lines = "; ".join(r["content"] for r in recalled)
                    mem_hint = f"[本地记忆偏好]: {mem_lines}"
                parts = [p for p in (*ctx.steering_hints, mem_hint, ctx_pack["guardrail_block"]) if p]
                hint = "\n".join(parts) if parts else None
                out = self.semantic_worker.run(
                    StepInput(
                        run_id=ctx.run_id,
                        task_id=ctx.task_id,
                        goal=envelope.raw_input or "",
                        work_mode=envelope.constraints.work_mode,
                        interaction_mode=decision.interaction_mode,
                        context_messages=ctx_pack["context_messages"],
                        steering_hint=hint,
                    )
                )
                art_paths: list[str] = []
                if meta.get("target_path") and meta.get("new_content") is not None:
                    tp = pathlib.Path(str(meta["target_path"]))
                    tp.parent.mkdir(parents=True, exist_ok=True)
                    tp.write_text(str(meta["new_content"]), encoding="utf-8")
                    art_paths.append(str(tp))
                saved = ctx.save_artifact("semantic_notes.md", out.summary)
                art_paths.append(str(saved))
                notes = out.model_notes
                trace_tags = [f"🔗 会话第 {ctx_pack['turn_index']} 轮跟进"]
                if ctx_pack["matched_experiences"]:
                    trace_tags.append(f"🛡️ 挂载 {len(ctx_pack['matched_experiences'])} 条经验护栏")
                if recalled:
                    trace_tags.append(f"已结合 {len(recalled)} 条本地透明记忆")
                notes = f"{notes} | {' · '.join(trace_tags)}".strip(" |")
                return {
                    "summary": out.summary,
                    "model_notes": notes,
                    "artifact_paths": art_paths,
                }

            return SequentialFlow(
                node_id="flow_l2s_semantic",
                steps=[
                    TaskNode(
                        node_id="semantic_cocreate",
                        fn=_run_l2s,
                        permission=perm,
                        action=custom_action,
                        target_path_key="target_path" if meta.get("target_path") else None,
                    )
                ],
            )

        # 3. L1 / L2-C / L3 通道（柔性跨界协同：有本地表格/文档优先联动确定性引擎，或驱动 ReActWorker）
        perm = requested_perm if requested_perm in {"READ", "WRITE", "DELETE", "EXECUTE"} else (
            "WRITE" if (apply_changes or meta.get("new_content") is not None) else "READ"
        )

        def _run_structured(ctx: FlowContext) -> dict[str, Any]:
            attachments = list(envelope.input.attachments) if envelope.input else []
            if attachments:
                ext = pathlib.Path(attachments[0]).suffix.lower()
                if ext in {".csv", ".tsv"} and self.skills.get_manifest("genesis-table-analyst"):
                    res = self.skills.execute_skill("genesis-table-analyst", envelope, dict(ctx.state))
                    saved = ctx.save_artifact(res["artifact_name"], res["artifact_content"])
                    return {
                        "summary": res["summary"],
                        "model_notes": f"[跨通道协同 -> genesis-table-analyst] {res.get('model_notes', '')}",
                        "artifact_paths": [str(saved)],
                    }
                if ext in {".md", ".txt", ".json", ".html", ".docx", ".pdf"} and self.skills.get_manifest("genesis-doc-digest"):
                    res = self.skills.execute_skill("genesis-doc-digest", envelope, dict(ctx.state))
                    saved = ctx.save_artifact(res["artifact_name"], res["artifact_content"])
                    return {
                        "summary": res["summary"],
                        "model_notes": f"[跨通道协同 -> genesis-doc-digest] {res.get('model_notes', '')}",
                        "artifact_paths": [str(saved)],
                    }

            if (
                decision.channel == ExecutionChannel.L2C_CODEACT
                and self._codeact_infer_fn is not None
            ):
                if envelope.constraints.work_mode == WorkMode.ASK:
                    hint = "；".join(ctx.steering_hints) if ctx.steering_hints else None
                    out_ro = self.semantic_worker.run(
                        StepInput(
                            run_id=ctx.run_id,
                            task_id=ctx.task_id,
                            goal=envelope.raw_input or "",
                            work_mode=WorkMode.ASK,
                            interaction_mode=InteractionMode.COPILOT_EXECUTE,
                            steering_hint=hint,
                        )
                    )
                    saved_ro = ctx.save_artifact("code_blueprint.md", out_ro.summary)
                    return {
                        "summary": out_ro.summary,
                        "model_notes": (
                            "当前处于『Ask · 观照只读』模式，仅输出代码方案而不写入可执行应用文件；"
                            "若需让本地大模型直接在沙箱生成可点开的小程序/脚本，请切换顶部为『Execute · 金刚行持』模式！"
                        ),
                        "artifact_paths": [str(saved_ro)],
                    }

                tier = (
                    decision.sandbox_tier
                    if decision.sandbox_tier != SandboxTier.NONE
                    else SandboxTier.T2_OS_RESTRICTED
                )
                ws_dir = (
                    pathlib.Path(str(envelope.constraints.allowed_paths[0])).resolve()
                    if envelope.constraints.allowed_paths
                    else (self.store.artifacts_root / ctx.run_id / "sandbox_ws").resolve()
                )
                ws_dir.mkdir(parents=True, exist_ok=True)
                follow_ctx = bool(meta.get("follow_context", True))
                ses_id = str(meta.get("session_id") or "") or None
                ctx_pack = self.hub.prepare_continuous_context(
                    envelope.raw_input or "",
                    session_id=ses_id,
                    follow_context=follow_ctx,
                )
                ca_worker = CodeActWorker(
                    infer_fn=self._codeact_infer_fn,
                    sandbox=self.sandbox,
                    sandbox_tier=tier,
                    workspace_dir=ws_dir,
                    guard=self.guard,
                    constitution=self.constitution,
                    verifier_code=str(meta.get("verifier_code", "")).strip() or None,
                    timeout_sec=30.0,
                )
                steer_parts = [p for p in (*ctx.steering_hints, ctx_pack["guardrail_block"]) if p]
                hint = "\n".join(steer_parts) if steer_parts else None
                effective_goal = (
                    ctx_pack["augmented_goal"]
                    if ctx_pack["attached_prev_artifact"]
                    else (envelope.raw_input or "")
                )
                out = ca_worker.run(
                    StepInput(
                        run_id=ctx.run_id,
                        task_id=ctx.task_id,
                        goal=effective_goal,
                        work_mode=envelope.constraints.work_mode,
                        interaction_mode=decision.interaction_mode,
                        effective_ctx_budget=decision.capability_check.effective_ctx_budget,
                        context_messages=ctx_pack["context_messages"],
                        steering_hint=hint,
                    )
                )
                if not out.success:
                    raise RuntimeError(out.error or out.summary or "CodeAct 执行失败")
                registered_paths: list[str] = []
                for art_p in out.artifacts:
                    fp = pathlib.Path(art_p)
                    if fp.is_file():
                        saved_art = ctx.save_artifact(fp.name, fp.read_bytes())
                        registered_paths.append(str(saved_art))
                    else:
                        registered_paths.append(str(art_p))
                base_note = out.model_notes or f"已由本地模型 ({self.active_local_model or 'custom'}) 在 M08 安全沙箱内生成并验证通过。"
                trace_bits = [f"🔗 会话第 {ctx_pack['turn_index']} 轮不断档"]
                if ctx_pack["attached_prev_artifact"]:
                    trace_bits.append("📎 已继承上一版代码增量演进")
                if ctx_pack["matched_experiences"]:
                    trace_bits.append(f"🛡️ 已自动挂载 {len(ctx_pack['matched_experiences'])} 条经验防坑护栏")
                return {
                    "summary": out.summary,
                    "model_notes": f"{base_note} | {' · '.join(trace_bits)}",
                    "artifact_paths": registered_paths,
                }

            if self._react_infer_fn is not None:
                follow_ctx = bool(meta.get("follow_context", True))
                ses_id = str(meta.get("session_id") or "") or None
                ctx_pack = self.hub.prepare_continuous_context(
                    envelope.raw_input or "",
                    session_id=ses_id,
                    follow_context=follow_ctx,
                )
                worker = ReActWorker(
                    infer_fn=self._react_infer_fn,
                    guard=self.guard,
                    constitution=self.constitution,
                )
                steer_parts = [p for p in (*ctx.steering_hints, ctx_pack["guardrail_block"]) if p]
                hint = "\n".join(steer_parts) if steer_parts else None
                out = worker.run(
                    StepInput(
                        run_id=ctx.run_id,
                        task_id=ctx.task_id,
                        goal=envelope.raw_input or "",
                        work_mode=envelope.constraints.work_mode,
                        interaction_mode=decision.interaction_mode,
                        context_messages=ctx_pack["context_messages"],
                        steering_hint=hint,
                    )
                )
                return {"summary": out.summary, "model_notes": out.model_notes, "error": out.error}

            if meta.get("target_path") and meta.get("new_content") is not None:
                tp = pathlib.Path(str(meta["target_path"]))
                tp.parent.mkdir(parents=True, exist_ok=True)
                tp.write_text(str(meta["new_content"]), encoding="utf-8")
                return {
                    "summary": f"已在受控工作区完成文件写入：`{tp}`",
                    "model_notes": "已通过 M04 GovernanceGuard 路径与模式校验。",
                    "artifact_paths": [str(tp)],
                }

            hint_suffix = f"\n- **已吸纳中途改向**：{'；'.join(ctx.steering_hints)}" if ctx.steering_hints else ""
            summary = (
                f"### 结构化任务执行回执（通道：`{decision.channel.value}`）\n"
                f"- **任务目标**：{envelope.raw_input}\n"
                f"- **工作模式**：`{envelope.constraints.work_mode.value}`\n"
                f"- **路由依据**：{decision.rationale}{hint_suffix}"
            )
            saved = ctx.save_artifact("structured_execution_plan.md", summary)
            return {
                "summary": summary,
                "model_notes": "M08/M09 接入沙箱 CodeAct 后将自动升级为受控容器执行。",
                "artifact_paths": [str(saved)],
            }

        return SequentialFlow(
            node_id=f"flow_{decision.channel.value.lower()}",
            steps=[
                TaskNode(
                    node_id="structured_step",
                    fn=_run_structured,
                    permission=perm,
                    action=custom_action,
                    target_path_key="target_path" if self._initial_paths(envelope).get("target_path") else None,
                )
            ],
        )

    @staticmethod
    def _initial_paths(envelope: TaskEnvelope) -> dict[str, Any]:
        meta = envelope.metadata or {}
        extra: dict[str, Any] = {}
        if meta.get("target_path"):
            extra["target_path"] = str(meta["target_path"])
        elif envelope.input and envelope.input.attachments and meta.get("apply_changes"):
            extra["target_path"] = str(envelope.input.attachments[0])
        if "old_content" in meta and "new_content" in meta:
            extra["old_content"] = str(meta["old_content"])
            extra["new_content"] = str(meta["new_content"])
        return extra

    def stream_task(
        self,
        text: str,
        *,
        work_mode: WorkMode | str = WorkMode.ASK,
        source: str = "api",
        attachments: list[str] | None = None,
        allowed_paths: list[str] | None = None,
        skill_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """流式提交任务并实时推送事件（供 WebSocket 与流式终端消费）。"""
        envelope = self.accept(
            {
                "text": text,
                "work_mode": work_mode,
                "attachments": attachments or [],
                "allowed_paths": allowed_paths or [],
                "metadata": metadata or {},
            },
            source=source,
        )
        explicit = skill_id or (envelope.metadata.get("skill_id") if envelope.metadata else None)
        decision = self._resolve_route(envelope, explicit_skill_id=explicit)
        run_id = new_id("run")

        init_state: dict[str, Any] = {
            "_envelope": envelope.model_dump(mode="json"),
            "_route": decision.model_dump(mode="json"),
            "apply_changes": bool(envelope.metadata.get("apply_changes", False)),
            **self._initial_paths(envelope),
        }
        effective_allowed = list(envelope.constraints.allowed_paths)
        if str(self.workspace_dir) not in effective_allowed:
            effective_allowed.append(str(self.workspace_dir))
        init_state["allowed_paths"] = effective_allowed

        # 若触发 C00 宪章底线拦截或 A5 谦卑暂缓，直接落盘透明说明
        if decision.channel == ExecutionChannel.HONEST_DEFER:
            status = (
                "REJECTED_BY_CONSTITUTION"
                if not decision.constitution_audit.passed
                else "DEFERRED_HUMBLE"
            )
            init_state["summary"] = f"【透明边界说明】{decision.rationale}"
            init_state["model_notes"] = "依据 C00 众生和谐增上宪章守住底线，未执行潜在越界动作。"
            self.store.create_run(
                run_id=run_id,
                task_id=envelope.task_id,
                flow_name="honest_defer",
                initial_state=init_state,
            )
            self.store.save_checkpoint(
                run_id=run_id,
                node_id="constitution_gate",
                step_index=0,
                state=init_state,
                completed_nodes=[],
                status=status,
                error=decision.rationale if status == "REJECTED_BY_CONSTITUTION" else None,
            )
            yield self.store.append_event(
                run_id=run_id,
                task_id=envelope.task_id,
                event_type="route_decided",
                payload=decision.model_dump(mode="json"),
            )
            yield self.store.append_event(
                run_id=run_id,
                task_id=envelope.task_id,
                event_type="run_deferred",
                payload={"status": status, "rationale": decision.rationale},
            )
            return

        flow = self._build_flow(envelope, decision)
        first = True
        for ev in self.engine.stream_run(
            flow,
            task_id=envelope.task_id,
            initial_state=init_state,
            run_id=run_id,
            work_mode=envelope.constraints.work_mode,
        ):
            yield ev
            if first:
                first = False
                yield self.store.append_event(
                    run_id=run_id,
                    task_id=envelope.task_id,
                    event_type="route_decided",
                    payload=decision.model_dump(mode="json"),
                )

        # 任务完成后自动写入不断档上下文跟踪链
        rec_done = self.store.get_run(run_id)
        if rec_done and rec_done.get("status") == "COMPLETED":
            meta_in = envelope.metadata or {}
            ses_id = str(meta_in.get("session_id") or "") or None
            arts = self.store.list_artifacts(run_id)
            st_done = rec_done.get("state") or {}
            self.hub.record_turn_completion(
                session_id=ses_id,
                run_id=run_id,
                raw_goal=envelope.raw_input or "",
                summary=str(st_done.get("summary") or ""),
                artifacts=arts,
            )

    def submit_task(
        self,
        text: str,
        *,
        work_mode: WorkMode | str = WorkMode.ASK,
        source: str = "api",
        attachments: list[str] | None = None,
        allowed_paths: list[str] | None = None,
        skill_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        events = list(
            self.stream_task(
                text,
                work_mode=work_mode,
                source=source,
                attachments=attachments,
                allowed_paths=allowed_paths,
                skill_id=skill_id,
                metadata=metadata,
            )
        )
        run_id = events[0]["run_id"]
        return self.get_run(run_id)

    def steer_run(self, run_id: str, hint: str) -> dict[str, Any]:
        self.engine.steer(run_id, hint)
        rec = self.store.get_run(run_id)
        if rec is None:
            raise KeyError(f"运行不存在: {run_id}")
        self.store.append_event(
            run_id=run_id,
            task_id=rec["task_id"],
            event_type="steering_queued",
            payload={"hint": hint},
        )
        return self.get_run(run_id)

    def resume_run(
        self,
        run_id: str,
        *,
        approved: bool = True,
        work_mode: WorkMode | str = WorkMode.EXECUTE,
        approval_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rec = self.store.get_run(run_id)
        if rec is None:
            raise KeyError(f"运行不存在: {run_id}")
        state = rec["state"]
        envelope = TaskEnvelope.model_validate(state["_envelope"])
        decision = RouteDecision.model_validate(state["_route"])
        mode = work_mode if isinstance(work_mode, WorkMode) else WorkMode(str(work_mode).lower())
        envelope.constraints.work_mode = mode
        flow = self._build_flow(envelope, decision)

        self.engine.resume(
            flow,
            run_id,
            approved=approved,
            approval_payload=approval_payload,
            work_mode=mode,
        )
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        rec = self.store.get_run(run_id)
        if rec is None:
            raise KeyError(f"未找到运行记录: {run_id}")
        state = rec["state"]
        artifacts = self.store.list_artifacts(run_id)
        events = self.store.list_events(run_id)
        return {
            "run_id": rec["run_id"],
            "task_id": rec["task_id"],
            "flow_name": rec["flow_name"],
            "status": rec["status"],
            "step_count": rec["step_count"],
            "raw_input": (state.get("_envelope") or {}).get("raw_input", ""),
            "summary": state.get("summary", ""),
            "model_notes": state.get("model_notes", ""),
            "diff_preview": state.get("diff_preview")
            or ((rec.get("pending_interrupt") or {}).get("diff_preview", "")),
            "route_decision": state.get("_route"),
            "pending_interrupt": rec.get("pending_interrupt"),
            "error": rec.get("error"),
            "artifacts": artifacts,
            "events": events,
            "feedbacks": self.feedback.list_feedback_events(run_id=run_id),
            "spec": self.store.get_latest_spec(rec["task_id"]),
            "delivery": self.store.get_delivery(rec["task_id"]),
            "created_at": rec["created_at"],
            "updated_at": rec["updated_at"],
        }

    # --- M10 分层记忆与 1 秒 4 键反馈服务入口 ---
    def submit_feedback(
        self,
        run_id: str,
        *,
        kind: FeedbackKind | str,
        note: str = "",
        topic_key: str | None = None,
        scope: str = "default",
    ) -> dict[str, Any]:
        run_snap = self.get_run(run_id)
        ev = self.feedback.submit_feedback(
            run_id=run_id,
            kind=kind,
            note=note,
            topic_key=topic_key,
            scope=scope,
            run_snapshot=run_snap,
        )
        self.store.append_event(
            run_id=run_id,
            task_id=run_snap["task_id"],
            event_type=f"human_feedback_{ev.kind.value}",
            payload={
                "feedback_id": ev.feedback_id,
                "note": ev.note,
                "created_memory_id": ev.created_memory_id,
                "created_seed_id": ev.created_seed_id,
            },
        )
        # 用户每次点击『纠偏写入记忆』时，同步沉淀进经验防坑库，后续任务自动挂载防复发！
        if ev.kind == FeedbackKind.CORRECT and ev.note.strip():
            raw_goal = str(run_snap.get("raw_input") or "运行纠偏").strip()
            self.hub.add_experience(
                title=f"纠偏：{raw_goal[:18]}",
                pitfall=f"运行 {run_id} 中出现的偏差",
                rule=ev.note.strip(),
                category="用户纠偏",
                auto_inject=True,
                sync_to_memory=False,
            )
        return ev.model_dump(mode="json")

    def recall_memories(
        self,
        query: str = "",
        *,
        scope: str = "default",
        top_k: int = 10,
        include_history: bool = False,
    ) -> list[dict[str, Any]]:
        if not query.strip():
            return self.memory.list_memories(
                scope=scope,
                include_inactive=include_history,
                limit=top_k,
            )
        return self.memory.recall(
            query,
            scope=scope,
            top_k=top_k,
            include_history=include_history,
        )

    def add_memory(
        self,
        content: str,
        *,
        layer: str = "core",
        topic_key: str | None = None,
        tags: list[str] | None = None,
        scope: str = "default",
    ) -> dict[str, Any]:
        mem_id = self.memory.commit(
            {
                "content": content,
                "layer": layer,
                "topic_key": topic_key,
                "tags": tags or [],
                "source": "human_edit",
            },
            scope=scope,
        )
        items = [m for m in self.memory.list_memories(scope=scope, include_inactive=True) if m["memory_id"] == mem_id]
        return items[0] if items else {"memory_id": mem_id}

    def edit_memory(
        self,
        memory_id: str,
        *,
        content: str,
        topic_key: str | None = None,
    ) -> dict[str, Any]:
        return self.memory.update_memory(memory_id, content=content, topic_key=topic_key)

    def forget_memory(self, memory_id: str) -> dict[str, Any]:
        return self.memory.forget(memory_id)

    def sync_memories_from_markdown(self) -> dict[str, int]:
        return self.memory.sync_from_markdown()

    def list_skill_seeds(self) -> list[dict[str, Any]]:
        return [s.model_dump(mode="json") for s in self.feedback.list_skill_seeds()]

    # --- M11 双闸门防坍塌自演化与普惠导出服务入口 ---
    def _refresh_router(self) -> None:
        self.skills.reload()
        self.router = HybridRouter(skills=self.skills.list_manifests(active_only=True))

    def list_evolution_drafts(self) -> list[dict[str, Any]]:
        return [d.model_dump(mode="json") for d in self.evolution.list_drafts()]

    def evolve_from_seed(
        self,
        seed_id: str,
        *,
        skill_id_override: str | None = None,
        auto_verify: bool = True,
    ) -> dict[str, Any]:
        seed_map = {s.seed_id: s for s in self.feedback.list_skill_seeds()}
        seed = seed_map.get(seed_id)
        if seed is None:
            raise KeyError(f"未找到技能种子: {seed_id}")
        draft = self.evolution.draft_from_seed(seed, skill_id_override=skill_id_override)
        if auto_verify:
            draft = self.evolution.verify_draft(draft.draft_id)
        return draft.model_dump(mode="json")

    def review_evolution_draft(
        self,
        draft_id: str,
        *,
        approved: bool = True,
        reviewer: str = "human",
        review_note: str = "",
    ) -> dict[str, Any]:
        draft = self.evolution.activate_draft(
            draft_id,
            approved=approved,
            reviewer=reviewer,
            review_note=review_note,
        )
        if approved:
            self._refresh_router()
        return draft.model_dump(mode="json")

    def rollback_skill(self, skill_id: str) -> dict[str, Any]:
        res = self.evolution.rollback_skill(skill_id)
        self._refresh_router()
        return res

    def export_portable_skill(
        self,
        skill_id: str,
        output_zip: pathlib.Path | str,
    ) -> dict[str, Any]:
        card = self.evolution.export_skill(skill_id, output_zip)
        return {
            "zip_path": str(pathlib.Path(output_zip).resolve()),
            "card": card.model_dump(mode="json"),
        }

    def import_portable_skill(
        self,
        zip_path: pathlib.Path | str,
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        info = self.evolution.import_skill(zip_path, overwrite=overwrite)
        self._refresh_router()
        return info

    # --- 本机 Ollama 模型热发现与切换 ---
    def list_local_models(self) -> dict[str, Any]:
        if self._auto_ollama_enabled:
            fresh = list_ollama_models()
            if fresh:
                self.available_local_models = fresh
                if not self.active_local_model:
                    self.active_local_model = pick_best_local_model(fresh)
                    ollama_fn = make_ollama_infer_fn(lambda: self.active_local_model)
                    self._semantic_infer_fn = ollama_fn
                    self._react_infer_fn = ollama_fn
                    self._codeact_infer_fn = ollama_fn
                    self.semantic_worker = SemanticCoCreatorWorker(
                        infer_fn=ollama_fn,
                        constitution=self.constitution,
                    )
        return {
            "active_model": self.active_local_model,
            "models": self.available_local_models,
        }

    def select_local_model(self, model_name: str) -> dict[str, Any]:
        info = self.list_local_models()
        names = {m["name"] for m in info["models"]}
        if model_name not in names:
            raise ValueError(f"未在本机 Ollama 中找到模型: {model_name}")
        self.active_local_model = model_name
        ollama_fn = make_ollama_infer_fn(lambda: self.active_local_model)
        self._semantic_infer_fn = ollama_fn
        self._react_infer_fn = ollama_fn
        self._codeact_infer_fn = ollama_fn
        self.semantic_worker = SemanticCoCreatorWorker(
            infer_fn=ollama_fn,
            constitution=self.constitution,
        )
        return {"active_model": self.active_local_model, "models": self.available_local_models}

    # --- PRD v3.0 铸泽 SFDP（先规格设计 -> 后沙箱构建与五件套交付）服务入口 ---
    def sfdp_clarify_and_draft(self, goal: str) -> dict[str, Any]:
        return self.sfdp.generate_clarify_questions(goal)

    def sfdp_update_spec(
        self,
        task_id: str,
        *,
        goal: str,
        qa_items: list[dict[str, str]] | None = None,
        spec_md: str | None = None,
        plan_md: str | None = None,
    ) -> dict[str, Any]:
        return self.sfdp.build_spec_workshop(
            task_id,
            goal,
            qa_items=qa_items,
            custom_spec_md=spec_md,
            custom_plan_md=plan_md,
            freeze=False,
        )

    def sfdp_build_from_spec(
        self,
        task_id: str,
        *,
        goal: str,
        qa_items: list[dict[str, str]] | None = None,
        spec_md: str | None = None,
        plan_md: str | None = None,
        session_id: str | None = None,
        follow_context: bool = True,
    ) -> dict[str, Any]:
        if qa_items is not None or spec_md is not None or plan_md is not None:
            self.sfdp.build_spec_workshop(
                task_id,
                goal,
                qa_items=qa_items,
                custom_spec_md=spec_md,
                custom_plan_md=plan_md,
                freeze=True,
            )
        ctx_pack = self.hub.prepare_continuous_context(
            goal,
            session_id=session_id,
            follow_context=follow_context,
        )
        extra_guard = ctx_pack["guardrail_block"]
        if ctx_pack["attached_prev_artifact"]:
            extra_guard = f"{ctx_pack['augmented_goal']}\n\n{extra_guard}".strip()
        out = self.sfdp.build_and_converge(
            task_id,
            goal=goal,
            infer_fn=self._codeact_infer_fn,
            context_messages=ctx_pack["context_messages"],
            extra_guardrails=extra_guard,
        )
        run_data = self.get_run(out["run_id"])
        self.hub.record_turn_completion(
            session_id=session_id,
            run_id=out["run_id"],
            raw_goal=goal,
            summary=str(run_data.get("summary") or ""),
            artifacts=run_data.get("artifacts") or [],
            spec_id=(run_data.get("spec") or {}).get("id"),
        )
        return run_data

    # --- 三大持久中枢（Skill 规划管理库 · 经验防坑库 · 不断档上下文跟踪）服务入口 ---
    def get_hub_overview(self) -> dict[str, Any]:
        return {
            "skill_hub": self.hub.get_skill_hub_overview(),
            "experiences": self.hub.list_experiences(),
            "experience_markdown_path": str(self.hub.experience_md_path),
            "context": self.hub.list_sessions(),
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
        return self.hub.add_skill_plan(
            title=title,
            goal=goal,
            category=category,
            priority=priority,
            triggers=triggers,
        )

    def incubate_skill_plan(self, plan_id: str, *, auto_activate: bool = True) -> dict[str, Any]:
        res = self.hub.incubate_skill_plan(plan_id, auto_activate=auto_activate)
        if auto_activate and res["draft"].get("status") == "ACTIVE":
            self._refresh_router()
        return res

    def delete_skill_plan(self, plan_id: str) -> dict[str, Any]:
        return self.hub.delete_skill_plan(plan_id)

    def add_experience_rule(
        self,
        *,
        title: str,
        pitfall: str,
        rule: str,
        category: str = "研发防坑",
        auto_inject: bool = True,
    ) -> dict[str, Any]:
        return self.hub.add_experience(
            title=title,
            pitfall=pitfall,
            rule=rule,
            category=category,
            auto_inject=auto_inject,
        )

    def toggle_experience_rule(self, exp_id: str, auto_inject: bool) -> dict[str, Any]:
        return self.hub.toggle_experience(exp_id, auto_inject)

    def delete_experience_rule(self, exp_id: str) -> dict[str, Any]:
        return self.hub.delete_experience(exp_id)

    def create_context_session(self, title: str = "新项目连续会话") -> dict[str, Any]:
        return self.hub.create_session(title)

    def switch_context_session(self, session_id: str) -> dict[str, Any]:
        return self.hub.switch_session(session_id)

    def list_recent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.store.list_runs(limit=limit)
