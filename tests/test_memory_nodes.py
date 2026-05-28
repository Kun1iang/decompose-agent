import pytest
from langchain_core.messages import HumanMessage

from agent_starter.memory.store import InMemoryStore
from agent_starter.nodes.memory import recall_memory, write_memory


@pytest.mark.asyncio
async def test_recall_returns_seeded_prefs():
    store = InMemoryStore()
    await store.upsert_preference(1, "nickname", "老张")
    out = await recall_memory({"user_id": 1, "messages": [HumanMessage(content="在吗")]}, store=store)
    rec = out["recalled_memory"]
    assert [(p.key, p.value) for p in rec.prefs] == [("nickname", "老张")]


@pytest.mark.asyncio
async def test_write_extracts_and_persists_pref():
    store = InMemoryStore()
    await write_memory({"user_id": 1, "messages": [HumanMessage(content="叫我老张")]}, store=store)
    rec = await store.recall(1, "q")
    assert [(p.key, p.value) for p in rec.prefs] == [("nickname", "老张")]


@pytest.mark.asyncio
async def test_write_no_pref_is_noop():
    store = InMemoryStore()
    out = await write_memory({"user_id": 1, "messages": [HumanMessage(content="今天几号")]}, store=store)
    assert out == {}
    assert (await store.recall(1, "q")).is_empty()
