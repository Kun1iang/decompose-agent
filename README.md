# Decompose Agent

基于 LangGraph 的复杂分析型 Agent —— 将用户问题拆解为独立子问题，并行检索，最后综合生成分析报告。

## 解决什么问题

传统 ReAct Agent 是"想一步 → 做一步 → 看一步"的串行循环，适合操作型任务（查订单、退款项）。但面对**跨多数据源的对比/趋势/归因分析**时，串行效率太低。

本项目的思路是：**先全局拆解，再并行执行，最后统一综合**。一次 LLM 调用拆出 3-5 个子问题，全部子问题同时检索，再用一次 LLM 综合结果。无论拆出多少子问题，LLM 调用固定 2 次。

**典型场景：**
- "对比三个产品线的退款率和投诉趋势，分析原因"
- "过去 6 个月各渠道的销售额变化，找出增长最快的渠道"
- "哪些品类的退货率在上升，可能的原因是什么"

## 架构

```
用户问题："对比三个产品线的退款率和投诉趋势"

START ──┬── classify（域分类）
        └── recall（记忆召回）
              │
              ▼
         decompose（拆成 5 个子问题）
              │
              ▼
         retrieve（5 路子问题并行检索）   ← 真正并行
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
| LLM 调用次数 | 每轮 1~N 次，不可控 | 固定 2 次（拆解 + 综合） |
| Token 消耗 | 随轮数线性增长 | ~700 token，可预测 |

### 三个核心节点

**Decompose（拆解）** — 1 次 LLM 调用，将复杂问题拆成 3-5 个独立子问题。每个子问题必须独立可答，不依赖其他子问题的结果。拆解失败时用原问题兜底，保证不崩溃。

**Retrieve（检索）** — `asyncio.gather` 真正并行执行所有子问题的检索。每个子问题调用全部可用工具。总耗时 = 最慢的那个子问题，而非累加。单个工具报错不影响其他子问题。

**Synthesize（综合）** — 1 次 LLM 调用，综合所有子问题结果 + 记忆上下文 + 历史对话，生成结构化分析报告。报告包含具体数据引用、趋势判断和归因分析。

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

## 项目结构

```
src/agent_starter/
├── graph.py              # Agent 图定义（Decompose → Retrieve → Synthesize）
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

Send API 是 LangGraph 官方的 fan-out 方式，但代码复杂度高不少。asyncio.gather 在一个节点内并行，效果一样、更直观。当前子问题数量在 3-5 个，asyncio.gather 完全够用。如果未来子问题量涨到 50+，再考虑切 Send API。

**子问题数量为什么限制 3-5 个？**

太少拆不细，太多综合节点的上下文压力大。Prompt 里引导 LLM 拆 3-5 个，代码层 `MAX_SUB_QUESTIONS=5` 硬截断。

**拆解失败怎么办？**

不崩溃。原问题作为唯一子问题兜底，走一遍完整的检索→综合流程。单个工具的检索失败同理——标记"检索失败"，不影响其他子问题的并行执行。

## License

MIT
