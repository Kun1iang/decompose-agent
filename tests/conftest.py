import pytest
from langchain_core.messages import AIMessage


class FakeLLM:
    """脚本化 LLM 替身。

    - 不传 responses：每次 ainvoke 返固定文本 AIMessage（兼容 Phase 1 用法）。
    - 传 responses：按顺序弹出；每项是 str（文本回复）或 dict（tool_calls，形如
      {"tool_calls": [{"name","args","id"}]}）。
    """

    def __init__(self, reply: str = "你好，我是 agent。", responses: list | None = None):
        self._reply = reply
        self._responses = list(responses) if responses else None
        self.calls = []
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages, *args, **kwargs):
        self.calls.append(list(messages))  # 存快照——agent_loop 会原地 append 同一个 list
        if self._responses is None:
            return AIMessage(content=self._reply)
        nxt = self._responses.pop(0)
        if isinstance(nxt, dict) and "tool_calls" in nxt:
            return AIMessage(content="", tool_calls=nxt["tool_calls"])
        return AIMessage(content=str(nxt))


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture(autouse=True)
def _clean_registries():
    """每个测试前后清空域/任务注册表 + memory store，隔离跨文件执行顺序影响。"""
    from agent_starter.memory.provider import reset_memory_store
    from agent_starter.serving.sessions import reset_session_store
    from agent_starter.skills.loader import reset_skills, set_skills
    from agent_starter.tasks import domains as d
    from agent_starter.tasks import registry as r
    d.clear_registry()
    r.REGISTRY.clear()
    reset_memory_store()
    reset_session_store()
    set_skills([])  # 单测默认无 skill，不依赖磁盘上的示例 skill
    yield
    d.clear_registry()
    r.REGISTRY.clear()
    reset_memory_store()
    reset_session_store()
    reset_skills()
