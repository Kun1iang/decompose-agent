"""checkpointer 生命周期工厂。默认 MemorySaver；配 DSN 时 opt-in Postgres。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from langgraph.checkpoint.memory import MemorySaver


def make_memory_checkpointer() -> MemorySaver:
    return MemorySaver()


@asynccontextmanager
async def checkpointer_context(settings):
    """Yield a checkpointer with the correct lifespan for the configured backend."""
    dsn = getattr(settings, "agent_pg_dsn", "") or ""
    if not dsn:
        yield make_memory_checkpointer()
        return

    # Lazy import keeps the default path free of optional [pg] dependencies.
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncPostgresSaver.from_conn_string(dsn) as saver:
        await saver.setup()
        yield saver
