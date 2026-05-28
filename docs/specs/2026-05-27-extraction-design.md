# Spec：langgraph-agent-starter —— 从 talentos-agent 抽取通用模板

**Date**: 2026-05-27
**Status**: Draft（待 review）
**Repo**: `aigc/langgraph-agent-starter`（已建空仓）
**抽取源（只读，不改动）**: `talentos-agent`

---

## 1. 目标 / 非目标

**目标**：把 talentos-agent 的 LangGraph 实现抽成一个**通用 agent 应用模板**，组内人 clone 即可起业务开发。模板自带一个可删的玩具示例域（`example_todo`）做"怎么加一个业务域"的活参照。

**非目标**：
- **不改 talentos-agent 任何代码**。它是只读抽取源；本仓的"内核泛型化"在拷贝过来的副本上做，不回灌。
- 不复刻 talentos 业务（HR / offer / probation / OPC / solo / resume）。
- 不做 cookiecutter/CLI 生成器——这是 clone-and-edit 模板（名字已定 `*-starter`）。

## 2. 两条硬契约（贯穿全 spec 的验收线）

**C1 — delete-clean**：删除示例域 = `rm -rf src/<pkg>/tasks/example_todo/` + 删一行注册 + 从 `.env.example` 删开关。**不需要改任何 core 文件，删完测试照过。** 这条同时是"内核是否真去业务化"的试金石——core 里只要还 `grep` 得到 `example_todo` / `todo`，就没达标。

**C2 — 开箱即跑**：`git clone && cp .env.example .env && run` 零外部依赖（无需 Postgres / pgvector / 真 MCP / 真 LLM key 之外的东西）就能跑通 example_todo 出回复。checkpointer 默认 `MemorySaver`，memory 默认 in-memory，示例 tool 是纯本地实现。Postgres checkpoint + pgvector MemoryStore 都是 opt-in；MCP 只预留配置，starter 不内置 client。

## 3. 模块清单（keep / generalize / strip）

> 三分类。`generalize` = 拷过来但要去业务名。标 ❓ 的需 Phase 0 inventory 时确认归类。

### 3.1 Keep（基本原样，最多清 docstring 里的 HR 例子）
| 模块 | 说明 |
|---|---|
| `graph.py` | StateGraph 装配，业务无关（仅 docstring 有 HR 例） |
| `clients/mcp_client.py` `mcp_catalog.py` | 不纳入当前 starter；`MCP_SERVER_URL` 只保留为扩展点 |
| `llm.py` `llm_retry.py` `tracing.py` `events.py` `principal_identity.py` `instance_routing.py` | 基础设施 |
| `settings.py` `runtime_deps.py` | 配置 + 依赖装配（要加 in-memory 默认分支，见 §5.5/§8） |
| `admin/`（metrics） | 观测 |
| `nodes/_shared.py` `tool_display.py` `tool_result_cache.py` | ReAct 公共件（去业务名后保留） |
| `memory/`：`composite.py` `conflict_detector.py` `embedding.py` `scope.py` `render.py` `models.py` `stores/{short,long,org,pinned,preferences,conflict,entitylink}.py` | 记忆内核（解耦后保留，见 §5.5） |
| `security/`：`prompt_template.py` `input_sanitizer.py` `output_sanitizer.py` `quota.py` | 安全件 |
| `tasks/registry.py` `domains.py` `_base.py` `_shared_prompt.py` `_output_format.py` | **域/任务注册机制——模板的核心扩展接口** |

### 3.2 Generalize（拷过来必须去业务化）
| 模块 | 泛型化动作 | 详见 |
|---|---|---|
| `state.py` | 删 `offer_draft*` / `employee_id`；引入通用 `working_draft` | §5.2 |
| `nodes/action.py`（1429行） | 草稿 merge/visible/dirty 机器 → 全走 TaskSpec hook；删 `_WRITE_PROMPT_DOMAINS`、内联 `KNOWLEDGE_DOMAIN_PROMPT`、offer-phase / parse_resume / department-picker 特判 | §5.3 |
| `nodes/classify.py`（500行） | 删全部业务正则（`_EMPLOYEE_CHANGE_HINT_RE` 等）；改为泛型读 `DomainSpec.triggers` | §5.1 |
| `nodes/memory.py`（recall/write 节点） | 去 HR extractor 链耦合 | §5.5 |
| `nodes/user_message_router.py` | 去 offer_draft / dept_pick 特判，保留通用前端隐藏块协议或降级为示例 | §5.3 |
| `personas.py` | 5 个 HR persona → 1 个通用 `assistant` persona（+ 可选 1 示例 persona） | §5.4 |
| `security/access_policy.py` | 删 `TOOL_REQUIRED_PERMISSIONS` 里的 HR 工具表 + `OFFER_READ` 等；保留权限过滤框架，权限点改由域/工具自带 | §5.7 |
| `tools/draft.py`（`set_offer_draft`） | → 通用 `set_working_draft`（或并入示例域） | §5.3 |

### 3.3 Strip（不拷贝）
`mcp_tools.py`（~2700行 talentos 工具）、`tasks/{employee_create_with_offer,hr_advice,knowledge}/` + `offer_phase.py`、`tools/kb.py`、`me_memory.py`、`resume/`、`workflows/`、`integrations/`（solo/OPC 连接器）、`opc_*.py` + `opc_admin/`、memory 里 HR 专属 extractor（`candidate_assessment` `hiring_preference` `entity_focus` `reference`）。

`main.py`（1891行）→ **重写为更瘦的 app 入口**（决策 §12.4），不在原文件上清理：新入口只保留 FastAPI app + SSE 流 + `/agent/chat` `/agent/sessions*` `/health` 等会话基础设施，checkpointer/memory 依赖 optional（§8）。`/opc*` `/v1/capabilities` `/agent/resume`（workflow 唤醒）等业务/集成端点不带。`sessions/` `views/` `ops/` ❓Phase 0 确认是基础设施还是业务。

## 5. 关键泛型化设计

### 5.1 classify 去业务化
现状：classify.py 用一堆硬编码正则（offer/employee_change/policy 关键词）+ `_state_signal_domain` 里整段 OFFER/EMPLOYEE_CHANGE 逻辑判 domain。
模板：classify 只认**已注册域**——泛型遍历 `DOMAIN_REGISTRY`，用每个 `DomainSpec.triggers`（已存在字段，domains.py:70）做 LLM classifier 的候选提示 + 轻量短路。core 不出现任何具体业务词。域自带触发线索，删域即删线索 → 满足 C1。

### 5.2 AgentState 去 offer_draft
现状：`offer_draft` / `offer_draft_visible` / `offer_draft_dirty` / `employee_id` 是 offer 专属字段焊进 core state。
模板：core state 只留通用字段（`messages` `user_id` `owner_user_id` `jwt` `persona` `domain` `recalled_memory` `user_scope` `connector_key` `workspace_id` `tenant_id` `page_context` `invoked_tool/args`）。引入**单个通用草稿袋** `working_draft: dict[str, Any]`（+ `working_draft_visible/dirty` 通用闸门），语义完全由当前域解释。`employee_id` 这类落库结果不进 core state，由域通过 hook 自取。

### 5.3 action.py 草稿机器 → hook 驱动
action.py 现在约一半篇幅在伺候 offer_draft（merge patches / visible / dirty / dispatch 草稿卡 / offer-phase 消歧 / 部门选择器 / 简历特判）。模板保留"**state-driven 草稿 + 单次写库 tool**"这个框架范式，但：
- merge/render/是否展示/字段映射 → 全部走已有的 TaskSpec hook（`tool_result_to_draft_patches` / `render_draft` / `is_draft_displayable`），core 不认识任何字段名。
- 删 `_WRITE_PROMPT_DOMAINS`、offer-phase、parse_resume、department-picker 等全部业务特判。
- `KNOWLEDGE_DOMAIN_PROMPT` 这类域专属 prompt 段 → 改由 `DomainSpec`/`TaskSpec` 自带 prompt fragment 注入（顺带修掉 talentos 那个"prompt 被 domain 门控关掉"的坑——但那是 talentos 的问题，本仓只是不复刻该结构）。

### 5.4 persona 收敛
5 个 HR persona → 1 个通用 `assistant`（精确、步骤化、不带 HR 业务）。示例可选带 1 个 `example` persona 演示多 persona override。`DEFAULT_PERSONA = "assistant"`。

### 5.5 memory 子系统：解耦 + 默认 in-memory
- 不复刻 talentos 的五路 composite / ConflictDetector；starter 保留一个小而稳的 `MemoryStore` 协议。
- 默认 `InMemoryStore`（满足 C2）：偏好 KV latest-wins，观察保留近期 N 条。
- `PgVectorStore` 作为 opt-in 实现：同时配 `AGENT_PG_DSN` + `AGENT_EMBED_BASE_URL` + `[pg]` 时由 lifespan 装配；偏好落表，观察走 pgvector 语义召回。
- preference key enum 收成通用集（nickname/response_format/verbosity/tone/...），去 HR 味。

### 5.6 MCP：预留配置，示例用本地 tool
当前 starter 不内置 MCP client。`MCP_SERVER_URL` 只作为扩展点预留；example_todo 的工具是**纯本地内存实现**（不依赖 MCP），保证 C2 + 示例自洽可删。

### 5.7 access_policy 去 HR 权限
保留"按 capability/permission 过滤工具"的框架；删 HR 工具→权限点的硬表。权限点改为工具/域自带元数据。

### 5.8 workflow runtime 不进 starter
offer 长流程实现和 workflow hook 不纳入当前 starter，避免模板过重。需要长流程时，业务方可在 `TaskSpec` 基础上自行扩展 hook 和独立 workflow graph。

## 6. 仓库骨架（拟）
```
langgraph-agent-starter/
  README.md                  # 规范：定位 + quickstart + 怎么加域 + 怎么删示例
  CONTRIBUTING.md            # 域开发约定（命名/注册/测试）
  .env.example               # 含 ENABLE_EXAMPLE_DOMAIN=0 等开关
  pyproject.toml
  docs/specs/                # 本 spec
  src/agent_starter/         # 包名待定（见 §9 待决）
    graph.py state.py settings.py runtime_deps.py llm.py ...
    clients/ memory/ nodes/ security/ admin/
    tasks/
      registry.py domains.py _base.py _shared_prompt.py
      example_todo/          # ← 唯一示例域，默认关，可整目录删
        __init__.py prompt.py tools.py taskspec.py domainspec.py
        tests/
        README.md            # "删我 = rm 本目录 + 删 X 处注册行"
  tests/                     # 框架级测试
```

## 7. example_todo 设计 + delete-clean 机制
- 自包含一个目录，含：域 prompt、本地内存 todo 工具（`add_todo` / `list_todos` / `complete_todo`）、TaskSpec（演示 `working_draft` 收集字段 + 单次"写库"）、DomainSpec（带 `triggers`）、它自己的测试、README。
- 注册：`tasks/__init__.py` 里 **唯一一行** `if settings.enable_example_domain: from . import example_todo`。core 不 import 它任何符号。
- 开关 `ENABLE_EXAMPLE_DOMAIN` 默认 `0`（生产干净）；新人置 `1` 看示例。
- `example_` 前缀 + 全部符号自包含 → `grep -r example_ src/` 能定位全部残留，验证 C1。

## 8. 配置 / 启动矩阵
| env | 缺省 | 缺省行为 | 配了之后 |
|---|---|---|---|
| `ENABLE_EXAMPLE_DOMAIN` | `0` | 无域，回退 common 兜底 | `1` 注册 example_todo |
| `AGENT_PG_DSN` | 空 | checkpointer=MemorySaver；memory=in-memory | AsyncPostgresSaver；若同时配 embedding 则启用 PgVectorStore |
| `AGENT_EMBED_BASE_URL` | 空 | memory 仍用 in-memory | 与 `AGENT_PG_DSN` 同配时启用 pgvector 语义召回 |
| `MCP_SERVER_URL` | 空 | 不绑 MCP 工具（示例用本地 tool） | 预留扩展点，starter 不内置 client |
| `OPENAI_API_KEY` / tenant LLM | 必填 | —— | LLM 调用 |

## 9. 分期（实现 plan 细化；本节定骨架）
- **Phase 0｜inventory 确认**：把 §3 里 ❓ 项（main.py 端点、sessions/views/ops、integrations/base、workflow runtime、HR extractor 边界）逐一定归类；定包名。产出最终 keep/strip 清单。
- **Phase 1｜骨架可启动**：拷 keep 模块 + 去业务化 state/settings/graph + 重写瘦 `main.py` + memory **in-memory 兜底**（recall/write 节点真跑、不空壳，§12.2）；空域也能 `run` 起来、`/health` OK。
- **Phase 2｜classify/action 泛型化**：§5.1/5.2/5.3 落地，core 零业务名。
- **Phase 3｜memory pgvector opt-in + extractor 解耦**：在 Phase 1 的 in-memory 兜底之上接 asyncpg + pgvector MemoryStore（配 env 才启用），抽掉 HR extractor、保留通用 extractor（§5.5）。
- **Phase 4｜example_todo + delete-clean 验收**：建示例域，跑通 C1（删除脚本验证）+ C2（零依赖启动）。
- **Phase 5｜规范文档**：README/CONTRIBUTING。
> 节奏按"一个 phase 一次性提交"，不自动 commit。

## 10. AC 矩阵
| AC | 验收 |
|---|---|
| AC1 | clone + `.env.example` + run，`ENABLE_EXAMPLE_DOMAIN=1`，对 example_todo 发"加一条买牛奶的待办"能出回复并"写库"（内存） |
| AC2 | 零外部依赖启动（无 AGENT_PG_DSN/AGENT_EMBED_BASE_URL/MCP）下 AC1 仍通过（C2） |
| AC3 | 删除手势（rm 目录 + 删注册行 + 删 env）后：`grep -r example_/todo src/<pkg>` 在 core 下 0 命中；框架测试全过（C1） |
| AC4 | `src/<pkg>/{graph,state,nodes,memory,security}` 下 `grep -riE "offer|probation|hr_|opc|solo"` 0 命中（去业务化达标） |
| AC5 | 配上 AGENT_PG_DSN+AGENT_EMBED_BASE_URL 后 Postgres checkpoint + pgvector MemoryStore 生效（opt-in 路径回归） |
| AC6 | 新加一个域只需：建目录 + 一行注册，无需改 core（扩展性） |

## 11. 规范文档交付物
- `README.md`：模板定位（一句话）、quickstart（C2 路径）、"加一个业务域"5 步、"删示例域"3 步、配置矩阵。
- `CONTRIBUTING.md`：域开发约定——目录结构、TaskSpec/DomainSpec 注册、本地 vs MCP 工具、测试要求、命名（`example_` 前缀仅限示例）。

## 12. 已定决策（2026-05-27 review 通过）
1. **包名 = `agent_starter`**（`src/agent_starter/`，所有 import 用此根）。
2. **memory 子系统 Phase 1 就带 in-memory 兜底**——否则 `recall/write` 节点是空壳、graph 拓扑失真。pgvector/extractor 留 Phase 3 opt-in。
3. **workflow：剥 runtime 实现；hook 接口也不进当前 starter**（§5.8）。
4. **`main.py` 重写为更瘦的 app 入口**，不在 1891 行原文件上清理（大半是 OPC/业务，重写成本低于清理）。
