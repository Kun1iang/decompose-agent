# 业务开发快速开始

这页只讲“拿到模板后怎么开始写一个业务 agent”。第一天不用看 `graph.py`、memory、PG、skills、MCP。

## 1. 先跑通空模板

```bash
cp .env.example .env
# 填 OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL

uv run --extra dev pytest -q
uv run uvicorn agent_starter.main:app --port 8201
```

健康检查：

```bash
curl http://localhost:8201/health
```

## 2. 生成一个业务域

以“工单 ticket”为例：

```bash
uv run python scripts/new_domain.py ticket --label 工单 --trigger 工单 --trigger ticket
```

脚本会生成：

```text
src/agent_starter/tasks/ticket/
  __init__.py
  domainspec.py
  prompt.py
  taskspec.py
  tools.py
tests/tasks/ticket/test_ticket.py
```

并自动在 `src/agent_starter/tasks/__init__.py` 里注册 `ticket.register()`。

## 3. 只改这几个地方

| 文件 | 你要做什么 |
|---|---|
| `tools.py` | 把脚手架里的内存工具换成真实 DB/API/MCP 调用 |
| `prompt.py` | 写清楚这个业务域的对话规则 |
| `domainspec.py` | 调整 `label`、`triggers`、read tools |
| `taskspec.py` | 调整创建动作、成功文案；复杂草稿再加 hook |
| `tests/tasks/<domain>/` | 补你的业务工具和注册测试 |

正常业务开发不需要改：

```text
graph.py
main.py
state.py
nodes/
memory/
security/
serving/
```

## 4. 跑本域测试

```bash
uv run --extra dev pytest tests/tasks/ticket/test_ticket.py -q
uv run --extra dev pytest -q
```

## 5. 调接口试一轮

```bash
curl -s http://localhost:8201/agent/chat \
  -H 'content-type: application/json' \
  -d '{"message":"帮我创建一个登录失败的工单","user_id":1,"thread_id":"t1"}'
```

## 6. 什么时候再看深入文档

| 你遇到的问题 | 去看 |
|---|---|
| 需要手写复杂 domain / 多轮草稿 | `docs/adding-a-domain.md` |
| 想理解 LangGraph 拓扑 | `docs/concepts-langgraph.md` |
| 要接权限/JWT | `docs/concepts-security.md` |
| 要接 PG/pgvector 记忆 | `docs/concepts-memory.md` |
| 要调服务端点/SSE/会话 | `docs/concepts-serving.md` |

## 7. 两个默认取舍

- 脚手架生成的业务域默认注册启用；如果你需要 env 开关，在 `register_enabled_domains()` 里包一层配置判断。
- 模板不内置 MCP client。真实业务如果走 MCP，在 `tools.py` 里把 MCP/后端 API 调用包成 LangChain `@tool` 即可，agent loop 不需要改。
