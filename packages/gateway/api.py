"""M07 B01 本地离线 FastAPI + WebSocket 统一网关（默认严格绑定 127.0.0.1）."""

from __future__ import annotations

import pathlib
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from packages.core.contracts import WorkMode
from packages.gateway.service import HuiQiaoService


class TaskSubmitRequest(BaseModel):
    text: str = Field(..., min_length=1)
    work_mode: WorkMode = Field(default=WorkMode.ASK)
    attachments: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    skill_id: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SteerRequest(BaseModel):
    hint: str = Field(..., min_length=1)


class ResumeRequest(BaseModel):
    approved: bool = Field(default=True)
    work_mode: WorkMode = Field(default=WorkMode.EXECUTE)
    approval_payload: dict[str, Any] = Field(default_factory=dict)


class FeedbackSubmitRequest(BaseModel):
    kind: str = Field(..., min_length=1, description="praise | dislike | correct | save_skill_seed")
    note: str = Field(default="")
    topic_key: str | None = Field(default=None)
    scope: str = Field(default="default")


class MemoryCreateRequest(BaseModel):
    content: str = Field(..., min_length=1)
    layer: str = Field(default="core")
    topic_key: str | None = Field(default=None)
    tags: list[str] = Field(default_factory=list)
    scope: str = Field(default="default")


class MemoryUpdateRequest(BaseModel):
    content: str = Field(..., min_length=1)
    topic_key: str | None = Field(default=None)


class EvolveSeedRequest(BaseModel):
    skill_id_override: str | None = Field(default=None)
    auto_verify: bool = Field(default=True)


class ReviewDraftRequest(BaseModel):
    approved: bool = Field(default=True)
    reviewer: str = Field(default="human")
    review_note: str = Field(default="")


class ExportSkillRequest(BaseModel):
    output_zip: str = Field(..., min_length=1)


class SelectModelRequest(BaseModel):
    model: str = Field(..., min_length=1)


class SfdpClarifyRequest(BaseModel):
    goal: str = Field(..., min_length=1)


class SfdpSpecBuildRequest(BaseModel):
    task_id: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    qa_items: list[dict[str, str]] | None = Field(default=None)
    spec_md: str | None = Field(default=None)
    plan_md: str | None = Field(default=None)
    session_id: str | None = Field(default=None)
    follow_context: bool = Field(default=True)


class SkillPlanCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    category: str = Field(default="自定义规划")
    priority: str = Field(default="P1")
    triggers: list[str] = Field(default_factory=list)


class IncubatePlanRequest(BaseModel):
    auto_activate: bool = Field(default=True)


class ExperienceCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    pitfall: str = Field(default="")
    rule: str = Field(..., min_length=1)
    category: str = Field(default="研发防坑")
    auto_inject: bool = Field(default=True)


class ExperienceToggleRequest(BaseModel):
    auto_inject: bool = Field(default=True)


class SessionCreateRequest(BaseModel):
    title: str = Field(default="新项目连续会话")


class CoachAnalyzeRequest(BaseModel):
    text: str = Field(default="")
    work_mode: str = Field(default="ask")
    session_id: str | None = Field(default=None)
    follow_context: bool = Field(default=True)
    use_ai: bool = Field(default=False)


def create_app(
    service: HuiQiaoService | None = None,
    *,
    webui_html_path: pathlib.Path | str | None = None,
) -> FastAPI:
    svc = service or HuiQiaoService()
    html_file = (
        pathlib.Path(webui_html_path)
        if webui_html_path is not None
        else svc.repo_root / "apps" / "webui" / "index.html"
    )

    app = FastAPI(
        title="汇桥 OS (HuiQiao OS) 本地共生智能网关",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.huiqiao = svc

    @app.get("/", response_class=HTMLResponse)
    def serve_webui() -> HTMLResponse:
        if html_file.exists():
            return HTMLResponse(html_file.read_text(encoding="utf-8"))
        return HTMLResponse("<h1>汇桥 OS 本地网关已启动</h1><p>未找到 apps/webui/index.html</p>")

    @app.get("/health")
    @app.get("/api/health")
    def get_health() -> dict[str, Any]:
        return svc.healthcheck()

    @app.get("/skills")
    @app.get("/api/skills")
    def list_skills() -> dict[str, Any]:
        items = [m.model_dump(mode="json") for m in svc.list_skills()]
        return {"count": len(items), "skills": items}

    @app.get("/skills/{skill_id}")
    @app.get("/api/skills/{skill_id}")
    def get_skill(skill_id: str) -> dict[str, Any]:
        try:
            return svc.get_skill_detail(skill_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/tasks")
    @app.post("/api/tasks")
    def submit_task(req: TaskSubmitRequest) -> dict[str, Any]:
        try:
            return svc.submit_task(
                req.text,
                work_mode=req.work_mode,
                source="webui",
                attachments=req.attachments,
                allowed_paths=req.allowed_paths,
                skill_id=req.skill_id,
                metadata=req.metadata,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/runs")
    @app.get("/api/runs")
    def list_runs(limit: int = 20) -> dict[str, Any]:
        runs = svc.list_recent_runs(limit=limit)
        return {"count": len(runs), "runs": runs}

    @app.get("/runs/{run_id}")
    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        try:
            return svc.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/runs/{run_id}/steer")
    @app.post("/api/runs/{run_id}/steer")
    def steer_run(run_id: str, req: SteerRequest) -> dict[str, Any]:
        try:
            return svc.steer_run(run_id, req.hint)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/runs/{run_id}/resume")
    @app.post("/api/runs/{run_id}/resume")
    def resume_run(run_id: str, req: ResumeRequest) -> dict[str, Any]:
        try:
            return svc.resume_run(
                run_id,
                approved=req.approved,
                work_mode=req.work_mode,
                approval_payload=req.approval_payload,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/runs/{run_id}/feedback")
    @app.post("/api/runs/{run_id}/feedback")
    def submit_feedback(run_id: str, req: FeedbackSubmitRequest) -> dict[str, Any]:
        try:
            return svc.submit_feedback(
                run_id,
                kind=req.kind,
                note=req.note,
                topic_key=req.topic_key,
                scope=req.scope,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/memory")
    @app.get("/api/memory")
    def query_memory(
        q: str = "",
        scope: str = "default",
        top_k: int = 20,
        include_history: bool = False,
    ) -> dict[str, Any]:
        items = svc.recall_memories(
            q,
            scope=scope,
            top_k=top_k,
            include_history=include_history,
        )
        return {
            "count": len(items),
            "memory_md_path": str(svc.memory.memory_md_path),
            "memories": items,
        }

    @app.post("/memory")
    @app.post("/api/memory")
    def create_memory(req: MemoryCreateRequest) -> dict[str, Any]:
        try:
            return svc.add_memory(
                req.content,
                layer=req.layer,
                topic_key=req.topic_key,
                tags=req.tags,
                scope=req.scope,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/memory/{memory_id}")
    @app.put("/api/memory/{memory_id}")
    def update_memory(memory_id: str, req: MemoryUpdateRequest) -> dict[str, Any]:
        try:
            return svc.edit_memory(memory_id, content=req.content, topic_key=req.topic_key)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/memory/{memory_id}")
    @app.delete("/api/memory/{memory_id}")
    def delete_memory(memory_id: str) -> dict[str, Any]:
        try:
            return svc.forget_memory(memory_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/memory/sync")
    @app.post("/api/memory/sync")
    def sync_memory_markdown() -> dict[str, Any]:
        return svc.sync_memories_from_markdown()

    @app.get("/skill-seeds")
    @app.get("/api/skill-seeds")
    def get_skill_seeds() -> dict[str, Any]:
        seeds = svc.list_skill_seeds()
        return {"count": len(seeds), "seeds": seeds}

    @app.get("/evolution/drafts")
    @app.get("/api/evolution/drafts")
    def list_evolution_drafts() -> dict[str, Any]:
        drafts = svc.list_evolution_drafts()
        return {"count": len(drafts), "drafts": drafts}

    @app.post("/evolution/seeds/{seed_id}/evolve")
    @app.post("/api/evolution/seeds/{seed_id}/evolve")
    def evolve_from_seed(seed_id: str, req: EvolveSeedRequest | None = None) -> dict[str, Any]:
        body = req or EvolveSeedRequest()
        try:
            return svc.evolve_from_seed(
                seed_id,
                skill_id_override=body.skill_id_override,
                auto_verify=body.auto_verify,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/evolution/drafts/{draft_id}/review")
    @app.post("/api/evolution/drafts/{draft_id}/review")
    def review_evolution_draft(draft_id: str, req: ReviewDraftRequest) -> dict[str, Any]:
        try:
            return svc.review_evolution_draft(
                draft_id,
                approved=req.approved,
                reviewer=req.reviewer,
                review_note=req.review_note,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    @app.post("/skills/{skill_id}/rollback")
    @app.post("/api/skills/{skill_id}/rollback")
    def rollback_skill(skill_id: str) -> dict[str, Any]:
        try:
            return svc.rollback_skill(skill_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/skills/{skill_id}/export")
    @app.post("/api/skills/{skill_id}/export")
    def export_skill(skill_id: str, req: ExportSkillRequest) -> dict[str, Any]:
        try:
            return svc.export_portable_skill(skill_id, req.output_zip)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/models")
    @app.get("/api/models")
    def get_local_models() -> dict[str, Any]:
        return svc.list_local_models()

    @app.post("/models/select")
    @app.post("/api/models/select")
    def select_local_model(req: SelectModelRequest) -> dict[str, Any]:
        try:
            return svc.select_local_model(req.model)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/preview/coach/{report_name}")
    def preview_coach_report(report_name: str) -> FileResponse:
        safe_name = pathlib.Path(report_name).name
        if not safe_name.endswith(".html") or safe_name != report_name:
            raise HTTPException(status_code=400, detail="非法报告文件名")
        fp = (svc.coach_reports_dir / safe_name).resolve()
        if not fp.is_file() or svc.coach_reports_dir not in fp.parents:
            raise HTTPException(status_code=404, detail="未找到教练对比报告")
        return FileResponse(fp)

    @app.get("/preview/{run_id}/{artifact_name}")
    def preview_run_artifact(run_id: str, artifact_name: str) -> FileResponse:
        """在浏览器中安全预览指定运行生成的本地小程序或产物文件（防路径穿越）。"""
        try:
            run_data = svc.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        for art in run_data.get("artifacts") or []:
            if art.get("name") == artifact_name:
                fp = pathlib.Path(str(art.get("file_path", ""))).resolve()
                if fp.is_file():
                    return FileResponse(fp)
        raise HTTPException(status_code=404, detail=f"未找到产物: {artifact_name}")

    @app.post("/sfdp/clarify")
    @app.post("/api/sfdp/clarify")
    def sfdp_clarify(req: SfdpClarifyRequest) -> dict[str, Any]:
        return svc.sfdp_clarify_and_draft(req.goal)

    @app.post("/sfdp/spec")
    @app.post("/api/sfdp/spec")
    def sfdp_update_spec(req: SfdpSpecBuildRequest) -> dict[str, Any]:
        try:
            return svc.sfdp_update_spec(
                req.task_id,
                goal=req.goal,
                qa_items=req.qa_items,
                spec_md=req.spec_md,
                plan_md=req.plan_md,
            )
        except (ValueError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/sfdp/build")
    @app.post("/api/sfdp/build")
    def sfdp_build(req: SfdpSpecBuildRequest) -> dict[str, Any]:
        try:
            return svc.sfdp_build_from_spec(
                req.task_id,
                goal=req.goal,
                qa_items=req.qa_items,
                spec_md=req.spec_md,
                plan_md=req.plan_md,
                session_id=req.session_id,
                follow_context=req.follow_context,
            )
        except (ValueError, PermissionError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # --- 三大持久中枢（Skill 规划管理库 · 经验防坑库 · 不断档上下文跟踪）REST API ---
    @app.get("/hub/overview")
    @app.get("/api/hub/overview")
    def get_hub_overview() -> dict[str, Any]:
        return svc.get_hub_overview()

    @app.post("/hub/skills/plan")
    @app.post("/api/hub/skills/plan")
    def create_skill_plan(req: SkillPlanCreateRequest) -> dict[str, Any]:
        return svc.add_skill_plan(
            title=req.title,
            goal=req.goal,
            category=req.category,
            priority=req.priority,
            triggers=req.triggers,
        )

    @app.post("/hub/skills/plan/{plan_id}/incubate")
    @app.post("/api/hub/skills/plan/{plan_id}/incubate")
    def incubate_skill_plan(plan_id: str, req: IncubatePlanRequest | None = None) -> dict[str, Any]:
        body = req or IncubatePlanRequest()
        try:
            return svc.incubate_skill_plan(plan_id, auto_activate=body.auto_activate)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/hub/skills/plan/{plan_id}")
    @app.delete("/api/hub/skills/plan/{plan_id}")
    def remove_skill_plan(plan_id: str) -> dict[str, Any]:
        try:
            return svc.delete_skill_plan(plan_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/hub/experiences")
    @app.post("/api/hub/experiences")
    def create_experience(req: ExperienceCreateRequest) -> dict[str, Any]:
        return svc.add_experience_rule(
            title=req.title,
            pitfall=req.pitfall,
            rule=req.rule,
            category=req.category,
            auto_inject=req.auto_inject,
        )

    @app.post("/hub/experiences/{exp_id}/toggle")
    @app.post("/api/hub/experiences/{exp_id}/toggle")
    def toggle_experience(exp_id: str, req: ExperienceToggleRequest) -> dict[str, Any]:
        try:
            return svc.toggle_experience_rule(exp_id, req.auto_inject)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.delete("/hub/experiences/{exp_id}")
    @app.delete("/api/hub/experiences/{exp_id}")
    def remove_experience(exp_id: str) -> dict[str, Any]:
        try:
            return svc.delete_experience_rule(exp_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/hub/sessions")
    @app.post("/api/hub/sessions")
    def create_session(req: SessionCreateRequest | None = None) -> dict[str, Any]:
        body = req or SessionCreateRequest()
        return svc.create_context_session(body.title)

    @app.post("/hub/sessions/{session_id}/switch")
    @app.post("/api/hub/sessions/{session_id}/switch")
    def switch_session(session_id: str) -> dict[str, Any]:
        try:
            return svc.switch_context_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # --- 汇桥七律架构教练 REST API（自动诊测对比 + 一键分享独立报告页） ---
    @app.post("/coach/analyze")
    @app.post("/api/coach/analyze")
    def coach_analyze(req: CoachAnalyzeRequest) -> dict[str, Any]:
        return svc.analyze_with_coach(
            req.text,
            work_mode=req.work_mode,
            session_id=req.session_id,
            follow_context=req.follow_context,
            use_ai=req.use_ai,
        )

    @app.post("/coach/share")
    @app.post("/api/coach/share")
    def coach_share(req: CoachAnalyzeRequest) -> dict[str, Any]:
        return svc.share_coach_report(
            req.text,
            work_mode=req.work_mode,
            session_id=req.session_id,
            follow_context=req.follow_context,
            use_ai=req.use_ai,
        )

    @app.websocket("/ws/tasks")
    async def ws_stream_tasks(ws: WebSocket) -> None:
        await ws.accept()
        try:
            while True:
                payload = await ws.receive_json()
                req = TaskSubmitRequest.model_validate(payload)
                last_run_id: str | None = None
                for event in svc.stream_task(
                    req.text,
                    work_mode=req.work_mode,
                    source="websocket",
                    attachments=req.attachments,
                    allowed_paths=req.allowed_paths,
                    skill_id=req.skill_id,
                    metadata=req.metadata,
                ):
                    last_run_id = event["run_id"]
                    await ws.send_json({"type": "event", "data": event})
                if last_run_id:
                    await ws.send_json({"type": "final", "data": svc.get_run(last_run_id)})
        except WebSocketDisconnect:
            return

    return app
