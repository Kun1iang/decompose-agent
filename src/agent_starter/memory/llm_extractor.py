"""LLM 富偏好抽取（opt-in）。抽 enum-keyed 风格偏好；nickname 仍走确定性 extractor。

fail-soft：LLM 调用 / JSON 解析失败一律返 []，绝不拖挂 write 节点。
"""
from __future__ import annotations

import json

import structlog

from agent_starter.llm import build_llm
from agent_starter.memory.extractor import _last_user_text
from agent_starter.memory.models import Preference

logger = structlog.get_logger(__name__)

LLM_PREF_KEYS = {"response_format", "verbosity", "tone", "answer_style"}

_SYSTEM = (
    "你是偏好提取器。从用户消息里抽取**用户对自己的风格偏好**，输出严格 JSON 数组"
    "（无 markdown 围栏）：[{\"key\":\"...\",\"value\":\"...\"}]。"
    f"key 只能取：{sorted(LLM_PREF_KEYS)}。没有可抽的返回 []。"
)


def _parse_json_array(raw: str) -> list[dict]:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("["):] if "[" in s else s
    i, j = s.find("["), s.rfind("]")
    if not (0 <= i < j):
        return []
    try:
        data = json.loads(s[i : j + 1])
        return data if isinstance(data, list) else []
    except (ValueError, TypeError):
        return []


async def extract_preferences_llm(messages: list, *, llm=None) -> list[Preference]:
    text = _last_user_text(messages)
    if not text:
        return []
    try:
        if llm is None:
            llm = build_llm(temperature=0.0)
        resp = await llm.ainvoke([("system", _SYSTEM), ("user", text)])
        items = _parse_json_array(getattr(resp, "content", "") or "")
    except Exception as e:  # noqa: BLE001  fail-soft
        logger.warning("llm_pref_extract.failed", error=str(e))
        return []
    out: list[Preference] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        key = str(it.get("key") or "").strip()
        value = it.get("value")
        if key in LLM_PREF_KEYS and value not in (None, ""):
            out.append(Preference(key=key, value=str(value)[:30]))
    return out
