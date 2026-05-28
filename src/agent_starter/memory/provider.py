"""进程级 MemoryStore 单例。默认 InMemoryStore；可按 settings opt-in 接 pgvector。"""
from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from agent_starter.memory.store import InMemoryStore, MemoryStore

_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = InMemoryStore()
    return _store


def set_memory_store(store: MemoryStore | None) -> None:
    global _store
    _store = store


def reset_memory_store() -> None:
    global _store
    _store = None


def memory_backend_configured(settings) -> bool:
    """是否配齐了 pgvector 后端（DSN + embedding）。"""
    return bool(settings.agent_pg_dsn and settings.agent_embed_base_url)


async def setup_memory_store_from_settings(
    settings,
    *,
    pool_factory: Callable[[str], Awaitable[Any]] | None = None,
    embedding_factory: Callable[[], Any] | None = None,
    store_factory: Callable[[Any, Any], MemoryStore] | None = None,
) -> Any | None:
    """按配置安装 MemoryStore；返回需要在 shutdown 时关闭的资源。

    只有同时配置 `AGENT_PG_DSN` 和 `AGENT_EMBED_BASE_URL` 才启用 pgvector store。
    """
    if not memory_backend_configured(settings):
        reset_memory_store()
        return None

    if pool_factory is None:
        import asyncpg
        pool_factory = asyncpg.create_pool
    if embedding_factory is None:
        from agent_starter.memory.embedding import EmbeddingClient
        embedding_factory = EmbeddingClient
    if store_factory is None:
        from agent_starter.memory.pgvector_store import PgVectorStore
        store_factory = PgVectorStore

    pool = await pool_factory(settings.agent_pg_dsn)
    try:
        dim = int(getattr(settings, "agent_embed_dim", 1536) or 1536)
        embedding = embedding_factory()
        store = _build_store(store_factory, pool, embedding, dim)
        await store.setup()
    except Exception:
        await close_memory_resource(pool)
        reset_memory_store()
        raise
    set_memory_store(store)
    return pool


def _build_store(store_factory: Callable[..., MemoryStore], pool: Any, embedding: Any, dim: int) -> MemoryStore:
    try:
        params = inspect.signature(store_factory).parameters
    except (TypeError, ValueError):
        params = {}
    if "dim" in params:
        return store_factory(pool, embedding, dim=dim)
    return store_factory(pool, embedding)


async def close_memory_resource(resource: Any | None) -> None:
    if resource is not None and hasattr(resource, "close"):
        maybe_awaitable = resource.close()
        if inspect.isawaitable(maybe_awaitable):
            await maybe_awaitable
