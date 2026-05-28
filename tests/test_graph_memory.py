import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agent_starter.graph import build_graph
from agent_starter.memory.provider import set_memory_store
from agent_starter.memory.store import InMemoryStore
from agent_starter.tasks import domains as d
from tests.conftest import FakeLLM


@pytest.mark.asyncio
async def test_nickname_remembered_across_turns(monkeypatch):
    d.clear_registry()              # 无域：classify 零 LLM
    set_memory_store(InMemoryStore())
    fake = FakeLLM(reply="好的")
    import agent_starter.nodes.agent as agent_mod
    import agent_starter.nodes.classify as classify_mod
    monkeypatch.setattr(agent_mod, "build_llm", lambda *a, **k: fake)
    monkeypatch.setattr(classify_mod, "build_llm", lambda *a, **k: fake)

    graph = build_graph(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t1"}}

    # turn 1：声明昵称 → write 落库
    await graph.ainvoke(
        {"messages": [HumanMessage(content="以后叫我老张")], "user_id": 1, "domain": ""}, cfg)
    # turn 2：recall 应把昵称注入 agent 的 system
    await graph.ainvoke(
        {"messages": [HumanMessage(content="在吗")], "user_id": 1, "domain": ""}, cfg)

    # fake 只被 agent 调用（classify 无域不调）。第 2 次调用的 system 含昵称。
    systems = [c[0][1] for c in fake.calls if isinstance(c[0], tuple) and c[0][0] == "system"]
    assert len(systems) == 2
    assert "老张" not in systems[0]   # turn1 写入前，无记忆
    assert "老张" in systems[1]       # turn2 召回注入
