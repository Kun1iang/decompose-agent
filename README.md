# langgraph-agent-starter

> 通用 **LangGraph agent 应用模板**。组内做新的对话式 agent 业务时，clone 本仓直接起步，不用从零搭 graph / 工具注册 / 记忆 / 服务入口。

抽取自生产项目 `talentos-agent`，去业务化后沉淀为可复用骨架。

---

## 状态

> 图例：✅ 开箱可用并测试 · 🔌 模板提供接线/参考实现，业务按需接真实 infra 或工具服务

| 能力 | 内容 | 状态 |
|---|---|---|
| 骨架 | 精简 settings / 通用 state / graph 装配 / 瘦 FastAPI 入口 | ✅ |
| 域机制 + 示例 | 泛型 classify + ReAct action + `DomainSpec`/`TaskSpec` 注册 + `example_todo`（默认关，可整目录删） | ✅ |
| 记忆 | recall/write 节点 + `MemoryStore` 接口 + `InMemoryStore` 默认 + 确定性偏好抽取 | ✅ |
| 安全 | 工具权限过滤 + 输入去注入/包裹 + 输出清理 + 系统基线 | ✅ |
| 服务化 | SSE 流式 + 会话列表/历史/删除端点 | ✅ |
| 业务脚手架 | `scripts/new_domain.py` 一键生成 domain 文件、测试骨架并注册 | ✅ |
| LLM 富偏好抽取 | `ENABLE_LLM_PREF_EXTRACTION` opt-in | ✅ |
| skills（Markdown 能力包） | 顶层 `skills/` 放 SKILL.md，按相关性注入 prompt（无需写代码） | ✅ |
| 持久化 + 语义召回 | 模板提供 Postgres checkpoint + pgvector MemoryStore 接线；业务需接自己的 PG/embedding 并验证 | 🔌 业务按需对接 |
| MCP 工具接入 | 预留 `MCP_SERVER_URL`；业务需把 MCP/后端 API 包成 `@tool` 注册到 domain | 🔌 业务自行对接 |

测试：`uv run --extra dev pytest` 零依赖全绿。设计依据见 [`docs/specs/2026-05-27-extraction-design.md`](docs/specs/2026-05-27-extraction-design.md)。

---

## 两条硬契约（贯穿设计）

1. **开箱即跑** — `clone && 配 LLM key && run`，**零外部依赖**（不需要 Postgres / pgvector / MCP）就能 `/health` + 跑通一个对话 turn。
2. **delete-clean** — 删一个业务域 = `rm` 一个目录 + 删一行注册，**不改任何 core 文件**，删完测试照过。core 里 `grep` 不到任何具体业务名。

---

## Quickstart

需要 **Python 3.11+**。

如果你只是要开始做一个业务 agent，先看 10 分钟版：[docs/quickstart-for-business.md](docs/quickstart-for-business.md)。

```bash
git clone http://gitlab.creditease.corp/aigc/langgraph-agent-starter.git
cd langgraph-agent-starter

python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"      # 公司内网建议配 PyPI mirror

cp .env.example .env
# 编辑 .env，至少填 OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL

# 起服务
.venv/bin/uvicorn agent_starter.main:app --port 8201
```

验证：

```bash
curl http://localhost:8201/health
# {"status":"ok"}

curl -s http://localhost:8201/agent/chat \
  -H 'content-type: application/json' \
  -d '{"message":"你好","user_id":1,"thread_id":"t1"}'
# {"reply":"..."}
```

跑测试：

```bash
.venv/bin/pytest -v        # 全绿
```

> 想看示例域：`.env` 里设 `ENABLE_EXAMPLE_DOMAIN=1`，对话发“帮我加个买牛奶的待办”，agent 会调用 todo 工具并回复。看完照着 `tasks/example_todo/` 抄自己的域，抄完按 [docs/adding-a-domain.md](docs/adding-a-domain.md) §6 三步删掉。

生成新业务域：

```bash
uv run python scripts/new_domain.py ticket --label 工单 --trigger 工单 --trigger ticket
```

> 本机默认 `python3` 是 3.9 装不了本包；用 3.11+。详见 [docs/development.md](docs/development.md)。

---

## 项目结构

```
langgraph-agent-starter/
├── pyproject.toml            # 包定义 + 依赖（[pg] 为可选）
├── .env.example              # 配置样例
├── scripts/new_domain.py     # ★ 业务域脚手架
├── skills/                   # ★ Markdown 能力包（业务同事丢 SKILL.md 即加能力，无需写代码）
│   └── example_concise/SKILL.md
├── src/agent_starter/
│   ├── settings.py           # 全局配置（可选项默认空 = 关闭）
│   ├── state.py              # AgentState（通用 working_draft，无业务字段）
│   ├── llm.py                # build_llm()
│   ├── graph.py              # build_graph()：START → {classify ∥ recall} → agent → write → END
│   ├── nodes/                # classify（选域）+ agent（ReAct）+ memory（recall/write）
│   ├── tasks/                # 域/任务注册机制（DomainSpec/TaskSpec）+ example_todo 示例域
│   ├── memory/               # MemoryStore 接口 + InMemoryStore + 确定性/LLM 抽取 + pgvector(opt-in)
│   ├── security/             # 权限过滤 + 输入/输出脱敏 + 系统基线
│   ├── serving/              # 会话索引 + checkpointer 生命周期工厂
│   ├── skills/               # skill 加载/相关性选择/注入（loader）
│   └── main.py               # FastAPI：lifespan + /health + /agent/chat(+stream) + 会话端点
├── tests/                    # pytest 套件
└── docs/
    ├── specs/ · plans/       # 设计 spec + 实现 plan
    ├── concepts-langgraph.md # LangGraph 核心概念
    ├── concepts-memory.md    # 记忆模型
    ├── concepts-security.md  # 安全层
    ├── concepts-serving.md   # 服务化（SSE/会话/checkpoint）
    ├── concepts-skills.md    # skills（Markdown 能力包）
    ├── architecture.md       # 整体架构
    ├── quickstart-for-business.md # 业务开发 10 分钟路径
    ├── development.md        # 开发指南
    └── adding-a-domain.md    # 业务怎么对接（域/工具）
```

---

## 文档索引

| 文档 | 讲什么 |
|---|---|
| [docs/quickstart-for-business.md](docs/quickstart-for-business.md) | 业务同事第一天怎么生成 domain、改工具、跑测试 |
| [docs/concepts-langgraph.md](docs/concepts-langgraph.md) | LangGraph 是什么、State/Node/Edge/Checkpointer/ReAct 核心概念 |
| [docs/concepts-memory.md](docs/concepts-memory.md) | 记忆模型：MemoryStore 接口、InMemoryStore、偏好/观察、扩展点 |
| [docs/concepts-security.md](docs/concepts-security.md) | 安全层：权限过滤、输入去注入/包裹、输出清理、系统基线 |
| [docs/concepts-serving.md](docs/concepts-serving.md) | 服务化：lifespan/app.state、SSE 协议、会话 store vs checkpointer、PG opt-in |
| [docs/concepts-skills.md](docs/concepts-skills.md) | skills：SKILL.md 格式、相关性选中、skill vs domain、怎么加/删 |
| [docs/architecture.md](docs/architecture.md) | 本模板的图拓扑、模块职责、数据流、设计原则（标注现状/规划） |
| [docs/development.md](docs/development.md) | 环境搭建、运行、测试、文件放哪儿、编码与提交约定 |
| [docs/adding-a-domain.md](docs/adding-a-domain.md) | 业务对接：怎么加一个域、TaskSpec/DomainSpec、删除示例域 |
| [docs/specs/](docs/specs/) · [docs/plans/](docs/plans/) | 设计 spec 与实现 plan |

---

## 与 talentos-agent 的关系

`talentos-agent` 是本模板的**抽取源**，本仓泛型化是在副本上做的——**不回改 talentos-agent**。两者是“产品”与“模板”关系，不共享代码依赖。
