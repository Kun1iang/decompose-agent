"""FastAPI 入口：/health + /agent/chat（同步）+ /agent/chat/stream（SSE）+ 会话端点。

lifespan 启动时：注册域 → 建 checkpointer（默认 MemorySaver；配 AGENT_PG_DSN 走
AsyncPostgresSaver，**未经验证的 opt-in 路径**）→ 建会话 store → 编译 graph 挂 app.state。
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agent_starter.graph import build_graph
from agent_starter.memory.provider import (
    close_memory_resource,
    reset_memory_store,
    setup_memory_store_from_settings,
)
from agent_starter.serving.checkpointer import checkpointer_context
from agent_starter.serving.sessions import get_session_store
from agent_starter.settings import get_settings
from agent_starter.tasks import register_enabled_domains

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    register_enabled_domains()
    app.state.sessions = get_session_store()
    memory_resource = await setup_memory_store_from_settings(settings)
    try:
        async with checkpointer_context(settings) as checkpointer:
            app.state.graph = build_graph(checkpointer=checkpointer)
            logger.info(
                "serving.ready",
                checkpointer="postgres" if settings.agent_pg_dsn else "memory",
            )
            yield
    finally:
        await close_memory_resource(memory_resource)
        reset_memory_store()


app = FastAPI(title="langgraph-agent-starter", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    user_id: int = 0
    thread_id: str = "default"
    jwt: str = ""
    permissions: list[str] | None = None
    user_scope: dict[str, Any] | None = None
    workspace_id: int | None = None
    page_context: dict[str, Any] | None = None


def _inputs(req: ChatRequest) -> dict:
    workspace_id = req.workspace_id
    if workspace_id is None:
        try:
            workspace_id = get_settings().agent_workspace_id
        except Exception:  # noqa: BLE001 - settings load must not block serving default
            workspace_id = 1
    return {
        "messages": [HumanMessage(content=req.message)],
        "user_id": req.user_id,
        "jwt": req.jwt,
        "domain": "",
        "permissions": req.permissions,
        "user_scope": req.user_scope,
        "workspace_id": workspace_id,
        "page_context": req.page_context,
    }


def _cfg(req: ChatRequest) -> dict:
    return {"configurable": {"thread_id": req.thread_id}}


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/agent/chat")
async def chat(req: ChatRequest, request: Request) -> dict:
    out = await request.app.state.graph.ainvoke(_inputs(req), _cfg(req))
    await request.app.state.sessions.touch(req.user_id, req.thread_id, req.message)
    last = out["messages"][-1]
    return {"reply": getattr(last, "content", "")}


@app.post("/agent/chat/stream")
async def chat_stream(req: ChatRequest, request: Request) -> StreamingResponse:
    graph = request.app.state.graph
    sessions = request.app.state.sessions

    async def gen():
        reply = ""
        async for update in graph.astream(_inputs(req), _cfg(req), stream_mode="updates"):
            for node, delta in (update or {}).items():
                msgs = delta.get("messages") if isinstance(delta, dict) else None
                if msgs:
                    content = getattr(msgs[-1], "content", "")
                    if content:
                        reply = content
                yield _sse({"type": "update", "node": node})
        await sessions.touch(req.user_id, req.thread_id, req.message)
        yield _sse({"type": "done", "reply": reply})

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/agent/sessions")
async def list_sessions(user_id: int, request: Request) -> dict:
    metas = await request.app.state.sessions.list_for_user(user_id)
    return {"sessions": [
        {"thread_id": m.thread_id, "title": m.title, "updated_at": m.updated_at} for m in metas
    ]}


@app.get("/agent/sessions/{thread_id}/messages")
async def session_messages(thread_id: str, user_id: int, request: Request) -> dict:
    metas = await request.app.state.sessions.list_for_user(user_id)
    if not any(m.thread_id == thread_id for m in metas):
        raise HTTPException(status_code=404, detail="session not found")
    snap = await request.app.state.graph.aget_state({"configurable": {"thread_id": thread_id}})
    msgs = (snap.values or {}).get("messages", []) if snap else []
    out = []
    for m in msgs:
        role = m.__class__.__name__.replace("Message", "").lower()  # human/ai/tool
        out.append({"role": role, "content": getattr(m, "content", "")})
    return {"messages": out}


@app.delete("/agent/sessions/{thread_id}")
async def delete_session(thread_id: str, user_id: int, request: Request) -> dict:
    ok = await request.app.state.sessions.delete(user_id, thread_id)
    return {"deleted": ok}
