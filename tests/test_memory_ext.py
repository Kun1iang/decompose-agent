import pytest
from langchain_core.messages import HumanMessage

from agent_starter.memory.llm_extractor import extract_preferences_llm
from agent_starter.memory.provider import memory_backend_configured
from agent_starter.memory.store import InMemoryStore
from agent_starter.nodes.memory import write_memory
from tests.conftest import FakeLLM


@pytest.mark.asyncio
async def test_llm_extracts_enum_pref():
    llm = FakeLLM(responses=['[{"key":"tone","value":"direct"}]'])
    out = await extract_preferences_llm([HumanMessage(content="说话直接点")], llm=llm)
    assert [(p.key, p.value) for p in out] == [("tone", "direct")]


@pytest.mark.asyncio
async def test_llm_drops_non_enum_key():
    llm = FakeLLM(responses=['[{"key":"hairstyle","value":"x"},{"key":"verbosity","value":"concise"}]'])
    out = await extract_preferences_llm([HumanMessage(content="简洁")], llm=llm)
    assert [(p.key, p.value) for p in out] == [("verbosity", "concise")]


@pytest.mark.asyncio
async def test_llm_bad_json_failsoft():
    llm = FakeLLM(responses=["not json at all"])
    assert await extract_preferences_llm([HumanMessage(content="x")], llm=llm) == []


@pytest.mark.asyncio
async def test_write_memory_with_llm_extraction(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://x/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("OPENAI_MODEL", "m")
    monkeypatch.setenv("ENABLE_LLM_PREF_EXTRACTION", "1")
    store = InMemoryStore()
    llm = FakeLLM(responses=['[{"key":"tone","value":"direct"}]'])
    await write_memory({"user_id": 1, "messages": [HumanMessage(content="说话直接点")]}, store=store, llm=llm)
    rec = await store.recall(1, "q")
    assert ("tone", "direct") in [(p.key, p.value) for p in rec.prefs]


def test_memory_backend_configured():
    class _S:
        agent_pg_dsn = ""
        agent_embed_base_url = ""
    assert memory_backend_configured(_S()) is False

    class _S2:
        agent_pg_dsn = "postgres://x"
        agent_embed_base_url = "https://e"
    assert memory_backend_configured(_S2()) is True


@pytest.mark.asyncio
async def test_setup_memory_store_from_settings_configures_pgvector_store():
    from agent_starter.memory import provider

    class Settings:
        agent_pg_dsn = "postgres://x"
        agent_embed_base_url = "https://embed"

    class Pool:
        closed = False

        async def close(self):
            self.closed = True

    class Store:
        def __init__(self, pool, embedding, dim=1536):
            self.pool = pool
            self.embedding = embedding
            self.dim = dim
            self.setup_called = False

        async def setup(self):
            self.setup_called = True

    pool = Pool()

    async def create_pool(dsn):
        assert dsn == "postgres://x"
        return pool

    resource = await provider.setup_memory_store_from_settings(
        Settings(),
        pool_factory=create_pool,
        embedding_factory=lambda: "embedding",
        store_factory=Store,
    )

    store = provider.get_memory_store()
    assert isinstance(store, Store)
    assert store.pool is pool
    assert store.embedding == "embedding"
    assert store.dim == 1536
    assert store.setup_called is True
    await provider.close_memory_resource(resource)
    assert pool.closed is True


@pytest.mark.asyncio
async def test_setup_memory_store_closes_pool_when_setup_fails():
    from agent_starter.memory import provider

    class Settings:
        agent_pg_dsn = "postgres://x"
        agent_embed_base_url = "https://embed"
        agent_embed_dim = 768

    class Pool:
        closed = False

        async def close(self):
            self.closed = True

    class Store:
        def __init__(self, pool, embedding, dim=1536):
            self.dim = dim

        async def setup(self):
            raise RuntimeError("setup failed")

    pool = Pool()

    async def create_pool(dsn):
        return pool

    with pytest.raises(RuntimeError, match="setup failed"):
        await provider.setup_memory_store_from_settings(
            Settings(),
            pool_factory=create_pool,
            embedding_factory=lambda: "embedding",
            store_factory=Store,
        )

    assert pool.closed is True
    assert isinstance(provider.get_memory_store(), InMemoryStore)


@pytest.mark.asyncio
async def test_close_memory_resource_accepts_sync_close():
    from agent_starter.memory.provider import close_memory_resource

    class Resource:
        closed = False

        def close(self):
            self.closed = True

    resource = Resource()

    await close_memory_resource(resource)

    assert resource.closed is True
