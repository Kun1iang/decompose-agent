# Phase 3：memory 接线 + 接口 + in-memory 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐 task 执行。步骤用 `- [ ]` 勾选跟踪。

**Goal:** 给图补上记忆环：`START → {classify ∥ recall} → agent → write → END`，配一个干净的 `MemoryStore` 接口 + 零依赖的 `InMemoryStore` 默认实现，让“记住用户偏好、下轮召回注入 prompt”开箱即用。

**Architecture:** recall 节点 turn 起召回用户记忆写入 `state.recalled_memory`；agent 把它拼进 system prompt；write 节点 turn 末用**确定性抽取**（不调 LLM）把显式偏好（如昵称）落进 store。store 经 `MemoryStore` 协议抽象，默认 `InMemoryStore`（偏好 KV latest-wins + 近期观察）。

**Tech Stack:** LangGraph（fan-out/fan-in）、Python 标准库（无新依赖）、pytest。

**对应 spec：** `docs/specs/2026-05-27-extraction-design.md` §5.5。承接 P2（`docs/plans/2026-05-27-phase2-domain-mechanism.md`）。

**范围决策（2026-05-27，偏离 spec 原写的“pgvector opt-in”）：** P3 只做接线 + 接口 + in-memory + 确定性抽取 + 注入。**不在 P3**（均为文档化扩展点）：pgvector 语义召回、embedding、ConflictDetector、LLM-based 偏好抽取、Postgres 持久化。`MemoryStore` 接口设计成可平滑替换这些实现。

**前置：** 测试用 `/Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest`（见 memory `reference_local_python_env`）。

---

## File Structure（本 plan 产出/修改）

```
src/agent_starter/memory/
  __init__.py
  models.py          # Preference / Observation / RecalledMemory
  store.py           # MemoryStore 协议 + InMemoryStore
  provider.py        # get/set/reset_memory_store（进程级单例）
  extractor.py       # 确定性偏好抽取（昵称；不调 LLM）+ _last_user_text
src/agent_starter/nodes/memory.py   # recall_memory + write_memory
src/agent_starter/nodes/agent.py    # 修改：system prompt 注入 recalled_memory
src/agent_starter/graph.py          # 修改：fan-out/fan-in 加 recall + write
tests/
  conftest.py        # 修改：autouse reset_memory_store
  test_memory_store.py
  test_extractor.py
  test_memory_nodes.py
  test_graph_memory.py
docs/
  concepts-memory.md # 记忆模型 + 扩展点说明
  architecture.md    # 修改：拓扑 + 模块表
  README.md          # 修改：状态表 Phase 3 → ✅ + 结构树
```

---

## Task 1：memory 模型 + store + provider

**Files:**
- Create: `src/agent_starter/memory/__init__.py`（空）
- Create: `src/agent_starter/memory/models.py`
- Create: `src/agent_starter/memory/store.py`
- Create: `src/agent_starter/memory/provider.py`
- Test: `tests/test_memory_store.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_memory_store.py
import pytest

from agent_starter.memory.store import InMemoryStore


@pytest.mark.asyncio
async def test_pref_latest_wins_and_recall():
    s = InMemoryStore()
    await s.upsert_preference(1, "nickname", "老张")
    await s.upsert_preference(1, "nickname", "张哥")  # latest-wins
    r = await s.recall(1, "随便")
    assert [(p.key, p.value) for p in r.prefs] == [("nickname", "张哥")]


@pytest.mark.asyncio
async def test_observations_recent_cap_and_user_isolation():
    s = InMemoryStore()
    for i in range(7):
        await s.add_observation(1, f"o{i}")
    await s.add_observation(2, "other")
    r1 = await s.recall(1, "q")
    assert [o.text for o in r1.observations] == ["o2", "o3", "o4", "o5", "o6"]  # 近 5 条
    r2 = await s.recall(2, "q")
    assert [o.text for o in r2.observations] == ["other"]


@pytest.mark.asyncio
async def test_empty_recall_is_empty():
    r = await InMemoryStore().recall(99, "q")
    assert r.is_empty()
```

- [ ] **Step 2: 跑测试确认 fail**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_memory_store.py -v`
Expected: FAIL（`ModuleNotFoundError: agent_starter.memory.store`）

- [ ] **Step 3: 写实现**

```python
# src/agent_starter/memory/__init__.py
"""记忆子系统：接口 + in-memory 默认实现。语义召回/持久化见 docs/concepts-memory.md 扩展点。"""
```

```python
# src/agent_starter/memory/models.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Preference:
    key: str
    value: str


@dataclass
class Observation:
    text: str


@dataclass
class RecalledMemory:
    prefs: list[Preference] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.prefs and not self.observations
```

```python
# src/agent_starter/memory/store.py
"""MemoryStore 协议 + 零依赖 InMemoryStore 默认实现。

接口刻意小而稳：换 Postgres / pgvector 语义召回时实现同一协议即可，节点与 agent 不改。
recall 的 query 参数当前 InMemoryStore 忽略（always-on 全返）；语义实现里用它做向量检索。
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_starter.memory.models import Observation, Preference, RecalledMemory

_RECENT_OBS = 5


@runtime_checkable
class MemoryStore(Protocol):
    async def recall(self, user_id: int, query: str) -> RecalledMemory: ...
    async def upsert_preference(self, user_id: int, key: str, value: str) -> None: ...
    async def add_observation(self, user_id: int, text: str) -> None: ...


class InMemoryStore:
    """进程内默认实现：偏好 KV（latest-wins）+ 近期观察。重启即丢。"""

    def __init__(self) -> None:
        self._prefs: dict[int, dict[str, str]] = {}
        self._obs: dict[int, list[str]] = {}

    async def recall(self, user_id: int, query: str) -> RecalledMemory:
        prefs = [Preference(k, v) for k, v in self._prefs.get(user_id, {}).items()]
        obs = [Observation(t) for t in self._obs.get(user_id, [])[-_RECENT_OBS:]]
        return RecalledMemory(prefs=prefs, observations=obs)

    async def upsert_preference(self, user_id: int, key: str, value: str) -> None:
        self._prefs.setdefault(user_id, {})[key] = value  # latest-wins

    async def add_observation(self, user_id: int, text: str) -> None:
        self._obs.setdefault(user_id, []).append(text)
```

```python
# src/agent_starter/memory/provider.py
"""进程级 MemoryStore 单例。默认 InMemoryStore；接 PG/语义实现时 set_memory_store 注入。"""
from __future__ import annotations

from agent_starter.memory.store import InMemoryStore, MemoryStore

_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    global _store
    if _store is None:
        _store = InMemoryStore()
    return _store


def set_memory_store(store: MemoryStore | None) -> None:
    global _store
    _store = store


def reset_memory_store() -> None:
    global _store
    _store = None
```

- [ ] **Step 4: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_memory_store.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 暂存**

```bash
git add src/agent_starter/memory/__init__.py src/agent_starter/memory/models.py src/agent_starter/memory/store.py src/agent_starter/memory/provider.py tests/test_memory_store.py
```

---

## Task 2：确定性偏好抽取

**Files:**
- Create: `src/agent_starter/memory/extractor.py`
- Test: `tests/test_extractor.py`

> 只做确定性昵称抽取（“叫我X / 喊我X / 称呼我为X”），**不调 LLM**——零依赖、可测、write 节点不会偷偷打 LLM。更丰富的偏好抽取（response_format/tone…）= 文档化扩展点。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_extractor.py
from langchain_core.messages import AIMessage, HumanMessage

from agent_starter.memory.extractor import extract_preferences


def test_extract_nickname():
    out = extract_preferences([HumanMessage(content="以后叫我老张")])
    assert [(p.key, p.value) for p in out] == [("nickname", "老张")]


def test_negation_skipped():
    assert extract_preferences([HumanMessage(content="别叫我老张")]) == []


def test_no_pref_returns_empty():
    assert extract_preferences([HumanMessage(content="今天天气不错")]) == []


def test_uses_last_user_message_only():
    msgs = [HumanMessage(content="叫我小李"), AIMessage(content="好的"), HumanMessage(content="查下天气")]
    assert extract_preferences(msgs) == []  # 最后一条不是偏好声明
```

- [ ] **Step 2: 跑测试确认 fail**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_extractor.py -v`
Expected: FAIL（`ModuleNotFoundError: agent_starter.memory.extractor`）

- [ ] **Step 3: 写实现**

```python
# src/agent_starter/memory/extractor.py
"""确定性偏好抽取（不调 LLM）。当前只抽昵称；LLM-based 富抽取见 docs 扩展点。"""
from __future__ import annotations

import re

from langchain_core.messages import HumanMessage

from agent_starter.memory.models import Preference

# “叫我X / 喊我X / 称呼我为X / 称呼我成X”——只匹配明确的命名声明，避免误伤。
_NICKNAME_RE = re.compile(
    r"(?:叫我|喊我|称呼我(?:为|成|作)?)\s*([^\s，。！？,.!?；;:：\"'“”]{1,20})"
)
_NEG_PREFIXES = ("不要", "别", "不用", "不准")


def _last_user_text(messages: list) -> str:
    for m in reversed(messages or []):
        if isinstance(m, HumanMessage):
            c = getattr(m, "content", "")
            return c if isinstance(c, str) else ""
    return ""


def extract_preferences(messages: list) -> list[Preference]:
    """从最后一条用户消息确定性抽取偏好。返回 0~1 条（昵称取最后命中）。"""
    text = _last_user_text(messages)
    last_name: str | None = None
    for m in _NICKNAME_RE.finditer(text):
        prefix = text[max(0, m.start() - 4):m.start()]
        if any(n in prefix for n in _NEG_PREFIXES):
            continue
        name = m.group(1).strip().removesuffix("吧").strip()
        if name:
            last_name = name
    return [Preference(key="nickname", value=last_name)] if last_name else []
```

- [ ] **Step 4: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_extractor.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 暂存**

```bash
git add src/agent_starter/memory/extractor.py tests/test_extractor.py
```

---

## Task 3：recall_memory + write_memory 节点

**Files:**
- Create: `src/agent_starter/nodes/memory.py`
- Test: `tests/test_memory_nodes.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_memory_nodes.py
import pytest
from langchain_core.messages import HumanMessage

from agent_starter.memory.store import InMemoryStore
from agent_starter.nodes.memory import recall_memory, write_memory


@pytest.mark.asyncio
async def test_recall_returns_seeded_prefs():
    store = InMemoryStore()
    await store.upsert_preference(1, "nickname", "老张")
    out = await recall_memory({"user_id": 1, "messages": [HumanMessage(content="在吗")]}, store=store)
    rec = out["recalled_memory"]
    assert [(p.key, p.value) for p in rec.prefs] == [("nickname", "老张")]


@pytest.mark.asyncio
async def test_write_extracts_and_persists_pref():
    store = InMemoryStore()
    await write_memory({"user_id": 1, "messages": [HumanMessage(content="叫我老张")]}, store=store)
    rec = await store.recall(1, "q")
    assert [(p.key, p.value) for p in rec.prefs] == [("nickname", "老张")]


@pytest.mark.asyncio
async def test_write_no_pref_is_noop():
    store = InMemoryStore()
    out = await write_memory({"user_id": 1, "messages": [HumanMessage(content="今天几号")]}, store=store)
    assert out == {}
    assert (await store.recall(1, "q")).is_empty()
```

- [ ] **Step 2: 跑测试确认 fail**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_memory_nodes.py -v`
Expected: FAIL（`ModuleNotFoundError: agent_starter.nodes.memory`）

- [ ] **Step 3: 写实现**

```python
# src/agent_starter/nodes/memory.py
"""recall_memory（turn 起召回）+ write_memory（turn 末写入）。

write 用确定性抽取，不调 LLM——所以不会拖慢/拖挂 turn。需要 LLM 富抽取时在此接入
（建议 fail-soft + 可异步），见 docs/concepts-memory.md。
"""
from __future__ import annotations

import structlog

from agent_starter.memory.extractor import _last_user_text, extract_preferences
from agent_starter.memory.provider import get_memory_store
from agent_starter.state import AgentState

logger = structlog.get_logger(__name__)


async def recall_memory(state: AgentState, *, store=None) -> dict:
    store = store or get_memory_store()
    user_id = int(state.get("user_id") or 0)
    query = _last_user_text(state.get("messages") or [])
    recalled = await store.recall(user_id, query)
    logger.info("recall.done", user_id=user_id, prefs=len(recalled.prefs), obs=len(recalled.observations))
    return {"recalled_memory": recalled}


async def write_memory(state: AgentState, *, store=None) -> dict:
    store = store or get_memory_store()
    user_id = int(state.get("user_id") or 0)
    prefs = extract_preferences(state.get("messages") or [])
    for p in prefs:
        await store.upsert_preference(user_id, p.key, p.value)
    if prefs:
        logger.info("write.prefs", user_id=user_id, n=len(prefs))
    return {}
```

- [ ] **Step 4: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_memory_nodes.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 暂存**

```bash
git add src/agent_starter/nodes/memory.py tests/test_memory_nodes.py
```

---

## Task 4：agent 把 recalled_memory 注入 system prompt

**Files:**
- Modify: `src/agent_starter/nodes/agent.py`
- Test: `tests/test_agent_loop.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
# tests/test_agent_loop.py 末尾追加
@pytest.mark.asyncio
async def test_recalled_memory_injected_into_system():
    from agent_starter.memory.models import Preference, RecalledMemory
    llm = FakeLLM(reply="好的")
    state = {
        "messages": [HumanMessage(content="在吗")],
        "domain": "", "user_id": 1,
        "recalled_memory": RecalledMemory(prefs=[Preference("nickname", "老张")]),
    }
    await agent_loop_action(state, llm=llm)
    system = llm.calls[0][0][1]  # conversation[0] == ("system", <str>)
    assert "老张" in system
```

- [ ] **Step 2: 跑测试确认 fail**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_agent_loop.py::test_recalled_memory_injected_into_system -v`
Expected: FAIL（system 不含“老张”）

- [ ] **Step 3: 改 `nodes/agent.py` 的 `_build_system`**

在 `nodes/agent.py` 顶部 import 区加：
```python
from agent_starter.memory.models import RecalledMemory  # noqa: F401  (类型参考)
```

把 `_build_system` 替换为：
```python
def _render_memory(recalled) -> str:
    if recalled is None or recalled.is_empty():
        return ""
    lines = ["【用户记忆】"]
    for p in recalled.prefs:
        lines.append(f"- 偏好 {p.key} = {p.value}")
    for o in recalled.observations:
        lines.append(f"- {o.text}")
    return "\n".join(lines)


def _build_system(state: AgentState) -> str:
    parts = [_BASE_PROMPT]
    mem = _render_memory(state.get("recalled_memory"))
    if mem:
        parts.append(mem)
    parts.extend(collect_prompt_fragments_for_domain(state.get("domain") or ""))
    parts.extend(collect_draft_renderings(dict(state)))
    return "\n\n".join(p for p in parts if p)
```

- [ ] **Step 4: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_agent_loop.py -v`
Expected: PASS（原 2 + 新 1）

- [ ] **Step 5: 暂存**

```bash
git add src/agent_starter/nodes/agent.py tests/test_agent_loop.py
```

---

## Task 5：graph fan-out/fan-in 接入 recall + write

**Files:**
- Modify: `src/agent_starter/nodes/__init__.py`
- Modify: `src/agent_starter/graph.py`

- [ ] **Step 1: 改 `nodes/__init__.py` 导出**

```python
# src/agent_starter/nodes/__init__.py
from agent_starter.nodes.agent import agent_loop_action, agent_node
from agent_starter.nodes.classify import classify_intent
from agent_starter.nodes.memory import recall_memory, write_memory

__all__ = ["agent_loop_action", "agent_node", "classify_intent", "recall_memory", "write_memory"]
```

- [ ] **Step 2: 改 `graph.py`**

```python
# src/agent_starter/graph.py
"""StateGraph 装配：START → {classify ∥ recall} → agent → write → END。

classify 与 recall 并行 fan-out（写不同 state 字段，无冲突），agent 处 fan-in。
"""
from langgraph.graph import END, START, StateGraph

from agent_starter.nodes import agent_loop_action, classify_intent, recall_memory, write_memory
from agent_starter.state import AgentState


def build_graph(checkpointer=None):
    builder = StateGraph(AgentState)
    builder.add_node("classify", classify_intent)
    builder.add_node("recall", recall_memory)
    builder.add_node("agent", agent_loop_action)
    builder.add_node("write", write_memory)
    builder.add_edge(START, "classify")
    builder.add_edge(START, "recall")
    builder.add_edge("classify", "agent")
    builder.add_edge("recall", "agent")
    builder.add_edge("agent", "write")
    builder.add_edge("write", END)
    return builder.compile(checkpointer=checkpointer)
```

- [ ] **Step 3: 验证可 import + 编译**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && OPENAI_BASE_URL=x OPENAI_API_KEY=x OPENAI_MODEL=x /Users/aisenyc/work/talentos-agent/.venv/bin/python -c "from agent_starter.graph import build_graph; build_graph(); print('graph ok')"`
Expected: 打印 `graph ok`

- [ ] **Step 4: 暂存**

```bash
git add src/agent_starter/nodes/__init__.py src/agent_starter/graph.py
```

---

## Task 6：conftest 隔离 + 端到端跨轮记忆测试 + 回归修订

**Files:**
- Modify: `tests/conftest.py`（autouse reset_memory_store）
- Create: `tests/test_graph_memory.py`

- [ ] **Step 1: conftest 追加 autouse 重置 memory store**

把 `tests/conftest.py` 的 `_clean_registries` fixture 替换为同时清 store：
```python
@pytest.fixture(autouse=True)
def _clean_registries():
    """每个测试前后清空域/任务注册表 + memory store，隔离执行顺序影响。"""
    from agent_starter.memory.provider import reset_memory_store
    from agent_starter.tasks import domains as d
    from agent_starter.tasks import registry as r
    d.clear_registry(); r.REGISTRY.clear(); reset_memory_store()
    yield
    d.clear_registry(); r.REGISTRY.clear(); reset_memory_store()
```

- [ ] **Step 2: 写端到端跨轮记忆测试**

```python
# tests/test_graph_memory.py
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agent_starter.graph import build_graph
from agent_starter.memory.provider import set_memory_store
from agent_starter.memory.store import InMemoryStore
from agent_starter.tasks import domains as d
from tests.conftest import FakeLLM


@pytest.mark.asyncio
async def test_nickname_remembered_across_turns(monkeypatch):
    d.clear_registry()              # 无域：classify 零 LLM
    set_memory_store(InMemoryStore())
    fake = FakeLLM(reply="好的")
    import agent_starter.nodes.agent as agent_mod
    import agent_starter.nodes.classify as classify_mod
    monkeypatch.setattr(agent_mod, "build_llm", lambda *a, **k: fake)
    monkeypatch.setattr(classify_mod, "build_llm", lambda *a, **k: fake)

    graph = build_graph(checkpointer=MemorySaver())
    cfg = {"configurable": {"thread_id": "t1"}}

    # turn 1：声明昵称 → write 落库
    await graph.ainvoke(
        {"messages": [HumanMessage(content="以后叫我老张")], "user_id": 1, "domain": ""}, cfg)
    # turn 2：recall 应把昵称注入 agent 的 system
    await graph.ainvoke(
        {"messages": [HumanMessage(content="在吗")], "user_id": 1, "domain": ""}, cfg)

    # fake 只被 agent 调用（classify 无域不调）。第 2 次调用的 system 含昵称。
    systems = [c[0][1] for c in fake.calls if isinstance(c[0], tuple) and c[0][0] == "system"]
    assert len(systems) == 2
    assert "老张" not in systems[0]   # turn1 写入前，无记忆
    assert "老张" in systems[1]       # turn2 召回注入
```

- [ ] **Step 3: 跑全量回归**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests src/agent_starter/tasks/example_todo/tests -v 2>&1 | tail -15`
Expected: 全 PASS。重点回归：
- `tests/test_agent_node.py::test_graph_runs_one_turn`（图加了 recall/write，仍应过——recall/write 无 LLM、in-memory）
- `tests/test_app.py`（同上，app 经 build_graph 透明升级）

- [ ] **Step 4: 暂存**

```bash
git add tests/conftest.py tests/test_graph_memory.py
```

---

## Task 7：文档（memory 模型 + 扩展点 + 翻牌）

**Files:**
- Create: `docs/concepts-memory.md`
- Modify: `docs/architecture.md`
- Modify: `README.md`

- [ ] **Step 1: 写 `docs/concepts-memory.md`**

```markdown
# 记忆模型

本模板的记忆 = 一个 `MemoryStore` 接口 + 默认 `InMemoryStore`，挂在图的 recall（turn 起召回）/ write（turn 末写入）两个节点上。

## 数据模型
- `Preference{key,value}`：结构化偏好，KV、latest-wins（同 key 覆写）。
- `Observation{text}`：自由文本观察，保留近期 N 条。
- `RecalledMemory{prefs, observations}`：recall 返回，注入 agent 的 system prompt。

## 流程
`recall_memory` 调 `store.recall(user_id, query)` → 写 `state.recalled_memory` →
agent 拼进 system → `write_memory` 用**确定性抽取**（`extractor.py`，当前只抽昵称，不调 LLM）
把偏好 `upsert` 回 store。

## 默认实现 InMemoryStore
进程内 dict，always-on 全量召回（不做相似度），重启即丢。零依赖、开箱即用。

## 扩展点（按需自己接，实现 `MemoryStore` 协议即可，节点/agent 不改）
1. **Postgres 持久化**：偏好 KV 落表（`UNIQUE(user_id,key)` + upsert latest-wins），结构化、无需 embedding——最简、最可靠。
2. **LLM 富抽取**：在 `write_memory` 接一个 LLM extractor 抽 response_format/tone 等（建议 fail-soft + 异步，别拖挂 turn）。
3. **pgvector 语义召回**：observations 走 embedding + 向量检索；`recall` 的 `query` 参数就是为它留的。注意语义召回会漏，高价值偏好建议仍走 KV always-on。

> 取舍参考：结构化 KV（精确、always-on、latest-wins）适合“必须每轮生效”的偏好；
> 语义召回（pgvector）适合开放式经验记忆，但召回不保证命中。详见抽取源 talentos-agent
> 的双车道设计。
```

- [ ] **Step 2: 改 `docs/architecture.md`**

- §1 拓扑“当前”改为：`START → {classify ∥ recall} → agent → write → END`。
- 模块表 `nodes/memory.py` 行状态 🚧 P3 → ✅，描述改“recall/write 节点（in-memory 默认；语义/持久化见扩展点）”。
- 新增一行：`memory/{models,store,provider,extractor}.py` | MemoryStore 接口 + InMemoryStore | ✅。

- [ ] **Step 3: 改 `README.md`**

- 状态表 Phase 3 行 🚧 规划 → ✅ 已实现。
- 结构树 `src/agent_starter/` 下加一行 `│   ├── memory/             # MemoryStore 接口 + InMemoryStore 默认`。
- 文档索引加一行 `concepts-memory.md`。

- [ ] **Step 4: 校验文档 API 一致**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -c "from agent_starter.memory.store import MemoryStore, InMemoryStore; from agent_starter.memory.models import Preference, Observation, RecalledMemory; print('memory docs API ok')"`
Expected: 打印 `memory docs API ok`

- [ ] **Step 5: 暂存**

```bash
git add docs/concepts-memory.md docs/architecture.md README.md
```

---

## Task 8：全量回归 + 启动冒烟

**Files:** 无新增（验收）

- [ ] **Step 1: 全测试通过**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests src/agent_starter/tasks/example_todo/tests -q 2>&1 | tail -4`
Expected: 全 PASS（P1+P2 原有 + P3 新增 ~14）

- [ ] **Step 2: 去业务化守卫仍 CLEAN**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_delete_clean.py -q 2>&1 | tail -3`
Expected: PASS（memory/ 也属 core，不得含业务名）

- [ ] **Step 3: 启动冒烟（零依赖，无 PG/MCP）**

后台起 uvicorn → curl /health → 关：用 P1 同款命令（端口 8201），确认加了 memory 节点后仍零依赖启动、`/health` OK。

- [ ] **Step 4: 暂存（如有微调）**

```bash
git add -A
```

---

## 验收（映射 spec §10 + 本 plan 目标）
- **记忆环成型**：Task 5 图拓扑 = `START→{classify∥recall}→agent→write→END`。
- **跨轮记忆生效**：Task 6 `test_nickname_remembered_across_turns`——turn1 声明昵称、turn2 召回注入 system。
- **开箱即跑保持**：Task 8 Step 3——加 memory 后零依赖仍启动。
- **去业务化保持**：Task 8 Step 2——memory/ 纳入 core 守卫。

## Self-Review
- **spec 覆盖**：§5.5 memory 子系统——接线 + 接口 + in-memory + 抽取解耦 ✓；pgvector/语义/LLM 抽取/PG 持久化按范围决策**显式移到扩展点**（已在 plan 头 + concepts-memory.md 记录），非遗漏。
- **占位扫描**：无 TBD；所有 step 含真实代码/命令。
- **类型一致性**：`MemoryStore.recall(user_id,query)->RecalledMemory` / `upsert_preference(user_id,key,value)` / `add_observation(user_id,text)`（Task 1 定义；Task 3 节点 + Task 6 测试调用一致）；`recall_memory(state,*,store=None)` / `write_memory(state,*,store=None)`（Task 3 定义；Task 5 graph + Task 6 测试调用）；`extract_preferences(messages)->list[Preference]` 与 `_last_user_text`（Task 2 定义；Task 3 import 复用）；`RecalledMemory.is_empty()`（Task 1 定义；Task 4 `_render_memory` 调用）。
- **回归**：recall/write 无 LLM → `test_app` / `test_graph_runs_one_turn` 不需新 monkeypatch；autouse 重置 store 防跨测试污染。
