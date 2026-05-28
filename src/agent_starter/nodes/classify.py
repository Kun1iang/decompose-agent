"""classify 节点：在已注册域里选一个 domain。去业务化——无任何业务硬编码。

无注册域 → 直接返空（零 LLM）。有域 → 把“域名 + label + triggers”喂给 LLM，
让它回一个域名（或 none）；解析后校验必须是已注册域，否则兜底空。
"""
from __future__ import annotations

import structlog
from langchain_core.messages import HumanMessage

from agent_starter.llm import build_llm
from agent_starter.tasks.domains import get_domain, list_domains

logger = structlog.get_logger(__name__)


def _last_user_text(messages: list) -> str:
    for m in reversed(messages or []):
        if isinstance(m, HumanMessage):
            c = getattr(m, "content", "")
            return c if isinstance(c, str) else ""
    return ""


def _build_prompt() -> str:
    lines = ["你是业务域分类器。根据用户最新消息，从下面候选域里选**最匹配的一个**。",
             "只输出域名本身（小写），无法归类就输出 none。不要任何多余文字。", "", "候选域："]
    for s in list_domains():
        trig = "，".join(s.triggers) if s.triggers else ""
        lines.append(f"- {s.name}（{s.label}）{('｜线索：' + trig) if trig else ''}")
    return "\n".join(lines)


def _trigger_match(user_text: str) -> str:
    q = (user_text or "").lower()
    best: tuple[int, str] = (0, "")
    for spec in list_domains():
        score = sum(1 for trig in spec.triggers if trig and trig.lower() in q)
        if score > best[0]:
            best = (score, spec.name)
    return best[1]


async def classify_intent(state: dict, *, llm=None) -> dict:
    domains = list_domains()
    if not domains:
        return {"domain": ""}  # 无域：零 LLM

    user_text = _last_user_text(state.get("messages") or [])
    if llm is None:
        llm = build_llm()
    try:
        resp = await llm.ainvoke([("system", _build_prompt()), ("user", user_text)])
        raw = (getattr(resp, "content", "") or "").strip().lower()
    except Exception as e:  # noqa: BLE001  分类失败降级到 trigger
        logger.warning("classify.failed", error=str(e))
        raw = ""
    domain = raw if get_domain(raw) else _trigger_match(user_text)
    logger.info("classify.done", domain=domain, raw=raw)
    return {"domain": domain}
