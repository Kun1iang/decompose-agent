"""Embedding 客户端（包 langchain OpenAIEmbeddings）。供 pgvector 语义召回用。

fail-soft：嵌入失败返 None，调用方降级（不阻断 turn）。
⚠️ 真实 embedding 端点未在 CI 验证，需配 AGENT_EMBED_* 后在你环境验。
"""
from __future__ import annotations

import structlog

from agent_starter.settings import get_settings

logger = structlog.get_logger(__name__)


class EmbeddingClient:
    def __init__(self) -> None:
        s = get_settings()
        from langchain_openai import OpenAIEmbeddings
        self._emb = OpenAIEmbeddings(
            base_url=s.agent_embed_base_url or s.openai_base_url,
            api_key=s.agent_embed_api_key or s.openai_api_key,
            model=s.agent_embed_model,
        )

    async def aembed(self, text: str) -> list[float] | None:
        try:
            return await self._emb.aembed_query(text or "")
        except Exception as e:  # noqa: BLE001
            logger.warning("embedding.failed", error=str(e))
            return None
