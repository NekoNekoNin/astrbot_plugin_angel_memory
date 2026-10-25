"""Trusted note ownership, independent of note text or model supplied arguments."""
import re
from pathlib import PurePosixPath


LEGACY_NOTE_SCOPE = "legacy_unattributed"
_SESSION_SCOPE = re.compile(r"session_[0-9a-f]{64}\Z")


def require_session_scope(memory_scope: str) -> str:
    if not isinstance(memory_scope, str) or not _SESSION_SCOPE.fullmatch(memory_scope):
        raise ValueError("无法确定笔记所属会话，操作已拒绝。")
    return memory_scope


def note_scope_from_path(relative_path: str) -> str:
    parts = PurePosixPath(str(relative_path).replace("\\", "/")).parts
    if len(parts) >= 4 and parts[:2] == (".angel", "note") and _SESSION_SCOPE.fullmatch(parts[2]):
        if ".." not in parts:
            return parts[2]
    return LEGACY_NOTE_SCOPE
