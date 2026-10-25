"""Authenticated dashboard routes for learning revisions and safe undo."""

from __future__ import annotations

import asyncio
import sqlite3

from quart import jsonify, request

from ..llm_memory.components.memory_history import (
    HistoryConflict,
    MemoryHistory,
    undo_learning,
)


class HistoryAPI:
    def __init__(self, plugin_context):
        self.plugin_context = plugin_context

    async def list_records(self):
        manager = self.plugin_context.get_component("memory_sql_manager")
        if manager is None:
            return jsonify(
                {
                    "ok": True,
                    "items": [],
                    "total": 0,
                    "scopes": [],
                    "note": "记忆存储尚未初始化。",
                }
            )
        try:
            limit = max(1, min(100, int(request.args.get("limit", 30))))
            offset = max(0, int(request.args.get("offset", 0)))
        except (ValueError, TypeError):
            return jsonify({"ok": False, "error": "分页参数无效。"}), 400
        result = await asyncio.to_thread(
            MemoryHistory.list_records,
            manager,
            str(request.args.get("memory_scope", "")).strip(),
            limit,
            offset,
        )
        return jsonify(result)

    async def undo(self):
        data = await request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "需要 JSON 对象参数。"}), 400
        try:
            raw_id = data.get("id", 0)
            if isinstance(raw_id, (bool, float)):
                raise TypeError
            history_id = int(raw_id)
            memory_scope = str(data.get("memory_scope", "")).strip()
            if history_id < 1 or not memory_scope:
                raise ValueError
        except (ValueError, TypeError):
            return jsonify(
                {"ok": False, "error": "需要有效的 id 和精确的 memory_scope。"}
            ), 400
        try:
            result = await undo_learning(self.plugin_context, history_id, memory_scope)
            return jsonify(result)
        except LookupError as error:
            return jsonify({"ok": False, "error": str(error)}), 404
        except HistoryConflict as error:
            return jsonify({"ok": False, "error": str(error), "code": "conflict"}), 409
        except RuntimeError as error:
            return jsonify({"ok": False, "error": str(error)}), 503
        except (sqlite3.Error, OSError):
            return jsonify(
                {"ok": False, "error": "记忆数据库暂时无法写入，请稍后重试。"}
            ), 503
