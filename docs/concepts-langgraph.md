# LangGraph 核心概念

给第一次接触 LangGraph 的同学：用本模板前需要理解的 6 个概念。读完你应该能看懂 `graph.py` / `state.py` / `nodes/` 在干嘛。

> 官方文档：https://langchain-ai.github.io/langgraph/

---

## 1. 为什么是 LangGraph，而不是裸调 LLM

裸调 LLM = “一问一答”。真实 agent 要：多步推理、调工具、补查信息、跨轮记住上下文、可中断/恢复、可观测。LangGraph 把这套编排成一张**有向图**：节点是计算步骤，边是流转，状态在节点间传递并被持久化。它解决的核心是 **“多步 + 有状态 + 可恢复”**。

---

## 2. State（状态）

整张图共享一份状态对象，用 `TypedDict` 声明字段。节点读它、返回“要更新的字段”，LangGraph 把更新合并回去。

本模板的状态在 `src/agent_starter/state.py`：

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]   # 对话历史
    domain: str                               # 当前业务域
    working_draft: dict | None                # 通用草稿袋
    recalled_memory: Any | None               # recall 节点写入
    ...
```

**关键：reducer（合并策略）**。普通字段，节点返回的值**覆盖**旧值。`messages` 用了 `Annotated[list, add_messages]` —— `add_messages` 是一个 reducer，让节点返回的消息**追加**到历史而不是覆盖。所以节点里 `return {"messages": [resp]}` 是“追加一条”，不是“把历史替换成一条”。

> 这就是为什么 `state.py` 里只有 `messages` 带 `Annotated[..., add_messages]`，其它字段都是覆盖语义。

---

## 3. Node（节点）

一个节点 = 一个函数：`async def node(state) -> dict`。入参是当前完整状态，返回**部分更新**（只含要改的字段）。

本模板最简单的节点是 `recall_memory`（`src/agent_starter/nodes/memory.py`）：

```python
async def recall_memory(state, *, store=None) -> dict:
    recalled = await (store or get_memory_store()).recall(...)
    return {"recalled_memory": recalled}   # 部分更新：只写 recalled_memory
```

约定：节点是 **async**；返回 dict 只放要更新的键；副作用（调 LLM/工具/DB）都在节点里。当前主链最复杂的节点是 `decompose` / `retrieve` / `synthesize`（见 §6）。

> 模板约定节点带 `*, llm=None`/`*, store=None` 这类可注入依赖，方便测试用假实现替换。

---

## 4. Edge（边）与图装配

- **普通边** `add_edge(A, B)`：A 跑完无条件去 B。
- **fan-out / fan-in**：从同一节点拉**多条**普通边到不同节点 = 并行；多条边汇入同一节点 = 该节点等全部上游完成再跑。
- **条件边** `add_conditional_edges(A, router_fn, {...})`：A 跑完调 `router_fn(state)` 返回 key 决定下一站（本模板暂未用，扩展分支路由时会用到）。
- `START` / `END` 是入口/出口哨兵。

本模板实际拓扑（`src/agent_starter/graph.py`）：

```python
builder.add_edge(START, "classify")
builder.add_edge(START, "recall")      # classify ∥ recall 并行 fan-out
builder.add_edge("classify", "decompose")
builder.add_edge("recall", "decompose") # decompose 等两路都完成
builder.add_edge("decompose", "retrieve")
builder.add_edge("retrieve", "synthesize")
builder.add_edge("synthesize", "write")
builder.add_edge("write", END)
# START → {classify ∥ recall} → decompose → retrieve → synthesize → write → END
```

`classify` 写 `state.domain`、`recall` 写 `state.recalled_memory`——字段不冲突，所以能安全并行。**加节点/边不改 `build_graph(checkpointer=None)` 签名**，拓扑演进对调用方透明。

---

## 5. Checkpointer（检查点 / 会话持久化）

图编译时传 `checkpointer`。它按 **thread_id** 把每个 turn 后的状态存下来，下一个 turn 用同一个 thread_id 进来时，历史状态自动加载——这就是“多轮对话记忆”的底座（与 §6 之外的语义记忆/偏好是两回事，那些在 `memory/`）。

```python
graph = build_graph(checkpointer=MemorySaver())   # 进程内内存，零依赖
await graph.ainvoke(inputs, config={"configurable": {"thread_id": "t1"}})
```

- `MemorySaver`：内存，重启即丢——本模板**默认**，保证开箱即跑。
- `AsyncPostgresSaver`：落 Postgres，跨重启/多实例——配 `AGENT_PG_DSN` 时由 `main.py` lifespan 启用（opt-in，需装 `[pg]`；该路径未经本仓 CI 验证，见 [concepts-serving.md](concepts-serving.md)）。

**thread_id = 一个会话**。同 thread_id 续聊，不同 thread_id 互相隔离。

---

## 6. 结构化工具调用

LLM 本身不能执行动作，只能“说要调哪个工具、传什么参数”。当前主链在 `decompose` 中一次性生成结构化检索计划：

```
LLM 生成计划
  → planning.py 校验工具名和参数
  → asyncio.gather 并行执行各步骤
  → synthesize 统一生成结果
```

仓库仍保留 `agent_loop_action` 作为旧模板能力，但 `main.py` 和 CLI 实际调用的是 `DecomposeGraph`。阅读当前项目时，不应再把 `nodes/agent.py` 当作主链。

---

## 这些概念在本模板的落点

| 概念 | 文件 | 说明 |
|---|---|---|
| State | `state.py` | `AgentState`，`messages` 用 `add_messages` reducer |
| Node | `nodes/{classify,memory}.py` + `graph.py` | classify / recall / decompose / retrieve / synthesize / write |
| Edge / 装配 | `graph.py` | `build_graph()`：`START→{classify∥recall}→decompose→retrieve→synthesize→write→END` |
| Checkpointer | `main.py` lifespan | 默认 `MemorySaver`；配 `AGENT_PG_DSN` 走 Postgres（opt-in，未验证） |
| 工具 / 计划 | `planning.py` + `graph.py` | 校验工具名/参数，并行执行结构化检索步骤 |

下一步看 [architecture.md](architecture.md)（本模板整体架构）和 [adding-a-domain.md](adding-a-domain.md)（怎么把业务接进来）。
