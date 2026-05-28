"""工具权限过滤。工具自行声明所需权限点（无声明=公开）；按 state 授予的权限收口。

去业务化：不写死任何权限常量。权限点是普通字符串，由域/工具注册时声明。
"""
from __future__ import annotations

from langchain_core.tools import BaseTool

_TOOL_PERMISSIONS: dict[str, set[str]] = {}


def register_tool_permissions(tool_name: str, perms: list[str]) -> None:
    _TOOL_PERMISSIONS[tool_name] = set(perms)


def required_permissions(tool_name: str) -> set[str]:
    return _TOOL_PERMISSIONS.get(tool_name, set())


def clear_tool_permissions() -> None:
    """仅测试用。"""
    _TOOL_PERMISSIONS.clear()


def granted_permissions(state: dict) -> set[str] | None:
    """从 state 读授予的权限。无信息返 None（= 不限制，starter fail-open 默认）。"""
    perms = state.get("permissions")
    if perms is None:
        scope = state.get("user_scope")
        if isinstance(scope, dict):
            perms = scope.get("permissions")
        elif scope is not None:
            perms = getattr(scope, "permissions", None)
    if perms is None:
        return None
    return set(perms)


def filter_tools_for_permissions(
    tools: list[BaseTool], granted: set[str] | None,
) -> list[BaseTool]:
    """granted=None → 不限制；否则只保留 required ⊆ granted 的工具（无声明=公开）。"""
    if granted is None:
        return list(tools)
    return [t for t in tools if required_permissions(t.name) <= granted]
