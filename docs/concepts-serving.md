# 服务化（FastAPI 入口）

`main.py` 把 graph 包成 HTTP 服务：lifespan 装配 + 同步/流式对话 + 会话端点。

## lifespan 与 app.state
启动时 `lifespan` 依次：① `register_enabled_domains()`；② 建会话 store（默认 in-memory）；
③ 按 env 可选安装 pgvector MemoryStore；④ 通过 `serving/checkpointer.py` 建 checkpointer 并 `build_graph` 挂到 `app.state.graph`。handler 用 `request.app.state.graph / .sessions`。

> 用 `TestClient(app)` 测试时要用 `with TestClient(app) as c:`（context manager）才会触发 lifespan。

## 端点
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| POST | `/agent/chat` | 同步：跑完返回 `{reply}` |
| POST | `/agent/chat/stream` | **SSE 流式**：逐节点推 `{"type":"update","node":...}`，末尾 `{"type":"done","reply":...}` |
| GET | `/agent/sessions?user_id=` | 用户的会话列表（按最近活跃倒序） |
| GET | `/agent/sessions/{thread_id}/messages?user_id=` | 会话历史（先校验该 thread 属于该 user，再从 checkpointer `aget_state` 读 role+content） |
| DELETE | `/agent/sessions/{thread_id}?user_id=` | 删会话索引 |

SSE 事件体：`data: {json}\n\n`。token 级流式（逐字）需要 streaming LLM + `astream_events`，本模板先做**节点级**更新流（`stream_mode="updates"`），token 级留扩展。

## 会话 store vs checkpointer（分工）
- **checkpointer**（LangGraph）：存“每个 thread 的完整对话状态”，是历史/续聊的真相源。
- **SessionStore**：只存“用户 → 会话列表”的轻量索引（标题 + 最近活跃），给会话列表 UI 用；会话历史读取也先查这个索引做用户隔离。
- 删除会话目前只删索引、**不清 checkpointer**（starter 简化）；要彻底清需调 checkpointer 的删除 API（扩展）。

## checkpointer：默认 MemorySaver / Postgres opt-in
- 默认 `MemorySaver`（进程内，重启即丢）——零依赖。
- 配 `AGENT_PG_DSN` → lifespan 里 lazy import `AsyncPostgresSaver`（`from_conn_string` async 上下文 + `await setup()`），跨重启/多实例持久化。需装可选依赖：`pip install -e ".[pg]"`。
- > ⚠️ **Postgres checkpoint 路径未经本仓自动化验证**（CI 默认无 PG）。请在你的真库上跑一次确认 `setup()` 建表 + 续聊正常。SSE/会话/MemorySaver 路径已单测覆盖。

## memory store：默认 InMemory / pgvector opt-in
- 默认 `InMemoryStore`，重启即丢。
- 同时配 `AGENT_PG_DSN` + `AGENT_EMBED_BASE_URL` → lifespan 安装 `PgVectorStore`，偏好落 KV 表，观察走 pgvector 语义召回；`AGENT_EMBED_DIM` 要与实际 embedding 模型维度一致。
- shutdown 会关闭 memory pool 并 reset 全局 store；初始化失败时也会关闭已创建的 pool，避免测试/热重载串状态。

## 请求上下文
`/agent/chat` 和 `/agent/chat/stream` 的 body 支持可选 `permissions`、`user_scope`、`workspace_id`、`page_context`。入口只负责透传到 `AgentState`，权限过滤和业务上下文解释由后续节点/域工具处理。
