"""M05 SQLite WAL 持久化底座：runs / checkpoints / events / artifacts 四表管理.

设计原则：
- 开启 WAL + synchronous=NORMAL，兼顾消费级本地磁盘性能与断电/强杀崩溃恢复；
- `events` 严格仅追加（Append-Only），天然支持全链路审计与轨迹级评测；
- `artifacts` 在每步完成时立即落盘保存，即使后续步骤失败/超时，已有产物 100% 保留。
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteStateStore:
    """单机零运维持久化状态库，支持进程强杀后按最近已完成节点精确续跑。"""

    def __init__(
        self,
        db_path: pathlib.Path | str,
        *,
        artifacts_root: pathlib.Path | str | None = None,
    ) -> None:
        self.db_path = pathlib.Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_root = (
            pathlib.Path(artifacts_root)
            if artifacts_root is not None
            else self.db_path.parent.parent / "workspace" / "runs"
        )
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    flow_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    completed_nodes_json TEXT NOT NULL,
                    pending_interrupt_json TEXT,
                    steering_hints_json TEXT NOT NULL DEFAULT '[]',
                    step_count INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    node_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_checkpoints_run ON checkpoints(run_id, step_index);
                CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, id);
                CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id);
                """
            )

    def journal_mode(self) -> str:
        with self._connect() as conn:
            row = conn.execute("PRAGMA journal_mode;").fetchone()
            return str(row[0]).lower() if row else ""

    def create_run(
        self,
        *,
        run_id: str,
        task_id: str,
        flow_name: str,
        initial_state: dict[str, Any],
    ) -> None:
        now = _utc_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, task_id, flow_name, status, state_json,
                    completed_nodes_json, pending_interrupt_json,
                    steering_hints_json, step_count, error, created_at, updated_at
                ) VALUES (?, ?, ?, 'RUNNING', ?, '[]', NULL, '[]', 0, NULL, ?, ?)
                """,
                (run_id, task_id, flow_name, json.dumps(initial_state, ensure_ascii=False), now, now),
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                return None
            return {
                "run_id": row["run_id"],
                "task_id": row["task_id"],
                "flow_name": row["flow_name"],
                "status": row["status"],
                "state": json.loads(row["state_json"]),
                "completed_nodes": json.loads(row["completed_nodes_json"]),
                "pending_interrupt": (
                    json.loads(row["pending_interrupt_json"])
                    if row["pending_interrupt_json"]
                    else None
                ),
                "steering_hints": json.loads(row["steering_hints_json"]),
                "step_count": row["step_count"],
                "error": row["error"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    def save_checkpoint(
        self,
        *,
        run_id: str,
        node_id: str,
        step_index: int,
        state: dict[str, Any],
        completed_nodes: list[str],
        status: str = "RUNNING",
        pending_interrupt: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        now = _utc_iso()
        state_str = json.dumps(state, ensure_ascii=False)
        interrupt_str = (
            json.dumps(pending_interrupt, ensure_ascii=False)
            if pending_interrupt is not None
            else None
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints (run_id, node_id, step_index, state_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, node_id, step_index, state_str, status, now),
            )
            conn.execute(
                """
                UPDATE runs
                SET status = ?, state_json = ?, completed_nodes_json = ?,
                    pending_interrupt_json = ?, step_count = ?, error = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (
                    status,
                    state_str,
                    json.dumps(completed_nodes, ensure_ascii=False),
                    interrupt_str,
                    step_index,
                    error,
                    now,
                    run_id,
                ),
            )

    def add_steering_hint(self, run_id: str, hint: str) -> None:
        """用户中途改向：将新指引原子追加到运行态，下一节点立即吸纳。"""
        now = _utc_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT steering_hints_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"运行实例不存在: {run_id}")
            hints: list[str] = json.loads(row["steering_hints_json"])
            hints.append(hint)
            conn.execute(
                "UPDATE runs SET steering_hints_json = ?, updated_at = ? WHERE run_id = ?",
                (json.dumps(hints, ensure_ascii=False), now, run_id),
            )

    def consume_steering_hints(self, run_id: str) -> list[str]:
        now = _utc_iso()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT steering_hints_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                return []
            hints: list[str] = json.loads(row["steering_hints_json"])
            if hints:
                conn.execute(
                    "UPDATE runs SET steering_hints_json = '[]', updated_at = ? WHERE run_id = ?",
                    (now, run_id),
                )
            return hints

    def append_event(
        self,
        *,
        run_id: str,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
        node_id: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO events (run_id, task_id, event_type, node_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, task_id, event_type, node_id, json.dumps(payload, ensure_ascii=False), now),
            )
        return {
            "run_id": run_id,
            "task_id": task_id,
            "event_type": event_type,
            "node_id": node_id,
            "payload": payload,
            "created_at": now,
        }

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY id ASC", (run_id,)
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "run_id": r["run_id"],
                    "task_id": r["task_id"],
                    "event_type": r["event_type"],
                    "node_id": r["node_id"],
                    "payload": json.loads(r["payload_json"]),
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    def list_checkpoints(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM checkpoints WHERE run_id = ? ORDER BY id ASC", (run_id,)
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "run_id": r["run_id"],
                    "node_id": r["node_id"],
                    "step_index": r["step_index"],
                    "state": json.loads(r["state_json"]),
                    "status": r["status"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    def save_artifact(
        self,
        *,
        run_id: str,
        node_id: str,
        name: str,
        content: str | bytes,
    ) -> pathlib.Path:
        """立即落盘节点产物并登记到 artifacts 表，确保后续失败时已有工作绝不白费。"""
        safe_name = pathlib.Path(name).name
        art_dir = self.artifacts_root / run_id / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        target = art_dir / safe_name
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")

        now = _utc_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (run_id, node_id, name, file_path, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, node_id, safe_name, str(target), now),
            )
        return target

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM artifacts WHERE run_id = ? ORDER BY id ASC", (run_id,)
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "run_id": r["run_id"],
                    "node_id": r["node_id"],
                    "name": r["name"],
                    "file_path": r["file_path"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
