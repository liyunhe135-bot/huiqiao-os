"""M10 (B08) File-First 分层本地记忆引擎（Markdown 第一真相源 + SQLite WAL/FTS5/向量混合双时态索引）.

核心设计（严守 C00 A1 人类主权与透明可逆）：
  1. File-First 人类可读可改：
     - `workspace/MEMORY.md` 存放所有 ACTIVE 核心记忆与反模式警示，格式清晰，用户随时可用记事本增删改；
     - `workspace/memory/YYYY-MM-DD.md` 按日追加情景流水日志；
     - `sync_from_markdown()` 自动检测用户手改 `MEMORY.md`（新增行入库、修改行更新、删掉行标记遗忘）！
  2. 中英双语混合检索（零外部 C++ 编译依赖）：
     - 自带中英分词器（英文词干 + 中文单字与双字 Bigram）驱动 SQLite 原生 `FTS5` BM25 检索；
     - 叠加 128 维本地确定性特征哈希向量余弦相似度 + 置信度权重，单次召回 < 5ms；
  3. 双时态演化（Bi-Temporal）：
     - 同 `scope + topic_key` 写入新偏好或纠偏时，旧记录自动设置 `status=SUPERSEDED`、`invalidated_at` 与 `valid_until`，
       既保证默认召回零冲突，又保留完整时间轴供历史追溯。
"""

from __future__ import annotations

import hashlib
import json
import math
import pathlib
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from packages.core.contracts import new_id, utc_now
from packages.memory.models import MemoryLayer, MemoryRecord, MemoryStatus

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[a-z0-9_]+", re.IGNORECASE)
_MD_ITEM_RE = re.compile(
    r"^\s*-\s*(?:\[(?P<id>mem_[a-z0-9_]+)\]\s*)?"
    r"(?:\((?P<layer>core|anti_pattern|episodic)(?::(?P<topic>[a-zA-Z0-9_.-]+))?\)\s*)?"
    r"(?P<content>.+?)\s*$"
)
_VEC_DIM = 128


def tokenize_bilingual(text: str) -> list[str]:
    """零依赖中英混合分词：英文/数字词元 + 中文单字与相邻双字 Bigram，彻底解决 SQLite FTS5 中文断词盲区。"""
    lowered = (text or "").lower()
    tokens: list[str] = []
    tokens.extend(_WORD_RE.findall(lowered))
    for chunk in _CJK_RE.findall(lowered):
        if len(chunk) == 1:
            tokens.append(chunk)
        else:
            tokens.extend(chunk[i : i + 2] for i in range(len(chunk) - 1))
            tokens.extend(list(chunk))
    return tokens


def embed_feature_hash(text: str, dim: int = _VEC_DIM) -> list[float]:
    """本地零模型确定性特征哈希嵌入（L2 归一化），用于与 FTS5 BM25 构成混合检索。"""
    vec = [0.0] * dim
    toks = tokenize_bilingual(text)
    if not toks:
        return vec
    for tok in toks:
        h = hashlib.blake2b(tok.encode("utf-8"), digest_size=4).digest()
        idx = int.from_bytes(h[:2], "little") % dim
        sign = 1.0 if (h[2] & 1) == 0 else -1.0
        weight = 1.6 if len(tok) >= 2 else 0.7
        vec[idx] += sign * weight
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 1e-9:
        vec = [round(v / norm, 6) for v in vec]
    return vec


def cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


class FileFirstMemoryStore:
    """B08 File-First 分层双时态记忆引擎（完整实现 MemoryStoreProtocol）。"""

    def __init__(
        self,
        workspace_dir: pathlib.Path | str | None = None,
        *,
        db_path: pathlib.Path | str | None = None,
    ) -> None:
        base_ws = (
            pathlib.Path(workspace_dir).resolve()
            if workspace_dir is not None
            else (pathlib.Path(__file__).resolve().parents[2] / "workspace").resolve()
        )
        base_ws.mkdir(parents=True, exist_ok=True)
        self.workspace_dir = base_ws
        self.memory_md_path = self.workspace_dir / "MEMORY.md"
        self.daily_dir = self.workspace_dir / "memory"
        self.daily_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = (
            pathlib.Path(db_path).resolve()
            if db_path is not None
            else (self.workspace_dir / ".huiqiao" / "memory.db").resolve()
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_synced_mtime_ns: int | None = None
        self._init_db()
        if self.memory_md_path.exists():
            self.sync_from_markdown()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    layer TEXT NOT NULL,
                    status TEXT NOT NULL,
                    content TEXT NOT NULL,
                    topic_key TEXT,
                    tags_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    source_run_id TEXT,
                    superseded_by TEXT,
                    recorded_at TEXT NOT NULL,
                    invalidated_at TEXT,
                    valid_from TEXT NOT NULL,
                    valid_until TEXT,
                    embedding_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_mem_scope_status ON memories(scope, status);
                CREATE INDEX IF NOT EXISTS idx_mem_topic ON memories(scope, topic_key, status);

                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    memory_id UNINDEXED,
                    scope UNINDEXED,
                    search_tokens
                );
                """
            )

    def healthcheck(self) -> bool:
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1 FROM memories LIMIT 1;").fetchall()
            return True
        except Exception:
            return False

    def _upsert_sql(self, conn: sqlite3.Connection, rec: MemoryRecord) -> None:
        tokens_str = " ".join(tokenize_bilingual(f"{rec.topic_key or ''} {' '.join(rec.tags)} {rec.content}"))
        emb = embed_feature_hash(f"{rec.topic_key or ''} {rec.content}")
        conn.execute(
            """
            INSERT INTO memories (
                memory_id, scope, layer, status, content, topic_key, tags_json,
                confidence, source, source_run_id, superseded_by,
                recorded_at, invalidated_at, valid_from, valid_until,
                embedding_json, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(memory_id) DO UPDATE SET
                scope=excluded.scope,
                layer=excluded.layer,
                status=excluded.status,
                content=excluded.content,
                topic_key=excluded.topic_key,
                tags_json=excluded.tags_json,
                confidence=excluded.confidence,
                source=excluded.source,
                source_run_id=excluded.source_run_id,
                superseded_by=excluded.superseded_by,
                invalidated_at=excluded.invalidated_at,
                valid_from=excluded.valid_from,
                valid_until=excluded.valid_until,
                embedding_json=excluded.embedding_json,
                metadata_json=excluded.metadata_json;
            """,
            (
                rec.memory_id,
                rec.scope,
                rec.layer.value,
                rec.status.value,
                rec.content,
                rec.topic_key,
                json.dumps(rec.tags, ensure_ascii=False),
                rec.confidence,
                rec.source,
                rec.source_run_id,
                rec.superseded_by,
                rec.recorded_at.isoformat(),
                rec.invalidated_at.isoformat() if rec.invalidated_at else None,
                rec.valid_from.isoformat(),
                rec.valid_until.isoformat() if rec.valid_until else None,
                json.dumps(emb),
                json.dumps(rec.metadata, ensure_ascii=False),
            ),
        )
        conn.execute("DELETE FROM memories_fts WHERE memory_id = ?;", (rec.memory_id,))
        if rec.status == MemoryStatus.ACTIVE:
            conn.execute(
                "INSERT INTO memories_fts (memory_id, scope, search_tokens) VALUES (?, ?, ?);",
                (rec.memory_id, rec.scope, tokens_str),
            )

    def _row_to_record(self, row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            memory_id=row["memory_id"],
            scope=row["scope"],
            layer=MemoryLayer(row["layer"]),
            status=MemoryStatus(row["status"]),
            content=row["content"],
            topic_key=row["topic_key"],
            tags=json.loads(row["tags_json"] or "[]"),
            confidence=float(row["confidence"]),
            source=row["source"],
            source_run_id=row["source_run_id"],
            superseded_by=row["superseded_by"],
            recorded_at=datetime.fromisoformat(row["recorded_at"]),
            invalidated_at=datetime.fromisoformat(row["invalidated_at"]) if row["invalidated_at"] else None,
            valid_from=datetime.fromisoformat(row["valid_from"]),
            valid_until=datetime.fromisoformat(row["valid_until"]) if row["valid_until"] else None,
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    def _render_memory_md(self) -> None:
        """将当前全部 ACTIVE 的 CORE 与 ANTI_PATTERN 记忆渲染回人类可直接编辑的 MEMORY.md。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memories
                WHERE status = 'ACTIVE' AND layer IN ('core', 'anti_pattern')
                ORDER BY recorded_at ASC;
                """
            ).fetchall()

        core_lines: list[str] = []
        anti_lines: list[str] = []
        for r in rows:
            topic_suffix = f":{r['topic_key']}" if r["topic_key"] else ""
            clean_text = str(r["content"]).replace("\n", " ").strip()
            bullet = f"- [{r['memory_id']}] ({r['layer']}{topic_suffix}) {clean_text}"
            if r["layer"] == MemoryLayer.ANTI_PATTERN.value:
                anti_lines.append(bullet)
            else:
                core_lines.append(bullet)

        sections = [
            "# 汇桥 OS 本地核心记忆账本 (MEMORY.md)",
            "",
            "> 本文件为人类第一真相源（File-First）：您可随时直接新增、修改或删除下方条目，系统将自动双向同步。",
            "",
            "## 一、长期偏好与核心认知 (Core Memory)",
        ]
        sections.extend(core_lines if core_lines else ["<!-- 暂无核心记忆，可直接以 `- 偏好内容` 新增 -->"])
        sections.extend(["", "## 二、避坑与反模式警示 (Anti-Patterns)"])
        sections.extend(anti_lines if anti_lines else ["<!-- 暂无反模式警示 -->"])
        sections.append("")

        self.memory_md_path.write_text("\n".join(sections), encoding="utf-8")
        try:
            self._last_synced_mtime_ns = self.memory_md_path.stat().st_mtime_ns
        except OSError:
            self._last_synced_mtime_ns = None

    def _append_daily_episodic_md(self, rec: MemoryRecord) -> pathlib.Path:
        day_str = rec.recorded_at.astimezone(timezone.utc).strftime("%Y-%m-%d")
        daily_file = self.daily_dir / f"{day_str}.md"
        ts_str = rec.recorded_at.astimezone(timezone.utc).strftime("%H:%M:%S UTC")
        header_needed = not daily_file.exists()
        with daily_file.open("a", encoding="utf-8") as f:
            if header_needed:
                f.write(f"# 汇桥每日情景记忆日志 ({day_str})\n\n")
            run_part = f" | run={rec.source_run_id}" if rec.source_run_id else ""
            f.write(f"- `{ts_str}` [{rec.memory_id}] ({rec.source}{run_part}) {rec.content.strip()}\n")
        return daily_file

    def sync_from_markdown(self) -> dict[str, int]:
        """双向同步：解析人类手改后的 MEMORY.md，自动入库新增行、更新修改行、遗忘被删行。"""
        if not self.memory_md_path.exists():
            return {"added": 0, "updated": 0, "forgotten": 0}

        lines = self.memory_md_path.read_text(encoding="utf-8").splitlines()
        current_section_layer = MemoryLayer.CORE
        seen_ids: set[str] = set()
        added = 0
        updated = 0
        forgotten = 0
        now = utc_now()

        with self._connect() as conn:
            existing_rows = conn.execute(
                "SELECT * FROM memories WHERE status = 'ACTIVE' AND layer IN ('core', 'anti_pattern');"
            ).fetchall()
            existing_by_id = {r["memory_id"]: self._row_to_record(r) for r in existing_rows}

            for raw_line in lines:
                stripped = raw_line.strip()
                if stripped.startswith("## ") and ("反模式" in stripped or "Anti-Pattern" in stripped):
                    current_section_layer = MemoryLayer.ANTI_PATTERN
                    continue
                if stripped.startswith("## ") and ("核心" in stripped or "Core" in stripped):
                    current_section_layer = MemoryLayer.CORE
                    continue
                if not stripped.startswith("- "):
                    continue

                m = _MD_ITEM_RE.match(stripped)
                if not m:
                    continue
                mem_id = m.group("id")
                layer_str = m.group("layer")
                topic = m.group("topic")
                content = m.group("content").strip()
                if not content:
                    continue

                layer = MemoryLayer(layer_str) if layer_str else current_section_layer
                if mem_id and mem_id in existing_by_id:
                    seen_ids.add(mem_id)
                    old = existing_by_id[mem_id]
                    if old.content != content or old.layer != layer or old.topic_key != topic:
                        edited = old.model_copy(
                            update={
                                "content": content,
                                "layer": layer,
                                "topic_key": topic,
                                "source": "human_edit",
                            }
                        )
                        self._upsert_sql(conn, edited)
                        updated += 1
                else:
                    new_rec = MemoryRecord(
                        memory_id=mem_id or new_id("mem"),
                        layer=layer,
                        content=content,
                        topic_key=topic,
                        source="human_edit",
                        confidence=0.95,
                    )
                    seen_ids.add(new_rec.memory_id)
                    self._upsert_sql(conn, new_rec)
                    added += 1

            # 原本在 MEMORY.md 中 ACTIVE、但被人类手工删除的条目 -> 自动标记为 FORGOTTEN
            for old_id, old_rec in existing_by_id.items():
                if old_id not in seen_ids:
                    forgotten_rec = old_rec.model_copy(
                        update={
                            "status": MemoryStatus.FORGOTTEN,
                            "invalidated_at": now,
                            "valid_until": now,
                        }
                    )
                    self._upsert_sql(conn, forgotten_rec)
                    forgotten += 1

        if added or updated or forgotten:
            self._render_memory_md()
        else:
            try:
                self._last_synced_mtime_ns = self.memory_md_path.stat().st_mtime_ns
            except OSError:
                pass
        return {"added": added, "updated": updated, "forgotten": forgotten}

    def _auto_sync_if_file_modified(self) -> None:
        if not self.memory_md_path.exists():
            return
        try:
            mtime = self.memory_md_path.stat().st_mtime_ns
        except OSError:
            return
        if self._last_synced_mtime_ns is None or mtime != self._last_synced_mtime_ns:
            self.sync_from_markdown()

    def commit_record(self, record: MemoryRecord) -> MemoryRecord:
        """写入一条结构化记忆（自动处理同 topic_key 的双时态旧记录闭合与 Markdown 同步）。"""
        self._auto_sync_if_file_modified()
        now = utc_now()
        with self._connect() as conn:
            if record.topic_key and record.status == MemoryStatus.ACTIVE:
                old_rows = conn.execute(
                    """
                    SELECT * FROM memories
                    WHERE scope = ? AND topic_key = ? AND status = 'ACTIVE' AND memory_id != ?;
                    """,
                    (record.scope, record.topic_key, record.memory_id),
                ).fetchall()
                for r in old_rows:
                    old_rec = self._row_to_record(r).model_copy(
                        update={
                            "status": MemoryStatus.SUPERSEDED,
                            "superseded_by": record.memory_id,
                            "invalidated_at": now,
                            "valid_until": record.valid_from,
                        }
                    )
                    self._upsert_sql(conn, old_rec)

            self._upsert_sql(conn, record)

        if record.layer in (MemoryLayer.CORE, MemoryLayer.ANTI_PATTERN):
            self._render_memory_md()
        else:
            self._append_daily_episodic_md(record)
        return record

    def commit(self, record: dict[str, Any], *, scope: str = "default") -> str:
        """满足 packages.core.interfaces.MemoryStoreProtocol 标准签名。"""
        payload = dict(record)
        payload.setdefault("scope", scope)
        if "layer" in payload and isinstance(payload["layer"], str):
            payload["layer"] = MemoryLayer(payload["layer"].lower())
        mem = MemoryRecord.model_validate(payload)
        saved = self.commit_record(mem)
        return saved.memory_id

    def recall(
        self,
        query: str,
        *,
        scope: str = "default",
        top_k: int = 5,
        include_history: bool = False,
    ) -> list[dict[str, Any]]:
        """混合双时态检索（FTS5 BM25 + 本地余弦相似度 + 字面子串加成 + 置信度权重）。"""
        self._auto_sync_if_file_modified()
        q_clean = (query or "").strip()
        q_tokens = tokenize_bilingual(q_clean)
        q_vec = embed_feature_hash(q_clean)

        fts_scores: dict[str, float] = {}
        with self._connect() as conn:
            if q_tokens and not include_history:
                # 使用 OR 连接中英分词，配合 bm25 排序召回候选
                safe_terms = [f'"{t}"' for t in dict.fromkeys(q_tokens) if t]
                if safe_terms:
                    match_expr = " OR ".join(safe_terms[:32])
                    fts_rows = conn.execute(
                        """
                        SELECT memory_id, bm25(memories_fts) AS rank_score
                        FROM memories_fts
                        WHERE scope = ? AND memories_fts MATCH ?
                        ORDER BY rank_score ASC
                        LIMIT ?;
                        """,
                        (scope, match_expr, max(20, top_k * 5)),
                    ).fetchall()
                    for fr in fts_rows:
                        # SQLite bm25 越小越相关（常为负数），转为正相关分
                        fts_scores[fr["memory_id"]] = max(0.1, -float(fr["rank_score"]))

            if include_history:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE scope = ? AND status != 'FORGOTTEN' ORDER BY recorded_at DESC;",
                    (scope,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE scope = ? AND status = 'ACTIVE' ORDER BY recorded_at DESC;",
                    (scope,),
                ).fetchall()

        scored: list[tuple[float, dict[str, Any]]] = []
        q_lower = q_clean.lower()
        for r in rows:
            rec = self._row_to_record(r)
            emb = json.loads(r["embedding_json"] or "[]")
            vec_score = max(0.0, cosine_sim(q_vec, emb))
            bm25_score = fts_scores.get(rec.memory_id, 0.0)
            substr_bonus = 1.5 if (q_lower and q_lower in rec.content.lower()) else 0.0
            layer_bonus = 0.25 if rec.layer == MemoryLayer.ANTI_PATTERN else (0.15 if rec.layer == MemoryLayer.CORE else 0.0)

            if not q_clean:
                total = rec.confidence + layer_bonus
            else:
                total = bm25_score * 0.55 + vec_score * 1.45 + substr_bonus + rec.confidence * 0.20 + layer_bonus
                if bm25_score == 0.0 and vec_score < 0.08 and substr_bonus == 0.0:
                    continue

            item = rec.model_dump(mode="json")
            item["score"] = round(total, 4)
            scored.append((total, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[: max(1, top_k)]]

    def list_memories(
        self,
        *,
        scope: str = "default",
        include_inactive: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        self._auto_sync_if_file_modified()
        with self._connect() as conn:
            if include_inactive:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE scope = ? ORDER BY recorded_at DESC LIMIT ?;",
                    (scope, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE scope = ? AND status = 'ACTIVE' ORDER BY recorded_at DESC LIMIT ?;",
                    (scope, limit),
                ).fetchall()
        return [self._row_to_record(r).model_dump(mode="json") for r in rows]

    def update_memory(
        self,
        memory_id: str,
        *,
        content: str,
        topic_key: str | None = None,
    ) -> dict[str, Any]:
        """人类主动编辑指定记忆条目，立即同步 SQLite 与 MEMORY.md。"""
        self._auto_sync_if_file_modified()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memories WHERE memory_id = ?;", (memory_id,)).fetchone()
            if row is None:
                raise KeyError(f"未找到记忆条目: {memory_id}")
            old = self._row_to_record(row)
            updated = old.model_copy(
                update={
                    "content": content.strip(),
                    "topic_key": topic_key if topic_key is not None else old.topic_key,
                    "source": "human_edit",
                }
            )
            self._upsert_sql(conn, updated)
        if updated.layer in (MemoryLayer.CORE, MemoryLayer.ANTI_PATTERN):
            self._render_memory_md()
        return updated.model_dump(mode="json")

    def forget(self, memory_id: str) -> dict[str, Any]:
        """一键可解释遗忘（C00 A1 可逆底线）：立即从 ACTIVE 索引与 MEMORY.md 中移除。"""
        self._auto_sync_if_file_modified()
        now = utc_now()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memories WHERE memory_id = ?;", (memory_id,)).fetchone()
            if row is None:
                raise KeyError(f"未找到记忆条目: {memory_id}")
            old = self._row_to_record(row)
            forgotten = old.model_copy(
                update={
                    "status": MemoryStatus.FORGOTTEN,
                    "invalidated_at": now,
                    "valid_until": now,
                }
            )
            self._upsert_sql(conn, forgotten)
        if forgotten.layer in (MemoryLayer.CORE, MemoryLayer.ANTI_PATTERN):
            self._render_memory_md()
        return forgotten.model_dump(mode="json")
