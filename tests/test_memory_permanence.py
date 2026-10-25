"""Exercise retention flags through real feedback replacements and SQL audit."""

from __future__ import annotations

import asyncio

import pytest

from llm_memory.components.memory_history import MemoryHistory
from llm_memory.components.memory_sql_manager import MemorySqlManager


@pytest.mark.parametrize(
    ("action", "source_flags", "override", "expected"),
    [
        ("updata", (True,), None, True),
        ("updata", (False,), None, False),
        ("updata", (True,), False, False),
        ("updata", (False,), True, True),
        ("merge", (False, True), None, True),
        ("merge", (True, False), None, True),
        ("merge", (False, False), None, False),
        ("merge", (True, True), None, True),
        ("merge", (True, False), False, False),
        ("merge", (False, False), True, True),
    ],
    ids=[
        "update-inherits-permanent",
        "update-inherits-passive",
        "update-explicit-passive",
        "update-explicit-permanent",
        "merge-inherits-last-permanent",
        "merge-inherits-first-permanent",
        "merge-keeps-passive",
        "merge-keeps-permanent",
        "merge-explicit-passive",
        "merge-explicit-permanent",
    ],
)
def test_feedback_replacement_preserves_retention_unless_explicitly_overridden(
    tmp_path, action, source_flags, override, expected
):
    manager = MemorySqlManager(tmp_path / "retention.db")
    scope = "private:test:permanence:persona"
    sources = [
        manager._remember_sync(
            "knowledge",
            f"Test preference {index}",
            "Temporary regression fixture",
            ["retention-test"],
            is_active=flag,
            strength=50 if flag else 2,
            memory_scope=scope,
        )
        for index, flag in enumerate(source_flags)
    ]
    target = {
        "type": "knowledge",
        "judgment": "Updated test preference",
        "reasoning": "The user corrected a preference",
        "tags": ["retention-test", "corrected"],
    }
    if override is not None:
        target["is_active"] = override

    replaced = asyncio.run(
        manager.process_feedback(
            memory_actions=[
                {
                    "action": action,
                    "source_memory_ids": [source.id for source in sources],
                    "memory": target,
                }
            ],
            memory_scope=scope,
        )
    )

    assert len(replaced) == 1
    assert replaced[0].is_active is expected
    assert replaced[0].strength == sum(source.strength for source in sources)
    persisted = manager._get_memories_by_ids_sync([replaced[0].id])[0]
    assert persisted.is_active is expected
    assert manager._get_memories_by_ids_sync([source.id for source in sources]) == []
    revision = MemoryHistory.list_records(manager, scope)["items"][0]
    assert revision["action"] == ("update" if action == "updata" else "merge")
    assert sorted(row["is_active"] for row in revision["before"]) == sorted(
        source_flags
    )
    assert bool(revision["after"][0]["is_active"]) is expected
