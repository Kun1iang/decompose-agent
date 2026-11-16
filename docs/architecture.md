# 架构

本文描述当前 `main.py` 和 CLI 实际使用的 Decompose Agent 主链。仓库中仍保留
`nodes/agent.py` 等 ReAct 模板能力，但它们不属于当前主图。

## 1. 项目定位

项目面向**跨多个指标的经营分析问题**，典型问题包括：

- 对比不同产品线的销售、退款和投诉趋势。
- 计算退款率时同时查询销售额和退款笔数。
- 找出投诉增长最明显的产品线及主要投诉类别。

它不试图让模型在循环中逐轮决定下一步，而是先生成一份有边界的检索计划，再并行取数，最后统一生成报告。

## 2. 图拓扑

```text
START
  ├─ classify（业务域分类）
  └─ recall（偏好记忆召回）
             ↓ 两路均完成后汇合
        decompose（一次核心 LLM）
             ↓
        retrieve（结构化计划并行执行）
             ↓
        synthesize（一次核心 LLM）
             ↓
          write
             ↓
           END
```

`classify` 和 `recall` 从 `START` 并行 fan-out，并在 `decompose` 处 fan-in。`decompose` 会等两者都完成后才开始。

## 3. 结构化检索计划

拆解节点不再返回裸字符串子问题，而是返回经过代码校验的计划：

```json
{
  "steps": [
    {
      "question": "查询三个产品线的退款数据",
      "tool": "search_refunds",
      "arguments": {
        "product_id": "",
        "month": ""
      }
    },
    {
      "question": "查询三个产品线的销售数据",
      "tool": "search_sales",
      "arguments": {
        "product_id": "",
        "month": ""
      }
    }
  ]
}
```

`planning.py` 负责：

- 移除 Markdown JSON 代码围栏。
- 校验计划必须是 `{"steps": [...]}`。
- 校验工具真实存在。
- 使用工具的 Pydantic 参数模型校验 `arguments`。
- 限制最多 5 步。
- 按 `tool + arguments` 去重。
- 跳过单个非法步骤；如果一个合法步骤都没有，则执行安全兜底计划。

安全兜底计划是：所有全局读工具各调用一次，参数为 `{}`。因此模型偶尔输出坏 JSON 时，系统仍可返回一个较宽泛的分析，而不是直接挂掉。

## 4. 一个请求的数据流

```text
HTTP POST /agent/chat
  或 CLI run_query
      ↓
组装 inputs：HumanMessage + user_id + workspace_id 等
      ↓
checkpointer 按 thread_id 加载会话状态
      ↓
classify：写入 domain
recall：写入 recalled_memory
      ↓
decompose：生成并校验结构化步骤
      ↓
retrieve：asyncio.gather 并行执行每一步
      ↓
synthesize：拼接原始问题、检索步骤、参数、状态、结果和偏好
      ↓
write：默认抽取昵称偏好并写入 MemoryStore
      ↓
返回末条 AIMessage
```

FastAPI 的 `/agent/chat/stream` 使用 LangGraph `stream_mode="updates"`，逐节点发送进度事件，最后发送完整 `done.reply`。它不是逐 token 流。

## 5. 节点契约

| 节点 | 输入 | 输出 | 失败处理 |
|---|---|---|---|
| `classify` | 用户最新消息、已注册域 | `domain` | LLM 失败时使用 trigger 兜底 |
| `recall` | `user_id`、用户问题 | `recalled_memory` | 默认内存实现不依赖外部服务 |
| `decompose` | 原问题、工具目录 | `working_draft.plan` | 坏 JSON/坏参数时使用全量读工具兜底 |
| `retrieve` | 结构化计划 | `working_draft.sub_results` | 单步骤失败保留错误状态，其他步骤继续 |
| `synthesize` | 原始问题、检索结果、偏好 | `AIMessage` | 输出清理后写回消息 |
| `write` | 本轮消息 | 更新 MemoryStore | 默认确定性抽取，不额外调用 LLM |

每个检索结果包含：

```json
{
  "question": "该步骤要回答什么",
  "tool": "工具名",
  "arguments": {},
  "status": "success",
  "result": "工具返回文本"
}
```

异常步骤使用 `status="error"` 和错误类型名，避免异常静默消失。

## 6. 上下文控制

系统使用两级截断：

1. 工具原始结果在 `retrieve` 中截断到 2,000 字符。
2. 每个结果送入综合 Prompt 前再截断到 500 字符。

当前没有经过基准测试的 token 节省数据，因此文档不宣称固定 token 消耗或固定延迟。

## 7. 三产品线模拟数据

`tasks/analytics/data.py` 提供三条产品线：

| 产品线 | 名称 | 销售数据月份 |
|---|---|---|
| `prod_a` | AI客服Agent | 2025-03 至 2025-08 |
| `prod_b` | 数据分析平台 | 2025-01 至 2025-08 |
| `prod_c` | 知识库SaaS | 2025-06 至 2025-08 |

三条产品线的数据时间范围不一致，因此只能比较共同覆盖月份，不能笼统宣称三者都有八个月完整数据。

## 8. 记忆与会话

项目有两套不同存储：

1. **会话状态**：LangGraph checkpointer 按 `thread_id` 保存完整图和消息状态。
2. **长期偏好**：`MemoryStore` 按 `user_id` 保存结构化偏好，默认 `InMemoryStore`。

默认两套都是进程内内存实现，服务重启即丢失。`PgVectorStore` 提供 PostgreSQL + pgvector 参考实现，但仓库没有可用的真实 PostgreSQL/pgvector 集成测试，不能标记为生产验证完成。

## 9. 服务与配置

| 配置 | 默认 | 作用 |
|---|---|---|
| `LLM_PROVIDER` | `deepseek` | LLM 提供商 |
| `OPENAI_BASE_URL` | 按提供商 | OpenAI 兼容接口地址 |
| `OPENAI_API_KEY` | 空 | 模型密钥 |
| `OPENAI_MODEL` | `deepseek-chat` | 模型名 |
| `ENABLE_EXAMPLE_DOMAIN` | `false` | 是否注册 todo 示例域 |
| `ENABLE_LLM_PREF_EXTRACTION` | `false` | 是否启用 LLM 富偏好抽取 |
| `AGENT_PG_DSN` | 空 | 可选 PostgreSQL checkpointer/记忆 |
| `AGENT_EMBED_*` | 空 | 可选 embedding 配置 |

## 10. 扩展边界

新增分析工具时：

1. 使用 LangChain `@tool` 定义工具，并写清参数说明。
2. 将工具加入业务域的 `read_tools`。
3. 保证工具参数能由 JSON 对象表示。
4. 为成功、无数据和异常路径增加测试。

当前 `classify` 还不是工具路由依据；`retrieve` 使用全局读工具目录。如果未来存在多个业务域，应增加按 domain 限制工具集合的路由，而不是让模型在全部写工具中自由选择。

## 11. 当前能力边界

- 数据来自本地模拟数据，不是生产数据库。
- 结构化计划质量依赖 LLM，真实 DeepSeek 集成需要配置密钥后做人工验收。
- 失败兜底采用全量读工具，结果可能较宽泛。
- pgvector 和 PostgreSQL 路径未完成真集成验证。
- 没有性能、并发和长时间运行基准。
- 主图不执行写业务工具。
