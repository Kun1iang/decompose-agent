# Phase 1：Walking Skeleton 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐 task 执行。步骤用 `- [ ]` 勾选跟踪。

**Goal:** 把 `langgraph-agent-starter` 拉成一个能 `uvicorn` 起来、零外部依赖（除 LLM key）就能跑通一个最小 LangGraph turn 的可运行骨架。

**Architecture:** 全新精简实现（不 port talentos-agent 那批业务缠绕的 node/main）。最小拓扑 `START → agent → END`，`agent` 节点按 `state.domain` 选工具（Phase 1 无域、不绑工具）后调一次 LLM 出回复。settings/state/graph/main 全部去业务化、可零依赖启动；Postgres / pgvector / MCP / 真实域留后续 plan 接入。

**Tech Stack:** Python 3.11+, LangGraph, langchain-openai, FastAPI, uvicorn, pydantic-settings, structlog, pytest（+ pytest-asyncio）。

**对应 spec：** `docs/specs/2026-05-27-extraction-design.md` §9 Phase 1 的第一个垂直切片（§12 决策：包名 `agent_starter`、main.py 重写瘦入口、memory Phase 1 先 in-memory 兜底——本 plan 先做到“无 memory 也能跑”，in-memory 兜底放 Phase 3 接 memory 时落）。

**后续 plan（不在本 plan 范围）：** P2 泛型化 classify/action + registry + `example_todo` 域；P3 memory（in-memory 兜底 + pgvector opt-in）；P4 README/CONTRIBUTING 规范。

---

## File Structure（本 plan 产出）

```
langgraph-agent-starter/
  pyproject.toml                 # 包定义 + 依赖
  .env.example                   # 配置样例（含 ENABLE_EXAMPLE_DOMAIN=0）
  .gitignore
  src/agent_starter/
    __init__.py
    settings.py                  # 精简 Settings（pydantic-settings）
    state.py                     # 通用 AgentState（含 working_draft，无 offer_draft）
    llm.py                       # build_llm()：从 settings 造 ChatOpenAI
    graph.py                     # build_graph()：START→agent→END
    nodes/
      __init__.py
      agent.py                   # agent 节点：选工具 + 调 LLM
    main.py                      # FastAPI：/health + /agent/chat（sync）
  tests/
    __init__.py
    conftest.py                  # fake LLM fixture
    test_settings.py
    test_state.py
    test_agent_node.py
    test_app.py
```

每个文件单一职责；node 拆到 `nodes/` 包，后续 plan 往里加 classify/memory 不动 `graph.py` 结构。

---

## Task 1：项目脚手架

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `src/agent_starter/__init__.py`

- [ ] **Step 1: 写 `pyproject.toml`**

```toml
[project]
name = "agent-starter"
version = "0.1.0"
description = "LangGraph agent application starter template"
requires-python = ">=3.11"
dependencies = [
    "langgraph>=0.2.0",
    "langchain-core>=0.3.0",
    "langchain-openai>=0.2.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic-settings>=2.4.0",
    "structlog>=24.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: 写 `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
.venv/
venv/
.env
*.egg-info/
.pytest_cache/
.ruff_cache/
```

- [ ] **Step 3: 写 `.env.example`**

```bash
# ---- LLM（必填）----
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-4o-mini

# ---- 可选 ----
JWT_SECRET=dev-secret
LOG_LEVEL=INFO
LOG_FORMAT=console

# ---- 示例域开关（默认关；置 1 看 example_todo，P2 才有效）----
ENABLE_EXAMPLE_DOMAIN=0

# ---- 后续 plan 才用（留空 = 关闭对应能力）----
AGENT_PG_DSN=
AGENT_EMBED_BASE_URL=
AGENT_EMBED_API_KEY=
MCP_SERVER_URL=
AGENT_WORKSPACE_ID=1
```

- [ ] **Step 4: 写空包标记**

```python
# src/agent_starter/__init__.py
"""langgraph-agent-starter：通用 LangGraph agent 应用模板。"""
```

- [ ] **Step 5: 建虚拟环境并安装**

Run:
```bash
cd /Users/aisenyc/work/langgraph-agent-starter && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```
Expected: 安装成功，结尾 `Successfully installed agent-starter-0.1.0 ...`

- [ ] **Step 6: Commit**

```bash
cd /Users/aisenyc/work/langgraph-agent-starter && git add pyproject.toml .gitignore .env.example src/agent_starter/__init__.py && git commit -m "chore: scaffold agent_starter package"
```

---

## Task 2：精简 Settings

**Files:**
- Create: `src/agent_starter/settings.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_settings.py
import os
from agent_starter.settings import Settings


def test_settings_boots_without_optional_deps(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://x/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    for k in ("AGENT_PG_DSN", "MCP_SERVER_URL", "AGENT_EMBED_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    s = Settings()
    assert s.openai_model == "gpt-4o-mini"
    assert s.agent_pg_dsn == ""       # 可选，默认空
    assert s.mcp_server_url == ""     # 可选，默认空
    assert s.enable_example_domain is False


def test_enable_example_domain_parses_truthy(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://x/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("ENABLE_EXAMPLE_DOMAIN", "1")
    assert Settings().enable_example_domain is True
```

- [ ] **Step 2: 跑测试确认 fail**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && .venv/bin/pytest tests/test_settings.py -v`
Expected: FAIL（`ModuleNotFoundError: agent_starter.settings`）

- [ ] **Step 3: 写实现**

```python
# src/agent_starter/settings.py
"""精简全局配置。可选项默认空字符串 = 关闭对应能力，保证零依赖启动。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- LLM（必填）----
    openai_base_url: str
    openai_api_key: str
    openai_model: str

    # ---- 基础 ----
    jwt_secret: str = "dev-secret"
    log_level: str = "INFO"
    log_format: str = "console"  # console | json
    agent_workspace_id: int = 1

    # ---- 示例域开关 ----
    enable_example_domain: bool = False

    # ---- 可选能力（空 = 关闭，后续 plan 接入）----
    agent_pg_dsn: str = ""
    agent_embed_base_url: str = ""
    agent_embed_api_key: str = ""
    agent_embed_model: str = "text-embedding-3-small"
    mcp_server_url: str = ""
    mcp_request_timeout_seconds: int = 30


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 4: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && .venv/bin/pytest tests/test_settings.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
cd /Users/aisenyc/work/langgraph-agent-starter && git add src/agent_starter/settings.py tests/test_settings.py && git commit -m "feat: lean Settings with optional-deps default-off"
```

---

## Task 3：通用 AgentState

**Files:**
- Create: `src/agent_starter/state.py`
- Test: `tests/test_state.py`

> 关键去业务化：无 `offer_draft` / `employee_id`，改通用 `working_draft`（域自解释的草稿袋）。`recalled_memory` / `user_scope` 在 Phase 1 用 `Any` 占位，P3 接 memory 时换成强类型。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_state.py
from agent_starter.state import AgentState


def test_agentstate_has_generic_working_draft_not_business_fields():
    keys = set(AgentState.__annotations__.keys())
    assert "working_draft" in keys
    assert "messages" in keys
    assert "domain" in keys
    # 去业务化：不允许任何 HR/offer 专属字段
    assert "offer_draft" not in keys
    assert "employee_id" not in keys
```

- [ ] **Step 2: 跑测试确认 fail**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && .venv/bin/pytest tests/test_state.py -v`
Expected: FAIL（`ModuleNotFoundError: agent_starter.state`）

- [ ] **Step 3: 写实现**

```python
# src/agent_starter/state.py
"""LangGraph state schema（去业务化）。

- messages: 对话历史（自动 append）
- working_draft: 通用草稿袋——当前业务域自行解释字段含义。框架层不认识任何
  具体字段名（替代过去那种业务专属的单一草稿字段）。
- working_draft_visible / _dirty: 通用展示/脏闸门，由域的 TaskSpec hook 决定何时推前端。
- domain: classify 写入的业务域名；空串表示无明确域。
- recalled_memory / user_scope: Phase 1 占位（Any），P3 接 memory 换强类型。
"""
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_id: int
    jwt: str
    persona: str
    domain: str
    working_draft: dict[str, Any] | None
    working_draft_visible: bool | None
    working_draft_dirty: bool | None
    recalled_memory: Any | None
    user_scope: Any | None
    workspace_id: int
    page_context: dict[str, Any] | None
    invoked_tool: str
    invoked_args: dict[str, Any] | None
```

- [ ] **Step 4: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && .venv/bin/pytest tests/test_state.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: Commit**

```bash
cd /Users/aisenyc/work/langgraph-agent-starter && git add src/agent_starter/state.py tests/test_state.py && git commit -m "feat: generic AgentState with working_draft (no business fields)"
```

---

## Task 4：LLM 工厂

**Files:**
- Create: `src/agent_starter/llm.py`

> 无独立行为测试（薄封装）；由 Task 5/6 的 fake LLM 覆盖。

- [ ] **Step 1: 写实现**

```python
# src/agent_starter/llm.py
"""从 settings 构造 ChatOpenAI。"""
from langchain_openai import ChatOpenAI

from agent_starter.settings import get_settings


def build_llm(temperature: float = 0.0) -> ChatOpenAI:
    s = get_settings()
    return ChatOpenAI(
        base_url=s.openai_base_url,
        api_key=s.openai_api_key,
        model=s.openai_model,
        temperature=temperature,
    )
```

- [ ] **Step 2: 验证可 import**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && OPENAI_BASE_URL=x OPENAI_API_KEY=x OPENAI_MODEL=x .venv/bin/python -c "from agent_starter.llm import build_llm; print('ok')"`
Expected: 打印 `ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/aisenyc/work/langgraph-agent-starter && git add src/agent_starter/llm.py && git commit -m "feat: build_llm factory from settings"
```

---

## Task 5：agent 节点（最小 ReAct 雏形）

**Files:**
- Create: `src/agent_starter/nodes/__init__.py`
- Create: `src/agent_starter/nodes/agent.py`
- Test: `tests/conftest.py`, `tests/test_agent_node.py`

> Phase 1 的 agent 节点只做：拼 system prompt + 调一次 LLM + 把回复作为 AIMessage 返回。Phase 1 无域 → 不绑工具。`build_llm` 通过参数注入便于测试替换（依赖注入，避免 mock 网络）。

- [ ] **Step 1: 写 fake LLM fixture**

```python
# tests/conftest.py
import pytest
from langchain_core.messages import AIMessage


class FakeLLM:
    """最小 LLM 替身：ainvoke 返回固定 AIMessage。"""

    def __init__(self, reply: str = "你好，我是 agent。"):
        self._reply = reply
        self.calls = []

    def bind_tools(self, tools):
        return self  # Phase 1 无工具，原样返回

    async def ainvoke(self, messages, *args, **kwargs):
        self.calls.append(messages)
        return AIMessage(content=self._reply)


@pytest.fixture
def fake_llm():
    return FakeLLM()
```

- [ ] **Step 2: 写失败测试**

```python
# tests/test_agent_node.py
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agent_starter.nodes.agent import agent_node


@pytest.mark.asyncio
async def test_agent_node_returns_ai_message(fake_llm):
    state = {
        "messages": [HumanMessage(content="在吗")],
        "user_id": 1,
        "domain": "",
    }
    out = await agent_node(state, llm=fake_llm)
    assert "messages" in out
    msgs = out["messages"]
    assert len(msgs) == 1
    assert isinstance(msgs[0], AIMessage)
    assert msgs[0].content == "你好，我是 agent。"
    # system prompt 被前置传给 LLM
    assert fake_llm.calls and fake_llm.calls[0][0][0] == "system"
```

- [ ] **Step 3: 跑测试确认 fail**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && .venv/bin/pytest tests/test_agent_node.py -v`
Expected: FAIL（`ModuleNotFoundError: agent_starter.nodes.agent`）

- [ ] **Step 4: 写实现**

```python
# src/agent_starter/nodes/__init__.py
from agent_starter.nodes.agent import agent_node

__all__ = ["agent_node"]
```

```python
# src/agent_starter/nodes/agent.py
"""最小 agent 节点：拼 system prompt → 调 LLM → 返回 AIMessage。

Phase 1 不绑工具（无业务域）。P2 在此接入 select_tools_for_state(state) +
ReAct 多轮循环；本节点的签名（state, *, llm）保持稳定，便于测试注入与扩展。
"""
from __future__ import annotations

import structlog
from langchain_core.messages import BaseMessage

from agent_starter.llm import build_llm
from agent_starter.state import AgentState

logger = structlog.get_logger(__name__)

_SYSTEM_PROMPT = (
    "你是一个通用 AI 助手。用简洁、准确的中文回答用户。"
    "（这是 langgraph-agent-starter 的默认 persona，业务方按需替换。）"
)


async def agent_node(state: AgentState, *, llm=None) -> dict:
    if llm is None:
        llm = build_llm()
    history: list[BaseMessage] = list(state.get("messages") or [])
    conversation = [("system", _SYSTEM_PROMPT), *history]
    resp = await llm.ainvoke(conversation)
    logger.info("agent_node.done", domain=state.get("domain") or "")
    return {"messages": [resp]}
```

- [ ] **Step 5: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && .venv/bin/pytest tests/test_agent_node.py -v`
Expected: PASS（1 passed）

- [ ] **Step 6: Commit**

```bash
cd /Users/aisenyc/work/langgraph-agent-starter && git add src/agent_starter/nodes tests/conftest.py tests/test_agent_node.py && git commit -m "feat: minimal agent node (system prompt + single LLM call)"
```

---

## Task 6：graph 装配

**Files:**
- Create: `src/agent_starter/graph.py`
- Test: `tests/test_agent_node.py`（追加 graph 级测试）

- [ ] **Step 1: 追加失败测试**

```python
# tests/test_agent_node.py 末尾追加
from langgraph.checkpoint.memory import MemorySaver

from agent_starter.graph import build_graph


@pytest.mark.asyncio
async def test_graph_runs_one_turn(fake_llm, monkeypatch):
    # 把 agent 节点用的 build_llm 换成 fake
    import agent_starter.nodes.agent as agent_mod
    monkeypatch.setattr(agent_mod, "build_llm", lambda *a, **k: fake_llm)

    graph = build_graph(checkpointer=MemorySaver())
    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="在吗")], "user_id": 1, "domain": ""},
        config={"configurable": {"thread_id": "t1"}},
    )
    assert isinstance(out["messages"][-1], AIMessage)
    assert out["messages"][-1].content == "你好，我是 agent。"
```

- [ ] **Step 2: 跑测试确认 fail**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && .venv/bin/pytest tests/test_agent_node.py::test_graph_runs_one_turn -v`
Expected: FAIL（`ModuleNotFoundError: agent_starter.graph`）

- [ ] **Step 3: 写实现**

```python
# src/agent_starter/graph.py
"""StateGraph 装配。Phase 1 最小拓扑：START → agent → END。

P2 会扩成 START → user_message_router → {classify ∥ recall} → agent → write → END。
届时只在此加 node/edge，不改 build_graph 签名。
"""
from langgraph.graph import END, START, StateGraph

from agent_starter.nodes import agent_node
from agent_starter.state import AgentState


def build_graph(checkpointer=None):
    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_edge(START, "agent")
    builder.add_edge("agent", END)
    return builder.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && .venv/bin/pytest tests/test_agent_node.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
cd /Users/aisenyc/work/langgraph-agent-starter && git add src/agent_starter/graph.py tests/test_agent_node.py && git commit -m "feat: minimal StateGraph (START->agent->END)"
```

---

## Task 7：瘦 FastAPI 入口（/health + /agent/chat）

**Files:**
- Create: `src/agent_starter/main.py`
- Test: `tests/test_app.py`

> 决策 §12.4：重写瘦入口，不 port 1891 行 main.py。Phase 1 用同步（非 SSE）`/agent/chat`，checkpointer 用 `MemorySaver`（零依赖）。SSE 流式 + Postgres checkpoint 留后续 plan。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_app.py
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage


@pytest.fixture
def client(monkeypatch, fake_llm):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://x/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    import agent_starter.nodes.agent as agent_mod
    monkeypatch.setattr(agent_mod, "build_llm", lambda *a, **k: fake_llm)
    from agent_starter.main import app
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_chat_returns_reply(client):
    r = client.post("/agent/chat", json={"message": "在吗", "user_id": 1, "thread_id": "t1"})
    assert r.status_code == 200
    assert r.json()["reply"] == "你好，我是 agent。"
```

- [ ] **Step 2: 跑测试确认 fail**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && .venv/bin/pytest tests/test_app.py -v`
Expected: FAIL（`ModuleNotFoundError: agent_starter.main`）

- [ ] **Step 3: 写实现**

```python
# src/agent_starter/main.py
"""瘦 FastAPI 入口：/health + /agent/chat（同步）。

Phase 1：MemorySaver checkpointer（零依赖）、同步返回。
后续 plan：SSE 流式、Postgres checkpoint、会话列表/历史端点、recall/write 节点接入。
"""
from __future__ import annotations

import structlog
from fastapi import FastAPI
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from agent_starter.graph import build_graph

logger = structlog.get_logger(__name__)

app = FastAPI(title="langgraph-agent-starter")

# Phase 1：进程内单图 + 内存 checkpoint。后续 plan 在 lifespan 里换 Postgres saver。
_graph = build_graph(checkpointer=MemorySaver())


class ChatRequest(BaseModel):
    message: str
    user_id: int = 0
    thread_id: str = "default"
    jwt: str = ""


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/agent/chat")
async def chat(req: ChatRequest) -> dict:
    out = await _graph.ainvoke(
        {
            "messages": [HumanMessage(content=req.message)],
            "user_id": req.user_id,
            "jwt": req.jwt,
            "domain": "",
        },
        config={"configurable": {"thread_id": req.thread_id}},
    )
    last = out["messages"][-1]
    return {"reply": getattr(last, "content", "")}
```

- [ ] **Step 4: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && .venv/bin/pytest tests/test_app.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
cd /Users/aisenyc/work/langgraph-agent-starter && git add src/agent_starter/main.py tests/test_app.py && git commit -m "feat: thin FastAPI app (/health + sync /agent/chat)"
```

---

## Task 8：全量冒烟 + 启动验证

**Files:** 无新增（验收）

- [ ] **Step 1: 全测试通过**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && .venv/bin/pytest -v`
Expected: 全 PASS（settings 2 + state 1 + agent_node 2 + app 2 = 7 passed）

- [ ] **Step 2: 真起进程冒烟（零依赖：无 PG/MCP，只给假 LLM env）**

Run（后台起、探活、关掉）:
```bash
cd /Users/aisenyc/work/langgraph-agent-starter && \
OPENAI_BASE_URL=https://x/v1 OPENAI_API_KEY=sk-test OPENAI_MODEL=gpt-4o-mini \
.venv/bin/uvicorn agent_starter.main:app --port 8201 & \
SVPID=$!; sleep 3; curl -s http://localhost:8201/health; echo; kill $SVPID
```
Expected: 打印 `{"status":"ok"}`（证明无 PG/MCP 也能启动 —— spec C2 的“开箱即跑”基线）

- [ ] **Step 3: 确认无业务残留（去业务化基线，对应 AC4）**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && grep -riE "offer|probation|hr_|opc|solo|talentos" src/ || echo "CLEAN"`
Expected: 打印 `CLEAN`（src/ 下零业务名命中）

- [ ] **Step 4: Commit（若 Step 1-3 有微调）**

```bash
cd /Users/aisenyc/work/langgraph-agent-starter && git add -A && git commit -m "test: phase1 walking-skeleton smoke green" || echo "nothing to commit"
```

---

## 验收（本 plan 的 AC，映射 spec §10）
- **AC2（开箱即跑基线）**：Task 8 Step 2 —— 无 PG/MCP，`/health` OK。
- **AC4（去业务化基线）**：Task 8 Step 3 —— `src/` 下零业务名。
- 完整 AC1（example_todo 跑通）/ AC3（delete-clean）/ AC5（pgvector opt-in）/ AC6（加域只改一行）落在 P2/P3。

## Self-Review 备注
- 本 plan 只覆盖 spec §9 Phase 1 的“可启动骨架”切片；§9 里 Phase 1 提到的 “memory in-memory 兜底” 因 `recall/write` 节点尚未接入（Phase 1 拓扑只有 agent 节点），顺延到 P3 接 memory 时落，不留空壳——已在本 plan 头部与 graph.py 注释标明 P2 才加 router/recall/write。
- 所有步骤含真实代码 / 真实命令；无 TBD / 占位。
- 类型一致性：`agent_node(state, *, llm=None)` 签名在 Task 5 定义、Task 6/7 测试与 main 均按此调用；`build_graph(checkpointer=None)` 在 Task 6 定义、Task 7 main 按此调用。
