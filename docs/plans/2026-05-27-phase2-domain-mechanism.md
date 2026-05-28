# Phase 2：域注册机制 + 泛型化 classify/action + example_todo 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐 task 执行。步骤用 `- [ ]` 勾选跟踪。

**Goal:** 让 `agent_starter` 具备“注册式业务扩展”能力——加一个域 = 建目录 + 一行注册（不改 core），并带一个默认关、可整目录删的 `example_todo` 示例域跑通完整链路。

**Architecture:** 移植 talentos-agent 的 `DomainSpec`/`TaskSpec` 注册机制（去业务化）。classify 节点**只读已注册域的 `triggers`** 选 domain（无业务硬编码）。`agent_loop_action` 按 domain 选工具跑 ReAct 多轮循环，工具返值经 `TaskSpec` 钩子累积进通用 `working_draft`。图拓扑升级为 `START → classify → agent_loop_action → END`。

**Tech Stack:** LangGraph, langchain-core（`@tool` / `BaseTool` / `ToolMessage`）, pytest。

**对应 spec：** `docs/specs/2026-05-27-extraction-design.md` §5.1（classify 读 triggers）、§5.2/5.3（working_draft + hook 驱动）、§7（example_todo + delete-clean）。承接 Phase 1（`docs/plans/2026-05-27-phase1-walking-skeleton.md`）。

**前置：** 用 `talentos-agent/.venv`（py3.12，依赖齐）跑测试：命令里的 `pytest` 均指 `/Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest`（见 memory `reference_local_python_env`）。

**不在本 plan：** memory（recall/write 节点、pgvector）= P3；前端隐藏块路由 `user_message_router` = 后续。

---

## File Structure（本 plan 产出/修改）

```
src/agent_starter/
  tasks/
    __init__.py            # 新增：按 ENABLE_EXAMPLE_DOMAIN 触发注册
    domains.py             # 新增：DomainSpec + 注册表 + select_tools_for_state
    registry.py            # 新增：TaskSpec + 注册表 + collect helpers
    example_todo/          # 新增：唯一示例域（默认关，可整目录删）
      __init__.py          # 注册 DomainSpec + TaskSpec
      tools.py             # 本地内存工具：add_todo / list_todos / complete_todo
      prompt.py            # 域 prompt 片段
      domainspec.py        # DomainSpec(...)
      taskspec.py          # TaskSpec(...)
      tests/test_example_todo.py
  nodes/
    classify.py            # 新增：去业务化 classify（读 triggers）
    agent.py               # 重写：agent_node → agent_loop_action（ReAct + 工具）
  graph.py                 # 修改：START → classify → agent_loop_action → END
tests/
  conftest.py              # 修改：FakeLLM 支持 scripted 多轮（含 tool_calls）
  test_classify.py         # 新增
  test_agent_loop.py       # 新增
  test_delete_clean.py     # 新增：AC3/AC4 守卫
```

---

## Task 1：DomainSpec + 域注册表 + select_tools_for_state

**Files:**
- Create: `src/agent_starter/tasks/__init__.py`（先建空包，Task 5 再填注册逻辑）
- Create: `src/agent_starter/tasks/domains.py`
- Test: `tests/test_domains.py`

- [ ] **Step 1: 建空 `tasks/__init__.py`**

```python
# src/agent_starter/tasks/__init__.py
"""业务域 / 任务注册包。加一个域：在本包下建 <domain>/ 目录并在此触发其注册。"""
```

- [ ] **Step 2: 写失败测试**

```python
# tests/test_domains.py
from langchain_core.tools import tool

from agent_starter.tasks import domains as d


@tool
def _r() -> str:
    """read tool."""
    return "r"


@tool
def _w() -> str:
    """write tool."""
    return "w"


def setup_function():
    d.clear_registry()


def test_register_and_list():
    d.register_domain(d.DomainSpec(name="todo", label="待办", read_tools=[_r], write_tools=[_w], triggers=["待办"]))
    assert [s.name for s in d.list_domains()] == ["todo"]
    assert d.get_domain("todo").label == "待办"


def test_select_tools_global_reads_plus_active_writes():
    d.register_domain(d.DomainSpec(name="todo", label="待办", read_tools=[_r], write_tools=[_w]))
    # 命中域：global read ∪ 本域 write
    names = {t.name for t in d.select_tools_for_state({"domain": "todo"})}
    assert names == {"_r", "_w"}
    # 无域：只 global read，不绑 write
    names_no = {t.name for t in d.select_tools_for_state({"domain": ""})}
    assert names_no == {"_r"}


def test_select_tools_extra_appended_and_deduped():
    d.register_domain(d.DomainSpec(name="todo", label="待办", read_tools=[_r]))
    names = {t.name for t in d.select_tools_for_state({"domain": "todo"}, extra_tools=[_r, _w])}
    assert names == {"_r", "_w"}  # _r 去重
```

- [ ] **Step 3: 跑测试确认 fail**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_domains.py -v`
Expected: FAIL（`ModuleNotFoundError: agent_starter.tasks.domains`）

- [ ] **Step 4: 写实现**

```python
# src/agent_starter/tasks/domains.py
"""业务域定义 + 注册表 + 工具选择。

去业务化：框架不认识任何具体域名/工具名。classify 读 DomainSpec.triggers 选域，
agent_loop_action 调 select_tools_for_state 按域绑工具。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.tools import BaseTool


@dataclass
class DomainSpec:
    name: str
    label: str
    read_tools: list[BaseTool] = field(default_factory=list)   # 查询工具，全局候选
    write_tools: list[BaseTool] = field(default_factory=list)  # 写工具，仅本域激活时绑
    triggers: list[str] = field(default_factory=list)          # classify 命中线索（非硬正则）


DOMAIN_REGISTRY: dict[str, DomainSpec] = {}


def register_domain(spec: DomainSpec) -> None:
    DOMAIN_REGISTRY[spec.name] = spec


def get_domain(name: str) -> DomainSpec | None:
    return DOMAIN_REGISTRY.get(name)


def list_domains() -> list[DomainSpec]:
    return list(DOMAIN_REGISTRY.values())


def clear_registry() -> None:
    """仅测试用。"""
    DOMAIN_REGISTRY.clear()


def _dedupe(tools: list[BaseTool]) -> list[BaseTool]:
    seen: set[str] = set()
    out: list[BaseTool] = []
    for t in tools:
        if t.name in seen:
            continue
        seen.add(t.name)
        out.append(t)
    return out


def global_read_tools() -> list[BaseTool]:
    """所有域的 read 工具汇总（查询能力全局可达）。"""
    out: list[BaseTool] = []
    for spec in list_domains():
        out.extend(spec.read_tools)
    return _dedupe(out)


def select_tools_for_state(state: dict, *, extra_tools: list[BaseTool] | None = None) -> list[BaseTool]:
    """按 state.domain 选工具：global read ∪ 当前域 write ∪ extra，按 name 去重。

    （权限 / capability 过滤是 talentos 的安全层，本模板留到后续安全 plan，不在 P2。）
    """
    tools = list(global_read_tools())
    spec = get_domain(state.get("domain") or "")
    if spec:
        tools.extend(spec.write_tools)
    if extra_tools:
        tools.extend(extra_tools)
    return _dedupe(tools)
```

- [ ] **Step 5: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_domains.py -v`
Expected: PASS（3 passed）

- [ ] **Step 6: Commit（检查点，按 phase 汇总提交）**

```bash
git add src/agent_starter/tasks/__init__.py src/agent_starter/tasks/domains.py tests/test_domains.py
```

---

## Task 2：TaskSpec + 任务注册表 + collect helpers

**Files:**
- Create: `src/agent_starter/tasks/registry.py`
- Test: `tests/test_registry.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_registry.py
from langchain_core.tools import tool

from agent_starter.tasks import registry as r


@tool
def _create() -> dict:
    """create tool."""
    return {"ok": True}


def setup_function():
    r.REGISTRY.clear()


def test_register_and_collect_prompt_fragment_by_domain():
    r.REGISTRY.append(r.TaskSpec(
        task_type="create_todo", domain="todo", create_tool=_create,
        prompt_fragment="收集 todo 标题再确认创建。",
        success_message=lambda raw: "done",
    ))
    assert r.collect_prompt_fragments_for_domain("todo") == ["收集 todo 标题再确认创建。"]
    assert r.collect_prompt_fragments_for_domain("other") == []


def test_merge_tool_result_into_draft_uses_hook():
    r.REGISTRY.append(r.TaskSpec(
        task_type="create_todo", domain="todo", create_tool=_create,
        prompt_fragment="", success_message=lambda raw: "",
        tool_result_to_draft_patches=lambda name, raw: ({"todo_id": raw["id"]} if name == "add_todo" else None),
    ))
    merged = r.merge_tool_result_into_draft("add_todo", {"id": 7}, {"title": "买奶"})
    assert merged == {"title": "买奶", "todo_id": 7}
    # 不认领的 tool 原样返回
    assert r.merge_tool_result_into_draft("other", {}, {"a": 1}) == {"a": 1}
```

- [ ] **Step 2: 跑测试确认 fail**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: FAIL（`ModuleNotFoundError: agent_starter.tasks.registry`）

- [ ] **Step 3: 写实现**

```python
# src/agent_starter/tasks/registry.py
"""TaskSpec：域内“收集字段 → 确认 → 落库”的写任务单元 + 注册表 + 聚合 helper。

去业务化：通用层只调钩子 + 拼接，永远不认识具体业务字段名。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool


@dataclass(frozen=True)
class TaskSpec:
    task_type: str
    domain: str
    create_tool: BaseTool                         # @tool，HR 确认后一次性写库
    prompt_fragment: str                          # 域专属规则段，拼进 system prompt
    success_message: Callable[[dict], str]        # create 成功后给用户的文案
    # 可选钩子（None = 不参与）：
    tool_result_to_draft_patches: Callable[[str, dict[str, Any]], dict | None] | None = None
    render_draft: Callable[[dict[str, Any]], str | None] | None = None


REGISTRY: list[TaskSpec] = []


def collect_action_tools() -> list[BaseTool]:
    return [s.create_tool for s in REGISTRY]


def collect_prompt_fragments_for_domain(domain: str) -> list[str]:
    name = (domain or "").strip()
    if not name:
        return []
    return [s.prompt_fragment for s in REGISTRY if s.prompt_fragment and s.domain == name]


def collect_draft_renderings(state: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for s in REGISTRY:
        if s.render_draft is None:
            continue
        text = s.render_draft(state)
        if text:
            out.append(text)
    return out


def merge_tool_result_into_draft(tool_name: str, raw_result: dict[str, Any], current_draft: dict) -> dict:
    """问每个 spec “这个 tool 返值要 merge 啥到 working_draft”，merge 第一个非空结果。"""
    merged = dict(current_draft)
    for s in REGISTRY:
        if s.tool_result_to_draft_patches is None:
            continue
        patches = s.tool_result_to_draft_patches(tool_name, raw_result)
        if patches:
            merged.update(patches)
            break  # 一个 tool 只让一个 spec 认领
    return merged
```

- [ ] **Step 4: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_registry.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 暂存**

```bash
git add src/agent_starter/tasks/registry.py tests/test_registry.py
```

---

## Task 3：example_todo 本地工具

**Files:**
- Create: `src/agent_starter/tasks/example_todo/__init__.py`（先空）
- Create: `src/agent_starter/tasks/example_todo/tools.py`
- Test: `src/agent_starter/tasks/example_todo/tests/test_example_todo.py`, `src/agent_starter/tasks/example_todo/tests/__init__.py`

> 纯内存实现，不依赖 MCP/DB，保证零依赖可跑 + 自洽可删。

- [ ] **Step 1: 写失败测试**

```python
# src/agent_starter/tasks/example_todo/tests/__init__.py  (空文件)
```

```python
# src/agent_starter/tasks/example_todo/tests/test_example_todo.py
import pytest

from agent_starter.tasks.example_todo import tools as t


def setup_function():
    t._STORE.clear()
    t._SEQ[0] = 0


@pytest.mark.asyncio
async def test_add_and_list_and_complete():
    add = await t.add_todo.ainvoke({"user_id": 1, "title": "买牛奶"})
    assert add["ok"] and add["title"] == "买牛奶"
    tid = add["id"]
    listed = await t.list_todos.ainvoke({"user_id": 1})
    assert listed["items"][0]["title"] == "买牛奶"
    assert listed["items"][0]["done"] is False
    done = await t.complete_todo.ainvoke({"user_id": 1, "todo_id": tid})
    assert done["ok"] is True
    listed2 = await t.list_todos.ainvoke({"user_id": 1})
    assert listed2["items"][0]["done"] is True


@pytest.mark.asyncio
async def test_user_isolation():
    await t.add_todo.ainvoke({"user_id": 1, "title": "A"})
    listed_other = await t.list_todos.ainvoke({"user_id": 2})
    assert listed_other["items"] == []
```

- [ ] **Step 2: 跑测试确认 fail**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest src/agent_starter/tasks/example_todo/tests -v`
Expected: FAIL（`ModuleNotFoundError: ...example_todo.tools`）

- [ ] **Step 3: 写实现**

```python
# src/agent_starter/tasks/example_todo/__init__.py  (Task 5 填注册，先放空)
```

```python
# src/agent_starter/tasks/example_todo/tools.py
"""example_todo 的本地内存工具。纯演示，不连任何外部存储。

删除整个 example_todo 目录即删掉本域所有痕迹（delete-clean）。
"""
from __future__ import annotations

from langchain_core.tools import tool

# 进程内内存：{user_id: [ {id,title,done}, ... ]}
_STORE: dict[int, list[dict]] = {}
_SEQ = [0]  # 自增 id


@tool
async def add_todo(user_id: int, title: str) -> dict:
    """新增一条待办。入参：user_id, title。"""
    _SEQ[0] += 1
    item = {"id": _SEQ[0], "title": title, "done": False}
    _STORE.setdefault(user_id, []).append(item)
    return {"ok": True, "id": item["id"], "title": title}


@tool
async def list_todos(user_id: int) -> dict:
    """列出某用户的全部待办。入参：user_id。"""
    return {"items": list(_STORE.get(user_id, []))}


@tool
async def complete_todo(user_id: int, todo_id: int) -> dict:
    """把某条待办标记完成。入参：user_id, todo_id。"""
    for item in _STORE.get(user_id, []):
        if item["id"] == todo_id:
            item["done"] = True
            return {"ok": True, "id": todo_id}
    return {"ok": False, "error": "not_found"}
```

- [ ] **Step 4: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest src/agent_starter/tasks/example_todo/tests -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 暂存**

```bash
git add src/agent_starter/tasks/example_todo/
```

---

## Task 4：example_todo 的 DomainSpec + TaskSpec + prompt

**Files:**
- Create: `src/agent_starter/tasks/example_todo/prompt.py`
- Create: `src/agent_starter/tasks/example_todo/domainspec.py`
- Create: `src/agent_starter/tasks/example_todo/taskspec.py`

> 无独立行为测试（纯声明）；由 Task 9 端到端测试覆盖。

- [ ] **Step 1: 写 prompt 片段**

```python
# src/agent_starter/tasks/example_todo/prompt.py
DOMAIN_PROMPT = (
    "你在“待办（todo）”域。用户要增/查/标记完成待办时，调用对应工具完成，"
    "并用简洁中文回复结果。新增待办前如果缺标题就先问标题。"
)
```

- [ ] **Step 2: 写 DomainSpec**

```python
# src/agent_starter/tasks/example_todo/domainspec.py
from agent_starter.tasks.domains import DomainSpec
from agent_starter.tasks.example_todo.tools import add_todo, complete_todo, list_todos

SPEC = DomainSpec(
    name="todo",
    label="待办（任务清单）",
    triggers=["待办", "todo", "任务", "提醒我", "清单"],
    read_tools=[list_todos],
    write_tools=[add_todo, complete_todo],
)
```

- [ ] **Step 3: 写 TaskSpec**

```python
# src/agent_starter/tasks/example_todo/taskspec.py
from agent_starter.tasks.example_todo.prompt import DOMAIN_PROMPT
from agent_starter.tasks.example_todo.tools import add_todo
from agent_starter.tasks.registry import TaskSpec

SPEC = TaskSpec(
    task_type="create_todo",
    domain="todo",
    create_tool=add_todo,
    prompt_fragment=DOMAIN_PROMPT,
    success_message=lambda raw: f"✅ 已添加待办：{raw.get('title', '')}",
)
```

- [ ] **Step 4: 验证可 import**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -c "from agent_starter.tasks.example_todo import domainspec, taskspec; print(domainspec.SPEC.name, taskspec.SPEC.task_type)"`
Expected: 打印 `todo create_todo`

- [ ] **Step 5: 暂存**

```bash
git add src/agent_starter/tasks/example_todo/
```

---

## Task 5：注册接线 + ENABLE_EXAMPLE_DOMAIN 门控

**Files:**
- Modify: `src/agent_starter/tasks/example_todo/__init__.py`
- Modify: `src/agent_starter/tasks/__init__.py`
- Test: `tests/test_registration_gate.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_registration_gate.py
import importlib

from agent_starter.tasks import domains as d
from agent_starter.tasks import registry as r


def _reset_and_register(enable: bool):
    d.clear_registry()
    r.REGISTRY.clear()
    import agent_starter.tasks as tasks_pkg
    importlib.reload(tasks_pkg)
    tasks_pkg.register_enabled_domains(enable_example=enable)


def test_example_registered_when_enabled():
    _reset_and_register(True)
    assert d.get_domain("todo") is not None
    assert any(s.task_type == "create_todo" for s in r.REGISTRY)


def test_example_absent_when_disabled():
    _reset_and_register(False)
    assert d.get_domain("todo") is None
    assert r.REGISTRY == []
```

- [ ] **Step 2: 跑测试确认 fail**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_registration_gate.py -v`
Expected: FAIL（`register_enabled_domains` 不存在）

- [ ] **Step 3: 写 example_todo 自注册入口**

```python
# src/agent_starter/tasks/example_todo/__init__.py
"""example_todo 示例域。删除本目录 + tasks/__init__.py 里那一行 import 即彻底移除。"""
from agent_starter.tasks.domains import register_domain
from agent_starter.tasks.example_todo.domainspec import SPEC as DOMAIN_SPEC
from agent_starter.tasks.example_todo.taskspec import SPEC as TASK_SPEC
from agent_starter.tasks.registry import REGISTRY


def register() -> None:
    register_domain(DOMAIN_SPEC)
    if TASK_SPEC not in REGISTRY:
        REGISTRY.append(TASK_SPEC)
```

- [ ] **Step 4: 写 tasks 包注册总入口**

```python
# src/agent_starter/tasks/__init__.py
"""业务域 / 任务注册包。

加一个域：在本包下建 <domain>/ 目录（含 register()），并在 register_enabled_domains
里加一行调用。删一个域：删目录 + 删那一行。core 不 import 任何域符号。
"""


def register_enabled_domains(enable_example: bool | None = None) -> None:
    """按开关注册内置域。生产由 main.py 启动时调用一次。

    enable_example=None 时读 settings.enable_example_domain。
    """
    if enable_example is None:
        from agent_starter.settings import get_settings
        enable_example = get_settings().enable_example_domain

    # ↓↓↓ 删除 example_todo 域：删掉下面这一段 + 删 example_todo/ 目录 ↓↓↓
    if enable_example:
        from agent_starter.tasks import example_todo
        example_todo.register()
    # ↑↑↑ ↑↑↑
```

- [ ] **Step 5: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_registration_gate.py -v`
Expected: PASS（2 passed）

- [ ] **Step 6: 暂存**

```bash
git add src/agent_starter/tasks/__init__.py src/agent_starter/tasks/example_todo/__init__.py tests/test_registration_gate.py
```

---

## Task 6：去业务化 classify 节点

**Files:**
- Create: `src/agent_starter/nodes/classify.py`
- Modify: `tests/conftest.py`（FakeLLM 支持 scripted 多轮）
- Test: `tests/test_classify.py`

> 去业务化要点：**无任何业务正则**。无注册域 → 直接返 `domain=""`，不调 LLM。有域 → LLM 在“域名 + label + triggers”里选一个，文本解析 + 校验。

- [ ] **Step 1: 升级 FakeLLM 支持脚本化多轮（含 tool_calls）**

```python
# tests/conftest.py —— 整体替换为：
import pytest
from langchain_core.messages import AIMessage


class FakeLLM:
    """脚本化 LLM 替身。

    - 不传 responses：每次 ainvoke 返固定文本 AIMessage（兼容 Phase 1 用法）。
    - 传 responses：按顺序弹出；每项是 str（文本回复）或 dict（tool_calls，形如
      {"tool_calls": [{"name","args","id"}]}）。
    """

    def __init__(self, reply: str = "你好，我是 agent。", responses: list | None = None):
        self._reply = reply
        self._responses = list(responses) if responses else None
        self.calls = []
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages, *args, **kwargs):
        self.calls.append(messages)
        if self._responses is None:
            return AIMessage(content=self._reply)
        nxt = self._responses.pop(0)
        if isinstance(nxt, dict) and "tool_calls" in nxt:
            return AIMessage(content="", tool_calls=nxt["tool_calls"])
        return AIMessage(content=str(nxt))


@pytest.fixture
def fake_llm():
    return FakeLLM()
```

- [ ] **Step 2: 写失败测试**

```python
# tests/test_classify.py
import pytest
from langchain_core.messages import HumanMessage

from agent_starter.nodes.classify import classify_intent
from agent_starter.tasks import domains as d
from agent_starter.tasks.domains import DomainSpec
from tests.conftest import FakeLLM


def setup_function():
    d.clear_registry()


@pytest.mark.asyncio
async def test_no_domains_returns_empty_without_llm():
    llm = FakeLLM(responses=[])  # 若被调用会 IndexError
    out = await classify_intent({"messages": [HumanMessage(content="随便说点")]}, llm=llm)
    assert out["domain"] == ""
    assert llm.calls == []  # 没注册域 → 不调 LLM


@pytest.mark.asyncio
async def test_llm_picks_registered_domain():
    d.register_domain(DomainSpec(name="todo", label="待办", triggers=["待办", "todo"]))
    llm = FakeLLM(responses=["todo"])
    out = await classify_intent({"messages": [HumanMessage(content="帮我加个待办")]}, llm=llm)
    assert out["domain"] == "todo"


@pytest.mark.asyncio
async def test_llm_unknown_domain_falls_back_empty():
    d.register_domain(DomainSpec(name="todo", label="待办"))
    llm = FakeLLM(responses=["nonsense"])
    out = await classify_intent({"messages": [HumanMessage(content="x")]}, llm=llm)
    assert out["domain"] == ""  # LLM 给了没注册的名 → 兜底空
```

- [ ] **Step 3: 跑测试确认 fail**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_classify.py -v`
Expected: FAIL（`ModuleNotFoundError: agent_starter.nodes.classify`）

- [ ] **Step 4: 写实现**

```python
# src/agent_starter/nodes/classify.py
"""classify 节点：在已注册域里选一个 domain。去业务化——无任何业务硬编码。

无注册域 → 直接返空（零 LLM）。有域 → 把“域名 + label + triggers”喂给 LLM，
让它回一个域名（或 none）；解析后校验必须是已注册域，否则兜底空。
"""
from __future__ import annotations

import structlog
from langchain_core.messages import HumanMessage

from agent_starter.llm import build_llm
from agent_starter.tasks.domains import get_domain, list_domains

logger = structlog.get_logger(__name__)


def _last_user_text(messages: list) -> str:
    for m in reversed(messages or []):
        if isinstance(m, HumanMessage):
            c = getattr(m, "content", "")
            return c if isinstance(c, str) else ""
    return ""


def _build_prompt() -> str:
    lines = ["你是业务域分类器。根据用户最新消息，从下面候选域里选**最匹配的一个**。",
             "只输出域名本身（小写），无法归类就输出 none。不要任何多余文字。", "", "候选域："]
    for s in list_domains():
        trig = "，".join(s.triggers) if s.triggers else ""
        lines.append(f"- {s.name}（{s.label}）{('｜线索：' + trig) if trig else ''}")
    return "\n".join(lines)


async def classify_intent(state: dict, *, llm=None) -> dict:
    domains = list_domains()
    if not domains:
        return {"domain": ""}  # 无域：零 LLM

    user_text = _last_user_text(state.get("messages") or [])
    if llm is None:
        llm = build_llm()
    resp = await llm.ainvoke([("system", _build_prompt()), ("user", user_text)])
    raw = (getattr(resp, "content", "") or "").strip().lower()
    domain = raw if get_domain(raw) else ""
    logger.info("classify.done", domain=domain, raw=raw)
    return {"domain": domain}
```

- [ ] **Step 5: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_classify.py tests/test_agent_node.py -v`
Expected: PASS（classify 3 + 原 agent_node 2，且 conftest 改动不破坏 Phase 1）

- [ ] **Step 6: 暂存**

```bash
git add src/agent_starter/nodes/classify.py tests/conftest.py tests/test_classify.py
```

---

## Task 7：agent_loop_action（ReAct 循环 + working_draft）

**Files:**
- Modify: `src/agent_starter/nodes/agent.py`（`agent_node` → `agent_loop_action`，保留向后兼容别名）
- Test: `tests/test_agent_loop.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_agent_loop.py
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agent_starter.nodes.agent import agent_loop_action
from agent_starter.tasks import domains as d
from agent_starter.tasks import registry as r
from tests.conftest import FakeLLM


def setup_function():
    d.clear_registry()
    r.REGISTRY.clear()


@pytest.mark.asyncio
async def test_no_domain_single_llm_reply():
    llm = FakeLLM(responses=["在的，有什么可以帮你"])
    out = await agent_loop_action({"messages": [HumanMessage(content="在吗")], "domain": "", "user_id": 1}, llm=llm)
    assert isinstance(out["messages"][-1], AIMessage)
    assert out["messages"][-1].content == "在的，有什么可以帮你"


@pytest.mark.asyncio
async def test_react_calls_tool_then_replies():
    from agent_starter.tasks.example_todo import register
    register()  # 注册 todo 域 + 工具
    # 第一轮：LLM 要求调 add_todo；第二轮：给最终答复
    llm = FakeLLM(responses=[
        {"tool_calls": [{"name": "add_todo", "args": {"user_id": 1, "title": "买牛奶"}, "id": "c1"}]},
        "✅ 已加上待办：买牛奶",
    ])
    out = await agent_loop_action(
        {"messages": [HumanMessage(content="加个买牛奶的待办")], "domain": "todo", "user_id": 1},
        llm=llm,
    )
    # 工具被绑定了（todo 域 read+write 至少 3 个）
    assert llm.bound_tools and len(llm.bound_tools) >= 3
    # 末条是最终答复
    assert out["messages"][-1].content == "✅ 已加上待办：买牛奶"
    # 中间产生了 ToolMessage
    from langchain_core.messages import ToolMessage
    assert any(isinstance(m, ToolMessage) for m in out["messages"])
```

- [ ] **Step 2: 跑测试确认 fail**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_agent_loop.py -v`
Expected: FAIL（`cannot import name 'agent_loop_action'`）

- [ ] **Step 3: 重写 `nodes/agent.py`**

```python
# src/agent_starter/nodes/agent.py
"""agent_loop_action：按 domain 选工具的 ReAct 多轮循环。

每轮：LLM → 有 tool_calls 就执行、把 ToolMessage 塞回、工具返值经 TaskSpec 钩子
累积进 working_draft → 再问；无 tool_calls 即最终答复，退出。无工具时退化为单次问答。
"""
from __future__ import annotations

import json
import uuid

import structlog
from langchain_core.messages import BaseMessage, ToolMessage

from agent_starter.llm import build_llm
from agent_starter.state import AgentState
from agent_starter.tasks.domains import select_tools_for_state
from agent_starter.tasks.registry import (
    collect_draft_renderings,
    collect_prompt_fragments_for_domain,
    merge_tool_result_into_draft,
)

logger = structlog.get_logger(__name__)

MAX_REACT_ROUNDS = 6

_BASE_PROMPT = (
    "你是一个通用 AI 助手。用简洁、准确的中文回答用户。需要时调用提供的工具完成任务。"
)


def _build_system(state: AgentState) -> str:
    parts = [_BASE_PROMPT]
    parts.extend(collect_prompt_fragments_for_domain(state.get("domain") or ""))
    parts.extend(collect_draft_renderings(dict(state)))
    return "\n\n".join(p for p in parts if p)


async def agent_loop_action(state: AgentState, *, llm=None) -> dict:
    if llm is None:
        llm = build_llm()
    tools = select_tools_for_state(dict(state))
    tool_map = {t.name: t for t in tools}
    bound = llm.bind_tools(tools) if tools else llm

    history: list[BaseMessage] = list(state.get("messages") or [])
    conversation: list = [("system", _build_system(state)), *history]
    new_msgs: list = []
    local_draft: dict = dict(state.get("working_draft") or {})

    for _ in range(MAX_REACT_ROUNDS):
        resp = await bound.ainvoke(conversation)
        if not getattr(resp, "id", None):
            resp.id = f"ai-{uuid.uuid4().hex[:12]}"
        new_msgs.append(resp)
        conversation.append(resp)

        tool_calls = getattr(resp, "tool_calls", None) or []
        if not tool_calls:
            break

        for tc in tool_calls:
            tool = tool_map.get(tc["name"])
            if tool is None:
                raw: dict = {"error": f"unknown tool {tc['name']}"}
            else:
                raw = await tool.ainvoke(tc["args"])
            tm = ToolMessage(
                content=json.dumps(raw, ensure_ascii=False),
                tool_call_id=tc["id"],
                name=tc["name"],
            )
            new_msgs.append(tm)
            conversation.append(tm)
            if isinstance(raw, dict):
                local_draft = merge_tool_result_into_draft(tc["name"], raw, local_draft)
    else:
        logger.warning("agent_loop.exhausted", rounds=MAX_REACT_ROUNDS)

    out: dict = {"messages": new_msgs}
    if local_draft:
        out["working_draft"] = local_draft
    return out


# 向后兼容：Phase 1 的 graph/测试用 agent_node 名字。
agent_node = agent_loop_action
```

- [ ] **Step 4: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests/test_agent_loop.py tests/test_agent_node.py -v`
Expected: PASS（agent_loop 2 + 原 agent_node 2 仍过——`agent_node` 别名 + 无域单次问答兼容）

- [ ] **Step 5: 暂存**

```bash
git add src/agent_starter/nodes/agent.py tests/test_agent_loop.py
```

---

## Task 8：graph 接入 classify

**Files:**
- Modify: `src/agent_starter/graph.py`
- Modify: `src/agent_starter/nodes/__init__.py`
- Test: `tests/test_agent_node.py`（图级测试改走 classify→agent）

- [ ] **Step 1: 改 `nodes/__init__.py` 导出**

```python
# src/agent_starter/nodes/__init__.py
from agent_starter.nodes.agent import agent_loop_action, agent_node
from agent_starter.nodes.classify import classify_intent

__all__ = ["agent_loop_action", "agent_node", "classify_intent"]
```

- [ ] **Step 2: 改 `graph.py`**

```python
# src/agent_starter/graph.py
"""StateGraph 装配：START → classify → agent_loop_action → END。

（P3 会在 classify 旁并行加 recall、在 agent 后加 write 记忆节点。）
"""
from langgraph.graph import END, START, StateGraph

from agent_starter.nodes import agent_loop_action, classify_intent
from agent_starter.state import AgentState


def build_graph(checkpointer=None):
    builder = StateGraph(AgentState)
    builder.add_node("classify", classify_intent)
    builder.add_node("agent", agent_loop_action)
    builder.add_edge(START, "classify")
    builder.add_edge("classify", "agent")
    builder.add_edge("agent", END)
    return builder.compile(checkpointer=checkpointer)
```

- [ ] **Step 3: 更新图级测试**（`tests/test_agent_node.py` 里的 `test_graph_runs_one_turn`）

```python
# 替换 test_graph_runs_one_turn 为：
@pytest.mark.asyncio
async def test_graph_runs_one_turn(monkeypatch):
    # 无注册域：classify 不调 LLM 返空；agent 单次问答
    from agent_starter.tasks import domains as d
    d.clear_registry()
    from tests.conftest import FakeLLM
    fake = FakeLLM(reply="你好，我是 agent。")
    import agent_starter.nodes.agent as agent_mod
    import agent_starter.nodes.classify as classify_mod
    monkeypatch.setattr(agent_mod, "build_llm", lambda *a, **k: fake)
    monkeypatch.setattr(classify_mod, "build_llm", lambda *a, **k: fake)

    graph = build_graph(checkpointer=MemorySaver())
    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="在吗")], "user_id": 1, "domain": ""},
        config={"configurable": {"thread_id": "t1"}},
    )
    assert isinstance(out["messages"][-1], AIMessage)
    assert out["messages"][-1].content == "你好，我是 agent。"
```

- [ ] **Step 4: 跑测试确认 pass**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest -v`
Expected: 全 PASS（含 app 测试——`main.py` 经 `build_graph` 透明升级，无需改）

- [ ] **Step 5: 暂存**

```bash
git add src/agent_starter/graph.py src/agent_starter/nodes/__init__.py tests/test_agent_node.py
```

---

## Task 9：main.py 启动注册 + 端到端 + delete-clean 守卫

**Files:**
- Modify: `src/agent_starter/main.py`（启动时调 `register_enabled_domains()`）
- Test: `tests/test_delete_clean.py`

- [ ] **Step 1: main.py 启动注册域**

在 `src/agent_starter/main.py` 顶部 `app = FastAPI(...)` 之后、`_graph = build_graph(...)` 之前插入：

```python
from agent_starter.tasks import register_enabled_domains

# 启动按 ENABLE_EXAMPLE_DOMAIN 注册内置域（含示例）。
register_enabled_domains()
```

- [ ] **Step 2: 写 delete-clean / 去业务化守卫测试**

```python
# tests/test_delete_clean.py
import pathlib
import re

CORE_DIRS = ["nodes", "graph.py", "state.py", "settings.py", "llm.py", "main.py"]
SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "agent_starter"
# core = 整个 src/agent_starter 但排除 tasks/（业务域目录）
BUSINESS_RE = re.compile(r"offer|probation|hr_|opc|solo|talentos", re.IGNORECASE)
EXAMPLE_RE = re.compile(r"example_todo|\btodo\b", re.IGNORECASE)


def _iter_core_py():
    for p in SRC.rglob("*.py"):
        if "tasks" in p.relative_to(SRC).parts:
            continue  # tasks/ 是业务域所在，不算 core
        yield p


def test_core_has_no_legacy_business_names():
    """AC4：core（tasks/ 外）零 talentos 业务名。"""
    hits = [str(p) for p in _iter_core_py() if BUSINESS_RE.search(p.read_text(encoding="utf-8"))]
    assert hits == [], f"core 残留业务名：{hits}"


def test_core_does_not_reference_example_todo():
    """AC3 守卫：core 不 import / 不提 example_todo——删它无需改 core。"""
    hits = [str(p) for p in _iter_core_py() if EXAMPLE_RE.search(p.read_text(encoding="utf-8"))]
    assert hits == [], f"core 引用了示例域（破坏 delete-clean）：{hits}"
```

> 说明：`tasks/__init__.py` 里那行 `from agent_starter.tasks import example_todo` 在 `tasks/` 目录内，不算 core，被排除——符合“删域 = 删目录 + 删 tasks/__init__ 那一行”。

- [ ] **Step 3: 跑测试确认 pass（含全量回归）**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest -v`
Expected: 全 PASS（含两条守卫）

- [ ] **Step 4: 真删演练（验证 delete-clean，不提交此删除）**

Run:
```bash
cd /Users/aisenyc/work/langgraph-agent-starter && cp -r src/agent_starter/tasks/example_todo /tmp/_eg_bak && \
rm -rf src/agent_starter/tasks/example_todo && \
python - <<'PY'
import re, pathlib
p = pathlib.Path("src/agent_starter/tasks/__init__.py")
# 删掉注册块（保守：把 example_todo import 行注释逻辑——演练用 sed 亦可）
print("手动确认：删 tasks/__init__.py 里 example_todo 注册块")
PY
/Users/aisenyc/work/talentos-agent/.venv/bin/python -m pytest tests -v --ignore=tests/test_agent_loop.py --ignore=tests/test_registration_gate.py 2>&1 | tail -5
# 还原
rm -rf src/agent_starter/tasks/example_todo && cp -r /tmp/_eg_bak src/agent_starter/tasks/example_todo && rm -rf /tmp/_eg_bak
echo "restored"
```
Expected: 删掉 example_todo 后核心 + classify/agent 测试仍过（`test_agent_loop`/`test_registration_gate` 依赖示例域，演练时 --ignore）。确认后还原。

> 这一步是人工验证 delete-clean，不进 git。AC3 的常驻守卫是 Step 2 的 `test_delete_clean.py`。

- [ ] **Step 5: 暂存**

```bash
git add src/agent_starter/main.py tests/test_delete_clean.py
```

---

## Task 10：文档翻牌（🚧 → ✅）

**Files:**
- Modify: `README.md`（状态表 Phase 2 → ✅）
- Modify: `docs/adding-a-domain.md`（去掉顶部 🚧 横幅，示例 API → 实际 API）
- Modify: `docs/architecture.md`（classify / tasks registry / example_todo 行 🚧 → ✅）

- [ ] **Step 1: README 状态表 Phase 2 标 ✅，Quickstart 加“开启示例域”说明**

在 README Quickstart 末尾追加：
```markdown
> 想看示例域：`.env` 里设 `ENABLE_EXAMPLE_DOMAIN=1`，对话发“帮我加个买牛奶的待办”。
```
并把状态表 Phase 2 行的 `🚧 规划` 改为 `✅ 已实现`。

- [ ] **Step 2: `docs/adding-a-domain.md` 去 🚧 横幅**

删除文件顶部 `> 🚧 状态：规划(P2)...` 整段横幅；把正文“示意 API / 目标用法”等措辞改为陈述实现（DomainSpec/TaskSpec 字段与 `domains.py`/`registry.py` 实际签名对齐）。§7 把“P2 会带”改为“仓内已带”。

- [ ] **Step 3: `docs/architecture.md` 模块表翻牌**

把 `nodes/classify.py`、`tasks/registry.py·domains.py`、`tasks/example_todo/` 三行状态由 🚧 P2 改为 ✅；§1 图拓扑“当前”更新为 `START → classify → agent → END`。

- [ ] **Step 4: 校验文档内代码与实现一致**

Run: `cd /Users/aisenyc/work/langgraph-agent-starter && /Users/aisenyc/work/talentos-agent/.venv/bin/python -c "from agent_starter.tasks.domains import DomainSpec; from agent_starter.tasks.registry import TaskSpec; print('docs API ok')"`
Expected: 打印 `docs API ok`（确认文档引用的类存在且名字一致）

- [ ] **Step 5: 暂存**

```bash
git add README.md docs/adding-a-domain.md docs/architecture.md
```

---

## 验收（映射 spec §10）
- **AC1**：Task 7 `test_react_calls_tool_then_replies` —— 开示例域，发“加待办”→ 调 add_todo → 出回复。
- **AC3**：Task 9 `test_delete_clean.py::test_core_does_not_reference_example_todo` 常驻守卫 + Step 4 人工删演练。
- **AC4**：Task 9 `test_delete_clean.py::test_core_has_no_legacy_business_names`。
- **AC6**：Task 5 + Task 1/4 —— 加域 = 建 `tasks/<d>/` + `register_enabled_domains` 里一行；core 零改动（由 AC3 守卫反向保证）。

## Self-Review
- **spec 覆盖**：§5.1 classify 读 triggers（Task 6）✓；§5.2 working_draft（state 已有，Task 7 用 hook 累积）✓；§5.3 hook 驱动草稿 + 域 prompt 注入（Task 2/7）✓；§7 example_todo + 默认关 + delete-clean（Task 3-5/9）✓。memory（§5.5）明确不在本 plan = P3。
- **占位扫描**：无 TBD；所有 step 含真实代码/命令。Task 9 Step 4 是人工演练脚本（标注不进 git），常驻守卫在 Step 2。
- **类型一致性**：`select_tools_for_state(state, *, extra_tools=None)`（Task 1 定义 / Task 7 调用）；`agent_loop_action(state, *, llm=None)` + `agent_node` 别名（Task 7 定义 / Task 8 graph + 原 Phase 1 测试调用）；`classify_intent(state, *, llm=None)`（Task 6 定义 / Task 8 graph 调用）；`register_enabled_domains(enable_example=None)`（Task 5 定义 / Task 9 main 调用 / Task 5 测试调用）；`TaskSpec.tool_result_to_draft_patches(name, raw)->dict|None`（Task 2 定义 / Task 2 测试 + Task 7 `merge_tool_result_into_draft` 调用）一致。
- **回归**：Phase 1 的 `agent_node` 名 + 无域单次问答经别名 + `select_tools` 空工具退化保留；`main.py` 经 `build_graph` 透明升级。
