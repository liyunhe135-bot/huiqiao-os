"""M07 汇桥 OS 本地命令行入口（Typer CLI：status / skills / ask / plan / run / runs / inspect / steer / resume / serve）."""

from __future__ import annotations

import json
import pathlib
from typing import Optional

import typer

from packages.core.contracts import WorkMode
from packages.gateway.service import HuiQiaoService

app = typer.Typer(
    name="huiqiao",
    help="汇桥 OS (HuiQiao OS) — 100% 本地离线乐高式共生智能终端",
    add_completion=False,
)

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _make_service(db_path: Optional[str] = None) -> HuiQiaoService:
    return HuiQiaoService(db_path=pathlib.Path(db_path) if db_path else None)


def _print_run_result(res: dict) -> None:
    route = res.get("route_decision") or {}
    typer.echo(
        f"[汇桥] run_id={res['run_id']} | status={res['status']} | "
        f"channel={route.get('channel', 'N/A')} | mode={route.get('interaction_mode', 'N/A')}"
    )
    if res.get("summary"):
        typer.echo("-" * 60)
        typer.echo(res["summary"])
    if res.get("pending_interrupt"):
        intr = res["pending_interrupt"]
        typer.echo("-" * 60)
        typer.echo(f"[等待人工确认 HITL] 原因: {intr.get('reason')}")
        if intr.get("diff_preview"):
            typer.echo(intr["diff_preview"])
    if res.get("error") and res["status"] != "PAUSED_FOR_HUMAN":
        typer.echo(f"[错误/拦截] {res['error']}")
    if res.get("artifacts"):
        paths = ", ".join(a["file_path"] for a in res["artifacts"])
        typer.echo(f"[落盘产物] {paths}")
    if res.get("model_notes"):
        typer.echo(f"[透明附注] {res['model_notes']}")


@app.command("status")
def cmd_status(
    db: Optional[str] = typer.Option(None, "--db", help="可选自定义状态库路径"),
    as_json: bool = typer.Option(False, "--json", help="输出原始 JSON"),
) -> None:
    """查看 C00 宪章指纹、积木健康状态与已激活创世技能数。"""
    svc = _make_service(db)
    info = svc.healthcheck()
    if as_json:
        typer.echo(json.dumps(info, ensure_ascii=False, indent=2))
        return
    typer.echo(
        f"汇桥 OS {info['version']} | 健康={'OK' if info['ok'] else 'DEGRADED'} | "
        f"离线模式={'开启' if info['offline_only'] else '关闭'} | "
        f"C00宪章={info['constitution_version']} ({info['constitution_sha256']}) | "
        f"活跃技能={info['active_skills_count']}"
    )
    for k, v in info["checks"].items():
        typer.echo(f"  - {k}: {'PASS' if v else 'FAIL'}")


@app.command("skills")
def cmd_skills(
    db: Optional[str] = typer.Option(None, "--db", help="可选自定义状态库路径"),
) -> None:
    """列出本地工作区已安装的创世与自定义技能。"""
    svc = _make_service(db)
    manifests = svc.list_skills()
    typer.echo(f"共发现 {len(manifests)} 个技能包：")
    for m in manifests:
        typer.echo(
            f"  - {m.skill_id} ({m.name}) [{m.status.value} | {m.verifiability.value}]: {m.description}"
        )


@app.command("ask")
def cmd_ask(
    text: str = typer.Argument(..., help="问题或只读分析需求"),
    attach: Optional[list[str]] = typer.Option(None, "--attach", "-a", help="附带本地文件或目录路径"),
    skill: Optional[str] = typer.Option(None, "--skill", "-s", help="显式指定技能 ID"),
    db: Optional[str] = typer.Option(None, "--db", help="可选自定义状态库路径"),
) -> None:
    """以 Ask 只读安全模式运行（内核物理禁写任何本地业务文件）。"""
    svc = _make_service(db)
    res = svc.submit_task(
        text,
        work_mode=WorkMode.ASK,
        source="cli",
        attachments=attach or [],
        skill_id=skill,
    )
    _print_run_result(res)


@app.command("plan")
def cmd_plan(
    text: str = typer.Argument(..., help="需要规划或预审变更的任务目标"),
    attach: Optional[list[str]] = typer.Option(None, "--attach", "-a", help="附带本地文件或目录路径"),
    skill: Optional[str] = typer.Option(None, "--skill", "-s", help="显式指定技能 ID"),
    apply_changes: bool = typer.Option(False, "--apply", help="请求在确认后应用写入变更"),
    db: Optional[str] = typer.Option(None, "--db", help="可选自定义状态库路径"),
) -> None:
    """以 Plan 方案预审模式运行（涉及写操作必先挂起并展示 Unified Diff）。"""
    svc = _make_service(db)
    res = svc.submit_task(
        text,
        work_mode=WorkMode.PLAN,
        source="cli",
        attachments=attach or [],
        skill_id=skill,
        metadata={"apply_changes": apply_changes},
    )
    _print_run_result(res)


@app.command("run")
def cmd_run(
    text: str = typer.Argument(..., help="授权在受控工作区内执行的任务"),
    attach: Optional[list[str]] = typer.Option(None, "--attach", "-a", help="附带本地文件或目录路径"),
    allow: Optional[list[str]] = typer.Option(None, "--allow", help="额外授权可写目录白名单"),
    skill: Optional[str] = typer.Option(None, "--skill", "-s", help="显式指定技能 ID"),
    apply_changes: bool = typer.Option(False, "--apply", help="对目录分类等技能实际应用移动"),
    db: Optional[str] = typer.Option(None, "--db", help="可选自定义状态库路径"),
) -> None:
    """以 Execute 受控执行模式运行（敏感路径与高危动作仍受 M04 闸门保护）。"""
    svc = _make_service(db)
    res = svc.submit_task(
        text,
        work_mode=WorkMode.EXECUTE,
        source="cli",
        attachments=attach or [],
        allowed_paths=allow or [],
        skill_id=skill,
        metadata={"apply_changes": apply_changes},
    )
    _print_run_result(res)


@app.command("runs")
def cmd_runs(
    limit: int = typer.Option(10, "--limit", "-n", help="显示最近 N 条运行记录"),
    db: Optional[str] = typer.Option(None, "--db", help="可选自定义状态库路径"),
) -> None:
    """查看最近持久化在 SQLite WAL 中的运行历史。"""
    svc = _make_service(db)
    items = svc.list_recent_runs(limit=limit)
    if not items:
        typer.echo("暂无运行记录。")
        return
    for r in items:
        typer.echo(
            f"  - {r['run_id']} | {r['status']} | flow={r['flow_name']} | steps={r['step_count']} | {r['updated_at']}"
        )


@app.command("inspect")
def cmd_inspect(
    run_id: str = typer.Argument(..., help="要查看的 run_id"),
    db: Optional[str] = typer.Option(None, "--db", help="可选自定义状态库路径"),
) -> None:
    """查看单次运行的完整状态、事件账本与保留产物。"""
    svc = _make_service(db)
    res = svc.get_run(run_id)
    _print_run_result(res)
    typer.echo(f"[事件轨迹] 共 {len(res['events'])} 条:")
    for ev in res["events"]:
        typer.echo(f"  * {ev['event_type']} ({ev.get('node_id') or '-'})")


@app.command("steer")
def cmd_steer(
    run_id: str = typer.Argument(..., help="目标 run_id"),
    hint: str = typer.Argument(..., help="中途改向补充指令"),
    db: Optional[str] = typer.Option(None, "--db", help="可选自定义状态库路径"),
) -> None:
    """向指定运行注入中途改向指令（下一执行步立即生效）。"""
    svc = _make_service(db)
    res = svc.steer_run(run_id, hint)
    typer.echo(f"已向 {res['run_id']} 注入改向指令：{hint}")


@app.command("resume")
def cmd_resume(
    run_id: str = typer.Argument(..., help="挂起待确认的 run_id"),
    approve: bool = typer.Option(True, "--approve/--reject", help="批准继续或驳回取消"),
    db: Optional[str] = typer.Option(None, "--db", help="可选自定义状态库路径"),
) -> None:
    """批准或驳回处于 PAUSED_FOR_HUMAN 状态的人工确认运行。"""
    svc = _make_service(db)
    res = svc.resume_run(run_id, approved=approve, work_mode=WorkMode.EXECUTE)
    _print_run_result(res)


@app.command("feedback")
def cmd_feedback(
    run_id: str = typer.Argument(..., help="目标 run_id"),
    kind: str = typer.Argument(..., help="praise | dislike | correct | save_skill_seed"),
    note: str = typer.Option("", "--note", "-n", help="1秒补充纠偏或技能种子标题"),
    topic: Optional[str] = typer.Option(None, "--topic", "-t", help="可选双时态主题键"),
    db: Optional[str] = typer.Option(None, "--db", help="可选自定义状态库路径"),
) -> None:
    """提交 1 秒 4 键反馈（赞 / 踩 / 纠偏 / 存为技能种子）。"""
    svc = _make_service(db)
    ev = svc.submit_feedback(run_id, kind=kind, note=note, topic_key=topic)
    typer.echo(
        f"[反馈已落盘] kind={ev['kind']} | elapsed={ev['elapsed_ms']}ms | "
        f"memory_id={ev.get('created_memory_id') or '-'} | seed_id={ev.get('created_seed_id') or '-'}"
    )


@app.command("memories")
def cmd_memories(
    query: str = typer.Option("", "--query", "-q", help="按关键词混合检索本地记忆"),
    add: Optional[str] = typer.Option(None, "--add", help="直接新增一条核心记忆"),
    forget: Optional[str] = typer.Option(None, "--forget", help="按 memory_id 一键遗忘"),
    db: Optional[str] = typer.Option(None, "--db", help="可选自定义状态库路径"),
) -> None:
    """查看、检索、新增或一键遗忘本地透明记忆（同步 MEMORY.md）。"""
    svc = _make_service(db)
    if add:
        rec = svc.add_memory(add)
        typer.echo(f"已写入核心记忆 [{rec['memory_id']}]: {rec['content']}")
        return
    if forget:
        rec = svc.forget_memory(forget)
        typer.echo(f"已彻底遗忘记忆 [{rec['memory_id']}] (status={rec['status']})")
        return
    items = svc.recall_memories(query, top_k=15)
    typer.echo(f"本地活跃记忆共 {len(items)} 条 (真相源文件: {svc.memory.memory_md_path}):")
    for m in items:
        typer.echo(f"  - [{m['memory_id']}] ({m['layer']}) {m['content']}")


@app.command("evolve")
def cmd_evolve(
    seed_id: str = typer.Argument(..., help="M10 捕获的技能种子 seed_id"),
    approve: bool = typer.Option(False, "--approve", help="双闸门通过后由人工当场确认激活"),
    db: Optional[str] = typer.Option(None, "--db", help="可选自定义状态库路径"),
) -> None:
    """从技能种子执行双闸门自演化（M08 沙箱单测 + C00 增上四问），按需经人工签发激活。"""
    svc = _make_service(db)
    draft = svc.evolve_from_seed(seed_id, auto_verify=True)
    typer.echo(
        f"[双闸门验真] draft_id={draft['draft_id']} | skill_id={draft['skill_id']} | status={draft['status']}"
    )
    if approve and draft["status"] == "PENDING_REVIEW":
        activated = svc.review_evolution_draft(draft["draft_id"], approved=True, reviewer="cli_human")
        typer.echo(f"[已人工签发上线] skill_id={activated['skill_id']} | status={activated['status']}")


@app.command("export-skill")
def cmd_export_skill(
    skill_id: str = typer.Argument(..., help="要导出为普惠便携包的 skill_id"),
    output_zip: str = typer.Argument(..., help="输出 .hqskill.zip 路径"),
    db: Optional[str] = typer.Option(None, "--db", help="可选自定义状态库路径"),
) -> None:
    """将已验真技能打包导出为低配离线设备可复用的 .hqskill.zip 普惠技能包。"""
    svc = _make_service(db)
    out = svc.export_portable_skill(skill_id, output_zip)
    typer.echo(f"[普惠技能已导出] {skill_id} -> {out['zip_path']} (lite_ready={out['card']['portable_lite_ready']})")


@app.command("import-skill")
def cmd_import_skill(
    zip_path: str = typer.Argument(..., help="待导入的 .hqskill.zip 路径"),
    overwrite: bool = typer.Option(False, "--overwrite", help="若技能已存在是否允许覆盖"),
    db: Optional[str] = typer.Option(None, "--db", help="可选自定义状态库路径"),
) -> None:
    """安全校验（防 Zip-Slip / SHA-256 / 复跑双闸门）并导入普惠离线技能包。"""
    svc = _make_service(db)
    info = svc.import_portable_skill(zip_path, overwrite=overwrite)
    typer.echo(f"[普惠技能已导入] {info['skill_id']} ({info['name']}) -> {info['installed_dir']}")


@app.command("serve")
def cmd_serve(
    host: str = typer.Option("127.0.0.1", "--host", help="默认严格绑定本机回环地址"),
    port: int = typer.Option(8765, "--port", help="本地监听端口"),
    allow_lan: bool = typer.Option(False, "--allow-lan", help="显式确认开放局域网访问（默认禁止）"),
    db: Optional[str] = typer.Option(None, "--db", help="可选自定义状态库路径"),
) -> None:
    """启动本地 FastAPI + 零依赖单页 WebUI 工作台。"""
    if host.lower() not in _LOOPBACK_HOSTS and not allow_lan:
        typer.echo(
            f"[安全拦截] 默认仅允许绑定本机回环地址 ({', '.join(sorted(_LOOPBACK_HOSTS))})；"
            "若确需局域网监听请显式传入 --allow-lan。",
            err=True,
        )
        raise typer.Exit(code=2)

    import uvicorn

    from packages.gateway.api import create_app

    svc = _make_service(db)
    fastapi_app = create_app(svc)
    typer.echo(f"汇桥 OS 本地工作台已启动: http://{host}:{port}")
    uvicorn.run(fastapi_app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()
