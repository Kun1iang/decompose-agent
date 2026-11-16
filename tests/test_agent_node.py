import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agent_starter.graph import build_graph
from agent_starter.nodes.agent import agent_node


@pytest.mark.asyncio
async def test_agent_node_returns_ai_message(fake_llm):
    state = {
        "messages": [HumanMessage(content="在吗")],
        "user_id": 1,
        "domain": "",
    }
    out = await agent_node(state, llm=fake_llm)
    assert "messages" in out
    msgs = out["messages"]
    assert isinstance(msgs[-1], AIMessage)
    assert msgs[-1].content == "你好，我是 agent。"
    # system prompt 被前置传给 LLM
    assert fake_llm.calls and fake_llm.calls[0][0][0] == "system"


@pytest.mark.asyncio
async def test_graph_runs_one_turn():
    # 无注册域：classify 不调 LLM；主图仍执行拆解和综合两个核心 LLM 调用。
    from agent_starter.tasks import domains as d
    d.clear_registry()
    from tests.conftest import FakeLLM
    fake = FakeLLM(
        responses=[
            json.dumps({"steps": []}),
            "你好，我是 agent。",
        ]
    )

    graph = build_graph(checkpointer=MemorySaver(), llm_factory=lambda: fake)
    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="在吗")], "user_id": 1, "domain": ""},
        config={"configurable": {"thread_id": "t1"}},
    )
    assert isinstance(out["messages"][-1], AIMessage)
    assert out["messages"][-1].content == "你好，我是 agent。"
