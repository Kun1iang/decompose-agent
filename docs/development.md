# 开发指南

环境搭建、运行、测试、文件放哪儿、编码与提交约定。

---

## 1. 环境要求

- **Python 3.11+**（`pyproject.toml` 锁 `requires-python>=3.11`）。
- 本机默认 `python3` 可能是 3.9（装不了本包），用 `python3.12` 之类显式版本建 venv。
- 公司内网拉 PyPI 易超时——配内网 mirror（`pip config set global.index-url <内网源>`）再装。

## 2. 安装

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

> 装不动（网络/pip 版本）时的应急：本机若已有其它装齐依赖的 3.11+ venv，可直接借它跑测试——`pyproject.toml` 里 `pythonpath=["src"]` 会让 pytest 找到 `agent_starter`，无需重复安装：
> `/path/to/other/.venv/bin/python -m pytest`

## 3. 运行

```bash
cp .env.example .env        # 填 OPENAI_BASE_URL / OPENAI_API_KEY / OPENAI_MODEL
.venv/bin/uvicorn agent_starter.main:app --port 8201
```

- 健康检查：`curl http://localhost:8201/health` → `{"status":"ok"}`
- 对话（同步）：
  ```bash
  curl -s http://localhost:8201/agent/chat -H 'content-type: application/json' \
    -d '{"message":"你好","user_id":1,"thread_id":"t1"}'
  ```
- `thread_id` = 会话标识；同 id 续聊（checkpointer 自动加载历史），不同 id 互相隔离。

## 4. 测试

```bash
uv run --extra dev pytest -v
```

约定（见 `tests/`）：
- **不打真实 LLM**。用 `tests/conftest.py` 里的 `FakeLLM`，通过 `agent_node(state, *, llm=...)` 注入，或 `monkeypatch` 掉节点里的 `build_llm`。
- 异步测试用 `@pytest.mark.asyncio`（`pyproject` 已设 `asyncio_mode=auto`）。
- HTTP 端点用 `fastapi.testclient.TestClient`。
- 每个行为一个测试，先红后绿（TDD）。

生成一个新业务域：

```bash
uv run python scripts/new_domain.py ticket --label 工单 --trigger 工单
uv run --extra dev pytest tests/tasks/ticket/test_ticket.py -q
```

## 5. 文件放哪儿（目录约定）

| 你要加的东西 | 放哪 |
|---|---|
| 新的图节点（通用，非业务） | `src/agent_starter/nodes/<node>.py`，并在 `graph.py` 接边 |
| 一个新业务域 | 先跑 `scripts/new_domain.py`；代码在 `src/agent_starter/tasks/<domain>/`（自包含，见 [adding-a-domain.md](adding-a-domain.md)） |
| 一个 Markdown skill | 顶层 `skills/<name>/SKILL.md`（见 [concepts-skills.md](concepts-skills.md)） |
| 全局配置项 | `src/agent_starter/settings.py` 的 `Settings`（可选项给默认值） |
| 状态新字段（通用） | `src/agent_starter/state.py` 的 `AgentState`（**不要放业务专属字段**，业务数据进 `working_draft`） |
| 记忆 store 实现 | `src/agent_starter/memory/`（实现 `MemoryStore` 协议，如 `pgvector_store.py`） |
| 测试 | `tests/`，文件名 `test_*.py`；业务域测试放 `tests/tasks/<domain>/` |
| 设计 / 计划文档 | `docs/specs/` / `docs/plans/` |

**原则**：业务相关的一切收进 `tasks/<domain>/`；core（`nodes/`、`graph.py`、`state.py`、`settings.py`）保持业务中立。判断标准：`grep -riE "你的业务名" src/agent_starter/{nodes,graph.py,state.py,settings.py}` 应为空。

## 6. 编码约定

- 节点是 `async def node(state) -> dict`，返回**部分更新**；需要 LLM 的节点用 `def node(state, *, llm=None)` 形式便于测试注入。
- 日志用 `structlog.get_logger(__name__)`，结构化字段（`logger.info("event.name", key=val)`），别用 print。
- 类型注解齐全；新公共函数写简短 docstring 说明“做什么 / 怎么用 / 依赖什么”。
- core 不 import 任何业务模块；业务通过注册接口（`DomainSpec`/`TaskSpec` 钩子）接入。
- 可选外部依赖一律“env 空 = 关闭 + 兜底”，不要让缺依赖直接把启动搞挂。

## 7. 提交流程

- 分支：本仓 bootstrap 落 `main`；后续较大改动走 feature 分支 + MR（与公司 GitLab 评审规矩一致）。
- 节奏：**按 phase 一次性提交**（不是每个小改一个 commit）。一个 phase 的代码攒齐、测试绿了再提。
- commit message 用约定式前缀（`feat:` / `fix:` / `docs:` / `chore:` / `test:`）。
- 提交前必跑 `.venv/bin/pytest`，全绿再提。

## 8. 常见问题

- **`ModuleNotFoundError: agent_starter`**：没装（`pip install -e .`）或没设 `PYTHONPATH=src`。pytest 走 `pyproject` 的 `pythonpath` 自动 OK；裸跑脚本需 `PYTHONPATH=src`。
- **启动报 `Field required: openai_*`**：`.env` 没填 LLM 三件套，或运行目录不在仓库根（`.env` 按 CWD 找）。
- **`pip install -e .` 报 “editable mode requires setuptools-based build”**：pip 太老，先 `pip install --upgrade pip`。
