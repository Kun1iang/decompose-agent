import pytest
from langchain_core.messages import HumanMessage

from agent_starter.nodes.classify import classify_intent
from agent_starter.tasks import domains as d
from agent_starter.tasks.domains import DomainSpec
from tests.conftest import FakeLLM


def setup_function():
    d.clear_registry()


@pytest.mark.asyncio
async def test_no_domains_returns_empty_without_llm():
    llm = FakeLLM(responses=[])  # 若被调用会 IndexError
    out = await classify_intent({"messages": [HumanMessage(content="随便说点")]}, llm=llm)
    assert out["domain"] == ""
    assert llm.calls == []  # 没注册域 → 不调 LLM


@pytest.mark.asyncio
async def test_llm_picks_registered_domain():
    d.register_domain(DomainSpec(name="todo", label="待办", triggers=["待办", "todo"]))
    llm = FakeLLM(responses=["todo"])
    out = await classify_intent({"messages": [HumanMessage(content="帮我加个待办")]}, llm=llm)
    assert out["domain"] == "todo"


@pytest.mark.asyncio
async def test_llm_unknown_domain_falls_back_empty():
    d.register_domain(DomainSpec(name="todo", label="待办"))
    llm = FakeLLM(responses=["nonsense"])
    out = await classify_intent({"messages": [HumanMessage(content="x")]}, llm=llm)
    assert out["domain"] == ""  # LLM 给了没注册的名 → 兜底空


@pytest.mark.asyncio
async def test_trigger_match_used_when_llm_returns_unknown():
    d.register_domain(DomainSpec(name="todo", label="待办", triggers=["待办"]))
    llm = FakeLLM(responses=["nonsense"])

    out = await classify_intent({"messages": [HumanMessage(content="帮我加个待办")]}, llm=llm)

    assert out["domain"] == "todo"


@pytest.mark.asyncio
async def test_classifier_failure_falls_back_to_trigger_match():
    d.register_domain(DomainSpec(name="todo", label="待办", triggers=["待办"]))

    class BrokenLLM:
        async def ainvoke(self, messages):
            raise RuntimeError("llm down")

    out = await classify_intent({"messages": [HumanMessage(content="帮我加个待办")]}, llm=BrokenLLM())

    assert out["domain"] == "todo"
