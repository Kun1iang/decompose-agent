# Phase 5：服务化（SSE 流式 + Postgres checkpoint + 会话端点）实现计划

> REQUIRED SUB-SKILL: subagent-driven-development / executing-plans。本 plan 内联执行。

**Goal:** 把瘦入口升级为可用服务：SSE 流式 `/agent/chat/stream`、可选 Postgres checkpoint、会话列表/历史/删除端点。

**Architecture:** 引入 lifespan：启动注册域 + 建 checkpointer（默认 MemorySaver，配 `AGENT_PG_DSN` 走 AsyncPostgresSaver）+ 建会话 store（默认 in-memory）+ 编译 graph 挂到 `app.state`。SSE 用 `graph.astream(stream_mode="updates")` 逐节点推事件。会话 store 索引 (user_id→threads)，历史从 checkpointer `aget_state` 读。

**Tech Stack:** FastAPI（StreamingResponse / lifespan）、LangGraph astream/aget_state、langgraph-checkpoint-postgres（**可选**，opt-in）。

**验证边界（用户决策）：** SSE / 会话 / MemorySaver 默认 → 零依赖单测可验。**Postgres checkpoint 真集成 = 未经我验证**，代码写好、lazy import、标注需真库跑。

**前置：** `/Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest`。

---

## File Structure
```
src/agent_starter/serving/
  __init__.py
  sessions.py        # SessionStore 协议 + InMemorySessionStore + provider
  checkpointer.py    # make_checkpointer：MemorySaver 默认 / PG opt-in（lazy）
src/agent_starter/main.py   # 重写：lifespan + /health + /agent/chat + /agent/chat/stream + 会话端点
tests/{test_sessions,test_serving}.py
docs/concepts-serving.md + architecture/README 翻牌
pyproject.toml      # 加 optional [pg] 依赖
```

---

## Task 1：会话 store

**Files:** `serving/__init__.py`(空), `serving/sessions.py`; Test `tests/test_sessions.py`

签名：
```python
# serving/sessions.py
@dataclass
class SessionMeta:
    thread_id: str
    title: str
    updated_at: float

class SessionStore(Protocol):
    async def touch(self, user_id: int, thread_id: str, title: str) -> None: ...
    async def list_for_user(self, user_id: int) -> list[SessionMeta]: ...
    async def delete(self, user_id: int, thread_id: str) -> bool: ...

class InMemorySessionStore:  # user_id -> {thread_id: SessionMeta}
    # touch: 不存在则建（title 取首条），存在则更新 updated_at
    # list_for_user: 按 updated_at 倒序
    # delete: 删除返 bool

# provider: get/set/reset_session_store（同 memory.provider 套路）
```
测试：touch 建/更，list 倒序，delete，按 user 隔离，首条 title 不被后续覆盖。

---

## Task 2：checkpointer 工厂

**Files:** `serving/checkpointer.py`; Test `tests/test_serving.py`（部分）

```python
# serving/checkpointer.py
from langgraph.checkpoint.memory import MemorySaver

def make_memory_checkpointer():
    return MemorySaver()

# PG 走 lifespan async 上下文（AsyncPostgresSaver 是 async CM），见 main.py。
# 这里只暴露默认；真 PG 在 main.lifespan 里 lazy import + setup。
```
测试：`make_memory_checkpointer()` 返 MemorySaver 实例。（PG 路径在 main.lifespan，单测覆盖“无 DSN 走 memory 分支”。）

---

## Task 3：重写 main.py（lifespan + SSE + 会话端点）

**Files:** `main.py`; `pyproject.toml`（加 `[project.optional-dependencies] pg = ["langgraph-checkpoint-postgres>=2.0"]`）

要点：
- `lifespan`：`register_enabled_domains()`；若 `settings.agent_pg_dsn` → `async with AsyncPostgresSaver.from_conn_string(dsn) as saver: await saver.setup(); app.state.graph = build_graph(saver)`（**lazy import，未验证分支**）；否则 `build_graph(MemorySaver())`。`app.state.sessions = get_session_store()`。
- handler 用 `request.app.state.graph / .sessions`。
- `POST /agent/chat`（同步，保留）：跑 graph，`sessions.touch`，返 `{reply}`。
- `POST /agent/chat/stream`（SSE）：`StreamingResponse`，`async for chunk in graph.astream(inputs, cfg, stream_mode="updates")` 逐节点 `data: {json}\n\n`；末尾 `data: {"type":"done","reply":...}\n\n`。
- `GET /agent/sessions?user_id=`：`sessions.list_for_user`。
- `GET /agent/sessions/{thread_id}/messages?user_id=`：`graph.aget_state(cfg)` 取 messages 序列化（role+content）。
- `DELETE /agent/sessions/{thread_id}?user_id=`：`sessions.delete`（注：不清 checkpointer，starter 简化，文档注明）。

SSE 格式 helper：`_sse(obj) -> f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"`。

---

## Task 4：端点测试（TestClient + FakeLLM + MemorySaver）

**Files:** `tests/test_serving.py`

- client fixture 用 `with TestClient(app) as c`（触发 lifespan）；monkeypatch agent+classify build_llm = FakeLLM；不设 AGENT_PG_DSN（走 memory）。
- `test_health` / `test_chat_sync`（reply）。
- `test_chat_stream_emits_done_with_reply`：读 SSE 文本，断言含 `"type": "done"` 且含 reply。
- `test_sessions_listed_after_chat`：chat 后 GET /agent/sessions 含该 thread。
- `test_session_messages`：chat 后 GET .../messages 返回含用户消息+回复。
- `test_session_delete`：DELETE 后 list 不含。

---

## Task 5：文档 + 验收
- `docs/concepts-serving.md`：lifespan/app.state、SSE 事件协议、会话 store vs checkpointer 分工、PG checkpoint opt-in（lazy + 需真库验）+ `[pg]` 安装。
- `architecture.md`：main.py 行更新（lifespan + SSE + 会话端点 ✅）；config 矩阵 `AGENT_PG_DSN` 标“PG checkpoint（未集成验证）”。
- `README.md`：状态表加“服务化 ✅（SSE+会话；PG checkpoint opt-in 未验证）”；结构树加 `serving/`；doc 索引加 concepts-serving。
- 验收：全量回归绿；`test_delete_clean`（`serving/` 纳入 core）CLEAN；零依赖启动 + `/health` + 一次 stream 冒烟。

## 验收（AC）
- AC-V1 SSE 流式出 done+reply（test_chat_stream_emits_done_with_reply）。
- AC-V2 会话 list/messages/delete（对应 3 测试）。
- AC-V3 无 DSN 走 MemorySaver（lifespan memory 分支，端点测试即覆盖）。
- AC4 保持：serving/ 零业务名。
- **未验证**：PG checkpoint 真集成（lazy 分支，需用户真库）。

## Self-Review
- 去业务化：serving/ 无业务名。
- 占位：PG 分支是真实代码 + 明确“未验证”标注，非占位。
- 类型一致：`SessionStore.touch/list_for_user/delete`、`get_session_store()`、`_sse(obj)`。
- 回归：`test_app.py` 的 client fixture 需改用 `with TestClient(app)`（lifespan）——Task 4 一并修；或保留旧 test_app 并新增 test_serving。**决定：把 test_app 的 2 个用例并入 test_serving 的 with-lifespan fixture，删除 test_app.py，避免无 lifespan 的旧 fixture 拿不到 app.state.graph。**
