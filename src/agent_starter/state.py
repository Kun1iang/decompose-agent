"""LangGraph state schema（去业务化）。

- messages: 对话历史（自动 append）
- working_draft: 通用草稿袋——当前业务域自行解释字段含义。框架层不认识任何
  具体字段名（替代过去那种业务专属的单一草稿字段）。
- working_draft_visible / _dirty: 通用展示/脏闸门，由域的 TaskSpec hook 决定何时推前端。
- domain: classify 写入的业务域名；空串表示无明确域。
- recalled_memory / user_scope: Phase 1 占位（Any），P3 接 memory 换强类型。
"""
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: int
    jwt: str
    persona: str
    domain: str
    working_draft: dict[str, Any] | None
    working_draft_visible: bool | None
    working_draft_dirty: bool | None
    recalled_memory: Any | None
    user_scope: Any | None
    permissions: list[str] | None
    workspace_id: int
    page_context: dict[str, Any] | None
    invoked_tool: str
    invoked_args: dict[str, Any] | None
