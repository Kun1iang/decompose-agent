"""TaskSpec：域内“收集字段 → 确认 → 落库”的写任务单元 + 注册表 + 聚合 helper。

去业务化：通用层只调钩子 + 拼接，永远不认识具体业务字段名。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog
from langchain_core.tools import BaseTool

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class TaskSpec:
    task_type: str
    domain: str
    create_tool: BaseTool                         # @tool，HR 确认后一次性写库
    prompt_fragment: str                          # 域专属规则段，拼进 system prompt
    success_message: Callable[[dict], str]        # create 成功后给用户的文案
    # 可选钩子（None = 不参与）：
    tool_result_to_draft_patches: Callable[[str, dict[str, Any]], dict | None] | None = None
    render_draft: Callable[[dict[str, Any]], str | None] | None = None
    is_draft_displayable: Callable[[dict[str, Any]], bool] | None = None


REGISTRY: list[TaskSpec] = []


def collect_action_tools() -> list[BaseTool]:
    return [s.create_tool for s in REGISTRY]


def collect_action_tools_for_domain(domain: str) -> list[BaseTool]:
    name = (domain or "").strip()
    if not name:
        return []
    return [s.create_tool for s in REGISTRY if s.domain == name]


def collect_prompt_fragments_for_domain(domain: str) -> list[str]:
    name = (domain or "").strip()
    if not name:
        return []
    return [s.prompt_fragment for s in REGISTRY if s.prompt_fragment and s.domain == name]


def _domain_matches_state(spec: TaskSpec, state: dict[str, Any]) -> bool:
    domain = (state.get("domain") or "").strip()
    return not domain or spec.domain == domain


def _domain_matches_name(spec: TaskSpec, domain: str) -> bool:
    name = (domain or "").strip()
    return not name or spec.domain == name


def collect_draft_renderings(state: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for s in REGISTRY:
        if not _domain_matches_state(s, state):
            continue
        if s.render_draft is None:
            continue
        try:
            text = s.render_draft(state)
        except Exception as e:  # noqa: BLE001 业务 hook 失败只影响本 hook
            logger.warning("tasks.render_draft_failed", task_type=s.task_type, domain=s.domain, error=str(e))
            continue
        if text:
            out.append(text)
    return out


def render_success_message(tool_name: str, raw_result: dict[str, Any], *, domain: str = "") -> str | None:
    """create_tool 成功后生成建议回复文案；失败/error 不输出。"""
    if raw_result.get("ok") is False or "error" in raw_result:
        return None
    for s in REGISTRY:
        if not _domain_matches_name(s, domain):
            continue
        if s.create_tool.name != tool_name:
            continue
        try:
            text = s.success_message(raw_result)
        except Exception as e:  # noqa: BLE001
            logger.warning("tasks.success_message_failed", task_type=s.task_type, domain=s.domain, error=str(e))
            return None
        return text or None
    return None


def should_display_draft(state: dict[str, Any]) -> bool:
    """聚合草稿展示门控；无 hook 时默认展示。"""
    for s in REGISTRY:
        if not _domain_matches_state(s, state):
            continue
        if s.is_draft_displayable is None:
            continue
        try:
            displayable = s.is_draft_displayable(state)
        except Exception as e:  # noqa: BLE001
            logger.warning("tasks.display_hook_failed", task_type=s.task_type, domain=s.domain, error=str(e))
            return False
        if not displayable:
            return False
    return True


def merge_tool_result_into_draft(
    tool_name: str,
    raw_result: dict[str, Any],
    current_draft: dict,
    *,
    domain: str = "",
) -> dict:
    """问每个 spec “这个 tool 返值要 merge 啥到 working_draft”，merge 第一个非空结果。"""
    merged = dict(current_draft)
    for s in REGISTRY:
        if not _domain_matches_name(s, domain):
            continue
        if s.tool_result_to_draft_patches is None:
            continue
        try:
            patches = s.tool_result_to_draft_patches(tool_name, raw_result)
        except Exception as e:  # noqa: BLE001
            logger.warning("tasks.merge_draft_failed", task_type=s.task_type, domain=s.domain, error=str(e))
            continue
        if patches:
            merged.update(patches)
            break  # 一个 tool 只让一个 spec 认领
    return merged
