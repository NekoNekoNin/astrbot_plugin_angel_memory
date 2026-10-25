"""Real temporary SQL/BM25/FAISS coverage for revision audit and restoration."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from quart import Quart

from llm_memory.components.faiss_memory_index import FaissVectorStore
from llm_memory.components.memory_history import (
    HistoryConflict,
    MemoryHistory,
    learning_source,
    undo_learning,
)
from llm_memory.components.memory_sql_manager import MemorySqlManager
from llm_memory.components.sqlite_vector_index import SqliteVectorStore
from llm_memory.models.data_models import ValidationError


@pytest.fixture
def manager(tmp_path):
    return MemorySqlManager(tmp_path / "test.db")


def create(manager, text="user prefers tea", scope="private:test:user:persona"):
    return manager._remember_sync(
        "knowledge", text, "user explicitly said so", ["preference"], memory_scope=scope
    )


def history(manager):
    return MemoryHistory.list_records(manager)["items"]


def context(manager, cognitive=None):
    return SimpleNamespace(
        get_component=lambda name: {
            "memory_sql_manager": manager,
            "cognitive_service": cognitive,
        }.get(name)
    )


class Embedding:
    ready = True

    async def embed_documents(self, texts):
        return [[1.0, 0.5, 0.2] for _ in texts] if self.ready else []

    def get_model_info(self):
        return {"provider_id": "history-test", "model_name": "fake", "dimension": 3}

    def get_provider_type(self):
        return "api"

    def is_available(self):
        return True


def runtime_classes():
    root = Path(__file__).resolve().parents[1]
    package_name = "history_runtime_test_plugin"
    for suffix, path in (
        ("", root),
        (".core", root / "core"),
        (".core.utils", root / "core/utils"),
    ):
        name = package_name + suffix
        if name not in sys.modules:
            package = types.ModuleType(name)
            package.__path__ = [str(path)]
            sys.modules[name] = package
    from history_runtime_test_plugin.core.memory_runtime import (
        SimpleMemoryRuntime,
        VectorMemoryRuntime,
    )
    from history_runtime_test_plugin.llm_memory.service.cognitive_service import (
        CognitiveService,
    )

    return SimpleMemoryRuntime, VectorMemoryRuntime, CognitiveService


@pytest.mark.parametrize("vector", [False, True])
def test_real_runtime_automatic_create_correction_merge_and_source(
    manager, tmp_path, vector
):
    SimpleMemoryRuntime, VectorMemoryRuntime, CognitiveService = runtime_classes()
    scope = "private:test:learner:persona"
    cognitive = None
    if vector:
        store = FaissVectorStore(
            embedding_provider=Embedding(),
            index_dir=tmp_path / "runtime-faiss",
            provider_id="history-test",
        )
        cognitive = CognitiveService(store, memory_sql_manager=manager)
        runtime = VectorMemoryRuntime(cognitive)
    else:
        runtime = SimpleMemoryRuntime(manager)

    async def run():
        with learning_source(
            "auto_learning",
            session_id="runtime-session",
            excerpt="please remember my preference",
            message_ids=["m1"],
        ):
            first, second = await runtime.feedback(
                memory_actions=[
                    {
                        "action": "create",
                        "memory": {"judgment": "prefers tea", "tags": ["tea"]},
                    },
                    {
                        "action": "create",
                        "memory": {"judgment": "prefers quiet", "tags": ["quiet"]},
                    },
                ],
                memory_scope=scope,
            )
            updated = (
                await runtime.feedback(
                    memory_actions=[
                        {
                            "action": "updata",
                            "source_memory_ids": [first.id],
                            "memory": {
                                "judgment": "prefers coffee",
                                "tags": ["coffee"],
                            },
                        }
                    ],
                    memory_scope=scope,
                )
            )[0]
            merged = (
                await runtime.feedback(
                    memory_actions=[
                        {
                            "action": "merge",
                            "source_memory_ids": [updated.id, second.id],
                            "memory": {
                                "judgment": "prefers quiet coffee",
                                "tags": ["coffee", "quiet"],
                            },
                        }
                    ],
                    memory_scope=scope,
                )
            )[0]
        records = history(manager)
        assert [record["action"] for record in records] == [
            "merge",
            "update",
            "create",
            "create",
        ]
        assert all(record["memory_scope"] == scope for record in records)
        assert all(record["source"]["message_ids"] == ["m1"] for record in records)
        assert all(
            record["source"]["session_id"] == "runtime-session" for record in records
        )
        undone = await undo_learning(
            context(manager, cognitive), records[0]["id"], scope
        )
        assert undone["index_sync"] == "synced"
        assert {
            item.id
            for item in await runtime.get_memories_by_ids(
                [first.id, second.id, updated.id, merged.id], memory_scope=scope
            )
        } == {second.id, updated.id}
        if vector:
            assert set(cognitive.memory_index_collection.list_ids()) == {
                second.id,
                updated.id,
            }

    asyncio.run(run())


def test_single_source_merge_keeps_action_and_multi_source_correction_is_refused(
    manager,
):
    first, second = create(manager, "first"), create(manager, "second")

    async def run():
        await manager.process_feedback(
            memory_actions=[
                {
                    "action": "merge",
                    "source_memory_ids": [first.id],
                    "memory": {"judgment": "single source merge", "tags": []},
                }
            ],
            memory_scope=first.memory_scope,
        )
        assert history(manager)[0]["action"] == "merge"
        with pytest.raises(ValidationError):
            await manager.process_feedback(
                memory_actions=[
                    {
                        "action": "updata",
                        "source_memory_ids": [first.id, second.id],
                        "memory": {"judgment": "invalid correction", "tags": []},
                    }
                ],
                memory_scope=first.memory_scope,
            )

    asyncio.run(run())


def test_create_audit_and_source_survive_reopen(manager):
    async def run():
        with learning_source(
            "auto_learning", session_id="test-session", excerpt="please remember tea"
        ):
            memory = await manager.remember(
                "knowledge",
                "user likes tea",
                "explicit",
                ["tea"],
                memory_scope="private:test",
            )
        return memory

    memory = asyncio.run(run())
    reopened = MemorySqlManager(manager.db_path)
    record = history(reopened)[0]
    assert record["source"]["session_id"] == "test-session"
    assert record["source"]["excerpt"] == "please remember tea"
    assert record["before"] == []
    assert record["after"][0]["id"] == memory.id
    assert record["memory_scope"] == "private:test"


def test_no_fabricated_old_history(manager):
    with manager._connect() as conn:
        conn.execute(
            "INSERT INTO memory_records(id,memory_type,judgment,reasoning,strength,is_active,memory_scope,created_at,updated_at) VALUES('old','知识记忆','old fact','old',1,0,'private:test',1,1)"
        )
    assert history(manager) == []


def test_parallel_learning_sources_remain_isolated(manager):
    async def run():
        async def remember(name):
            with learning_source(
                "auto_learning", session_id=name, excerpt=f"source {name}"
            ):
                await asyncio.sleep(0)
                await manager.remember(
                    "knowledge", name, "test", [name], memory_scope=name
                )

        await asyncio.gather(remember("private:test:A"), remember("group:test:B"))

    asyncio.run(run())
    records = history(manager)
    assert len(records) == 2
    assert all(
        record["source"]["session_id"] == record["memory_scope"] for record in records
    )
    assert all(
        record["source"]["excerpt"] == f"source {record['memory_scope']}"
        for record in records
    )


def test_create_undo_and_repeat_are_idempotent(manager):
    memory = create(manager)
    record = history(manager)[0]
    result = asyncio.run(
        undo_learning(context(manager), record["id"], memory.memory_scope)
    )
    assert result["status"] == "undone" and result["index_sync"] == "synced"
    assert manager._get_memories_by_ids_sync([memory.id]) == []
    again = asyncio.run(
        undo_learning(context(manager), record["id"], memory.memory_scope)
    )
    assert again["undone_at"] == result["undone_at"]
    assert len(history(manager)) == 1


def test_update_undo_restores_exact_previous_row_and_tags(manager):
    old = create(manager)
    with manager._connect() as conn:
        expected = MemoryHistory.snapshot(conn, [old.id])
    new = asyncio.run(
        manager.process_feedback(
            memory_actions=[
                {
                    "action": "updata",
                    "source_memory_ids": [old.id],
                    "memory": {
                        "judgment": "user now prefers coffee",
                        "reasoning": "explicit correction",
                        "tags": ["coffee"],
                    },
                }
            ],
            memory_scope=old.memory_scope,
        )
    )[0]
    record = history(manager)[0]
    assert record["action"] == "update"
    assert record["before"] == expected
    asyncio.run(undo_learning(context(manager), record["id"], old.memory_scope))
    with manager._connect() as conn:
        assert MemoryHistory.snapshot(conn, [old.id]) == expected
    assert manager._get_memories_by_ids_sync([new.id]) == []


def test_merge_undo_restores_both_sources_only(manager):
    first = create(manager, "fact A")
    second = create(manager, "fact B")
    unrelated = create(manager, "other session", "group:other:persona")
    new = manager._merge_action_sync(
        [first.id, second.id],
        {"judgment": "facts AB", "tags": ["combined"]},
        first.memory_scope,
    )
    record = history(manager)[0]
    assert record["action"] == "merge" and len(record["before"]) == 2
    asyncio.run(undo_learning(context(manager), record["id"], first.memory_scope))
    assert {
        memory.id
        for memory in manager._get_memories_by_ids_sync(
            [first.id, second.id, new.id, unrelated.id]
        )
    } == {first.id, second.id, unrelated.id}


def test_cross_scope_undo_and_merge_are_refused(manager):
    first = create(manager)
    second = create(manager, "other scope", "group:other:persona")
    with pytest.raises(LookupError):
        MemoryHistory.undo(manager, history(manager)[0]["id"], first.memory_scope)
    with pytest.raises(ValidationError):
        manager._merge_action_sync(
            [first.id, second.id], {"judgment": "bad", "tags": []}, first.memory_scope
        )
    assert len(manager._get_memories_by_ids_sync([first.id, second.id])) == 2
    filtered = MemoryHistory.list_records(manager, first.memory_scope)
    assert (
        filtered["total"] == 1
        and filtered["items"][0]["memory_scope"] == first.memory_scope
    )


@pytest.mark.parametrize("later", ["edit", "delete", "reinforce"])
def test_undo_refuses_later_changes(manager, later):
    memory = create(manager)
    record = history(manager)[0]
    with manager._connect() as conn:
        if later == "edit":
            conn.execute(
                "UPDATE memory_records SET judgment='new fact',updated_at=updated_at+1 WHERE id=?",
                (memory.id,),
            )
        elif later == "delete":
            conn.execute("DELETE FROM memory_records WHERE id=?", (memory.id,))
        else:
            conn.execute(
                "UPDATE memory_records SET strength=strength+1 WHERE id=?", (memory.id,)
            )
    with pytest.raises(HistoryConflict):
        MemoryHistory.undo(manager, record["id"], memory.memory_scope)
    assert history(manager)[0]["status"] == "committed"


def test_audit_failure_rolls_back_memory_and_merge(manager, monkeypatch):
    memory = create(manager)

    def fail(*args):
        raise sqlite3.OperationalError("simulated audit disk failure")

    monkeypatch.setattr(MemoryHistory, "record", fail)
    with pytest.raises(sqlite3.OperationalError):
        manager._remember_sync(
            "knowledge",
            "must not commit",
            "test",
            ["rollback-only-tag"],
            memory_scope=memory.memory_scope,
        )
    assert "rollback-only-tag" not in manager._tag_names
    with pytest.raises(sqlite3.OperationalError):
        manager._merge_action_sync(
            [memory.id],
            {"judgment": "must not replace", "tags": []},
            memory.memory_scope,
        )
    assert manager._get_memories_by_ids_sync([memory.id])[0].judgment == memory.judgment
    assert len(manager._get_memories_by_ids_sync([memory.id])) == 1
    with manager._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM memory_records").fetchone()[0] == 1
    assert len(history(manager)) == 1


def test_undo_write_failure_rolls_back_and_can_retry(manager, monkeypatch):
    old = create(manager)
    new = manager._merge_action_sync(
        [old.id], {"judgment": "replacement", "tags": ["new"]}, old.memory_scope
    )
    record = history(manager)[0]
    original = manager._upsert_tags_and_bind

    def fail(*args):
        raise sqlite3.OperationalError("simulated restore failure")

    monkeypatch.setattr(manager, "_upsert_tags_and_bind", fail)
    with pytest.raises(sqlite3.OperationalError):
        MemoryHistory.undo(manager, record["id"], old.memory_scope)
    assert manager._get_memories_by_ids_sync([new.id])
    assert not manager._get_memories_by_ids_sync([old.id])
    assert history(manager)[0]["status"] == "committed"
    monkeypatch.setattr(manager, "_upsert_tags_and_bind", original)
    asyncio.run(undo_learning(context(manager), record["id"], old.memory_scope))
    assert manager._get_memories_by_ids_sync([old.id])


@pytest.mark.parametrize(
    "error", [RuntimeError("temporary index failure"), TimeoutError()]
)
def test_index_failure_is_pending_and_retry_does_not_restore_sql_twice(
    manager, monkeypatch, error
):
    memory = create(manager)
    record = history(manager)[0]
    original = manager._sync_memory_fts_batch_sync

    def fail(**kwargs):
        raise error

    monkeypatch.setattr(manager, "_sync_memory_fts_batch_sync", fail)
    result = asyncio.run(
        undo_learning(context(manager), record["id"], memory.memory_scope)
    )
    assert result["status"] == "undone" and result["index_sync"] == "pending"
    assert history(manager)[0]["index_sync"] == "pending"
    assert not manager._get_memories_by_ids_sync([memory.id])
    monkeypatch.setattr(manager, "_sync_memory_fts_batch_sync", original)
    retried = asyncio.run(
        undo_learning(context(manager), record["id"], memory.memory_scope)
    )
    assert retried["index_sync"] == "synced"
    assert retried["undone_at"] == result["undone_at"]


def test_real_vector_restore_matches_sql(manager, tmp_path):
    async def run():
        store = FaissVectorStore(
            embedding_provider=Embedding(),
            index_dir=tmp_path / "faiss",
            provider_id="history-test",
        )
        collection = store.get_or_create_collection_with_dimension_check("memory_index")
        old = create(manager)
        new = manager._merge_action_sync(
            [old.id], {"judgment": "new preference", "tags": ["new"]}, old.memory_scope
        )
        await store.upsert_memory_index_rows(
            collection, [{"id": new.id, "vector_text": new.judgment}]
        )
        result = await undo_learning(
            context(
                manager,
                SimpleNamespace(memory_index_collection=collection, vector_store=store),
            ),
            history(manager)[0]["id"],
            old.memory_scope,
        )
        assert result["index_sync"] == "synced"
        assert collection.list_ids() == [old.id]
        assert manager._get_memories_by_ids_sync(
            [old.id]
        ) and not manager._get_memories_by_ids_sync([new.id])

    asyncio.run(run())


@pytest.mark.parametrize("store_class", [FaissVectorStore, SqliteVectorStore])
def test_empty_embedding_leaves_undo_pending_until_real_retry(
    manager, tmp_path, store_class
):
    embedding = Embedding()
    embedding.ready = False
    store = store_class(
        embedding_provider=embedding,
        index_dir=tmp_path / "empty-vector",
        provider_id="history-test",
    )
    collection = store.get_or_create_collection_with_dimension_check("memory_index")
    old = create(manager)
    new = manager._merge_action_sync(
        [old.id], {"judgment": "new", "tags": []}, old.memory_scope
    )
    record = history(manager)[0]
    plugin_context = context(
        manager, SimpleNamespace(memory_index_collection=collection, vector_store=store)
    )

    async def run():
        pending = await undo_learning(plugin_context, record["id"], old.memory_scope)
        assert pending["index_sync"] == "pending" and pending["index_error"]
        assert manager._get_memories_by_ids_sync(
            [old.id]
        ) and not manager._get_memories_by_ids_sync([new.id])
        embedding.ready = True
        retried = await undo_learning(plugin_context, record["id"], old.memory_scope)
        assert retried["index_sync"] == "synced"
        assert collection.list_ids() == [old.id]

    asyncio.run(run())


def test_delayed_index_retry_rechecks_concurrent_sql_change(
    manager, tmp_path, monkeypatch
):
    store = FaissVectorStore(
        embedding_provider=Embedding(),
        index_dir=tmp_path / "delayed",
        provider_id="history-test",
    )
    collection = store.get_or_create_collection_with_dimension_check("memory_index")
    old = create(manager)
    manager._merge_action_sync(
        [old.id], {"judgment": "replacement", "tags": []}, old.memory_scope
    )
    record = history(manager)[0]
    original = store.upsert_memory_index_rows
    calls = []

    async def delayed(collection, rows):
        await original(collection, rows)
        calls.append(rows)
        if len(calls) == 1:
            with manager._connect() as conn:
                conn.execute(
                    "UPDATE memory_records SET judgment='latest concurrent fact',updated_at=updated_at+1 WHERE id=?",
                    (old.id,),
                )

    monkeypatch.setattr(store, "upsert_memory_index_rows", delayed)
    result = asyncio.run(
        undo_learning(
            context(
                manager,
                SimpleNamespace(memory_index_collection=collection, vector_store=store),
            ),
            record["id"],
            old.memory_scope,
        )
    )
    assert result["index_sync"] == "synced" and len(calls) == 2
    with collection._connect() as conn:
        indexed = conn.execute(
            "SELECT vector_text FROM index_rows WHERE item_id=?", (old.id,)
        ).fetchone()[0]
    assert "latest concurrent fact" in indexed


def test_api_returns_conflict_and_rejects_missing_scope(manager):
    package_name = "history_test_plugin"
    package = types.ModuleType(package_name)
    package.__path__ = [str(Path(__file__).resolve().parents[1])]
    sys.modules[package_name] = package
    from history_test_plugin.web_api.history_api import HistoryAPI

    # This route uses the same package-qualified central manager and file.
    app = Quart(__name__)
    api = HistoryAPI(context(manager))
    app.add_url_rule("/history", view_func=api.list_records)
    app.add_url_rule("/undo", view_func=api.undo, methods=["POST"])
    memory = create(manager)
    record = history(manager)[0]
    with manager._connect() as conn:
        conn.execute("DELETE FROM memory_records WHERE id=?", (memory.id,))

    async def run():
        client = app.test_client()
        response = await client.get("/history")
        assert (await response.get_json())["total"] == 1
        assert (
            await client.post("/undo", json={"id": record["id"]})
        ).status_code == 400
        response = await client.post(
            "/undo", json={"id": record["id"], "memory_scope": memory.memory_scope}
        )
        assert response.status_code == 409
        assert (await response.get_json())["code"] == "conflict"

    asyncio.run(run())
