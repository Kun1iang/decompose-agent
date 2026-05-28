"""会话索引：哪个用户有哪些会话（thread）。与 checkpointer 分工——

checkpointer 存“每个 thread 的完整对话状态”；SessionStore 只存“用户→会话列表”的轻量索引
（标题 + 最近活跃），给会话列表 UI 用。默认 InMemorySessionStore，可换 PG 实现同协议。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class SessionMeta:
    thread_id: str
    title: str
    updated_at: float
    seq: int = 0  # 单调序，仅内部排序用（不对外序列化）


@runtime_checkable
class SessionStore(Protocol):
    async def touch(self, user_id: int, thread_id: str, title: str) -> None: ...
    async def list_for_user(self, user_id: int) -> list[SessionMeta]: ...
    async def delete(self, user_id: int, thread_id: str) -> bool: ...


class InMemorySessionStore:
    def __init__(self) -> None:
        self._by_user: dict[int, dict[str, SessionMeta]] = {}
        self._seq = 0

    async def touch(self, user_id: int, thread_id: str, title: str) -> None:
        self._seq += 1
        sessions = self._by_user.setdefault(user_id, {})
        m = sessions.get(thread_id)
        if m is None:
            sessions[thread_id] = SessionMeta(
                thread_id=thread_id, title=(title[:50] or thread_id),
                updated_at=time.time(), seq=self._seq,
            )
        else:
            m.updated_at = time.time()  # 标题保留首条
            m.seq = self._seq

    async def list_for_user(self, user_id: int) -> list[SessionMeta]:
        return sorted(self._by_user.get(user_id, {}).values(), key=lambda m: m.seq, reverse=True)

    async def delete(self, user_id: int, thread_id: str) -> bool:
        return self._by_user.get(user_id, {}).pop(thread_id, None) is not None


_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        _store = InMemorySessionStore()
    return _store


def set_session_store(store: SessionStore | None) -> None:
    global _store
    _store = store


def reset_session_store() -> None:
    global _store
    _store = None
