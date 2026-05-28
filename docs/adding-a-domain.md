# 业务怎么对接：加一个域

> ✅ **状态：已实现（Phase 2）。** 域/任务注册机制（`DomainSpec`/`TaskSpec`）已在 `src/agent_starter/tasks/` 落地，并随仓自带 `example_todo` 参照域（默认关）。下文 API 与代码一致。设计依据：[specs/2026-05-27-extraction-design.md](specs/2026-05-27-extraction-design.md)。

核心理念：**业务不进 core，靠注册接口接入。** 你加业务时只在 `tasks/<你的域>/` 下建一个自包含目录 + 在 `tasks/__init__.py` 加一行注册调用；`graph.py` / `classify` / `agent` 一律不动。

---

## 0. 推荐：先用脚手架生成

多数业务域先跑这个命令，再改生成的 `tools.py` / `prompt.py` 就够了：

```bash
uv run python scripts/new_domain.py ticket --label 工单 --trigger 工单 --trigger ticket
```

脚本会生成 `src/agent_starter/tasks/ticket/`、`tests/tasks/ticket/`，并自动把 `ticket.register()` 插到 `register_enabled_domains()` 的 scaffold marker 下。生成后先跑：

```bash
uv run --extra dev pytest tests/tasks/ticket/test_ticket.py -q
```

后面章节讲的是脚手架生成内容背后的机制，适合你要手写复杂域、多轮草稿或做权限收口时再看。

---

## 1. 两个概念：Domain 与 Task

- **Domain（业务域）**：一类相关的对话意图 + 工具的聚集。例：`todo`、`ticket`、`hr_offer`。classify 节点据此决定本轮绑哪些工具。用 `DomainSpec` 描述。
- **Task（任务）**：域内一个“收集字段 → 确认 → 落库”的写动作单元。用 `TaskSpec` 描述，挂一个一次性写库工具 `create_tool` + 一组可选钩子。

一个域可以有 0~N 个 task（纯查询域可以没有 task，只有 read 工具）。

---

## 2. DomainSpec（域定义，见 `tasks/domains.py`）

```python
DomainSpec(
    name="todo",
    label="待办（任务清单）",
    triggers=["待办", "todo", "任务", "提醒我"],   # classify 的命中线索（不是硬正则）
    read_tools=[list_todos],                       # 查询类工具，全局候选
    write_tools=[add_todo, complete_todo],         # 写类工具，仅本域激活时绑
)
```

- `triggers` 既会给 classify LLM 做提示，也会在 LLM 失败/输出未知域时作为确定性兜底；它仍然不写死在 core，删域就删掉了对应线索，core 不残留。
- `read_tools` 跨域全局可达；`write_tools` 只在当前域被选中时绑给 LLM（收敛写动作的误触发面）。

## 3. TaskSpec（写任务，见 `tasks/registry.py`）

```python
TaskSpec(
    task_type="create_todo",
    domain="todo",
    create_tool=create_todo_tool,        # @tool，HR 确认后一次性写库
    prompt_fragment="收集 todo 标题/截止日，齐了再确认创建……",
    success_message=lambda raw: f"✅ 已创建待办：{raw['title']}",
    # 可选钩子（按需实现，框架层不认识字段名）：
    tool_result_to_draft_patches=...,    # 工具返值 → working_draft 字段映射
    render_draft=...,                    # 当前 working_draft 怎么展示给 LLM/前端
    is_draft_displayable=...,            # 当前草稿值不值得弹给用户
)
```

`create_tool` 会在当前 `domain` 命中时自动作为写工具绑定给 LLM；不用在 `DomainSpec.write_tools` 里重复放一次。`success_message` 会作为工具成功后的建议回复注入下一轮模型上下文，避免业务同事在 prompt 里重复写固定成功文案。

`working_draft` 是通用草稿袋：用户分多轮把字段说全（标题、截止日…），由你的 hook 累积进 `state.working_draft`，齐了 + 用户确认后 LLM 调 `create_tool` 落库。`is_draft_displayable` 控制 `working_draft_visible`，用于前端决定是否展示草稿卡。框架层只搬运这个 dict，**不认识** `title`/`due` 这些字段名——含义全由你的域解释。

框架会把 TaskSpec hook 限制在当前 `domain`，且 hook 抛异常只记录 warning，不会拖垮整个 agent turn。`is_draft_displayable` 抛异常时按“不展示草稿”处理。

---

## 4. 加一个域的步骤

如果不用脚手架，手动以 `todo` 为例（`tasks/example_todo/` 就是这么搭的）：

1. 建目录 `src/agent_starter/tasks/todo/`，放：
   - `tools.py` — 工具实现（本地 or MCP，见 §5）
   - `prompt.py` — 域 prompt 片段
   - `domainspec.py` — `DomainSpec(...)`
   - `taskspec.py` — `TaskSpec(...)`（如有写动作）
   - `__init__.py` — 导出并 `register_domain(...)` / append 到 `REGISTRY`
2. 在顶层 `tests/tasks/todo/` 放本域测试；源码树 `src/agent_starter/` 不放 `test_*.py`。
3. 在 `tasks/__init__.py` 的 `register_enabled_domains()` 里加**一行注册调用**：
   ```python
   from agent_starter.tasks import todo
   todo.register()
   ```
4. 完事——不改 `graph.py`、`classify.py`、`agent`、`state.py`。

> classify 自动把你的 `triggers` 纳入候选；`agent_loop_action` 自动按域绑你的工具。这就是“注册式扩展”。

## 5. 工具：本地 vs MCP

- **本地工具**（✅ 已支持）：纯 Python 函数（读写内存/你自己的 DB/HTTP），用 LangChain `@tool` 暴露。示例域 `example_todo` 就是本地内存实现，保证零依赖可跑。
- **MCP 工具**（🔌 业务自行对接）：`MCP_SERVER_URL` 已在 settings 预留，但本模板不内置 MCP client。要接“agent 不碰业务库、统一走后端 MCP 服务”的架构（talentos 即如此），需在业务侧加一个 `clients/mcp_client`（Streamable HTTP + JWT 透传）把远端工具包成 `@tool` 注册到域里。

本地工具与（未来的）MCP 工具都用 `@tool` 暴露，对 ReAct 循环无差别。工具抛异常时框架会转成错误 `ToolMessage` 继续对话；但工具内部仍应返回结构化 dict（建议含 `ok`/`error`），方便 TaskSpec hook 和成功文案判断。

---

## 6. 删除一个域（delete-clean 验收）

这是模板的硬契约——以删 `example_todo` 为例，**3 步、不碰 core**：

```bash
rm -rf src/agent_starter/tasks/example_todo/      # 1. 删目录
# 2. 删 tasks/__init__.py 里 example_todo.register() 那段
# 3. 删 .env.example 里的 ENABLE_EXAMPLE_DOMAIN（可选）
```

验证删干净：

```bash
grep -ri "example_todo\|todo" src/agent_starter/ \
  --exclude-dir=tasks   # core 下应零命中
.venv/bin/pytest        # 框架测试照过
```

**如果 core 里 grep 还能搜到业务名，说明有 leak，不算合格。** 这条同时反向保证了 core 的业务中立。

---

## 7. 示例域 `example_todo`（仓内已带）

`src/agent_starter/tasks/example_todo/` 是活参照：增/查/完成待办，跑通完整链路“DomainSpec/TaskSpec 注册 → 按域绑工具 → ReAct 调本地工具 → 出回复”。默认关闭（`ENABLE_EXAMPLE_DOMAIN=0`），生产干净；新人设 `=1` 打开照着抄，抄完按 §6 删掉。

> 该示例用**直接工具调用**演示（LLM 调 `add_todo`）。你的域若需要“分多轮收集字段再确认落库”，照 §3 的 `tool_result_to_draft_patches` / `render_draft` / `is_draft_displayable` 三个钩子接即可。
