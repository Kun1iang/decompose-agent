"""确定性偏好抽取（不调 LLM）。当前只抽昵称；LLM-based 富抽取见 docs 扩展点。"""
from __future__ import annotations

import re

from langchain_core.messages import HumanMessage

from agent_starter.memory.models import Preference

# “叫我X / 喊我X / 称呼我为X / 称呼我成X”——只匹配明确的命名声明，避免误伤。
_NICKNAME_RE = re.compile(
    r"(?:叫我|喊我|称呼我(?:为|成|作)?)\s*([^\s，。！？,.!?；;:：\"'“”]{1,20})"
)
_NEG_PREFIXES = ("不要", "别", "不用", "不准")


def _last_user_text(messages: list) -> str:
    for m in reversed(messages or []):
        if isinstance(m, HumanMessage):
            c = getattr(m, "content", "")
            return c if isinstance(c, str) else ""
    return ""


def extract_preferences(messages: list) -> list[Preference]:
    """从最后一条用户消息确定性抽取偏好。返回 0~1 条（昵称取最后命中）。"""
    text = _last_user_text(messages)
    last_name: str | None = None
    for m in _NICKNAME_RE.finditer(text):
        prefix = text[max(0, m.start() - 4):m.start()]
        if any(n in prefix for n in _NEG_PREFIXES):
            continue
        name = m.group(1).strip().removesuffix("吧").strip()
        if name:
            last_name = name
    return [Preference(key="nickname", value=last_name)] if last_name else []
