"""M07 B01 本地离线 FastAPI + WebSocket 统一网关（默认严格绑定 127.0.0.1）."""

from __future__ import annotations

import pathlib
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
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
        version="0.1.0-alpha",
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
