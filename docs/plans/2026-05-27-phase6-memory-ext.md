# Phase 6：memory 扩展（LLM 富抽取 + pgvector 语义召回）

> 内联执行。承接 P3（memory 接口/in-memory）。

**Goal:** 把 P3 标注的两个 memory 扩展点落地：① LLM 富偏好抽取（enum keys，opt-in）；② pgvector 语义召回 store（实现 `MemoryStore` 协议，opt-in）。

**验证边界（用户决策）：** ① LLM 抽取**可零依赖验证**（FakeLLM）。② pgvector store / embedding 触及真 PG+embedding，**未经我验证**——写真实代码 + lazy 依赖 + 标注需真库验。

**Tech Stack:** langchain-openai（embeddings）、asyncpg + pgvector（可选 `[pg]`）。

---

## Task 1：LLM 富偏好抽取（可验证）

**Files:** `memory/llm_extractor.py`; `settings.py`(加 `enable_llm_pref_extraction`); `nodes/memory.py`(write 接入); Test `tests/test_llm_extractor.py`

- `LLM_PREF_KEYS = {"response_format","verbosity","tone","answer_style"}`（nickname 仍走确定性）。
- `extract_preferences_llm(messages, *, llm=None) -> list[Preference]`：LLM 出 JSON array `{key,value}`，校验 enum，fail-soft（解析/调用失败返 []）。
- `write_memory(state, *, store=None, llm=None)`：确定性抽取后，若 `settings.enable_llm_pref_extraction` 再叠加 LLM 抽取（try/except 包住）。默认关 → 既有测试不打 LLM。
- 测试：FakeLLM 返 `'[{"key":"tone","value":"direct"}]'` → 得 `Preference("tone","direct")`；非法 JSON → []；非 enum key → 丢弃；write 开关开时 llm 注入能落库。

## Task 2：embedding client + pgvector store（未验证参考实现）

**Files:** `memory/embedding.py`, `memory/pgvector_store.py`, `memory/provider.py`(加 `build_memory_store`); `main.py` lifespan 接入（opt-in）

- `embedding.py`：`EmbeddingClient`（包 `OpenAIEmbeddings`，`aembed(text)->list[float]|None`，fail-soft）。
- `pgvector_store.py`：`PgVectorStore`(实现 MemoryStore)：
  - `setup()`：建表 `agent_prefs(user_id,key,value, UNIQUE(user_id,key))` + `agent_observations(user_id,text,embedding vector(dim))`。
  - `upsert_preference`：`ON CONFLICT DO UPDATE`（latest-wins）。
  - `add_observation`：embed→INSERT。
  - `recall`：prefs 全取（always-on）+ observations 按 `<=>` cosine top-k。
  - **未做** ConflictDetector（KV latest-wins 已够；语义层不做合并，见 concepts-memory 取舍）。
- `provider.build_memory_store(settings)`：DSN+embed 都配 → 文档示例在 lifespan `set_memory_store(PgVectorStore(...))` + `await setup()`；否则 InMemoryStore。
- `main.py` lifespan：若 `agent_pg_dsn` 且 `agent_embed_base_url` → lazy 建 PgVectorStore + setup + set_memory_store（**未验证分支**，标注）。
- 测试：仅验 `build_memory_store` 无配置→InMemoryStore；EmbeddingClient 构造不报错。**PG 真集成不在 CI，需用户真库跑。**

## Task 3：文档 + 验收
- `concepts-memory.md`：把“扩展点①②”改为“已提供 opt-in 实现”，标 pgvector 未验证 + `[pg]` 安装 + env（`ENABLE_LLM_PREF_EXTRACTION` / `AGENT_PG_DSN`+`AGENT_EMBED_*`）。
- README/architecture：memory 行补“LLM 抽取 + pgvector opt-in（后者未验证）”。
- 验收：全量回归绿（LLM 抽取新测试 + 既有不破）；AC4 CLEAN（memory/ 仍零业务名）；零依赖启动 OK。

## Self-Review
- LLM 抽取可验、默认关不影响既有；pgvector/embedding 真实代码 + lazy + 明确未验证标注（非占位）。
- 类型一致：`extract_preferences_llm(messages,*,llm=None)->list[Preference]`、`write_memory(state,*,store=None,llm=None)`、`EmbeddingClient.aembed`、`PgVectorStore` 实现 `MemoryStore`、`build_memory_store(settings)`。
