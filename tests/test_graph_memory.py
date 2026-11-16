import json

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agent_starter.graph import build_graph
from agent_starter.memory.provider import set_memory_store
from agent_starter.memory.store import InMemoryStore
from agent_starter.tasks import domains as d
from tests.conftest import FakeLLM


@pytest.mark.asyncio
async def test_nickname_remembered_across_turns():
    d.clear_registry()              # 无域：classify 零 LLM
    set_memory_store(InMemoryStore())
    plan = json.dumps({"steps": []})
    fake = FakeLLM(responses=[plan, "好的", plan, "好的"])

    graph = build_graph(checkpointer=MemorySaver(), llm_factory=lambda: fake)
    cfg = {"configurable": {"thread_id": "t1"}}

    # turn 1：声明昵称 → write 落库
    await graph.ainvoke(
        {"messages": [HumanMessage(content="以后叫我老张")], "user_id": 1, "domain": ""}, cfg)
    # turn 2：recall 应把昵称注入 agent 的 system
    await graph.ainvoke(
        {"messages": [HumanMessage(content="在吗")], "user_id": 1, "domain": ""}, cfg)

    # 每轮各有一次拆解 + 一次综合。第二个 turn 的综合 Prompt 应包含昵称。
    synth_prompts = [call[0].content for call in fake.calls[1::2]]
    assert len(synth_prompts) == 2
    assert "【用户偏好】" not in synth_prompts[0]
    assert "【用户偏好】" in synth_prompts[1]
    assert "nickname = 老张" in synth_prompts[1]
