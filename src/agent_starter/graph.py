"""拆解-并行检索-综合 Agent 图（Decompose → Retrieve → Synthesize）。

与客服Agent的 ReAct 模式根本不同：
- ReAct 是"想一步做一步看一步"（Think→Act→Observe 循环）
- 这里是"先拆解→并行查→再综合"（先全局规划再执行）

适合需要跨多数据源的分析型问题，比如"对比三个产品线的退款率和投诉趋势"。

拓扑：
  START → classify ∥ recall → decompose → retrieve (并行) → synthesize → write → END
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from agent_starter.llm import build_llm
from agent_starter.nodes import recall_memory, write_memory
from agent_starter.nodes.classify import classify_intent
from agent_starter.security.sanitize import sanitize_output
from agent_starter.state import AgentState
from agent_starter.tasks.domains import global_read_tools

DECOMPOSE_PROMPT = """你是一个问题拆解专家。用户问了一个复杂问题，请你把它拆成 3-5 个可以独立检索的子问题。

规则：
1. 每个子问题必须独立可回答（不依赖其他子问题的结果）
2. 子问题要覆盖用户问题的所有维度（不同产品线、不同指标、不同角度）
3. 用中文写子问题
4. 返回 JSON 数组格式：["子问题1", "子问题2", "子问题3"]

用户问题：{user_input}

JSON："""

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

MAX_SUB_QUESTIONS = 5


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

    def __init__(self, checkpointer=None):
        self._tools = global_read_tools()
        self._tool_map = {t.name: t for t in self._tools}
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
        return await classify_intent(state)

    async def _decompose(self, state: AgentState) -> dict:
        """拆解节点：1次LLM调用，把复杂问题拆成子问题列表。"""
        user_text = _last_user_text(state.get("messages") or [])
        if not user_text:
            return {"working_draft": {"sub_questions": [], "original_query": ""}}

        llm = build_llm()
        prompt = DECOMPOSE_PROMPT.format(user_input=user_text)

        try:
            resp = await llm.ainvoke([HumanMessage(content=prompt)])
            raw = resp.content if isinstance(resp.content, str) else ""
            raw = raw.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:]) if len(lines) > 1 else raw
                if raw.endswith("```"):
                    raw = raw[:-3]
            sub_questions = json.loads(raw)
            if not isinstance(sub_questions, list):
                sub_questions = [str(sub_questions)]
            sub_questions = sub_questions[:MAX_SUB_QUESTIONS]
        except Exception:
            sub_questions = [user_text]

        draft = {
            "sub_questions": sub_questions,
            "original_query": user_text,
            "sub_results": [],
        }
        return {"working_draft": draft}

    async def _retrieve(self, state: AgentState) -> dict:
        """检索节点：每个子问题并行调用所有检索工具。"""
        draft = state.get("working_draft") or {}
        sub_questions = draft.get("sub_questions", [])
        if not sub_questions or not self._tools:
            return {}

        async def _search_one(sub_q: str) -> dict:
            results = []
            for tool in self._tools:
                try:
                    raw = await tool.ainvoke(sub_q)
                    content = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
                    results.append({"tool": tool.name, "query": sub_q, "result": content[:2000]})
                except Exception:
                    results.append({"tool": tool.name, "query": sub_q, "result": "检索失败"})
            return {"sub_question": sub_q, "findings": results}

        tasks = [_search_one(q) for q in sub_questions]
        sub_results = await asyncio.gather(*tasks)
        draft["sub_results"] = list(sub_results)
        return {"working_draft": draft}

    async def _synthesize(self, state: AgentState) -> dict:
        """综合节点：1次LLM调用，综合所有子结果生成分析报告。"""
        draft = state.get("working_draft") or {}
        original = draft.get("original_query", "")
        sub_results = draft.get("sub_results", [])

        parts = []
        for i, sr in enumerate(sub_results):
            parts.append(f"### 子问题{i+1}：{sr['sub_question']}")
            for f in sr.get("findings", []):
                parts.append(f"  [{f['tool']}]: {f['result'][:500]}")
        sub_text = "\n\n".join(parts)

        memory_text = _render_memory(state.get("recalled_memory"))
        prompt = SYNTHESIZE_PROMPT.format(user_input=original, sub_results=sub_text)
        if memory_text:
            prompt = memory_text + "\n\n" + prompt

        llm = build_llm()
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        reply = resp.content if isinstance(resp.content, str) else str(resp.content)
        reply = sanitize_output(reply)

        return {"messages": [AIMessage(content=reply)]}


def build_graph(checkpointer=None):
    """构建拆解-并行检索-综合 Agent 图。"""
    return DecomposeGraph(checkpointer=checkpointer).graph
