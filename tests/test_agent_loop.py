import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent_starter.nodes.agent import agent_loop_action
from agent_starter.tasks import domains as d
from agent_starter.tasks import registry as r
from tests.conftest import FakeLLM


def setup_function():
    d.clear_registry()
    r.REGISTRY.clear()


@pytest.fixture
def create_todo_tool():
    from langchain_core.tools import tool

    @tool
    async def create_todo(user_id: int, title: str) -> dict:
        """create todo."""
        return {"ok": True, "id": 7, "title": title}

    return create_todo


@pytest.mark.asyncio
async def test_no_domain_single_llm_reply():
    llm = FakeLLM(responses=["在的，有什么可以帮你"])
    out = await agent_loop_action({"messages": [HumanMessage(content="在吗")], "domain": "", "user_id": 1}, llm=llm)
    assert isinstance(out["messages"][-1], AIMessage)
    assert out["messages"][-1].content == "在的，有什么可以帮你"


@pytest.mark.asyncio
async def test_react_calls_tool_then_replies():
    from agent_starter.tasks.example_todo import register
    register()  # 注册 todo 域 + 工具
    # 第一轮：LLM 要求调 add_todo；第二轮：给最终答复
    llm = FakeLLM(responses=[
        {"tool_calls": [{"name": "add_todo", "args": {"user_id": 1, "title": "买牛奶"}, "id": "c1"}]},
        "✅ 已加上待办：买牛奶",
    ])
    out = await agent_loop_action(
        {"messages": [HumanMessage(content="加个买牛奶的待办")], "domain": "todo", "user_id": 1},
        llm=llm,
    )
    # 工具被绑定了（todo 域 read+write 至少 3 个）
    assert llm.bound_tools and len(llm.bound_tools) >= 3
    # 末条是最终答复
    assert out["messages"][-1].content == "✅ 已加上待办：买牛奶"
    # 中间产生了 ToolMessage
    assert any(isinstance(m, ToolMessage) for m in out["messages"])


@pytest.mark.asyncio
async def test_recalled_memory_injected_into_system():
    from agent_starter.memory.models import Preference, RecalledMemory
    llm = FakeLLM(reply="好的")
    state = {
        "messages": [HumanMessage(content="在吗")],
        "domain": "", "user_id": 1,
        "recalled_memory": RecalledMemory(prefs=[Preference("nickname", "老张")]),
    }
    await agent_loop_action(state, llm=llm)
    system = llm.calls[0][0][1]  # conversation[0] == ("system", <str>)
    assert "老张" in system


@pytest.mark.asyncio
async def test_unexpected_recalled_memory_shape_is_ignored():
    llm = FakeLLM(reply="好的")
    out = await agent_loop_action(
        {
            "messages": [HumanMessage(content="在吗")],
            "domain": "",
            "user_id": 1,
            "recalled_memory": {"unexpected": "shape"},
        },
        llm=llm,
    )

    assert out["messages"][-1].content == "好的"


@pytest.mark.asyncio
async def test_task_create_success_message_is_added_as_followup_hint(create_todo_tool):
    d.register_domain(d.DomainSpec(name="todo", label="待办"))
    r.REGISTRY.append(r.TaskSpec(
        task_type="create_todo", domain="todo", create_tool=create_todo_tool,
        prompt_fragment="", success_message=lambda raw: f"已创建待办：{raw['title']}",
    ))
    llm = FakeLLM(responses=[
        {"tool_calls": [{"name": "create_todo", "args": {"user_id": 1, "title": "买牛奶"}, "id": "c1"}]},
        "好的",
    ])

    await agent_loop_action(
        {"messages": [HumanMessage(content="加个买牛奶的待办")], "domain": "todo", "user_id": 1},
        llm=llm,
    )

    second_call = llm.calls[1]
    assert any("已创建待办：买牛奶" in str(item) for item in second_call)


@pytest.mark.asyncio
async def test_task_draft_display_hook_controls_state_flags(create_todo_tool):
    d.register_domain(d.DomainSpec(name="todo", label="待办"))
    r.REGISTRY.append(r.TaskSpec(
        task_type="create_todo", domain="todo", create_tool=create_todo_tool,
        prompt_fragment="", success_message=lambda raw: "",
        tool_result_to_draft_patches=lambda name, raw: {"ready": raw["ok"]} if name == "create_todo" else None,
        is_draft_displayable=lambda state: bool((state.get("working_draft") or {}).get("ready")),
    ))
    llm = FakeLLM(responses=[
        {"tool_calls": [{"name": "create_todo", "args": {"user_id": 1, "title": "买牛奶"}, "id": "c1"}]},
        "好的",
    ])

    out = await agent_loop_action(
        {"messages": [HumanMessage(content="加个买牛奶的待办")], "domain": "todo", "user_id": 1},
        llm=llm,
    )

    assert out["working_draft"] == {"ready": True}
    assert out["working_draft_visible"] is True
    assert out["working_draft_dirty"] is True


@pytest.mark.asyncio
async def test_tool_exception_becomes_tool_error_message():
    from langchain_core.tools import tool

    @tool
    async def unstable_tool(user_id: int) -> dict:
        """raises while doing work."""
        raise RuntimeError("backend unavailable")

    d.register_domain(d.DomainSpec(name="todo", label="待办", write_tools=[unstable_tool]))
    llm = FakeLLM(responses=[
        {"tool_calls": [{"name": "unstable_tool", "args": {"user_id": 1}, "id": "c1"}]},
        "工具暂时不可用",
    ])

    out = await agent_loop_action(
        {"messages": [HumanMessage(content="试一下工具")], "domain": "todo", "user_id": 1},
        llm=llm,
    )

    tool_messages = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    assert tool_messages
    assert "tool_failed" in tool_messages[0].content
    assert "backend unavailable" in tool_messages[0].content
    assert out["messages"][-1].content == "工具暂时不可用"


@pytest.mark.asyncio
async def test_non_json_tool_result_is_serialized_as_error_message():
    from langchain_core.tools import tool

    @tool
    async def odd_tool() -> dict:
        """returns data with a non-json value."""
        return {"ok": True, "value": object()}

    d.register_domain(d.DomainSpec(name="todo", label="待办", write_tools=[odd_tool]))
    llm = FakeLLM(responses=[
        {"tool_calls": [{"name": "odd_tool", "args": {}, "id": "c1"}]},
        "已处理",
    ])

    out = await agent_loop_action(
        {"messages": [HumanMessage(content="试一下工具")], "domain": "todo", "user_id": 1},
        llm=llm,
    )

    tool_messages = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    assert tool_messages
    assert "tool_result_not_serializable" in tool_messages[0].content
    assert out["messages"][-1].content == "已处理"
