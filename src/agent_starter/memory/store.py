"""MemoryStore 协议 + 零依赖 InMemoryStore 默认实现。

接口刻意小而稳：换 Postgres / pgvector 语义召回时实现同一协议即可，节点与 agent 不改。
recall 的 query 参数当前 InMemoryStore 忽略（always-on 全返）；语义实现里用它做向量检索。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_starter.memory.models import Observation, Preference, RecalledMemory

_RECENT_OBS = 5


@runtime_checkable
class MemoryStore(Protocol):
    async def recall(self, user_id: int, query: str) -> RecalledMemory: ...
    async def upsert_preference(self, user_id: int, key: str, value: str) -> None: ...
    async def add_observation(self, user_id: int, text: str) -> None: ...


class InMemoryStore:
    """进程内默认实现：偏好 KV（latest-wins）+ 近期观察。重启即丢。"""

    def __init__(self) -> None:
        self._prefs: dict[int, dict[str, str]] = {}
        self._obs: dict[int, list[str]] = {}

    async def recall(self, user_id: int, query: str) -> RecalledMemory:
        prefs = [Preference(k, v) for k, v in self._prefs.get(user_id, {}).items()]
        obs = [Observation(t) for t in self._obs.get(user_id, [])[-_RECENT_OBS:]]
        return RecalledMemory(prefs=prefs, observations=obs)

    async def upsert_preference(self, user_id: int, key: str, value: str) -> None:
        self._prefs.setdefault(user_id, {})[key] = value  # latest-wins

    async def add_observation(self, user_id: int, text: str) -> None:
        self._obs.setdefault(user_id, []).append(text)
