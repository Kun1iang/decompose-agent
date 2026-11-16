"""recall_memory（turn 起召回）+ write_memory（turn 末写入）。

write 用确定性抽取，不调 LLM——所以不会拖慢/拖挂 turn。需要 LLM 富抽取时在此接入
（建议 fail-soft + 可异步），见 docs/concepts-memory.md。
"""
from __future__ import annotations

import structlog

from agent_starter.memory.extractor import _last_user_text, extract_preferences
from agent_starter.memory.provider import get_memory_store
from agent_starter.state import AgentState

logger = structlog.get_logger(__name__)


async def recall_memory(state: AgentState, *, store=None) -> dict:
    store = store or get_memory_store()
    user_id = int(state.get("user_id") or 0)
    query = _last_user_text(state.get("messages") or [])
    recalled = await store.recall(user_id, query)
    logger.info("recall.done", user_id=user_id, prefs=len(recalled.prefs), obs=len(recalled.observations))
    return {"recalled_memory": recalled}


async def write_memory(state: AgentState, *, store=None, llm=None) -> dict:
    store = store or get_memory_store()
    user_id = int(state.get("user_id") or 0)
    messages = state.get("messages") or []
    prefs = list(extract_preferences(messages))  # 确定性（昵称）
    # opt-in：LLM 富抽取（风格类偏好）。默认关 → write 不打 LLM。fail-soft。
    from agent_starter.settings import get_settings
    try:
        llm_enabled = get_settings().enable_llm_pref_extraction
    except Exception:  # noqa: BLE001 - optional settings failure means disabled
        llm_enabled = False  # settings 未配齐（无 OPENAI_* env）→ 视为关闭，write 仍可零依赖跑
    if llm_enabled:
        from agent_starter.memory.llm_extractor import extract_preferences_llm
        prefs += await extract_preferences_llm(messages, llm=llm)
    for p in prefs:
        await store.upsert_preference(user_id, p.key, p.value)
    if prefs:
        logger.info("write.prefs", user_id=user_id, n=len(prefs))
    return {}
