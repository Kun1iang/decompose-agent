"""StateGraph 装配：START → {classify ∥ recall} → agent → write → END。

classify 与 recall 并行 fan-out（写不同 state 字段，无冲突），agent 处 fan-in。
"""
from langgraph.graph import END, START, StateGraph

from agent_starter.nodes import agent_loop_action, classify_intent, recall_memory, write_memory
from agent_starter.state import AgentState


def build_graph(checkpointer=None):
    builder = StateGraph(AgentState)
    builder.add_node("classify", classify_intent)
    builder.add_node("recall", recall_memory)
    builder.add_node("agent", agent_loop_action)
    builder.add_node("write", write_memory)
    builder.add_edge(START, "classify")
    builder.add_edge(START, "recall")
    builder.add_edge("classify", "agent")
    builder.add_edge("recall", "agent")
    builder.add_edge("agent", "write")
    builder.add_edge("write", END)
    return builder.compile(checkpointer=checkpointer)
