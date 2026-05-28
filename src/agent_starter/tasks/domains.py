"""业务域定义 + 注册表 + 工具选择。

去业务化：框架不认识任何具体域名/工具名。classify 读 DomainSpec.triggers 选域，
agent_loop_action 调 select_tools_for_state 按域绑工具。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.tools import BaseTool


@dataclass
class DomainSpec:
    name: str
    label: str
    read_tools: list[BaseTool] = field(default_factory=list)   # 查询工具，全局候选
    write_tools: list[BaseTool] = field(default_factory=list)  # 写工具，仅本域激活时绑
    triggers: list[str] = field(default_factory=list)          # classify 命中线索（非硬正则）


DOMAIN_REGISTRY: dict[str, DomainSpec] = {}


def register_domain(spec: DomainSpec) -> None:
    DOMAIN_REGISTRY[spec.name] = spec


def get_domain(name: str) -> DomainSpec | None:
    return DOMAIN_REGISTRY.get(name)


def list_domains() -> list[DomainSpec]:
    return list(DOMAIN_REGISTRY.values())


def clear_registry() -> None:
    """仅测试用。"""
    DOMAIN_REGISTRY.clear()


def _dedupe(tools: list[BaseTool]) -> list[BaseTool]:
    seen: set[str] = set()
    out: list[BaseTool] = []
    for t in tools:
        if t.name in seen:
            continue
        seen.add(t.name)
        out.append(t)
    return out


def global_read_tools() -> list[BaseTool]:
    """所有域的 read 工具汇总（查询能力全局可达）。"""
    out: list[BaseTool] = []
    for spec in list_domains():
        out.extend(spec.read_tools)
    return _dedupe(out)


def select_tools_for_state(state: dict, *, extra_tools: list[BaseTool] | None = None) -> list[BaseTool]:
    """按 state.domain 选工具：global read ∪ 当前域 write ∪ extra，按 name 去重。

    权限过滤在 agent_loop_action 里统一执行。
    """
    tools = list(global_read_tools())
    domain = state.get("domain") or ""
    spec = get_domain(domain)
    if spec:
        tools.extend(spec.write_tools)
        from agent_starter.tasks.registry import collect_action_tools_for_domain
        tools.extend(collect_action_tools_for_domain(domain))
    if extra_tools:
        tools.extend(extra_tools)
    return _dedupe(tools)
