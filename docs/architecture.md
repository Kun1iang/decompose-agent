# 架构

本模板的整体结构、模块职责、一个对话 turn 的数据流，以及设计原则。先读 [concepts-langgraph.md](concepts-langgraph.md) 了解 LangGraph 基础。

> **图例**：✅ 开箱可用并测试 · 🔌 模板提供接线/参考实现，业务按需接真实 infra 或工具服务。

---

## 1. 图拓扑

`src/agent_starter/graph.py`：

```
START → {classify ∥ recall} → agent → write → END
```

- `classify`：判当前业务 `domain`（**读已注册域的 `triggers`**，无业务硬编码；无域则零 LLM 返空；LLM 失败/未知时用 trigger 做确定性兜底）。
- `recall`：召回用户记忆（偏好/观察）写 `state.recalled_memory`（与 classify 并行 fan-out）。
- `agent`（`agent_loop_action`）：唯一 ReAct 入口，按 `domain` 选工具（+ 权限过滤），多轮 LLM↔工具，注入记忆/域 prompt，工具异常转 ToolMessage，不让单个业务工具拖垮 turn。
- `write`：turn 末确定性抽取偏好写 store（开 `ENABLE_LLM_PREF_EXTRACTION` 再叠加 LLM 抽取）。

> 演进只在 `graph.py` 加 node/edge，`build_graph(checkpointer=None)` 签名不变。需要“前端按钮/隐藏块路由”或“分支”时，可在 START 后加一个 router 节点走条件边——本模板未内置。

---

## 2. 模块职责

| 模块 | 职责 | 状态 |
|---|---|---|
| `settings.py` | 全局配置；可选能力（PG/embed/MCP/LLM 抽取）默认空/关 = 零依赖启动 | ✅ |
| `state.py` | `AgentState`；通用 `working_draft`（域自解释）+ `permissions`，**无业务字段** | ✅ |
| `llm.py` | `build_llm()` 从 settings 造 ChatOpenAI | ✅ |
| `graph.py` | `build_graph()` 装配 StateGraph | ✅ |
| `nodes/classify.py` | 域分类（读 `DomainSpec.triggers`；无域零 LLM） | ✅ |
| `nodes/memory.py` | recall（召回）/ write（抽取写入）记忆节点 | ✅ |
| `nodes/agent.py` | `agent_loop_action`：按域选工具的 ReAct 循环 + 记忆注入 + 安全钩子（`agent_node` 为兼容别名） | ✅ |
| `tasks/{registry,domains}.py` | **域/任务注册机制**（`TaskSpec`/`DomainSpec`）——业务扩展核心接口；`TaskSpec.create_tool` 会随当前域自动绑定 | ✅ |
| `tasks/example_todo/` | 唯一示例域（默认关，可整目录删，delete-clean 参照） | ✅ |
| `memory/{models,store,provider,extractor}.py` | `MemoryStore` 接口 + `InMemoryStore` 默认 + 确定性偏好抽取 | ✅ |
| `memory/llm_extractor.py` | LLM 富偏好抽取 | 🔌 `ENABLE_LLM_PREF_EXTRACTION` |
| `memory/{embedding,pgvector_store}.py` | pgvector MemoryStore + embedding 客户端；lifespan opt-in 装配 | 🔌 业务接 PG/embedding 后验证 |
| `security/{permissions,sanitize,prompt}.py` | 工具权限过滤 + 输入去注入/包裹 + 输出清理 + 系统基线 | ✅ |
| `serving/{sessions,checkpointer}.py` | 会话索引（InMemory 默认）+ checkpointer 生命周期工厂（Memory/PG） | ✅ |
| `skills/loader.py` + 顶层 `skills/` | Markdown 能力包：加载 + 按相关性选中 + 注入 system（无代码加 skill） | ✅ |
| `main.py` | FastAPI：lifespan 装配 + `/health` + `/agent/chat`（同步）+ `/agent/chat/stream`（SSE）+ 会话端点 | ✅ |
| Postgres checkpoint（`main.py` lifespan） | 配 `AGENT_PG_DSN` → AsyncPostgresSaver | 🔌 业务接 PG 后验证 |
| MCP 工具接入 | 预留 `MCP_SERVER_URL`；业务把 MCP/后端 API 包成 `@tool` 注册到 domain | 🔌 业务自行对接 |

**单一职责**：node 拆在 `nodes/`，业务域各自一目录在 `tasks/<domain>/`，记忆实现拆在 `memory/`。改一处不牵动全局。

---

## 3. 一个对话 turn 的数据流

```
HTTP POST /agent/chat {message, user_id, thread_id, jwt, permissions?, workspace_id?, page_context?}
   │
   ▼ main.py 组装 inputs（HumanMessage + user_id + domain="" ...）
   ▼ graph.ainvoke(inputs, {thread_id})
   │   checkpointer 按 thread_id 加载历史 state
   ├─ classify：state.domain = 命中域（LLM + trigger 兜底） ┐ 并行 fan-out
   ├─ recall：  state.recalled_memory = 偏好/观察        ┘
   ▼ agent（fan-in，等 classify+recall）：
   │   select_tools(domain) + 权限过滤 → bind →
   │   system 拼基线+记忆+**相关 skill**+域 prompt，user 输入 sanitize/wrap →
   │   ReAct 多轮（working_draft 经 TaskSpec hook 累积）→ 终答 sanitize
   ▼ write：确定性(+可选 LLM)抽取偏好 → MemoryStore
   ▼ main.py 取末条 AIMessage → 返回 {reply}（流式则逐节点 SSE + done）
   ▼ checkpointer 存本 turn 后 state；sessions.touch 更新会话索引
```

---

## 4. 设计原则（为什么这么拆）

1. **开箱即跑**：所有外部依赖（PG/pgvector/MCP/LLM 抽取）都 opt-in，env 留空即关闭、走 in-memory/no-op 兜底。新人 clone 配个 LLM key 就能跑。
2. **delete-clean**：业务域自包含在 `tasks/<domain>/`，core 不 import 业务符号、不含业务名。删域 = rm 目录 + 删一行注册。验收线：`grep -riE "offer|hr_|..." src/agent_starter`（tasks/ 外）必须 CLEAN。
3. **注册式扩展**：加业务只在 `tasks/` 下加目录 + 注册，不改 `graph.py`/`classify`/`agent`。框架层不认识具体业务字段名——靠 `DomainSpec`/`TaskSpec` 钩子注入。
4. **通用 `working_draft`**：取代业务专属草稿字段。框架只给一个 dict 草稿袋 + 通用闸门，含义由当前域解释。
5. **签名稳定 + 依赖可注入**：`build_graph(checkpointer=None)`、`agent_loop_action(state, *, llm=None)`、`recall/write(state, *, store=None)` 跨阶段不变，演进与测试都靠注入假实现。

---

## 5. 配置矩阵（能力开关）

| env | 空缺省 | 配置后 | 状态 |
|---|---|---|---|
| `OPENAI_*` | 必填 | LLM 调用 | ✅ |
| `ENABLE_EXAMPLE_DOMAIN` | 不注册示例域 | `1` 注册 `example_todo` | ✅ |
| `ENABLE_LLM_PREF_EXTRACTION` | write 只做确定性抽取（不打 LLM） | 叠加 LLM 富偏好抽取 | ✅ |
| `SKILLS_DIR` | `skills` | 从指定目录加载 Markdown skills | ✅ |
| `AGENT_PG_DSN` | checkpointer=MemorySaver + 记忆 in-memory | Postgres checkpoint；若同时配下行则启用 pgvector MemoryStore | 🔌 业务接 PG 后验证 |
| `AGENT_EMBED_BASE_URL` | 记忆仍用 in-memory | 与 `AGENT_PG_DSN` 同配时启用 pgvector 语义召回（需 `[pg]`） | 🔌 业务接 embedding 后验证 |
| `AGENT_EMBED_DIM` | `1536` | pgvector 表的 embedding 维度，需匹配 `AGENT_EMBED_MODEL` | 🔌 业务按模型配置 |
| `MCP_SERVER_URL` | 空 | 仅预留配置；业务自行封装 MCP/后端工具 | 🔌 业务自行对接 |

各能力的实现/扩展细节见对应 concepts 文档；落地节奏见 [specs/2026-05-27-extraction-design.md](specs/2026-05-27-extraction-design.md)。
