"""End-to-end tests for the decompose → retrieve → synthesize graph."""

from __future__ import annotations

import json

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from agent_starter.graph import DecomposeGraph, build_graph
from agent_starter.tasks import register_enabled_domains
from tests.conftest import FakeLLM


def _register_analytics():
    register_enabled_domains(enable_example=False)


@pytest.mark.asyncio
async def test_decompose_builds_validated_structured_plan():
    _register_analytics()
    plan = json.dumps(
        {
            "steps": [
                {
                    "question": "查询 prod_a 在 2025-06 的退款数据",
                    "tool": "search_refunds",
                    "arguments": {"product_id": "prod_a", "month": "2025-06"},
                },
                {
                    "question": "查询 prod_a 在 2025-06 的投诉数据",
                    "tool": "search_complaints",
                    "arguments": {"product_id": "prod_a", "month": "2025-06"},
                },
                {
                    "question": "查询 prod_a 在 2025-06 的销售数据",
                    "tool": "search_sales",
                    "arguments": {"product_id": "prod_a", "month": "2025-06"},
                },
            ]
        },
        ensure_ascii=False,
    )
    fake = FakeLLM(responses=[plan, "分析报告"])
    graph = DecomposeGraph(llm_factory=lambda: fake)

    update = await graph._decompose(
        {"messages": [HumanMessage(content="分析 prod_a 2025-06 的退款和投诉")]}
    )
    steps = update["working_draft"]["plan"]

    assert [step["tool"] for step in steps] == [
        "search_refunds",
        "search_complaints",
        "search_sales",
    ]
    assert steps[0]["arguments"] == {"product_id": "prod_a", "month": "2025-06"}
    assert update["working_draft"]["plan_fallback"] is False


@pytest.mark.asyncio
async def test_retrieve_executes_structured_arguments_not_raw_question():
    _register_analytics()
    graph = DecomposeGraph(llm_factory=lambda: FakeLLM())
    update = await graph._retrieve(
        {
            "working_draft": {
                "plan": [
                    {
                        "question": "查询 prod_a 2025-06 退款",
                        "tool": "search_refunds",
                        "arguments": {"product_id": "prod_a", "month": "2025-06"},
                    }
                ]
            }
        }
    )

    result = update["working_draft"]["sub_results"][0]
    assert result["status"] == "success"
    assert result["tool"] == "search_refunds"
    assert result["arguments"] == {"product_id": "prod_a", "month": "2025-06"}
    assert "2025-06" in result["result"]
    assert "AI客服Agent" in result["result"]
    assert "未找到" not in result["result"]


@pytest.mark.asyncio
async def test_invalid_model_plan_falls_back_to_all_read_tools():
    _register_analytics()
    graph = DecomposeGraph(llm_factory=lambda: FakeLLM(reply="这不是 JSON"))

    update = await graph._decompose(
        {"messages": [HumanMessage(content="看看整体经营数据")]}
    )
    draft = update["working_draft"]

    assert draft["plan_fallback"] is True
    assert len(draft["plan"]) == 4
    assert {step["tool"] for step in draft["plan"]} == {
        "search_sales",
        "search_refunds",
        "search_complaints",
        "list_products",
    }


@pytest.mark.asyncio
async def test_invalid_steps_are_dropped_while_valid_steps_remain():
    _register_analytics()
    plan = json.dumps(
        {
            "steps": [
                {
                    "question": "不存在的工具",
                    "tool": "drop_database",
                    "arguments": {},
                },
                {
                    "question": "查询 prod_b 销售",
                    "tool": "search_sales",
                    "arguments": {"product_id": "prod_b", "month": "2025-01"},
                },
            ]
        }
    )
    graph = DecomposeGraph(llm_factory=lambda: FakeLLM(reply=plan))

    update = await graph._decompose(
        {"messages": [HumanMessage(content="查询 prod_b 销售")]}
    )
    draft = update["working_draft"]

    assert draft["plan_fallback"] is False
    assert draft["plan_reason"] == "partially_invalid"
    assert draft["plan"] == [
        {
            "question": "查询 prod_b 销售",
            "tool": "search_sales",
            "arguments": {"product_id": "prod_b", "month": "2025-01"},
        }
    ]


@pytest.mark.asyncio
async def test_llm_failure_during_planning_falls_back_without_raising():
    class BrokenLLM:
        async def ainvoke(self, messages):
            raise RuntimeError("provider unavailable")

    _register_analytics()
    graph = DecomposeGraph(llm_factory=BrokenLLM)

    update = await graph._decompose(
        {"messages": [HumanMessage(content="分析全部产品")]}
    )
    draft = update["working_draft"]

    assert draft["plan_fallback"] is True
    assert draft["plan_reason"] == "RuntimeError"
    assert len(draft["plan"]) == 4


@pytest.mark.asyncio
async def test_one_failed_tool_does_not_cancel_other_parallel_steps():
    @tool
    async def broken_tool(value: str = "") -> str:
        """Always fails for the partial-failure test."""
        raise RuntimeError("backend unavailable")

    _register_analytics()
    graph = DecomposeGraph(llm_factory=lambda: FakeLLM())
    graph._tools = [broken_tool, *graph._tools[:1]]
    graph._tool_map = {item.name: item for item in graph._tools}

    update = await graph._retrieve(
        {
            "working_draft": {
                "plan": [
                    {"question": "坏工具", "tool": "broken_tool", "arguments": {}},
                    {
                        "question": "正常工具",
                        "tool": "search_sales",
                        "arguments": {"product_id": "prod_a"},
                    },
                ]
            }
        }
    )

    results = update["working_draft"]["sub_results"]
    assert results[0]["status"] == "error"
    assert results[0]["error"] == "RuntimeError"
    assert results[1]["status"] == "success"
    assert "AI客服Agent" in results[1]["result"]


@pytest.mark.asyncio
async def test_full_graph_uses_fake_planner_and_synthesizer():
    _register_analytics()
    plan = json.dumps(
        {
            "steps": [
                {
                    "question": "查询全部退款",
                    "tool": "search_refunds",
                    "arguments": {},
                }
            ]
        }
    )
    fake = FakeLLM(responses=["analytics", plan, "已完成分析"])
    graph = build_graph(
        checkpointer=MemorySaver(),
        llm_factory=lambda: fake,
    )

    out = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="分析退款")],
            "user_id": 1,
            "domain": "",
        },
        config={"configurable": {"thread_id": "structured-t1"}},
    )

    assert out["messages"][-1].content == "已完成分析"
    assert out["working_draft"]["plan"][0]["tool"] == "search_refunds"
    assert out["working_draft"]["sub_results"][0]["status"] == "success"
