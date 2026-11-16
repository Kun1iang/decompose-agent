"""拆解-并行检索-综合 Agent 图（Decompose → Retrieve → Synthesize）。

与客服Agent的 ReAct 模式根本不同：
- ReAct 是"想一步做一步看一步"（Think→Act→Observe 循环）
- 这里是"先拆解→并行查→再综合"（先全局规划再执行）

适合需要跨多数据源的分析型问题，比如"对比三个产品线的退款率和投诉趋势"。

拓扑：
  START → classify ∥ recall → decompose → retrieve (并行) → synthesize → write → END

拆解结果不是一组裸文本子问题，而是经过校验的检索计划：
  {"question": "...", "tool": "search_sales", "arguments": {...}}
这样工具能收到合法且语义正确的参数，而不是把自然语言误当成 product_id。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from agent_starter.llm import build_llm
from agent_starter.nodes import recall_memory, write_memory
from agent_starter.nodes.classify import classify_intent
from agent_starter.planning import (
    PlanParseResult,
    fallback_plan,
    parse_tool_plan,
    render_tool_catalog,
)
from agent_starter.security.sanitize import sanitize_output
from agent_starter.state import AgentState
from agent_starter.tasks.domains import global_read_tools

logger = structlog.get_logger(__name__)

DECOMPOSE_PROMPT = """你是一个经营分析检索规划器。把用户问题拆成 3-5 个可独立并行执行的检索步骤。

规则：
1. 每一步只能使用“可用工具”中的一个，工具名必须完全一致。
2. arguments 必须是该工具声明过的参数；没有筛选条件时使用空字符串或空对象。
3. 每一步必须可独立执行，不依赖其他步骤的运行结果。
4. 覆盖回答原问题所需的数据。计算退款率时要同时查询销售额和退款数据。
5. 不要编造产品 ID、月份、投诉类别或工具名。
6. 严格返回 JSON 对象，不要输出 Markdown、解释或额外字段。

【可用工具】
{tool_catalog}

用户问题：{user_input}

返回格式：
{{
  "steps": [
    {{
      "question": "这一步要回答什么",
      "tool": "工具名",
      "arguments": {{"参数名": "参数值"}}
    }}
  ]
}}
"""

SYNTHESIZE_PROMPT = """你是一个数据分析师。用户问了一个复杂问题，下面是你拆解的子问题和各自的检索结果。
请综合分析所有数据，生成一份专业的分析报告。

要求：
1. 覆盖用户关心的所有维度
2. 引用具体数据（数字、百分比、趋势）
3. 如果数据体现出趋势或异常，指出来
4. 结构清晰：先总述，再分维度展开，最后总结与建议
5. 用中文回答

【用户原始问题】
{user_input}

【子问题与检索结果】
{sub_results}

分析报告："""

MAX_RETRIEVAL_STEPS = 5


def _last_user_text(messages: list) -> str:
    for m in reversed(messages or []):
        if isinstance(m, HumanMessage):
            c = getattr(m, "content", "")
            return c if isinstance(c, str) else ""
    return ""


def _render_memory(recalled) -> str:
    if recalled is None:
        return ""
    is_empty = getattr(recalled, "is_empty", None)
    if not callable(is_empty) or is_empty():
        return ""
    lines = ["【用户偏好】"]
    for p in getattr(recalled, "prefs", []) or []:
        lines.append(f"- {p.key} = {p.value}")
    return "\n".join(lines)


class DecomposeGraph:
    """拆解-并行-综合 Agent 图"""

    def __init__(self, checkpointer=None, *, llm_factory=None):
        self._tools = global_read_tools()
        self._tool_map = {t.name: t for t in self._tools}
        self._llm_factory = llm_factory or build_llm
        self.graph = self._build(checkpointer)

    def _build(self, checkpointer):
        builder = StateGraph(AgentState)
        builder.add_node("classify", self._classify_wrapper)
        builder.add_node("recall", recall_memory)
        builder.add_node("decompose", self._decompose)
        builder.add_node("retrieve", self._retrieve)
        builder.add_node("synthesize", self._synthesize)
        builder.add_node("write", write_memory)
        builder.add_edge(START, "classify")
        builder.add_edge(START, "recall")
        builder.add_edge("classify", "decompose")
        builder.add_edge("recall", "decompose")
        builder.add_edge("decompose", "retrieve")
        builder.add_edge("retrieve", "synthesize")
        builder.add_edge("synthesize", "write")
        builder.add_edge("write", END)
        return builder.compile(checkpointer=checkpointer)

    async def _classify_wrapper(self, state: AgentState) -> dict:
        return await classify_intent(state, llm=self._llm_factory())

    async def _decompose(self, state: AgentState) -> dict:
        """拆解节点：1 次 LLM 调用，生成经过校验的结构化检索计划。"""
        user_text = _last_user_text(state.get("messages") or [])
        if not user_text:
            return {
                "working_draft": {
                    "original_query": "",
                    "plan": [],
                    "sub_results": [],
                    "plan_fallback": False,
                }
            }

        llm = self._llm_factory()
        prompt = DECOMPOSE_PROMPT.format(
            user_input=user_text,
            tool_catalog=render_tool_catalog(self._tools),
        )

        try:
            resp = await llm.ainvoke([HumanMessage(content=prompt)])
            raw = resp.content if isinstance(resp.content, str) else str(resp.content)
            plan_result = parse_tool_plan(
                raw,
                self._tools,
                user_text,
                max_steps=MAX_RETRIEVAL_STEPS,
            )
        except Exception as exc:  # noqa: BLE001 - provider failures must fail soft
            plan_result = PlanParseResult(
                steps=fallback_plan(
                    self._tools,
                    user_text,
                    max_steps=MAX_RETRIEVAL_STEPS,
                ),
                used_fallback=True,
                reason=type(exc).__name__,
            )

        logger.info(
            "decompose.done",
            steps=len(plan_result.steps),
            fallback=plan_result.used_fallback,
            reason=plan_result.reason,
        )

        draft = {
            "original_query": user_text,
            "plan": plan_result.steps,
            "sub_results": [],
            "plan_fallback": plan_result.used_fallback,
            "plan_reason": plan_result.reason,
        }
        return {"working_draft": draft}

    async def _retrieve(self, state: AgentState) -> dict:
        """检索节点：按计划并行执行独立工具调用。"""
        draft = state.get("working_draft") or {}
        steps = draft.get("plan", [])
        if not steps or not self._tools:
            return {}

        async def _run_step(step: dict[str, Any]) -> dict:
            tool = self._tool_map.get(step.get("tool", ""))
            base = {
                "question": step.get("question", ""),
                "tool": step.get("tool", ""),
                "arguments": step.get("arguments", {}),
            }
            if tool is None:
                return {
                    **base,
                    "status": "error",
                    "result": "检索失败：未知工具",
                    "error": "UnknownTool",
                }
            try:
                raw = await tool.ainvoke(base["arguments"])
                content = (
                    raw
                    if isinstance(raw, str)
                    else json.dumps(raw, ensure_ascii=False, default=str)
                )
                return {
                    **base,
                    "status": "success",
                    "result": content[:2000],
                }
            except Exception as exc:  # noqa: BLE001 - isolate each retrieval step
                return {
                    **base,
                    "status": "error",
                    "result": "检索失败",
                    "error": type(exc).__name__,
                }

        sub_results = await asyncio.gather(*(_run_step(step) for step in steps))
        draft["sub_results"] = list(sub_results)
        logger.info(
            "retrieve.done",
            steps=len(sub_results),
            failed=sum(1 for result in sub_results if result["status"] != "success"),
        )
        return {"working_draft": draft}

    async def _synthesize(self, state: AgentState) -> dict:
        """综合节点：1次LLM调用，综合所有子结果生成分析报告。"""
        draft = state.get("working_draft") or {}
        original = draft.get("original_query", "")
        sub_results = draft.get("sub_results", [])

        parts = []
        for i, result in enumerate(sub_results):
            args = json.dumps(result.get("arguments", {}), ensure_ascii=False, sort_keys=True)
            parts.append(
                f"### 检索任务{i + 1}：{result.get('question', '')}\n"
                f"工具：{result.get('tool', '')}  参数：{args}  "
                f"状态：{result.get('status', 'unknown')}\n"
                f"结果：{str(result.get('result', ''))[:500]}"
            )
        sub_text = "\n\n".join(parts)

        memory_text = _render_memory(state.get("recalled_memory"))
        prompt = SYNTHESIZE_PROMPT.format(user_input=original, sub_results=sub_text)
        if memory_text:
            prompt = memory_text + "\n\n" + prompt

        llm = self._llm_factory()
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        reply = resp.content if isinstance(resp.content, str) else str(resp.content)
        reply = sanitize_output(reply)

        return {"messages": [AIMessage(content=reply)]}


def build_graph(checkpointer=None, *, llm_factory=None):
    """构建拆解-并行检索-综合 Agent 图。"""
    return DecomposeGraph(
        checkpointer=checkpointer,
        llm_factory=llm_factory,
    ).graph
