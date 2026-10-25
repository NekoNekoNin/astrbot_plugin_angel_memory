"""Atomic learning history in the central memory database."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_source: ContextVar[dict[str, Any] | None] = ContextVar(
    "memory_learning_source", default=None
)


@contextmanager
def learning_source(
    kind: str, *, session_id: str = "", excerpt: str = "", message_ids=None
):
    """Carry verified turn metadata through async tasks and asyncio.to_thread."""
    token = _source.set(
        {
            "kind": str(kind)[:80],
            "session_id": str(session_id)[:300],
            "excerpt": str(excerpt)[:1000],
            "message_ids": [str(item)[:150] for item in (message_ids or [])][:20],
        }
    )
    try:
        yield
    finally:
        _source.reset(token)


class HistoryConflict(ValueError):
    """A later write prevents safe restoration of this learning operation."""


class MemoryHistory:
    """Persist snapshots in the same transaction as the memory mutation."""

    COLUMNS = (
        "id",
        "memory_type",
        "judgment",
        "reasoning",
        "strength",
        "is_active",
        "useful_count",
        "useful_score",
        "last_recalled_at",
        "last_decay_at",
        "memory_scope",
        "created_at",
        "updated_at",
    )

    @staticmethod
    def initialize(conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS memory_learning_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                memory_scope TEXT NOT NULL,
                source_json TEXT NOT NULL,
                before_json TEXT NOT NULL,
                after_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'committed',
                undone_at REAL,
                index_sync TEXT NOT NULL DEFAULT 'synced',
                index_error TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_learning_history_scope
                ON memory_learning_history(memory_scope, id DESC);
        """)

    @classmethod
    def snapshot(cls, conn: sqlite3.Connection, memory_ids: list[str]) -> list[dict]:
        result = []
        for memory_id in dict.fromkeys(memory_ids):
            row = conn.execute(
                "SELECT * FROM memory_records WHERE id = ?", (memory_id,)
            ).fetchone()
            if row is None:
                continue
            item = {key: row[key] for key in cls.COLUMNS}
            item["tags"] = [
                str(tag[0])
                for tag in conn.execute(
                    "SELECT t.name FROM global_tags t JOIN memory_tag_rel r ON t.id=r.tag_id "
                    "WHERE r.memory_id=? ORDER BY t.name",
                    (memory_id,),
                )
            ]
            result.append(item)
        return result

    @classmethod
    def current_snapshot(cls, manager, memory_ids: list[str]) -> list[dict]:
        """Read one consistent SQL revision for checking asynchronous index work."""
        with manager._connect() as conn:
            conn.execute("BEGIN")
            return cls.snapshot(conn, memory_ids)

    @staticmethod
    def record(
        conn, action: str, memory_scope: str, before: list[dict], after: list[dict]
    ) -> None:
        if before == after:
            return
        if any(item["memory_scope"] != memory_scope for item in before + after):
            raise HistoryConflict("学习变更涉及不同会话，已拒绝写入。")
        conn.execute(
            "INSERT INTO memory_learning_history(action,memory_scope,source_json,before_json,after_json,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (
                action,
                memory_scope,
                json.dumps(_source.get() or {}, ensure_ascii=False),
                json.dumps(before, ensure_ascii=False),
                json.dumps(after, ensure_ascii=False),
                time.time(),
            ),
        )

    @staticmethod
    def decode(row) -> dict:
        item = dict(row)
        for field in ("source", "before", "after"):
            item[field] = json.loads(item.pop(f"{field}_json"))
        return item

    @classmethod
    def list_records(
        cls, manager, memory_scope: str = "", limit: int = 30, offset: int = 0
    ) -> dict:
        with manager._connect() as conn:
            clauses = "WHERE memory_scope=?" if memory_scope else ""
            values = (memory_scope,) if memory_scope else ()
            total = conn.execute(
                f"SELECT COUNT(*) FROM memory_learning_history {clauses}", values
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM memory_learning_history {clauses} ORDER BY id DESC LIMIT ? OFFSET ?",
                (*values, limit, offset),
            ).fetchall()
            scopes = [
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT memory_scope FROM memory_learning_history ORDER BY memory_scope"
                )
            ]
        return {
            "ok": True,
            "items": [cls.decode(row) for row in rows],
            "total": total,
            "scopes": scopes,
        }

    @classmethod
    def undo(cls, manager, history_id: int, memory_scope: str) -> dict:
        """Restore one exact revision atomically, leaving index work retryable.

        Both before-only IDs and replacement IDs are checked under a write lock.
        Any later content, metadata, recall strength or deletion causes a conflict.
        """
        with manager._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM memory_learning_history WHERE id=? AND memory_scope=?",
                (history_id, memory_scope),
            ).fetchone()
            if row is None:
                raise LookupError("未找到该会话的学习记录。")
            record = cls.decode(row)
            if record["status"] == "undone":
                return record
            before = record["before"]
            after = record["after"]
            ids = list(dict.fromkeys(item["id"] for item in before + after))
            current = {item["id"]: item for item in cls.snapshot(conn, ids)}
            expected = {item["id"]: item for item in after}
            if current != expected:
                raise HistoryConflict(
                    "这些记忆在此次学习之后已被修改、合并或删除，无法安全撤销。"
                )
            for memory_id in ids:
                conn.execute(
                    "DELETE FROM memory_tag_rel WHERE memory_id=?", (memory_id,)
                )
                conn.execute("DELETE FROM memory_records WHERE id=?", (memory_id,))
            columns = ",".join(cls.COLUMNS)
            placeholders = ",".join("?" for _ in cls.COLUMNS)
            for item in before:
                conn.execute(
                    f"INSERT INTO memory_records({columns}) VALUES({placeholders})",
                    tuple(item[column] for column in cls.COLUMNS),
                )
                manager._upsert_tags_and_bind(conn, item["id"], item["tags"])
            undone_at = time.time()
            conn.execute(
                "UPDATE memory_learning_history SET status='undone',undone_at=?,index_sync='pending',index_error='' WHERE id=?",
                (undone_at, history_id),
            )
            conn.commit()
            record.update(
                status="undone",
                undone_at=undone_at,
                index_sync="pending",
                index_error="",
            )
        return record

    @staticmethod
    def set_index_state(manager, history_id: int, *, error: str = "") -> None:
        with manager._connect() as conn:
            conn.execute(
                "UPDATE memory_learning_history SET index_sync=?,index_error=? WHERE id=? AND status='undone'",
                ("pending" if error else "synced", str(error)[:400], history_id),
            )


async def undo_learning(plugin_context, history_id: int, memory_scope: str) -> dict:
    """Restore the source of truth, then refresh derived indexes idempotently."""
    import asyncio

    manager = plugin_context.get_component("memory_sql_manager")
    if manager is None:
        raise RuntimeError("记忆存储尚未初始化。")
    record = await asyncio.to_thread(
        MemoryHistory.undo, manager, history_id, memory_scope
    )
    if record["index_sync"] == "synced":
        return {"ok": True, **record}
    before_ids = [item["id"] for item in record["before"]]
    all_ids = list(
        dict.fromkeys([*before_ids, *(item["id"] for item in record["after"])])
    )
    try:
        await asyncio.to_thread(manager._ensure_fts_ready_sync)
        for _attempt in range(3):
            # Embedding can yield for seconds. Check again after it finishes so
            # a delayed retry never leaves an older revision in the index.
            snapshot = await asyncio.to_thread(
                MemoryHistory.current_snapshot, manager, all_ids
            )
            if any(item["memory_scope"] != memory_scope for item in snapshot):
                raise HistoryConflict("记忆作用域已经变更，索引同步已停止。")
            current_ids = {item["id"] for item in snapshot}
            deleted_ids = [
                memory_id for memory_id in all_ids if memory_id not in current_ids
            ]
            await asyncio.to_thread(
                manager._sync_memory_fts_batch_sync,
                upsert_ids=list(current_ids),
                delete_ids=deleted_ids,
            )
            cognitive = plugin_context.get_component("cognitive_service")
            if cognitive is not None:
                collection = cognitive.memory_index_collection
                if collection is None:
                    raise RuntimeError("向量记忆索引暂不可用。")
                if deleted_ids:
                    await asyncio.to_thread(collection.delete, ids=deleted_ids)
                rows = [
                    {
                        "id": item["id"],
                        "vector_text": manager.build_vector_text(
                            item["judgment"], item["tags"]
                        ),
                    }
                    for item in snapshot
                ]
                if rows:
                    await cognitive.vector_store.upsert_memory_index_rows(
                        collection=collection, rows=rows
                    )
            if snapshot == await asyncio.to_thread(
                MemoryHistory.current_snapshot, manager, all_ids
            ):
                break
        else:
            raise RuntimeError("记忆正在被持续修改，请稍后重试索引同步。")
        await asyncio.to_thread(MemoryHistory.set_index_state, manager, history_id)
        record.update(index_sync="synced", index_error="")
    except Exception as error:  # noqa: BLE001 - providers and indexes expose unrelated exception types.
        error_text = str(error).strip() or type(error).__name__
        await asyncio.to_thread(
            MemoryHistory.set_index_state, manager, history_id, error=error_text
        )
        record.update(index_sync="pending", index_error=error_text[:400])
    return {"ok": True, **record}
