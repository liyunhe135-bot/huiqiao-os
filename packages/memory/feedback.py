"""M10 (B08) 1 秒 4 键极简人类反馈闭环（赞 / 踩 / 纠偏 / 存为技能种子 → 直供 M11 自演化）."""

from __future__ import annotations

import json
import pathlib
import time
from typing import Any

from packages.memory.models import (
    FeedbackEvent,
    FeedbackKind,
    MemoryLayer,
    MemoryRecord,
    SkillSeedCandidate,
)
from packages.memory.store import FileFirstMemoryStore


class FeedbackLoopService:
    """将人类的 1 秒轻量反馈（👍 / 👎 / ✏️ / 🌱）实时转化为分层记忆与技能种子。"""

    def __init__(
        self,
        memory_store: FileFirstMemoryStore,
        *,
        seeds_dir: pathlib.Path | str | None = None,
    ) -> None:
        self.memory_store = memory_store
        self.seeds_dir = (
            pathlib.Path(seeds_dir).resolve()
            if seeds_dir is not None
            else (self.memory_store.workspace_dir / ".huiqiao" / "skill_seeds").resolve()
        )
        self.seeds_dir.mkdir(parents=True, exist_ok=True)
        self._feedback_log_path = self.memory_store.workspace_dir / ".huiqiao" / "feedback_events.jsonl"
        self._feedback_log_path.parent.mkdir(parents=True, exist_ok=True)

    def submit_feedback(
        self,
        *,
        run_id: str,
        kind: FeedbackKind | str,
        note: str = "",
        topic_key: str | None = None,
        scope: str = "default",
        run_snapshot: dict[str, Any] | None = None,
    ) -> FeedbackEvent:
        started = time.perf_counter()
        fb_kind = kind if isinstance(kind, FeedbackKind) else FeedbackKind(str(kind).strip().lower())
        snap = run_snapshot or {}
        route = snap.get("route_decision") or {}
        channel = str(route.get("channel") or "UNKNOWN")
        summary_excerpt = str(snap.get("summary") or "").strip().splitlines()[0][:160] if snap.get("summary") else ""
        goal_excerpt = str(snap.get("raw_input") or snap.get("goal") or "").strip()[:160]
        clean_note = note.strip()

        created_mem_id: str | None = None
        created_seed_id: str | None = None

        if fb_kind == FeedbackKind.PRAISE:
            content = (
                f"正向高分经验（通道={channel}）：{clean_note or summary_excerpt or f'运行 {run_id} 获人类点赞确认'}"
            )
            rec = self.memory_store.commit_record(
                MemoryRecord(
                    scope=scope,
                    layer=MemoryLayer.EPISODIC,
                    content=content,
                    tags=["praise", channel.lower()],
                    confidence=0.92,
                    source="feedback_praise",
                    source_run_id=run_id,
                )
            )
            created_mem_id = rec.memory_id

        elif fb_kind == FeedbackKind.DISLIKE:
            reason = clean_note or summary_excerpt or f"运行 {run_id} 效果不佳，需避免重复同类路径"
            rec = self.memory_store.commit_record(
                MemoryRecord(
                    scope=scope,
                    layer=MemoryLayer.ANTI_PATTERN,
                    content=f"避坑警示（通道={channel}）：{reason}",
                    topic_key=topic_key,
                    tags=["dislike", "anti_pattern", channel.lower()],
                    confidence=0.95,
                    source="feedback_dislike",
                    source_run_id=run_id,
                )
            )
            created_mem_id = rec.memory_id

        elif fb_kind == FeedbackKind.CORRECT:
            if not clean_note:
                raise ValueError("提交『纠偏 (correct)』反馈时必须提供非空纠偏内容 note。")
            rec = self.memory_store.commit_record(
                MemoryRecord(
                    scope=scope,
                    layer=MemoryLayer.CORE,
                    content=clean_note,
                    topic_key=topic_key,
                    tags=["correction", "user_preference"],
                    confidence=0.99,
                    source="feedback_correct",
                    source_run_id=run_id,
                )
            )
            created_mem_id = rec.memory_id

        elif fb_kind == FeedbackKind.SAVE_SKILL_SEED:
            artifacts = [
                str(a.get("file_path") if isinstance(a, dict) else a)
                for a in (snap.get("artifacts") or [])
            ]
            title = clean_note or goal_excerpt or f"来自运行 {run_id} 的高价值技能种子"
            seed = SkillSeedCandidate(
                source_run_id=run_id,
                title=title[:80],
                user_goal=goal_excerpt or title,
                channel=channel,
                summary=str(snap.get("summary") or "")[:1200],
                human_note=clean_note,
                artifact_paths=artifacts,
                extra={"route_decision": route},
            )
            seed_file = self.seeds_dir / f"{seed.seed_id}.json"
            seed_file.write_text(
                json.dumps(seed.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            created_seed_id = seed.seed_id

            # 同时在情景日志留痕，便于后续回顾
            rec = self.memory_store.commit_record(
                MemoryRecord(
                    scope=scope,
                    layer=MemoryLayer.EPISODIC,
                    content=f"已捕获技能种子 [{seed.seed_id}]：{seed.title}",
                    tags=["skill_seed", channel.lower()],
                    confidence=0.95,
                    source="feedback_skill_seed",
                    source_run_id=run_id,
                )
            )
            created_mem_id = rec.memory_id

        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
        event = FeedbackEvent(
            run_id=run_id,
            kind=fb_kind,
            note=clean_note,
            topic_key=topic_key,
            scope=scope,
            created_memory_id=created_mem_id,
            created_seed_id=created_seed_id,
            elapsed_ms=elapsed_ms,
        )
        with self._feedback_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return event

    def list_skill_seeds(self) -> list[SkillSeedCandidate]:
        seeds: list[SkillSeedCandidate] = []
        for p in sorted(self.seeds_dir.glob("seed_*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                seeds.append(SkillSeedCandidate.model_validate(data))
            except Exception:
                continue
        seeds.sort(key=lambda s: s.created_at, reverse=True)
        return seeds

    def list_feedback_events(self, *, run_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if not self._feedback_log_path.exists():
            return []
        items: list[dict[str, Any]] = []
        for line in self._feedback_log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                if run_id is None or obj.get("run_id") == run_id:
                    items.append(obj)
            except json.JSONDecodeError:
                continue
        return list(reversed(items[-limit:]))
