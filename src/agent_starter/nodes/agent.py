"""agent_loop_action：按 domain 选工具的 ReAct 多轮循环。

每轮：LLM → 有 tool_calls 就执行、把 ToolMessage 塞回、工具返值经 TaskSpec 钩子
累积进 working_draft → 再问；无 tool_calls 即最终答复，退出。无工具时退化为单次问答。
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from agent_starter.llm import build_llm
from agent_starter.security.permissions import (
    filter_tools_for_permissions,
    granted_permissions,
)
from agent_starter.security.prompt import SYSTEM_INSTRUCTIONS
from agent_starter.security.sanitize import (
    sanitize_output,
    sanitize_user_input,
    wrap_user_input,
)
from agent_starter.skills.loader import get_skills, render_skills_section, select_skills
from agent_starter.state import AgentState
from agent_starter.tasks.domains import select_tools_for_state
from agent_starter.tasks.registry import (
    collect_draft_renderings,
    collect_prompt_fragments_for_domain,
    merge_tool_result_into_draft,
    render_success_message,
    should_display_draft,
)

logger = structlog.get_logger(__name__)

MAX_REACT_ROUNDS = 6

_BASE_PROMPT = (
    "你是一个通用 AI 助手。用简洁、准确的中文回答用户。需要时调用提供的工具完成任务。"
)


def _render_memory(recalled) -> str:
    if recalled is None:
        return ""
    is_empty = getattr(recalled, "is_empty", None)
    if not callable(is_empty):
        logger.warning("memory.render_ignored", reason="unexpected_shape", type=type(recalled).__name__)
        return ""
    if is_empty():
        return ""
    lines = ["【用户记忆】"]
    for p in getattr(recalled, "prefs", []) or []:
        lines.append(f"- 偏好 {p.key} = {p.value}")
    for o in getattr(recalled, "observations", []) or []:
        lines.append(f"- {o.text}")
    return "\n".join(lines)


def _sanitize_history(messages: list) -> list:
    """对 HumanMessage 去注入 + 包裹定界符（仅用于本次 LLM 调用，不写回 state）。"""
    out = []
    for m in messages:
        if isinstance(m, HumanMessage):
            content = m.content if isinstance(m.content, str) else ""
            nm = HumanMessage(content=wrap_user_input(sanitize_user_input(content)))
            if getattr(m, "id", None):
                nm.id = m.id
            out.append(nm)
        else:
            out.append(m)
    return out


def _last_user_text(messages: list) -> str:
    for m in reversed(messages or []):
        if isinstance(m, HumanMessage):
            return m.content if isinstance(m.content, str) else ""
    return ""


def _build_system(state: AgentState) -> str:
    parts = [SYSTEM_INSTRUCTIONS, _BASE_PROMPT]
    mem = _render_memory(state.get("recalled_memory"))
    if mem:
        parts.append(mem)
    skills = render_skills_section(
        select_skills(_last_user_text(state.get("messages") or []), get_skills())
    )
    if skills:
        parts.append(skills)
    parts.extend(collect_prompt_fragments_for_domain(state.get("domain") or ""))
    parts.extend(collect_draft_renderings(dict(state)))
    return "\n\n".join(p for p in parts if p)


def _tool_call_get(tool_call: Any, key: str, default: Any = None) -> Any:
    if isinstance(tool_call, dict):
        return tool_call.get(key, default)
    return getattr(tool_call, key, default)


def _normalize_tool_call(tool_call: Any) -> tuple[str, Any, str, dict | None]:
    name = _tool_call_get(tool_call, "name")
    args = _tool_call_get(tool_call, "args", {})
    call_id = _tool_call_get(tool_call, "id") or f"call-{uuid.uuid4().hex[:12]}"
    if not isinstance(name, str) or not name:
        return "unknown_tool", {}, str(call_id), {
            "ok": False,
            "error": "malformed_tool_call",
            "detail": "tool call missing name",
        }
    if args is None:
        args = {}
    return name, args, str(call_id), None


def _json_tool_content(raw: Any) -> tuple[str, Any]:
    try:
        return json.dumps(raw, ensure_ascii=False), raw
    except (TypeError, ValueError) as e:
        safe = {
            "ok": False,
            "error": "tool_result_not_serializable",
            "detail": str(e),
            "repr": repr(raw)[:500],
        }
        return json.dumps(safe, ensure_ascii=False), safe


async def _invoke_tool_safely(tool, args: Any) -> Any:
    try:
        return await tool.ainvoke(args)
    except Exception as e:  # noqa: BLE001 业务工具失败不应拖垮整个 turn
        logger.warning("tool.invoke_failed", tool=getattr(tool, "name", ""), error=str(e))
        return {"ok": False, "error": "tool_failed", "detail": str(e)}


async def agent_loop_action(state: AgentState, *, llm=None) -> dict:
    if llm is None:
        llm = build_llm()
    tools = select_tools_for_state(dict(state))
    tools = filter_tools_for_permissions(tools, granted_permissions(dict(state)))
    tool_map = {t.name: t for t in tools}
    bound = llm.bind_tools(tools) if tools else llm

    history: list[BaseMessage] = _sanitize_history(list(state.get("messages") or []))
    conversation: list = [("system", _build_system(state)), *history]
    new_msgs: list = []
    local_draft: dict = dict(state.get("working_draft") or {})
    draft_changed = False

    for _ in range(MAX_REACT_ROUNDS):
        resp = await bound.ainvoke(conversation)
        if not getattr(resp, "id", None):
            resp.id = f"ai-{uuid.uuid4().hex[:12]}"
        new_msgs.append(resp)
        conversation.append(resp)

        tool_calls = getattr(resp, "tool_calls", None) or []
        if not tool_calls:
            if isinstance(resp.content, str):
                resp.content = sanitize_output(resp.content)
            break

        for tc in tool_calls:
            tool_name, tool_args, tool_call_id, malformed = _normalize_tool_call(tc)
            tool = tool_map.get(tool_name)
            if malformed is not None:
                raw: Any = malformed
            elif tool is None:
                raw = {"ok": False, "error": f"unknown tool {tool_name}"}
            else:
                raw = await _invoke_tool_safely(tool, tool_args)
            content, raw = _json_tool_content(raw)
            tm = ToolMessage(
                content=content,
                tool_call_id=tool_call_id,
                name=tool_name,
            )
            new_msgs.append(tm)
            conversation.append(tm)
            domain = state.get("domain") or ""
            success = render_success_message(tool_name, raw, domain=domain) if isinstance(raw, dict) else None
            if success:
                conversation.append(("system", f"工具执行成功后的建议回复：{success}"))
            if isinstance(raw, dict):
                next_draft = merge_tool_result_into_draft(tool_name, raw, local_draft, domain=domain)
                if next_draft != local_draft:
                    draft_changed = True
                    local_draft = next_draft
    else:
        logger.warning("agent_loop.exhausted", rounds=MAX_REACT_ROUNDS)
        fallback = AIMessage(content="工具调用轮次过多，已停止继续执行。请补充信息或稍后重试。")
        fallback.id = f"ai-{uuid.uuid4().hex[:12]}"
        new_msgs.append(fallback)

    out: dict = {"messages": new_msgs}
    if local_draft:
        out["working_draft"] = local_draft
        draft_state = {**dict(state), "working_draft": local_draft}
        out["working_draft_visible"] = should_display_draft(draft_state)
        out["working_draft_dirty"] = draft_changed or bool(state.get("working_draft_dirty"))
    return out


# 向后兼容：Phase 1 的 graph/测试用 agent_node 名字。
agent_node = agent_loop_action
