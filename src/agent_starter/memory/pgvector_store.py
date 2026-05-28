"""PgVectorStore —— MemoryStore 的 Postgres + pgvector 参考实现（opt-in）。

偏好走结构化 KV（latest-wins，UNIQUE 约束）；观察走 embedding + cosine top-k 语义召回。
刻意**不做 ConflictDetector**——KV latest-wins 已覆盖高价值偏好；语义层只做检索，
合并/去重的复杂度与收益权衡见 docs/concepts-memory.md。

⚠️ 未经本仓自动化验证（CI 无 PG/pgvector）。需 `pip install -e ".[pg]"` + 可连的
Postgres（装了 pgvector 扩展）+ embedding 端点，并在你环境跑 `setup()` 后验证。
"""
from __future__ import annotations

import structlog

from agent_starter.memory.embedding import EmbeddingClient
from agent_starter.memory.models import Observation, Preference, RecalledMemory

logger = structlog.get_logger(__name__)

_RECENT_OBS = 5


class PgVectorStore:
    def __init__(self, pool, embedding: EmbeddingClient, dim: int = 1536) -> None:
        self._pool = pool            # asyncpg pool
        self._emb = embedding
        self._dim = dim

    async def setup(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS agent_prefs ("
                "  user_id BIGINT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,"
                "  updated_at TIMESTAMPTZ DEFAULT now(),"
                "  PRIMARY KEY (user_id, key))"
            )
            await conn.execute(
                f"CREATE TABLE IF NOT EXISTS agent_observations ("
                f"  id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL,"
                f"  text TEXT NOT NULL, embedding vector({self._dim}),"
                f"  created_at TIMESTAMPTZ DEFAULT now())"
            )

    async def upsert_preference(self, user_id: int, key: str, value: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO agent_prefs (user_id, key, value) VALUES ($1,$2,$3) "
                "ON CONFLICT (user_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                user_id, key, value,
            )

    async def add_observation(self, user_id: int, text: str) -> None:
        vec = await self._emb.aembed(text)
        async with self._pool.acquire() as conn:
            if vec is None:
                await conn.execute(
                    "INSERT INTO agent_observations (user_id, text) VALUES ($1,$2)",
                    user_id, text,
                )
            else:
                await conn.execute(
                    "INSERT INTO agent_observations (user_id, text, embedding) VALUES ($1,$2,$3)",
                    user_id, text, str(vec),
                )

    async def recall(self, user_id: int, query: str) -> RecalledMemory:
        async with self._pool.acquire() as conn:
            pref_rows = await conn.fetch(
                "SELECT key, value FROM agent_prefs WHERE user_id=$1 ORDER BY updated_at DESC",
                user_id,
            )
            qvec = await self._emb.aembed(query)
            if qvec is None:
                obs_rows = await conn.fetch(
                    "SELECT text FROM agent_observations WHERE user_id=$1 "
                    "ORDER BY created_at DESC LIMIT $2",
                    user_id, _RECENT_OBS,
                )
            else:
                obs_rows = await conn.fetch(
                    "SELECT text FROM agent_observations WHERE user_id=$1 AND embedding IS NOT NULL "
                    "ORDER BY embedding <=> $2 LIMIT $3",
                    user_id, str(qvec), _RECENT_OBS,
                )
        return RecalledMemory(
            prefs=[Preference(r["key"], r["value"]) for r in pref_rows],
            observations=[Observation(r["text"]) for r in obs_rows],
        )
