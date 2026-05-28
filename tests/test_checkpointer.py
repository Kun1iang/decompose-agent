import pytest
from langgraph.checkpoint.memory import MemorySaver


@pytest.mark.asyncio
async def test_checkpointer_context_defaults_to_memory_saver():
    from agent_starter.serving.checkpointer import checkpointer_context

    class Settings:
        agent_pg_dsn = ""

    async with checkpointer_context(Settings()) as checkpointer:
        assert isinstance(checkpointer, MemorySaver)
