"""example_todo 示例域。删除本目录 + tasks/__init__.py 里那一行 import 即彻底移除。"""
from agent_starter.tasks.domains import register_domain
from agent_starter.tasks.example_todo.domainspec import SPEC as DOMAIN_SPEC
from agent_starter.tasks.example_todo.taskspec import SPEC as TASK_SPEC
from agent_starter.tasks.registry import REGISTRY


def register() -> None:
    register_domain(DOMAIN_SPEC)
    if TASK_SPEC not in REGISTRY:
        REGISTRY.append(TASK_SPEC)
