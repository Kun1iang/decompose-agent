"""数据分析域 —— 拆解-并行检索-综合 Agent"""
from agent_starter.tasks.analytics.domainspec import SPEC
from agent_starter.tasks.domains import register_domain


def register() -> None:
    """Register the analytics domain explicitly and idempotently."""
    register_domain(SPEC)
