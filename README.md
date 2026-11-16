# Decompose Agent

基于 LangGraph 的复杂分析型 Agent —— 将用户问题拆解为独立子问题，并行检索，最后综合生成分析报告。

## 解决什么问题

传统 ReAct Agent 是"想一步 → 做一步 → 看一步"的串行循环，适合操作型任务（查订单、退款项）。但面对**跨多数据源的对比/趋势/归因分析**时，串行效率太低。

本项目的思路是：**先全局拆解，再并行执行，最后统一综合**。一次 LLM 调用生成 3-5 个结构化检索步骤，每一步明确指定工具和参数；这些步骤并行执行，最后用一次 LLM 综合结果。核心拆解与综合是 2 次模型调用，注册业务域时分类节点还会额外调用 1 次模型。

**典型场景：**
- "对比三个产品线的退款率和投诉趋势，分析原因"
- "对比 prod_a 和 prod_b 近几个月的销售额，找出增长差异"
- "哪些产品线的投诉数量在上升，主要投诉类别是什么"

## 架构

```
用户问题："对比三个产品线的退款率和投诉趋势"

START ──┬── classify（域分类）
        └── recall（记忆召回）
              │
              ▼
         decompose（生成最多 5 个工具调用计划）
              │
              ▼
         retrieve（各检索步骤并行执行）   ← 真正并行
              │
              ▼
         synthesize（综合生成分析报告）
              │
              ▼
         write → END
```

### 与 ReAct 模式的对比

| | ReAct Agent | Decompose Agent |
|---|---|---|
| 模式 | Think → Act → Observe 循环 | Decompose → Retrieve → Synthesize |
| 适合场景 | 单意图、有依赖链的操作 | 多意图、无依赖的对比分析 |
| 执行方式 | 串行，每一步等上一步 | 子问题级并行 |
| LLM 调用次数 | 每轮 1~N 次，不可控 | 核心 2 次（拆解 + 综合），另有域分类 |
| Token 消耗 | 随轮数线性增长 | 有最大步骤和上下文截断，但未做基准测量 |

### 三个核心节点

**Decompose（拆解）** — 1 次核心 LLM 调用，将复杂问题拆成 3-5 个独立检索步骤。每一步包含 `question`、`tool` 和 `arguments`，工具名与参数会经过代码校验。无法生成合法计划时，退回对全部读工具执行一次全量查询，保证流程不崩溃。

**Retrieve（检索）** — `asyncio.gather` 并行执行结构化计划中的每一步。每一步只调用计划指定的工具，并传入经过校验的参数。单个工具报错只影响该步骤，不取消其他检索。

**Synthesize（综合）** — 1 次核心 LLM 调用，综合所有检索结果 + 记忆上下文，生成结构化分析报告。每条工具结果在送入模型前截断到 500 字符；Prompt 要求引用具体数据、趋势判断和归因分析。

## 快速开始

### 1. 安装

```bash
pip install -e .
```

### 2. 配置模型

```bash
cp .env.example .env
```

编辑 `.env`，选择模型提供商：

**DeepSeek（默认，推荐）：**
```env
LLM_PROVIDER=deepseek
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_API_KEY=sk-your-deepseek-key
OPENAI_MODEL=deepseek-chat
```

**OpenAI：**
```env
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-your-openai-key
OPENAI_MODEL=gpt-4o-mini
```

**其他兼容接口（Ollama / vLLM / 国产模型等）：**
```env
LLM_PROVIDER=custom
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
OPENAI_MODEL=qwen2.5:7b
```

所有兼容 OpenAI Chat Completions API 的接口都可以用。

### 3. 使用

**命令行模式（推荐）：**

```bash
# 直接问一个问题
decompose "对比三个产品线的退款率和投诉率，分析原因"

# 如果 decompose 命令不在 PATH 中，用：
python -m agent_starter.cli "对比三个产品线的退款率和投诉率，分析原因"

# 交互模式（一问一答）
decompose
```

**HTTP 服务模式：**

```bash
python -m uvicorn agent_starter.main:app --port 8201

# 发送请求
curl -X POST http://localhost:8201/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"对比三个产品线的退款率和投诉率","user_id":1,"thread_id":"t1"}'
```

### 4. 测试

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check .
```

## 项目结构

```
src/agent_starter/
├── graph.py              # Agent 图定义（Decompose → Retrieve → Synthesize）
├── planning.py           # 结构化检索计划解析与工具参数校验
├── llm.py                # 多模型 LLM 构造（DeepSeek / OpenAI / 兼容接口）
├── settings.py           # 全局配置
├── state.py              # Agent 状态定义
├── main.py               # FastAPI 入口
├── nodes/                # 图节点（classify / memory）
├── tasks/                # 业务域注册
│   ├── analytics/        # 数据分析域（模拟数据 + 检索工具）
│   └── example_todo/     # 示例域（可关闭）
├── memory/               # 记忆体系（偏好抽取 / 召回 / 写入）
├── security/             # 安全层（输入防注入 / 输出清理）
└── serving/              # 会话管理与 SSE 流式
```

## 设计决策

**为什么用 asyncio.gather 而不是 LangGraph Send API？**

Send API 是 LangGraph 官方的 fan-out 方式，但会增加图节点和状态编排复杂度。当前计划最多 5 步，`asyncio.gather` 在一个节点内并行已经完全够用。如果未来步骤涨到 50+，再考虑并发限流或 Send API。

**检索步骤为什么限制最多 5 个？**

太少覆盖不完整，太多会增加模型规划错误和综合节点的上下文压力。Prompt 引导生成 3-5 步，代码层硬限制为最多 5 步。

**拆解失败怎么办？**

不崩溃。解析失败、工具名非法或参数校验失败时，退回四个读工具各执行一次全量查询，再进入综合节点。单个工具运行失败只标记该步骤，其他并行步骤继续。

## 项目报告

- [本次检索链路修复报告](reports/2026-11-16-检索链路修复报告.md)
- [项目完整报告](reports/项目完整报告.md)

## License

MIT
